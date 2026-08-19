"""Offline end-to-end: the production CLI, driven by real foreign authorities.

The agent runs as a subprocess through its single production path.  This test
process plays the two external authorities with keys the agent never holds:
the recorder (owns the shared request-SLO ledger, signs T0 authorizations,
mirrors agent receipts into ledger events) and the oracle (signs semantic
verdicts from the pinned validator).  The stub ``ctr`` spawns a real HTTP
model server process, so drain/launch/readiness/inference are real process
and socket operations.

Terminal gate: the CLI's ``verify-evidence`` runs the pinned shared
``validate_ledger`` over the produced ledger and must report 2/2 valid
attempts.  Replay/second-occupant adversaries then re-invoke the same CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from . import helpers
from external_recorder import ExternalRecorder, build_trace
from node_local_oci import binding, contracts
from node_local_oci.journal import canonical_json
from oracle_service import OracleService

PRIOR_IMAGE = "registry.local/prior-model@sha256:" + "ef" * 32
OFFSET_2_MS = 3000


def _cli_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(binding.LANE_DIR), str(binding.FASTSTART_ROOT)]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def _run_cli(args: list[str], timeout: float = 180.0):
    return subprocess.run([sys.executable, "-m", "node_local_oci.cli", *args],
                          capture_output=True, text=True, timeout=timeout,
                          env=_cli_env(), check=False)


class OfflineEndToEnd(unittest.TestCase):
    maxDiff = None

    def _build_world(self, base: Path) -> dict:
        keys_env = helpers.make_keys(base)
        bin_dir = helpers.make_stub_bins(base)
        artifact = base / "artifact.bin"
        artifact.write_bytes(b"stub artifact bytes for the catalog model")
        validator = helpers.write_validator(base)
        port = 18123
        policy_body = helpers.make_policy_body(bin_dir=bin_dir,
                                               artifact_path=artifact,
                                               port=port,
                                               validator_path=validator)
        policy_envelope = helpers.sign_envelope(
            keys_env["privates"]["controller"], "controller",
            contracts.POLICY_SCHEMA, policy_body)
        policy_sha256 = helpers.sha256_bytes(
            canonical_json(policy_envelope).encode())

        helpers.seed_image(bin_dir, helpers.STUB_IMAGE)
        helpers.seed_image(bin_dir, PRIOR_IMAGE)
        # A real prior occupant process for the drain to stop.
        subprocess.run([str(bin_dir / "ctr"), "-n", "nlo-test", "run", "-d",
                        PRIOR_IMAGE, "nlo-prior-a", sys.executable, "-c",
                        "import time; time.sleep(600)"], check=True)

        payload_1 = json.dumps({"prompt": "fold protein one"}).encode()
        payload_2 = json.dumps({"prompt": "fold protein two"}).encode()
        requests = helpers.make_trace_requests(
            payload_1=payload_1, payload_2=payload_2,
            artifact_sha256=helpers.sha256_file(artifact),
            offset_2_ms=OFFSET_2_MS)
        trace = build_trace(trace_id="nlo-e2e-trace",
                            catalog={"models": ["stub-model"]},
                            requests=requests)
        trace_path = base / "trace.json"
        trace_path.write_text(canonical_json(trace) + "\n", encoding="utf-8")

        exchange = base / "exchange"
        ledger_path = base / "ledger.jsonl"
        recorder = ExternalRecorder(
            recorder_key_path=keys_env["authority_dir"] / "recorder.key",
            ledger_path=ledger_path, ledger_id="nlo-e2e-ledger",
            trace=trace, exchange_dir=exchange,
            recorder_id="nlo-e2e-external-recorder")
        oracle = OracleService(
            oracle_key_path=keys_env["authority_dir"] / "oracle.key",
            validator_source=validator, validator_id="stub-validator-v1",
            exchange_dir=exchange)

        switch_uid = "sw-e2e-1"
        container_id = f"nlo-{switch_uid}-b"
        environment = helpers.make_environment(policy_sha256=policy_sha256,
                                               code_revision=helpers.git_head())
        bundle_body = helpers.make_bundle_body(
            policy_envelope=policy_envelope, trace_id=trace["trace_id"],
            ledger_id="nlo-e2e-ledger", switch_uid=switch_uid, fence=1,
            nonce=helpers.sha256_bytes(b"nlo-e2e-nonce-1"),
            requests=[
                {"attempt_id": requests[0]["attempt_id"],
                 "request_id": requests[0]["request_id"],
                 "payload_sha256": helpers.sha256_bytes(payload_1),
                 "input_bytes": len(payload_1), "scenario": "a_to_b_local"},
                {"attempt_id": requests[1]["attempt_id"],
                 "request_id": requests[1]["request_id"],
                 "payload_sha256": helpers.sha256_bytes(payload_2),
                 "input_bytes": len(payload_2), "scenario": "same_model_hot"},
            ],
            prior_occupant={"model_id": "prior-model",
                            "model_version": "prior-1.0.0",
                            "container_id": "nlo-prior-a"})
        bundle_envelope = helpers.sign_envelope(
            keys_env["privates"]["controller"], "controller",
            contracts.BUNDLE_SCHEMA, bundle_body)

        policy_path = base / "policy.json"
        policy_path.write_text(canonical_json(policy_envelope) + "\n")
        bundle_path = base / "bundle.json"
        bundle_path.write_text(canonical_json(bundle_envelope) + "\n")
        return {
            "keys_env": keys_env, "bin_dir": bin_dir, "trace": trace,
            "trace_path": trace_path, "exchange": exchange,
            "ledger_path": ledger_path, "recorder": recorder, "oracle": oracle,
            "policy_path": policy_path, "bundle_path": bundle_path,
            "policy_envelope": policy_envelope, "requests": requests,
            "payloads": (payload_1, payload_2), "environment": environment,
            "container_id": container_id, "switch_uid": switch_uid,
            "state_dir": base / "state", "evidence_dir": base / "evidence",
            "keys_dir": keys_env["agent_dir"],
        }

    def _run_args(self, world: dict, state_dir=None) -> list[str]:
        return ["run",
                "--keys-dir", str(world["keys_dir"]),
                "--state-dir", str(state_dir or world["state_dir"]),
                "--evidence-dir", str(world["evidence_dir"]),
                "--exchange-dir", str(world["exchange"]),
                "--policy", str(world["policy_path"]),
                "--bundle", str(world["bundle_path"]),
                "--trace", str(world["trace_path"]),
                "--ledger", str(world["ledger_path"])]

    def test_full_switch_two_requests_and_replay_adversaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            world = self._build_world(base)
            recorder: ExternalRecorder = world["recorder"]
            oracle: OracleService = world["oracle"]
            requests = world["requests"]
            payload_1, payload_2 = world["payloads"]
            model_binding = {"model_id": "stub-model",
                             "model_version": "stub-1.0.0"}

            recorder.accept(
                requests[0], payload=payload_1,
                environment=world["environment"],
                ownership=helpers.make_ownership(world["container_id"]))
            accept_1_monotonic = time.monotonic_ns()

            proc = subprocess.Popen(
                [sys.executable, "-m", "node_local_oci.cli",
                 *self._run_args(world)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=_cli_env())
            receipts_path = world["evidence_dir"] / "receipts.jsonl"
            accepted_2 = False
            deadline = time.monotonic() + 150
            try:
                while proc.poll() is None:
                    self.assertLess(time.monotonic(), deadline,
                                    "agent did not finish in time")
                    if (not accepted_2 and time.monotonic_ns() >=
                            accept_1_monotonic + OFFSET_2_MS * 1_000_000):
                        recorder.accept(
                            requests[1], payload=payload_2,
                            environment=world["environment"],
                            ownership=helpers.make_ownership(None))
                        accepted_2 = True
                    recorder.mirror_new_receipts(receipts_path,
                                                 model_binding=model_binding)
                    oracle.answer_pending()
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
            stdout, stderr = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 0, f"stdout={stdout} stderr={stderr}")
            recorder.mirror_new_receipts(receipts_path, model_binding=model_binding)

            report = json.loads(
                (world["evidence_dir"] / "run_report.json").read_text())
            self.assertEqual(report["machine_state"], "ACCEPTED_B")
            self.assertIsNone(report["failure"])
            self.assertTrue(report["cleanup"]["complete"])

            deleted = [o["resource_id"] for o in report["cleanup"]["outcomes"]
                       if o["outcome"] == "deleted-verified"]
            self.assertEqual(deleted, [world["container_id"]])
            recorder.finalize_attempt(
                requests[0]["attempt_id"], cost_usd=0.0,
                gpu_active_seconds=0.0, gpu_idle_seconds=0.0, billed_seconds=0.0,
                cleanup={"required": True, "status": "complete",
                         "resources_deleted": [world["container_id"]],
                         "resources_retained": [],
                         "receipt_sha256": report["cleanup"]["report_sha256"],
                         "reason": "agent cleanup report verified"})
            recorder.finalize_attempt(
                requests[1]["attempt_id"], cost_usd=0.0,
                gpu_active_seconds=0.0, gpu_idle_seconds=0.0, billed_seconds=0.0,
                cleanup={"required": False, "status": "not_required",
                         "resources_deleted": [], "resources_retained": [],
                         "receipt_sha256": None,
                         "reason": "hot request owned no resources"})

            verify = _run_cli(["verify-evidence",
                               "--trace", str(world["trace_path"]),
                               "--ledger", str(world["ledger_path"]),
                               "--receipts", str(receipts_path)])
            self.assertEqual(verify.returncode, 0, verify.stderr)
            verdict = json.loads(verify.stdout)
            self.assertEqual(verdict["status"], "PASS")
            self.assertEqual(verdict["validator"],
                             "performance.request_slo.harness.validate_ledger")
            self.assertEqual(verdict["attempt_count"], 2)
            self.assertEqual(verdict["successes"], 2)
            self.assertEqual(verdict["failures"], 0)

            # The two raw responses are retained, distinct, and non-echo.
            responses_dir = world["evidence_dir"] / "responses"
            bodies = [
                (responses_dir / f"response-{r['attempt_id']}.bin").read_bytes()
                for r in requests]
            self.assertNotEqual(bodies[0], bodies[1])
            self.assertNotIn(bodies[0], (payload_1, payload_2))

            # The prior occupant was genuinely stopped and removed.
            containers = json.loads(
                (world["bin_dir"] / "ctr-state" / "containers.json").read_text())
            self.assertEqual(containers, {})

            # Occupancy was released only with absence evidence.
            self.assertFalse(
                (world["state_dir"] / "occupancy" / "occupant.json").exists())
            release_markers = list(
                (world["state_dir"] / "occupancy").glob("released-*.json"))
            self.assertEqual(len(release_markers), 1)

            # --- Adversary: identical bundle replayed after success -> fence.
            replay = _run_cli(self._run_args(world))
            self.assertEqual(replay.returncode, 2, replay.stderr)
            self.assertIn("fence.regression", replay.stderr)

            # --- Adversary: fresh fence, burned nonce -> nonce replay refused.
            bundle_envelope = json.loads(world["bundle_path"].read_text())
            body = {k: v for k, v in bundle_envelope.items() if k != "signature"}
            body["fence"] = 2
            body["command_id"] = "nlo-cmd-replay"
            resigned = helpers.sign_envelope(
                world["keys_env"]["privates"]["controller"], "controller",
                contracts.BUNDLE_SCHEMA, body)
            world["bundle_path"].write_text(canonical_json(resigned) + "\n")
            nonce_replay = _run_cli(self._run_args(world))
            self.assertEqual(nonce_replay.returncode, 2, nonce_replay.stderr)
            self.assertIn("nonce.replay", nonce_replay.stderr)

            # --- Adversary: correctly signed bundle against an occupied node.
            state_2 = base / "state-second-occupant"
            (state_2 / "occupancy").mkdir(parents=True)
            (state_2 / "occupancy" / "occupant.json").write_text(canonical_json({
                "schema": "catalog-switch/nlo-occupancy/v1",
                "switch_uid": "nlo-other-switch", "pid": 1,
                "boot_id": helpers.real_boot_id()}) + "\n")
            body["fence"] = 1
            body["nonce"] = helpers.sha256_bytes(b"nlo-e2e-nonce-2")
            body["command_id"] = "nlo-cmd-occupied"
            resigned = helpers.sign_envelope(
                world["keys_env"]["privates"]["controller"], "controller",
                contracts.BUNDLE_SCHEMA, body)
            world["bundle_path"].write_text(canonical_json(resigned) + "\n")
            occupied = _run_cli(self._run_args(world, state_dir=state_2))
            self.assertEqual(occupied.returncode, 2, occupied.stderr)
            self.assertIn("occupancy.held", occupied.stderr)


class OfflineFailurePath(unittest.TestCase):
    """A semantically invalid model: the attempt fails closed, is cleaned up
    with verified absence, and stays in the shared denominator."""

    def test_oracle_rejection_fails_attempt_and_keeps_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            world = OfflineEndToEnd._build_world(self, base)
            # Sabotage the model server: it will claim a wrong model identity,
            # which the pinned validator refuses.
            server = world["bin_dir"] / "stub_model_server.py"
            server.write_text(server.read_text().replace('"model": "stub"',
                                                         '"model": "impostor"'))
            recorder: ExternalRecorder = world["recorder"]
            oracle: OracleService = world["oracle"]
            requests = world["requests"]
            payload_1, payload_2 = world["payloads"]
            model_binding = {"model_id": "stub-model",
                             "model_version": "stub-1.0.0"}
            recorder.accept(requests[0], payload=payload_1,
                            environment=world["environment"],
                            ownership=helpers.make_ownership(world["container_id"]))
            accept_1_monotonic = time.monotonic_ns()
            proc = subprocess.Popen(
                [sys.executable, "-m", "node_local_oci.cli",
                 *OfflineEndToEnd._run_args(self, world)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=_cli_env())
            receipts_path = world["evidence_dir"] / "receipts.jsonl"
            deadline = time.monotonic() + 120
            try:
                while proc.poll() is None:
                    self.assertLess(time.monotonic(), deadline)
                    recorder.mirror_new_receipts(receipts_path,
                                                 model_binding=model_binding)
                    oracle.answer_pending()
                    time.sleep(0.05)
            finally:
                if proc.poll() is None:
                    proc.kill()
            stdout, stderr = proc.communicate(timeout=30)
            self.assertEqual(proc.returncode, 3, f"stdout={stdout} stderr={stderr}")
            recorder.mirror_new_receipts(receipts_path, model_binding=model_binding)

            report = json.loads(
                (world["evidence_dir"] / "run_report.json").read_text())
            self.assertEqual(report["machine_state"], "FAILED_INCOMPLETE")
            self.assertEqual(report["failure"]["code"], "oracle.invalid")
            # Cleanup still ran and verified absence of the launched container.
            self.assertTrue(report["cleanup"]["complete"])
            containers = json.loads(
                (world["bin_dir"] / "ctr-state" / "containers.json").read_text())
            self.assertEqual(containers, {})

            # Attempt 2 is still offered at its pinned schedule; the agent is
            # already gone, so the recorder accounts for it honestly and the
            # trace set stays complete.
            target_ns = accept_1_monotonic + OFFSET_2_MS * 1_000_000
            remaining = (target_ns - time.monotonic_ns()) / 1e9
            if remaining > 0:
                time.sleep(remaining)
            recorder.accept(requests[1], payload=payload_2,
                            environment=world["environment"],
                            ownership=helpers.make_ownership(None))
            recorder.fail_unprocessed_attempt(
                requests[1]["attempt_id"],
                "agent failed closed before this request was processed")
            recorder.finalize_attempt(
                requests[0]["attempt_id"], cost_usd=0.0, gpu_active_seconds=0.0,
                gpu_idle_seconds=0.0, billed_seconds=0.0,
                cleanup={"required": True, "status": "complete",
                         "resources_deleted": [world["container_id"]],
                         "resources_retained": [],
                         "receipt_sha256": report["cleanup"]["report_sha256"],
                         "reason": "agent cleanup report verified"})
            recorder.finalize_attempt(
                requests[1]["attempt_id"], cost_usd=0.0, gpu_active_seconds=0.0,
                gpu_idle_seconds=0.0, billed_seconds=0.0,
                cleanup={"required": False, "status": "not_required",
                         "resources_deleted": [], "resources_retained": [],
                         "receipt_sha256": None,
                         "reason": "unprocessed request owned no resources"})

            verify = _run_cli(["verify-evidence",
                               "--trace", str(world["trace_path"]),
                               "--ledger", str(world["ledger_path"]),
                               "--receipts", str(receipts_path)])
            self.assertEqual(verify.returncode, 0, verify.stderr)
            verdict = json.loads(verify.stdout)
            self.assertEqual(verdict["status"], "PASS")
            self.assertEqual(verdict["attempt_count"], 2)
            self.assertEqual(verdict["successes"], 0)
            self.assertEqual(verdict["failures"], 2)


class CrashRecovery(unittest.TestCase):
    def test_recover_replays_open_intents_and_removes_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            world = OfflineEndToEnd._build_world(self, base)
            # Simulate a crash window: an intent was journaled and the
            # container launched, then the agent died before cleanup.
            from node_local_oci.journal import IntentJournal
            state_dir = world["state_dir"]
            state_dir.mkdir(parents=True, exist_ok=True)
            intents = IntentJournal(state_dir / "intents.jsonl")
            intents.record_intent("container", "nlo-crashed-b", {})
            subprocess.run([str(world["bin_dir"] / "ctr"), "-n", "nlo-test",
                            "run", "-d", helpers.STUB_IMAGE, "nlo-crashed-b",
                            sys.executable, "-c",
                            "import time; time.sleep(600)"], check=True)
            recovered = _run_cli(["recover",
                                  "--keys-dir", str(world["keys_dir"]),
                                  "--state-dir", str(state_dir),
                                  "--policy", str(world["policy_path"])])
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            outcome = json.loads(recovered.stdout)
            self.assertEqual(outcome["status"], "RECOVERED")
            self.assertEqual(outcome["open_before"], ["nlo-crashed-b"])
            self.assertTrue(outcome["report"]["complete"])
            containers = json.loads((world["bin_dir"] / "ctr-state" /
                                     "containers.json").read_text())
            self.assertNotIn("nlo-crashed-b", containers)


if __name__ == "__main__":
    unittest.main()
