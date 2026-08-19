"""Production CLI for the node-local OCI switch adapter.

Exactly one execution path (``run``), plus crash recovery (``recover``) and
offline evidence verification (``verify-evidence``).  There is no mode flag,
no backend selector, and no fake anywhere in this package: execution is
always real subprocesses against controller-pinned binaries, and every
authority the agent obeys (policy, command bundle, T0 authorization, oracle
verdict) is verified against a foreign Ed25519 public key the agent cannot
sign for.

Exit codes: 0 success, 2 refusal before any side effect, 3 failure after
side effects began (cleanup attempted and its outcome persisted either way).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import admission, binding, contracts
from .cleanup import CleanupFailed, CleanupManager
from .errors import Refusal, require
from .execute import PinnedBinaries
from .gpu import GpuObserver, verify_scrub_claim
from .journal import (IntentJournal, NonceStore, OccupancyLock, ReceiptJournal,
                      FenceStore, canonical_json, sha256_hex)
from .keys import KeyRing
from .machine import (ACCEPTED_B, DRAINING_A, FAILED_INCOMPLETE, LAUNCHING_B,
                      PREPARING_B, QUARANTINED, SCRUBBING, SERVING_A,
                      SwitchMachine, VALIDATING_B, VERIFIED_CLEAN,
                      assert_not_quarantined)
from .oci import CtrAdapter
from .oracle import hash_file, verify_verdict
from .service import post_inference, wait_ready

MAX_CLOCK_SKEW_S = 5.0
DRAIN_TERM_WAIT_S = 30.0
DRAIN_KILL_WAIT_S = 15.0
READY_TIMEOUT_S = 600.0
INFER_TIMEOUT_S = 600.0
VERDICT_TIMEOUT_S = 120.0
AUTH2_TIMEOUT_S = 900.0
EXCHANGE_POLL_S = 0.1


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _SignalStop(Refusal):
    def __init__(self, signum: int) -> None:
        super().__init__("run.signal", f"received signal {signum}; failing closed")


def _install_signal_handlers() -> None:
    def handler(signum, frame):  # noqa: ARG001
        raise _SignalStop(signum)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


class ReceiptEmitter:
    """Agent-signed receipts appended to the durable hash-chained journal."""

    def __init__(self, journal: ReceiptJournal, keyring: KeyRing,
                 boot_id: str, switch_uid: str, phases: tuple[str, ...]) -> None:
        self.journal = journal
        self.keyring = keyring
        self.boot_id = boot_id
        self.switch_uid = switch_uid
        self.phases = phases
        self._finished: dict[str, dict[str, str]] = {}
        self._open: dict[str, str | None] = {}

    def emit(self, kind: str, data: dict, *, attempt_id: str | None = None) -> tuple[dict, str]:
        body = {
            "schema": contracts.RECEIPT_SCHEMA,
            "kind": kind,
            "switch_uid": self.switch_uid,
            "attempt_id": attempt_id,
            "boot_id": self.boot_id,
            "observed_utc": utc_now(),
            "observed_monotonic_ns": time.monotonic_ns(),
            "data": data,
        }
        signed = self.keyring.sign_agent(contracts.RECEIPT_SCHEMA, body)
        self.journal.append(signed)
        return signed, sha256_hex(canonical_json(signed).encode("utf-8"))

    def phase_started(self, attempt_id: str, phase: str) -> tuple[dict, str]:
        self._open[attempt_id] = phase
        return self.emit("phase-started", {"phase": phase, "occurrence": 0},
                         attempt_id=attempt_id)

    def phase_finished(self, attempt_id: str, phase: str, outcome: str, reason: str,
                       bytes_moved: int, data: dict) -> tuple[dict, str]:
        if self._open.get(attempt_id) == phase:
            self._open[attempt_id] = None
        self._finished.setdefault(attempt_id, {})[phase] = outcome
        payload = {"phase": phase, "occurrence": 0, "outcome": outcome,
                   "reason": reason, "bytes_moved": bytes_moved, "detail": data}
        return self.emit("phase-finished", payload, attempt_id=attempt_id)

    def fail_close_phases(self, attempt_id: str, reason: str) -> None:
        """On failure: close the open phase as failed, fail the next unrecorded
        phase if none failed yet, and mark every remaining phase skipped, so the
        shared ledger stays structurally complete and the attempt stays in the
        denominator."""
        open_phase = self._open.get(attempt_id)
        if open_phase is not None:
            self.phase_finished(attempt_id, open_phase, "failed", reason, 0, {})
        finished = self._finished.setdefault(attempt_id, {})
        if "failed" not in finished.values():
            for phase in self.phases:
                if phase not in finished:
                    self.phase_started(attempt_id, phase)
                    self.phase_finished(attempt_id, phase, "failed", reason, 0, {})
                    break
        for phase in self.phases:
            if phase not in finished:
                self.phase_skipped(attempt_id, phase,
                                   f"not reached: {reason}")

    def phase_completed(self, attempt_id: str, phase: str, reason: str,
                        bytes_moved: int, data: dict) -> tuple[dict, str]:
        """A synchronous phase observed as an immediate start/finish pair."""
        self.phase_started(attempt_id, phase)
        return self.phase_finished(attempt_id, phase, "completed", reason,
                                   bytes_moved, data)

    def phase_skipped(self, attempt_id: str, phase: str, reason: str) -> tuple[dict, str]:
        return self.phase_finished(attempt_id, phase, "skipped", reason, 0, {})


def _load_json_file(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refusal(f"cli.{label}-unreadable", f"{path}: {error}") from error
    require(isinstance(value, dict), f"cli.{label}-shape", f"{path} is not an object")
    return value


def _wait_for_file(path: Path, *, timeout_s: float, label: str) -> Path:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.is_file():
            return path
        time.sleep(EXCHANGE_POLL_S)
    raise Refusal(f"cli.{label}-timeout", f"{path} did not appear within {timeout_s}s")


def _utc_in_window(now: str, issued: str, deadline: str) -> None:
    skew = MAX_CLOCK_SKEW_S
    now_dt = datetime.strptime(now, "%Y-%m-%dT%H:%M:%S.%fZ")
    issued_dt = datetime.strptime(issued, "%Y-%m-%dT%H:%M:%S.%fZ")
    deadline_dt = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%S.%fZ")
    require((issued_dt - now_dt).total_seconds() <= skew, "cli.bundle-future",
            f"command bundle is future-issued ({issued} vs now {now}); refused")
    require(now_dt <= deadline_dt, "cli.bundle-expired",
            f"command bundle deadline {deadline} has passed (now {now})")


def _policy_sha256(envelope: dict) -> str:
    return sha256_hex(canonical_json(envelope).encode("utf-8"))


def _failure_class(code: str) -> str:
    """Map a refusal code onto the shared harness failure classes."""
    if "timeout" in code:
        return "timeout"
    if code.startswith("oracle."):
        return "validation"
    if code == "run.signal":
        return "cancelled"
    if code.startswith("occupancy."):
        return "capacity"
    return "backend"


class RunContext:
    """Everything the run needs, admitted in order, side effects last."""

    def __init__(self, args: argparse.Namespace) -> None:
        binding.verify_source_manifest()
        self.harness = binding.import_shared_harness()
        self.keys = KeyRing(Path(args.keys_dir))
        self.state_dir = Path(args.state_dir)
        self.evidence_dir = Path(args.evidence_dir)
        self.exchange_dir = Path(args.exchange_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir = self.evidence_dir / "responses"
        self.responses_dir.mkdir(exist_ok=True)
        assert_not_quarantined(self.state_dir)

        policy_envelope = _load_json_file(Path(args.policy), "policy")
        policy_body = self.keys.verify_role("controller", contracts.POLICY_SCHEMA,
                                            policy_envelope)
        self.policy = contracts.validate_policy(policy_body)
        self.policy_sha256 = _policy_sha256(policy_envelope)

        bundle_envelope = _load_json_file(Path(args.bundle), "bundle")
        bundle_body = self.keys.verify_role("controller", contracts.BUNDLE_SCHEMA,
                                            bundle_envelope)
        self.bundle = contracts.validate_bundle(bundle_body, self.policy,
                                                self.policy_sha256)
        _utc_in_window(utc_now(), self.bundle["issued_utc"], self.bundle["deadline_utc"])

        self.binaries = PinnedBinaries(self.policy)
        self.node_identity = admission.verify_node_identity(self.policy, self.binaries)
        self.storage_identity = admission.verify_storage(self.policy)

        self.trace = self.harness.load_trace(Path(args.trace))
        require(self.trace["trace_id"] == self.bundle["trace_id"], "cli.trace-id",
                "trace file trace_id != bundle trace_id")
        self.ledger_path = Path(args.ledger)

        self.journal = ReceiptJournal(self.evidence_dir / "receipts.jsonl")
        self.emitter = ReceiptEmitter(self.journal, self.keys,
                                      self.node_identity["boot_id"],
                                      self.bundle["switch_uid"],
                                      tuple(self.harness.PHASES))
        self.intents = IntentJournal(self.state_dir / "intents.jsonl")
        self.nonces = NonceStore(self.state_dir / "nonces")
        self.fence = FenceStore(self.state_dir / "fence.json")
        self.occupancy = OccupancyLock(self.state_dir / "occupancy")
        self.adapter = CtrAdapter(self.binaries, self.policy["containerd_namespace"],
                                  launch_class=self.policy["launch_class"])
        self.observer = GpuObserver(self.binaries, self.policy["gpu"])
        self.cleaner = CleanupManager(self.intents, self.adapter,
                                      self.policy["lease"]["resource_prefix"])
        self.model = self.policy["models"][self.bundle["target_model_id"]]
        self.container_id = f"nlo-{self.bundle['switch_uid']}-b"

    def read_authorization(self, attempt_id: str, *, timeout_s: float) -> dict:
        path = _wait_for_file(self.exchange_dir / f"authorization-{attempt_id}.json",
                              timeout_s=timeout_s, label="authorization")
        envelope = _load_json_file(path, "authorization")
        body = self.keys.verify_role("recorder", contracts.AUTHORIZATION_SCHEMA, envelope)
        return contracts.validate_authorization(body)

    def read_payload(self, request_binding: dict) -> bytes:
        path = _wait_for_file(
            self.exchange_dir / f"payload-{request_binding['attempt_id']}.bin",
            timeout_s=30.0, label="payload")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == request_binding["payload_sha256"], "cli.payload-hash",
                "provided payload does not hash to the command-bundle pin")
        require(len(payload) == request_binding["input_bytes"], "cli.payload-bytes",
                "provided payload size differs from the command-bundle pin")
        return payload

    def request_verdict(self, request_binding: dict, response_path: Path) -> dict:
        attempt_id = request_binding["attempt_id"]
        response_sha256, response_bytes = hash_file(response_path)
        request = {
            "schema": "catalog-switch/nlo-validation-request/v1",
            "switch_uid": self.bundle["switch_uid"],
            "attempt_id": attempt_id,
            "model_id": self.bundle["target_model_id"],
            "model_version": self.model["model_version"],
            "request_payload_sha256": request_binding["payload_sha256"],
            "response_path": str(response_path),
            "response_sha256": response_sha256,
            "response_bytes": response_bytes,
        }
        out = self.exchange_dir / f"validation-request-{attempt_id}.json"
        out.write_text(canonical_json(request) + "\n", encoding="utf-8")
        verdict_path = _wait_for_file(
            self.exchange_dir / f"verdict-{attempt_id}.json",
            timeout_s=VERDICT_TIMEOUT_S, label="verdict")
        envelope = _load_json_file(verdict_path, "verdict")
        return verify_verdict(self.keys, envelope, policy=self.policy,
                              bundle=self.bundle, attempt_id=attempt_id,
                              payload_sha256=request_binding["payload_sha256"],
                              response_path=response_path)


def _admit_t0(ctx: RunContext, request_binding: dict, *, timeout_s: float) -> dict:
    authorization = ctx.read_authorization(request_binding["attempt_id"],
                                           timeout_s=timeout_s)
    result = admission.verify_t0(ctx.harness, ctx.trace, ctx.ledger_path,
                                 authorization, ctx.bundle, request_binding,
                                 ctx.policy)
    require(result["trace_request"]["scenario"] == request_binding["scenario"],
            "cli.scenario", "trace scenario != command-bundle scenario")
    _, receipt_sha = ctx.emitter.emit(
        "t0-verified",
        {"attempt_id": request_binding["attempt_id"],
         "ledger_line_number": result["ledger_line_number"],
         "line_sha256": result["line_sha256"],
         "accepted_monotonic_ns": authorization["accepted_monotonic_ns"]},
        attempt_id=request_binding["attempt_id"])
    result["receipt_sha256"] = receipt_sha
    return result


def _drain_prior(ctx: RunContext, machine: SwitchMachine, attempt_id: str) -> None:
    prior = ctx.bundle["prior_occupant"]
    ctx.emitter.phase_started(attempt_id, "drain")
    _, sha = ctx.emitter.emit("drain-command",
                              {"prior_container_id": prior["container_id"]},
                              attempt_id=attempt_id)
    machine.transition(DRAINING_A, "drain-command", sha)
    inspect = ctx.adapter.task_row(prior["container_id"])
    stop = ctx.adapter.stop(prior["container_id"], inspect["pid"],
                            term_wait_s=DRAIN_TERM_WAIT_S,
                            kill_wait_s=DRAIN_KILL_WAIT_S)
    _, sha = ctx.emitter.emit("drain-complete", stop, attempt_id=attempt_id)
    machine.transition(SCRUBBING, "drain-complete", sha)
    ctx.emitter.phase_finished(attempt_id, "drain", "completed",
                               "prior occupant stopped with SIGTERM/SIGKILL escalation",
                               0, stop)


def _scrub_and_verify(ctx: RunContext, machine: SwitchMachine, attempt_id: str) -> None:
    prior = ctx.bundle["prior_occupant"]
    ctx.emitter.phase_started(attempt_id, "gpu_release")
    try:
        removal = ctx.adapter.remove(prior["container_id"])
        pre = ctx.observer.observe()
        ctx.observer.assert_zero_clients(pre)
        scrub_results = []
        for gpu in pre["gpus"]:
            execution = ctx.binaries.run("gpu-scrub", [gpu["uuid"]], timeout_s=300.0)
            require(execution.returncode == 0, "cli.scrub-rc",
                    f"gpu-scrub failed: {execution.stderr.strip()!r}")
            try:
                claim = json.loads(execution.stdout)
            except json.JSONDecodeError as error:
                raise Refusal("cli.scrub-parse",
                              f"gpu-scrub output unparseable: {error}") from error
            post = ctx.observer.observe()
            verified = verify_scrub_claim(claim, pre["gpus"], post, ctx.observer)
            verified["execution"] = execution.receipt_data()
            scrub_results.append(verified)
    except Refusal as error:
        _, sha = ctx.emitter.emit("scrub-unverifiable",
                                  {"error_code": error.code, "detail": error.detail},
                                  attempt_id=attempt_id)
        machine.transition(QUARANTINED, "scrub-unverifiable", sha)
        raise
    data = {"prior_removal": removal, "scrubs": scrub_results}
    _, sha = ctx.emitter.emit("scrub-verified", data, attempt_id=attempt_id)
    machine.transition(VERIFIED_CLEAN, "scrub-verified", sha)
    ctx.emitter.phase_finished(attempt_id, "gpu_release", "completed",
                               "zero compute+graphics clients and full-VRAM scrub "
                               "verified", 0, data)


def _clean_entry_check(ctx: RunContext, attempt_id: str) -> None:
    """Idle-node entry: still requires fresh zero-client + zero-memory proof."""
    ctx.emitter.phase_skipped(attempt_id, "drain", "no prior occupant")
    ctx.emitter.phase_started(attempt_id, "gpu_release")
    observation = ctx.observer.observe()
    ctx.observer.assert_zero_clients(observation)
    ctx.observer.assert_memory_zero(observation)
    ctx.emitter.phase_finished(attempt_id, "gpu_release", "completed",
                               "idle node verified: zero clients, zero used memory", 0,
                               {"observation_executions": observation["executions"]})


def _prepare_b(ctx: RunContext, machine: SwitchMachine, attempt_id: str) -> dict:
    model = ctx.model
    image_ref = model["image_digest"]
    ctx.emitter.phase_started(attempt_id, "image_readiness")
    if ctx.adapter.image_present(image_ref):
        image_state = "local_verified"
        pull_receipt = None
    else:
        pull_receipt = ctx.adapter.image_pull(image_ref, timeout_s=3600.0)
        image_state = "pulled"
    ctx.emitter.phase_finished(attempt_id, "image_readiness", "completed",
                               f"image {image_state}", 0,
                               {"image_ref": image_ref, "pull": pull_receipt})
    ctx.emitter.phase_started(attempt_id, "artifact_readiness")
    artifact = admission.verify_artifact(ctx.policy, ctx.bundle["target_model_id"])
    ctx.emitter.phase_finished(attempt_id, "artifact_readiness", "completed",
                               "artifact full-content hash matches pin", 0, artifact)
    ctx.emitter.phase_completed(attempt_id, "storage_readiness",
                                "pinned device/mount identity verified", 0,
                                ctx.storage_identity)

    ctx.emitter.phase_started(attempt_id, "cache_readiness")
    launch_mode = ctx.bundle["launch_mode"]
    fallback_reason = None
    if launch_mode == "snapshot":
        snapshot = ctx.bundle["snapshot"]
        observed_driver = {gpu["driver_version"]
                          for gpu in ctx.observer.observe()["gpus"]}
        if observed_driver != {snapshot["driver_version"]}:
            fallback_reason = (f"snapshot pinned driver {snapshot['driver_version']} "
                               f"!= observed {sorted(observed_driver)}; classified "
                               "pre-launch incompatibility, one conventional descent")
            launch_mode = "conventional"
    ctx.emitter.phase_finished(attempt_id, "cache_readiness", "completed",
                               fallback_reason or f"launch mode {launch_mode} admitted",
                               0, {"launch_mode": launch_mode,
                                   "fallback_reason": fallback_reason})
    _, sha = ctx.emitter.emit("artifact-verified",
                              {"artifact": artifact, "launch_mode": launch_mode},
                              attempt_id=attempt_id)
    machine.transition(PREPARING_B, "artifact-verified", sha)
    return {"launch_mode": launch_mode, "fallback_reason": fallback_reason}


def _launch_b(ctx: RunContext, machine: SwitchMachine, attempt_id: str,
              launch_mode: str) -> dict:
    model = ctx.model
    command = model["command"] if launch_mode == "conventional" else model["snapshot_command"]
    require(isinstance(command, list) and len(command) > 0, "cli.launch-command",
            f"policy pins no {launch_mode} command for this model")
    ctx.cleaner.register("container", ctx.container_id,
                         {"image_ref": model["image_digest"],
                          "term_wait_s": DRAIN_TERM_WAIT_S,
                          "kill_wait_s": DRAIN_KILL_WAIT_S})
    ctx.emitter.phase_started(attempt_id, "runtime_launch")
    _, sha = ctx.emitter.emit("launch-started",
                              {"container_id": ctx.container_id,
                               "launch_mode": launch_mode},
                              attempt_id=attempt_id)
    machine.transition(LAUNCHING_B, "launch-started", sha)
    try:
        inspect = ctx.adapter.launch(model["image_digest"], ctx.container_id,
                                     model["run_args"], command)
    except Refusal as error:
        ctx.emitter.phase_finished(attempt_id, "runtime_launch", "failed",
                                   f"{error.code}: {error.detail}", 0, {})
        _, sha = ctx.emitter.emit("launch-failed",
                                  {"error_code": error.code, "detail": error.detail},
                                  attempt_id=attempt_id)
        machine.transition(SCRUBBING, "launch-failed", sha)
        raise
    ctx.emitter.phase_finished(attempt_id, "runtime_launch", "completed",
                               f"container launched via ctr ({launch_mode})", 0, inspect)
    ctx.emitter.phase_started(attempt_id, "service_readiness")
    ready = wait_ready(model["endpoint"], model["health_path"],
                       deadline_monotonic=time.monotonic() + READY_TIMEOUT_S)
    _, sha = ctx.emitter.emit("readiness-observed",
                              {"inspect": inspect, "ready": ready},
                              attempt_id=attempt_id)
    machine.transition(VALIDATING_B, "readiness-observed", sha)
    ctx.emitter.phase_finished(attempt_id, "service_readiness", "completed",
                               "health endpoint returned 200", 0, ready)
    return inspect


def _infer_and_validate(ctx: RunContext, request_binding: dict,
                        launch_inspect: dict) -> dict:
    attempt_id = request_binding["attempt_id"]
    current = ctx.adapter.inspect_running(ctx.container_id, ctx.model["image_digest"])
    require(current["pid"] == launch_inspect["pid"], "cli.runtime-drift",
            f"runtime pid changed since launch ({launch_inspect['pid']} -> "
            f"{current['pid']}); not the same admitted runtime")
    payload = ctx.read_payload(request_binding)
    response_path = ctx.responses_dir / f"response-{attempt_id}.bin"
    ctx.cleaner.register("evidence-file", f"nlo-{ctx.bundle['switch_uid']}-resp-"
                                          f"{attempt_id}",
                         {"path": str(response_path)})
    ctx.emitter.phase_started(attempt_id, "inference")
    result = post_inference(ctx.model["endpoint"], ctx.model["infer_path"], payload,
                            response_path, timeout_s=INFER_TIMEOUT_S)
    # The inference phase only completes once the independent oracle accepts:
    # a semantically refused response is a failed inference, not a completed one.
    verdict = ctx.request_verdict(request_binding, response_path)
    ctx.emitter.phase_finished(attempt_id, "inference", "completed",
                               "raw response captured and oracle-accepted",
                               result["response_bytes"], result)
    _, sha = ctx.emitter.emit("verdict-verified", verdict, attempt_id=attempt_id)
    return {"verdict": verdict, "receipt_sha256": sha, "inference": result,
            "runtime": current}


def _trivial_phases(ctx: RunContext, attempt_id: str, phases: list[tuple[str, str, str]]) -> None:
    for phase, outcome, reason in phases:
        if outcome == "skipped":
            ctx.emitter.phase_skipped(attempt_id, phase, reason)
        else:
            ctx.emitter.phase_completed(attempt_id, phase, reason, 0, {})


def cmd_run(args: argparse.Namespace) -> int:
    _install_signal_handlers()
    ctx = RunContext(args)
    bundle = ctx.bundle
    req_1, req_2 = bundle["requests"]

    # T0 for attempt 1 must be durable and verified before any side effect.
    _admit_t0(ctx, req_1, timeout_s=30.0)

    # Burn replay protection durably, then take occupancy: first side effects.
    ctx.fence.advance(bundle["fence"], {"command_id": bundle["command_id"]})
    ctx.nonces.burn(bundle["nonce"], {"command_id": bundle["command_id"],
                                      "switch_uid": bundle["switch_uid"]})
    ctx.occupancy.acquire(bundle["switch_uid"], ctx.node_identity["boot_id"])
    ctx.emitter.emit("occupancy-acquired", {"boot_id": ctx.node_identity["boot_id"]})

    initial = SERVING_A if bundle["prior_occupant"] is not None else VERIFIED_CLEAN
    machine = SwitchMachine(ctx.journal, ctx.state_dir,
                            switch_uid=bundle["switch_uid"], initial_state=initial)
    attempt_1 = req_1["attempt_id"]
    current_attempt = attempt_1
    failure: Refusal | None = None
    results: dict = {"attempts": {}}
    try:
        _trivial_phases(ctx, attempt_1, [
            ("catalog_selection", "completed", "target pinned by admitted policy"),
            ("queue", "completed", "single-tenant node, no queue wait"),
        ])
        if initial == SERVING_A:
            _drain_prior(ctx, machine, attempt_1)
            _scrub_and_verify(ctx, machine, attempt_1)
        else:
            _clean_entry_check(ctx, attempt_1)
            _, sha = ctx.emitter.emit("scrub-verified",
                                      {"idle_entry": True}, attempt_id=attempt_1)
            # VERIFIED_CLEAN entry state: no transition needed, receipt retained.
        ctx.emitter.phase_completed(attempt_1, "placement",
                                    "node identity re-verified", 0, ctx.node_identity)
        prep = _prepare_b(ctx, machine, attempt_1)
        launch_inspect = _launch_b(ctx, machine, attempt_1, prep["launch_mode"])
        outcome_1 = _infer_and_validate(ctx, req_1, launch_inspect)
        machine.transition(ACCEPTED_B, "semantic-pass-durable",
                           outcome_1["receipt_sha256"])
        results["attempts"][attempt_1] = {"success": True,
                                          "verdict_id": outcome_1["verdict"]["verdict_id"]}

        # Attempt 2: distinct pinned request against the same admitted runtime.
        attempt_2 = req_2["attempt_id"]
        current_attempt = attempt_2
        _admit_t0(ctx, req_2, timeout_s=AUTH2_TIMEOUT_S)
        _trivial_phases(ctx, attempt_2, [
            ("catalog_selection", "completed", "same admitted target"),
            ("queue", "completed", "accepted during active trust epoch"),
            ("drain", "skipped", "runtime already serving target model"),
            ("gpu_release", "skipped", "same trust epoch, no release"),
            ("placement", "completed", "same admitted node"),
            ("image_readiness", "completed", "verified earlier in same trust epoch"),
            ("artifact_readiness", "completed", "verified earlier in same trust epoch"),
            ("storage_readiness", "completed", "verified earlier in same trust epoch"),
            ("cache_readiness", "completed", "runtime hot"),
            ("runtime_launch", "skipped", "runtime already running"),
        ])
        ctx.emitter.phase_started(attempt_2, "service_readiness")
        ready = wait_ready(ctx.model["endpoint"], ctx.model["health_path"],
                           deadline_monotonic=time.monotonic() + 30.0)
        ctx.emitter.phase_finished(attempt_2, "service_readiness", "completed",
                                   "health endpoint re-verified", 0, ready)
        outcome_2 = _infer_and_validate(ctx, req_2, launch_inspect)
        results["attempts"][attempt_2] = {"success": True,
                                          "verdict_id": outcome_2["verdict"]["verdict_id"]}
    except Exception as error:  # every failure takes the fail-closed path below
        failure = error if isinstance(error, Refusal) else Refusal(
            "run.unexpected", repr(error))
        ctx.emitter.fail_close_phases(current_attempt,
                                      f"{failure.code}: {failure.detail}")
        ctx.emitter.emit("attempt-failed",
                         {"error_code": failure.code, "detail": failure.detail,
                          "failure_class": _failure_class(failure.code)},
                         attempt_id=current_attempt)
        results["attempts"][current_attempt] = {"success": False,
                                                "error_code": failure.code}
        if machine.state not in (ACCEPTED_B, QUARANTINED, FAILED_INCOMPLETE):
            _, sha = ctx.emitter.emit("machine-failure",
                                      {"error_code": failure.code})
            machine.transition(FAILED_INCOMPLETE, "attempt-failed", sha)

    # Teardown and cleanup run on every path, success or failure.
    cleanup_error: Refusal | None = None
    cleanup_report = None
    try:
        cleanup_report = ctx.cleaner.cleanup_all()
        _, absence_sha = ctx.emitter.emit("cleanup-verified", cleanup_report)
        ctx.occupancy.release(bundle["switch_uid"], absence_sha)
        ctx.emitter.emit("occupancy-released", {"absence_receipt_sha256": absence_sha})
    except CleanupFailed as error:
        cleanup_error = error
        ctx.emitter.emit("cleanup-failed", error.report)
        # Unverifiable cleanup: quarantine marker via a dedicated machine edge is
        # only reachable from SCRUBBING; persist the marker directly instead.
        from .journal import write_durable  # noqa: PLC0415
        marker = ctx.state_dir / "quarantined.json"
        if not marker.exists():
            write_durable(marker, (canonical_json({
                "schema": "catalog-switch/nlo-quarantine/v1",
                "switch_uid": bundle["switch_uid"],
                "reason": "cleanup-failed",
            }) + "\n").encode("utf-8"))

    report = {
        "schema": contracts.REPORT_SCHEMA,
        "switch_uid": bundle["switch_uid"],
        "launch_class": ctx.policy["launch_class"],
        "policy_sha256": ctx.policy_sha256,
        "bundle_command_id": bundle["command_id"],
        "trace_id": bundle["trace_id"],
        "machine_state": machine.state,
        "results": results,
        "failure": None if failure is None else {"code": failure.code,
                                                 "detail": failure.detail},
        "cleanup": cleanup_report if cleanup_report is not None else
                   (cleanup_error.report if cleanup_error else None),
        "receipts_head_sha256": ctx.journal.head,
        "receipts_count": ctx.journal.sequence,
        "generated_utc": utc_now(),
    }
    report_path = ctx.evidence_dir / "run_report.json"
    report_path.write_text(canonical_json(report) + "\n", encoding="utf-8")
    ctx.emitter.emit("run-terminal", {"report_sha256":
                     sha256_hex((canonical_json(report) + "\n").encode("utf-8"))})

    if failure is not None or cleanup_error is not None:
        print(f"FAIL: {(failure or cleanup_error)}", file=sys.stderr)
        return 3
    print(canonical_json({"status": "PASS", "report": str(report_path)}))
    return 0


def cmd_recover(args: argparse.Namespace) -> int:
    """Replay the intent journal after a crash; cleanup every open resource."""
    binding.verify_source_manifest()
    keys = KeyRing(Path(args.keys_dir))
    policy_envelope = _load_json_file(Path(args.policy), "policy")
    policy = contracts.validate_policy(
        keys.verify_role("controller", contracts.POLICY_SCHEMA, policy_envelope))
    state_dir = Path(args.state_dir)
    intents = IntentJournal(state_dir / "intents.jsonl")
    binaries = PinnedBinaries(policy)
    adapter = CtrAdapter(binaries, policy["containerd_namespace"],
                         launch_class=policy["launch_class"])
    cleaner = CleanupManager(intents, adapter, policy["lease"]["resource_prefix"])
    open_before = [entry["resource_id"] for entry in intents.open_resources()]
    report = cleaner.cleanup_all()
    print(canonical_json({"status": "RECOVERED", "open_before": open_before,
                          "report": report}))
    return 0


def cmd_verify_evidence(args: argparse.Namespace) -> int:
    """Offline gate: shared request-SLO validation plus receipt-chain checks."""
    binding.verify_source_manifest()
    harness = binding.import_shared_harness()
    trace = harness.load_trace(Path(args.trace))
    events = harness.load_ledger(Path(args.ledger))
    attempts = harness.validate_ledger(events, trace)
    receipts_summary = None
    if args.receipts:
        journal = ReceiptJournal(Path(args.receipts))
        entries = journal.entries()  # re-verifies the hash chain from disk
        receipts_summary = {"count": len(entries), "head_sha256": journal.head}
    print(canonical_json({
        "status": "PASS",
        "validator": "performance.request_slo.harness.validate_ledger",
        "attempt_count": len(attempts),
        "successes": sum(1 for a in attempts if a["success"]),
        "failures": sum(1 for a in attempts if not a["success"]),
        "ledger_sha256": harness.file_sha256(Path(args.ledger)),
        "trace_sha256": trace["trace_sha256"],
        "receipts": receipts_summary,
    }))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="node-local-oci")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute one admitted catalog switch")
    run.add_argument("--keys-dir", required=True)
    run.add_argument("--state-dir", required=True)
    run.add_argument("--evidence-dir", required=True)
    run.add_argument("--exchange-dir", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--bundle", required=True)
    run.add_argument("--trace", required=True)
    run.add_argument("--ledger", required=True)
    run.set_defaults(handler=cmd_run)

    recover = sub.add_parser("recover", help="replay cleanup intents after a crash")
    recover.add_argument("--keys-dir", required=True)
    recover.add_argument("--state-dir", required=True)
    recover.add_argument("--policy", required=True)
    recover.set_defaults(handler=cmd_recover)

    verify = sub.add_parser("verify-evidence",
                            help="run the shared request-SLO validator over a ledger")
    verify.add_argument("--trace", required=True)
    verify.add_argument("--ledger", required=True)
    verify.add_argument("--receipts", default=None)
    verify.set_defaults(handler=cmd_verify_evidence)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except Refusal as error:
        print(f"REFUSED {error.code}: {error.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
