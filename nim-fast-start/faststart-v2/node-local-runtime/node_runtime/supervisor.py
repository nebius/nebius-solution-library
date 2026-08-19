"""Synchronous node-local A-to-B switch state machine.

The supervisor accepts one externally recorded trace request, performs every
request-specific action after T0, and emits the exact shared SLO contract. It
has no Kubernetes, cloud, registry, or object-storage client.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from performance.request_slo import harness

from .audit import AuditChain
from .cache import CacheError, ContentAddressedCache
from .security import AdmissionError, CommandAuthenticator, verify_checkpoint_binding


class RuntimeFailure(RuntimeError):
    def __init__(self, reason: str, *, failure_class: str = "backend", retryable: bool = False) -> None:
        super().__init__(reason)
        if failure_class not in harness.FAILURE_CLASSES:
            raise ValueError("failure_class is not canonical")
        self.failure_class = failure_class
        self.retryable = retryable


class RuntimeBackend(Protocol):
    occupant: dict[str, str] | None
    runtime_version: str

    def drain(self, deadline_ns: int) -> dict[str, Any]: ...
    def gpu_release(self) -> dict[str, Any]: ...
    def place(self, target: dict[str, Any]) -> dict[str, Any]: ...
    def image_ready(self, target: dict[str, Any]) -> dict[str, Any]: ...
    def storage_ready(self) -> dict[str, Any]: ...
    def cache_ready(self, path: Path) -> dict[str, Any]: ...
    def launch(self, target: dict[str, Any], artifact: Path, mode: str) -> dict[str, Any]: ...
    def ready(self, deadline_ns: int) -> dict[str, Any]: ...
    def infer(self, payload: bytes, deadline_ns: int) -> bytes: ...
    def semantic_validate(self, target: dict[str, Any], payload: bytes, response: bytes) -> dict[str, Any]: ...
    def cleanup(self) -> dict[str, Any]: ...
    def accounting(self) -> dict[str, float]: ...


@dataclass(frozen=True)
class PhaseResult:
    reason: str
    bytes_moved: int = 0
    evidence: dict[str, Any] | None = None


class ExclusiveNodeLease:
    """Agent-side second-launch refusal independent of any control plane."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._token: bytes | None = None

    def acquire(self, attempt_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise RuntimeFailure("exclusive-lease directory is a symlink")
        token = hashlib.sha256(f"{attempt_id}:{os.getpid()}:{time.monotonic_ns()}".encode()).hexdigest().encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            raise RuntimeFailure("exclusive occupancy refused a concurrent launch", retryable=True) from exc
        try:
            os.write(fd, token + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        self._token = token

    def release(self) -> None:
        if self._token is None:
            return
        try:
            observed = self.path.read_bytes().rstrip(b"\n")
        except OSError as exc:
            raise RuntimeFailure("exclusive occupancy receipt is unreadable") from exc
        if not hmac_compare(observed, self._token):
            raise RuntimeFailure("exclusive occupancy token changed")
        self.path.unlink()
        self._token = None


def hmac_compare(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)


class _Recorder:
    def __init__(
        self,
        ledger_path: Path,
        audit: AuditChain,
        *,
        ledger_id: str,
        trace_id: str,
        request_id: str,
        attempt_id: str,
        recorder: dict[str, Any],
    ) -> None:
        self.ledger_path = ledger_path
        self.audit = audit
        self.ledger_id = ledger_id
        self.trace_id = trace_id
        self.request_id = request_id
        self.attempt_id = attempt_id
        self.recorder = recorder
        self.bytes_moved = 0
        self.phase_receipts: dict[str, dict[str, Any]] = {}

    def emit(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event = harness.append_event(
            self.ledger_path,
            ledger_id=self.ledger_id,
            trace_id=self.trace_id,
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            recorder=self.recorder,
            event_type=event_type,
            data=data,
        )
        self.audit.append(event)
        return event

    def started(self, phase: str) -> None:
        self.emit("phase.started", {"phase": phase, "occurrence": 0})

    def finished(self, phase: str, outcome: str, reason: str, bytes_moved: int = 0) -> None:
        self.emit(
            "phase.finished",
            {
                "phase": phase,
                "occurrence": 0,
                "outcome": outcome,
                "reason": reason,
                "bytes_moved": bytes_moved,
            },
        )
        self.bytes_moved += bytes_moved


class SwitchSupervisor:
    def __init__(
        self,
        *,
        cache: ContentAddressedCache,
        authenticator: CommandAuthenticator,
        node_lease: ExclusiveNodeLease,
        checkpoint_key: bytes,
        checkpoint_profiles: dict[str, str],
        validator_id: str,
        validator_sha256: str,
    ) -> None:
        self.cache = cache
        self.authenticator = authenticator
        self.node_lease = node_lease
        self.checkpoint_key = checkpoint_key
        self.checkpoint_profiles = checkpoint_profiles
        self.validator_id = validator_id
        self.validator_sha256 = validator_sha256

    @staticmethod
    def _phase(
        recorder: _Recorder,
        phase: str,
        operation: Any,
    ) -> PhaseResult:
        recorder.started(phase)
        try:
            result = operation()
            if result is None:
                result = PhaseResult("completed")
            elif isinstance(result, dict):
                result = PhaseResult(
                    str(result.get("reason", "completed")),
                    int(result.get("bytes_moved", 0)),
                    result,
                )
            if not isinstance(result, PhaseResult):
                raise RuntimeFailure(f"{phase} returned an invalid receipt")
        except RuntimeFailure:
            recorder.finished(phase, "failed", f"{phase} failed", 0)
            raise
        except (AdmissionError, CacheError) as exc:
            recorder.finished(phase, "failed", f"{phase} refused", 0)
            raise RuntimeFailure(str(exc), failure_class="validation") from exc
        except Exception as exc:
            recorder.finished(phase, "failed", f"{phase} failed", 0)
            raise RuntimeFailure(f"{phase}: {type(exc).__name__}") from exc
        evidence = result.evidence or {
            "reason": result.reason,
            "bytes_moved": result.bytes_moved,
        }
        receipt_sha256 = harness.canonical_sha256(evidence)
        recorder.phase_receipts[phase] = {
            "receipt_sha256": receipt_sha256,
            "evidence": evidence,
        }
        recorder.finished(
            phase,
            "completed",
            f"{result.reason}; receipt_sha256={receipt_sha256}",
            result.bytes_moved,
        )
        return result

    @staticmethod
    def _skip(recorder: _Recorder, phase: str, reason: str) -> None:
        recorder.finished(phase, "skipped", reason, 0)

    def run(
        self,
        *,
        trace: dict[str, Any],
        command: dict[str, Any],
        payload: bytes,
        backend: RuntimeBackend,
        environment: dict[str, Any],
        checkpoint_environment: dict[str, Any],
        ownership: dict[str, Any],
        ledger_path: Path,
        audit_path: Path,
        artifact_source: Path | None = None,
        checkpoint_binding: dict[str, Any] | None = None,
        deadline_ns: int | None = None,
        cost_usd: float = 0.0,
        billed_seconds: float = 0.0,
        cleanup_disposition: str = "complete",
    ) -> dict[str, Any]:
        trace = harness.validate_trace(trace)
        if trace["request_count"] != 1:
            raise ValueError("one supervisor invocation must contain exactly one trace request")
        request = trace["requests"][0]
        if hashlib.sha256(payload).hexdigest() != request["input"]["payload_sha256"]:
            raise ValueError("payload bytes differ from the trace before external acceptance")
        if len(payload) != request["input"]["input_bytes"]:
            raise ValueError("payload size differs from the trace before external acceptance")
        if ledger_path.exists() or audit_path.exists():
            raise ValueError("per-attempt ledger and audit outputs must be new")
        if cleanup_disposition not in {"complete", "retained"}:
            raise ValueError("cleanup_disposition must be complete or retained")
        if (
            not isinstance(cost_usd, (int, float))
            or not math.isfinite(cost_usd)
            or cost_usd < 0
            or not isinstance(billed_seconds, (int, float))
            or not math.isfinite(billed_seconds)
            or billed_seconds < 0
        ):
            raise ValueError("cost and billed seconds must be finite and nonnegative")
        if deadline_ns is None:
            deadline_ns = time.time_ns() + 300_000_000_000

        audit = AuditChain(audit_path)
        recorder = _Recorder(
            ledger_path,
            audit,
            ledger_id=f"{trace['trace_id']}-ledger",
            trace_id=trace["trace_id"],
            request_id=request["request_id"],
            attempt_id=request["attempt_id"],
            recorder=harness.default_recorder("catalog-switch-node-external-recorder", max_error_ms=50.0),
        )
        recorder.emit(
            "request.accepted",
            {
                "boundary": harness.T0_BOUNDARY,
                "trace_request_sha256": harness.canonical_sha256(request),
                "scenario": request["scenario"],
                "target": request["target"],
                "input": request["input"],
                "precondition": request["precondition"],
                "environment": environment,
                "ownership": ownership,
            },
        )

        completed: set[str] = set()
        acquired = False
        terminal_failure: RuntimeFailure | None = None
        response: bytes | None = None
        semantic: dict[str, Any] | None = None
        accounting_error: RuntimeFailure | None = None
        accounting_collected = False
        gpu_active_seconds = 0.0
        gpu_idle_seconds = 0.0
        effective_mode = str(command.get("launch_mode", "conventional"))
        artifact_path: Path | None = None

        def collect_accounting() -> None:
            nonlocal accounting_collected, gpu_active_seconds, gpu_idle_seconds
            accounting = backend.accounting()
            active = float(accounting.get("gpu_active_seconds", 0.0))
            idle_seconds = float(accounting.get("gpu_idle_seconds", 0.0))
            if (
                not math.isfinite(active)
                or active < 0
                or not math.isfinite(idle_seconds)
                or idle_seconds < 0
            ):
                raise RuntimeFailure(
                    "accounting contains invalid GPU seconds",
                    failure_class="infrastructure",
                )
            gpu_active_seconds = active
            gpu_idle_seconds = idle_seconds
            accounting_collected = True

        def complete(phase: str, operation: Any) -> PhaseResult:
            result = self._phase(recorder, phase, operation)
            completed.add(phase)
            return result

        try:
            complete(
                "catalog_selection",
                lambda: self._authenticate(command, request),
            )
            complete(
                "queue",
                lambda: self._acquire(request["attempt_id"]),
            )
            acquired = True
            same_hot = request["scenario"] == "same_model_hot"
            idle = request["precondition"]["current_node_occupant"] is None
            if same_hot or idle:
                self._skip(recorder, "drain", "no distinct model A to drain")
                completed.add("drain")
                self._skip(recorder, "gpu_release", "no distinct model A held the GPU")
                completed.add("gpu_release")
            else:
                complete("drain", lambda: backend.drain(deadline_ns))
                complete("gpu_release", lambda: self._gpu_release(backend))

            if same_hot:
                self._skip(recorder, "placement", "target model already occupies the node")
                completed.add("placement")
            else:
                complete("placement", lambda: backend.place(request["target"]))

            complete("image_readiness", lambda: backend.image_ready(request["target"]))
            complete(
                "artifact_readiness",
                lambda: self._artifact_ready(request, artifact_source),
            )
            artifact_path = Path(self.cache.verify(request["target"]["artifact_sha256"]).path)
            complete("storage_readiness", backend.storage_ready)

            def cache_operation() -> PhaseResult:
                nonlocal effective_mode
                mount_receipt = backend.cache_ready(artifact_path)
                checkpoint_receipt: dict[str, Any] | None = None
                if effective_mode == "snapshot":
                    try:
                        if checkpoint_binding is None:
                            raise AdmissionError("snapshot launch lacks a checkpoint binding")
                        checkpoint_receipt = verify_checkpoint_binding(
                            checkpoint_binding,
                            self.checkpoint_key,
                            target=request["target"],
                            environment=checkpoint_environment,
                            expected_profiles=self.checkpoint_profiles,
                        )
                    except AdmissionError:
                        if request["scenario"] != "checkpoint_fallback":
                            raise
                        effective_mode = "conventional"
                        return PhaseResult(
                            "checkpoint refused; descending once to conventional local start",
                            evidence={
                                "mount": mount_receipt,
                                "launch_mode": effective_mode,
                                "checkpoint_binding_verified": False,
                                "fallback": "conventional-local",
                            },
                        )
                return PhaseResult(
                    f"artifact cache verified; launch mode {effective_mode}",
                    evidence={
                        "mount": mount_receipt,
                        "launch_mode": effective_mode,
                        "checkpoint_binding": checkpoint_receipt,
                    },
                )

            complete("cache_readiness", cache_operation)
            if same_hot:
                self._skip(recorder, "runtime_launch", "target runtime already serving")
                completed.add("runtime_launch")
            else:
                complete(
                    "runtime_launch",
                    lambda: backend.launch(request["target"], artifact_path, effective_mode),
                )
            complete("service_readiness", lambda: backend.ready(deadline_ns))

            def infer() -> PhaseResult:
                nonlocal accounting_error, response, semantic
                response = backend.infer(payload, deadline_ns)
                semantic = backend.semantic_validate(request["target"], payload, response)
                try:
                    collect_accounting()
                except Exception as exc:
                    accounting_error = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure(
                        f"accounting: {type(exc).__name__}",
                        failure_class="infrastructure",
                    )
                    raise accounting_error
                return PhaseResult(
                    "complete response body passed the pinned semantic validator",
                    evidence={
                        "validator_id": self.validator_id,
                        "validator_sha256": self.validator_sha256,
                        "response_sha256": hashlib.sha256(response).hexdigest(),
                        "response_bytes": len(response),
                        "semantic": semantic,
                    },
                )

            complete("inference", infer)
        except RuntimeFailure as exc:
            terminal_failure = exc
            for phase in harness.PHASES:
                if phase not in completed:
                    # The failing phase has already emitted its failed finish.
                    events = harness.load_ledger(ledger_path)
                    if any(
                        event["event_type"] == "phase.finished"
                        and event["data"].get("phase") == phase
                        for event in events
                    ):
                        completed.add(phase)
                        continue
                    self._skip(recorder, phase, "not reached after exposed phase failure")
                    completed.add(phase)

        if not accounting_collected and accounting_error is None:
            try:
                collect_accounting()
            except Exception as exc:
                accounting_error = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure(
                    f"accounting: {type(exc).__name__}", failure_class="infrastructure"
                )

        if terminal_failure is None:
            assert response is not None and semantic is not None
            recorder.emit(
                "response.validated",
                {
                    "boundary": harness.TERMINAL_BOUNDARY,
                    "validator_id": self.validator_id,
                    "validator_sha256": self.validator_sha256,
                    "response_sha256": hashlib.sha256(response).hexdigest(),
                    "response_bytes": len(response),
                    "complete_body": True,
                    "semantically_valid": True,
                    "model_id": request["target"]["model_id"],
                    "model_version": request["target"]["model_version"],
                },
            )
        else:
            recorder.emit(
                "attempt.failed",
                {
                    "failure_class": terminal_failure.failure_class,
                    "reason": str(terminal_failure),
                    "retryable": terminal_failure.retryable,
                },
            )

        recorder.emit(
            "accounting.recorded",
            {
                "currency": "USD",
                "cost_usd": cost_usd,
                "gpu_active_seconds": gpu_active_seconds,
                "gpu_idle_seconds": gpu_idle_seconds,
                "billed_seconds": billed_seconds,
                "bytes_moved_total": recorder.bytes_moved,
            },
        )

        cleanup_error: RuntimeFailure | None = None
        cleanup_receipt: dict[str, Any] = {}
        try:
            cleanup_receipt = backend.cleanup()
            if acquired:
                self.node_lease.release()
                acquired = False
        except Exception as exc:
            cleanup_error = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure(
                f"cleanup: {type(exc).__name__}"
            )

        resource_ids = [resource["id"] for resource in ownership["resources"]]
        required = ownership["cleanup_required"]
        if not required:
            status = "not_required"
            deleted: list[str] = []
            retained: list[str] = []
            reason = "attempt owns no cleanup-scoped resources"
        elif cleanup_error is not None:
            status = "failed"
            deleted = []
            retained = resource_ids
            reason = "cleanup verification failed; resource remains quarantined"
        elif cleanup_disposition == "retained":
            status = "retained"
            deleted = []
            retained = resource_ids
            reason = "task-owned lease retained within its frozen TTL for the next cohort"
        elif cleanup_disposition == "complete":
            status = "complete"
            deleted = resource_ids
            retained = []
            reason = "all attempt-scoped resources deleted with receipts"
        receipt_sha = harness.canonical_sha256(
            {"backend": cleanup_receipt, "deleted": deleted, "retained": retained, "status": status}
        )
        recorder.emit(
            "cleanup.finished",
            {
                "required": required,
                "status": status,
                "resources_deleted": deleted,
                "resources_retained": retained,
                "receipt_sha256": receipt_sha,
                "reason": reason,
            },
        )

        events = harness.load_ledger(ledger_path)
        attempts = harness.validate_ledger(events, trace)
        audit_receipt = audit.verify_events(events)
        return {
            "schema": "catalog-switch-node-run-receipt/v1",
            "attempt": attempts[0],
            "audit": audit_receipt,
            "audit_file_sha256": audit.file_sha256(),
            "artifact": None if artifact_path is None else str(artifact_path),
            "phase_receipts": recorder.phase_receipts,
            "effective_launch_mode": effective_mode,
            "terminal_failure": None if terminal_failure is None else str(terminal_failure),
            "cleanup_failure": None if cleanup_error is None else str(cleanup_error),
            "cleanup_backend_receipt": cleanup_receipt,
            "accounting_failure": None if accounting_error is None else str(accounting_error),
        }

    def _authenticate(self, command: dict[str, Any], request: dict[str, Any]) -> PhaseResult:
        receipt = self.authenticator.verify(command, request, time.time_ns())
        return PhaseResult(
            f"catalog digest pinned; authenticated command key {receipt['key_id']} admitted",
            evidence=receipt,
        )

    def _acquire(self, attempt_id: str) -> PhaseResult:
        self.node_lease.acquire(attempt_id)
        return PhaseResult(
            "exclusive node switch lease acquired; second launch denied",
            evidence={
                "attempt_id": attempt_id,
                "exclusive_occupancy": True,
                "second_launch_policy": "deny",
            },
        )

    @staticmethod
    def _gpu_release(backend: RuntimeBackend) -> PhaseResult:
        receipt = backend.gpu_release()
        if receipt.get("foreign_process_count") != 0 or receipt.get("gpu_memory_at_baseline") is not True:
            raise RuntimeFailure("GPU-free proof failed; node quarantined")
        if receipt.get("active_scrub") is not True:
            raise RuntimeFailure("GPU release lacks an active scrub receipt")
        method = receipt.get("scrub_method")
        bytes_scrubbed = receipt.get("vram_bytes_scrubbed")
        if method == "cpu-fixture-surrogate":
            if backend.runtime_version != "deterministic-fixture-v1" or bytes_scrubbed != 0:
                raise RuntimeFailure("CPU scrub surrogate is forbidden outside the test backend")
        elif method not in {"full-vram-zero", "gpu-reset", "mig-recreate"}:
            raise RuntimeFailure("GPU release has an unapproved active scrub method")
        elif not isinstance(bytes_scrubbed, int) or bytes_scrubbed <= 0:
            raise RuntimeFailure("GPU release lacks the positive scrubbed-byte count")
        if not isinstance(receipt.get("gpu_uuid"), str) or not receipt["gpu_uuid"]:
            raise RuntimeFailure("GPU release lacks the exact device identity")
        return PhaseResult(
            "active GPU scrub and zero-foreign-process proof passed",
            evidence=receipt,
        )

    def _artifact_ready(self, request: dict[str, Any], source: Path | None) -> PhaseResult:
        target = request["target"]
        cache_state = request["precondition"]["cache"]["artifact"]
        if cache_state == "remote_miss":
            if source is None:
                raise RuntimeFailure("artifact miss has no bounded localization source", retryable=True)
            receipt = self.cache.ingest(source, target["artifact_sha256"])
            return PhaseResult(
                "artifact localized and content-verified",
                receipt.bytes_moved,
                evidence={**receipt.__dict__, "cache_state": cache_state},
            )
        receipt = self.cache.verify(target["artifact_sha256"])
        return PhaseResult(
            f"{cache_state} verified by {receipt.seal}; bytes already present",
            0,
            evidence={**receipt.__dict__, "cache_state": cache_state},
        )


class DeterministicBackend:
    """CPU-only backend for integration/adversary tests, never performance evidence."""

    runtime_version = "deterministic-fixture-v1"

    def __init__(
        self,
        occupant: dict[str, str] | None,
        *,
        fail_phase: str | None = None,
        failure_class: str = "backend",
        cleanup_fails: bool = False,
        accounting_fails: bool = False,
    ) -> None:
        self.occupant = occupant
        self.fail_phase = fail_phase
        self.failure_class = failure_class
        self.cleanup_fails = cleanup_fails
        self.accounting_fails = accounting_fails
        self.target: dict[str, Any] | None = None
        self.calls: list[str] = []

    def _step(self, phase: str) -> None:
        self.calls.append(phase)
        if self.fail_phase == phase:
            raise RuntimeFailure(
                f"injected {phase} failure",
                failure_class=self.failure_class,
                retryable=self.failure_class in {"preempted", "infrastructure", "timeout"},
            )

    def drain(self, deadline_ns: int) -> dict[str, Any]:
        self._step("drain")
        if time.time_ns() >= deadline_ns:
            raise RuntimeFailure("drain deadline expired", failure_class="timeout", retryable=True)
        self.occupant = None
        return {"reason": "model A drained with bounded TERM/KILL policy"}

    def gpu_release(self) -> dict[str, Any]:
        self._step("gpu_release")
        return {
            "reason": "CPU fixture active-scrub surrogate",
            "foreign_process_count": 0,
            "gpu_memory_at_baseline": True,
            "active_scrub": True,
            "scrub_method": "cpu-fixture-surrogate",
            "vram_bytes_scrubbed": 0,
            "gpu_uuid": "cpu-fixture",
        }

    def place(self, target: dict[str, Any]) -> dict[str, Any]:
        self._step("placement")
        self.target = target
        return {"reason": "target digest assigned to the exclusive fixture slot"}

    def image_ready(self, target: dict[str, Any]) -> dict[str, Any]:
        self._step("image_readiness")
        return {"reason": "task-owned fixture image identity verified"}

    def storage_ready(self) -> dict[str, Any]:
        self._step("storage_readiness")
        return {"reason": "attached storage control ready"}

    def cache_ready(self, path: Path) -> dict[str, Any]:
        self._step("cache_readiness")
        if path.is_symlink() or not path.is_file():
            raise RuntimeFailure("artifact path is not an immutable regular file")
        return {"reason": "read-only artifact mount prepared"}

    def launch(self, target: dict[str, Any], artifact: Path, mode: str) -> dict[str, Any]:
        self._step("runtime_launch")
        if mode not in {"conventional", "snapshot"}:
            raise RuntimeFailure("unsupported launch mode")
        self.target = target
        self.occupant = {
            "model_id": target["model_id"],
            "model_version": target["model_version"],
        }
        return {"reason": f"{mode} CPU fixture launch completed"}

    def ready(self, deadline_ns: int) -> dict[str, Any]:
        self._step("service_readiness")
        if self.occupant is None:
            raise RuntimeFailure("fixture has no serving occupant")
        return {"reason": "fixture readiness probe passed"}

    def infer(self, payload: bytes, deadline_ns: int) -> bytes:
        self._step("inference")
        if time.time_ns() >= deadline_ns:
            raise RuntimeFailure("inference deadline expired", failure_class="timeout", retryable=True)
        assert self.target is not None
        result = {
            "artifact_sha256": self.target["artifact_sha256"],
            "input_sha256": hashlib.sha256(payload).hexdigest(),
            "model_id": self.target["model_id"],
            "model_version": self.target["model_version"],
            "result_sha256": hashlib.sha256(b"node-runtime-v1\0" + payload).hexdigest(),
        }
        return (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def semantic_validate(self, target: dict[str, Any], payload: bytes, response: bytes) -> dict[str, Any]:
        try:
            value = json.loads(response)
        except json.JSONDecodeError as exc:
            raise RuntimeFailure("fixture response is not JSON", failure_class="validation") from exc
        expected = {
            "artifact_sha256": target["artifact_sha256"],
            "input_sha256": hashlib.sha256(payload).hexdigest(),
            "model_id": target["model_id"],
            "model_version": target["model_version"],
            "result_sha256": hashlib.sha256(b"node-runtime-v1\0" + payload).hexdigest(),
        }
        if value != expected:
            raise RuntimeFailure("fixture semantic response differs", failure_class="validation")
        return {"semantically_valid": True}

    def cleanup(self) -> dict[str, Any]:
        self.calls.append("cleanup")
        if self.cleanup_fails:
            raise RuntimeFailure("injected unverifiable cleanup")
        self.occupant = None
        return {"uid_processes": 0, "mounts": 0, "logs": 0, "namespaces": 0}

    def accounting(self) -> dict[str, float]:
        if self.accounting_fails:
            raise RuntimeFailure("injected accounting failure", failure_class="infrastructure")
        return {"gpu_active_seconds": 0.0, "gpu_idle_seconds": 0.0}
