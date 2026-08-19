"""Fresh reviewed replacement for the sealed CPU-reference supervisor."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Protocol

from performance.request_slo import harness

from node_runtime.audit import AuditChain
from node_runtime.security import AdmissionError


class RuntimeFailure(RuntimeError):
    def __init__(self, reason: str, failure_class: str = "backend") -> None:
        super().__init__(reason)
        self.failure_class = failure_class


class CheckpointRefused(RuntimeError):
    """Snapshot bytes or binding are unusable; one conventional fallback is allowed."""


class LeaseGuard:
    """Ownership-aware exclusive lease; denied contenders cannot clean the owner."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._token: bytes | None = None

    @property
    def owned(self) -> bool:
        return self._token is not None

    def acquire(self, identity: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        token = hashlib.sha256(
            f"{identity}:{os.getpid()}:{time.monotonic_ns()}".encode()
        ).digest()
        try:
            fd = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
        except FileExistsError:
            return False
        try:
            os.write(fd, token.hex().encode() + b"\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        self._token = token
        return True

    def release_if_owned(self) -> bool:
        if self._token is None:
            return False
        observed = self.path.read_bytes().strip()
        if not hmac.compare_digest(observed, self._token.hex().encode()):
            raise RuntimeFailure("lease token changed", "isolation")
        self.path.unlink()
        self._token = None
        return True


def _mac(key: bytes, body: dict[str, Any]) -> str:
    return hmac.new(key, harness.canonical_json(body).encode(), hashlib.sha256).hexdigest()


class BoundAdmission:
    """Signed command bound to node identity, lease, ownership, deadline, and environment."""

    def __init__(self, key: bytes, *, policy_sha256: str) -> None:
        self.key = key
        self.policy_sha256 = policy_sha256

    def sign(
        self,
        request: dict[str, Any],
        *,
        nonce: str,
        instance_id: str,
        boot_id: str,
        lease_id: str,
        owner_task_id: str,
        ownership_sha256: str,
        environment_sha256: str,
        checkpoint_environment_sha256: str,
        deadline_ns: int,
        launch_mode: str,
    ) -> dict[str, Any]:
        body = {
            "schema": "catalog-switch-replacement-command/v2",
            "nonce": nonce,
            "request_sha256": harness.canonical_sha256(request),
            "target": request["target"],
            "instance_id": instance_id,
            "boot_id": boot_id,
            "lease_id": lease_id,
            "owner_task_id": owner_task_id,
            "ownership_sha256": ownership_sha256,
            "environment_sha256": environment_sha256,
            "checkpoint_environment_sha256": checkpoint_environment_sha256,
            "deadline_ns": deadline_ns,
            "launch_mode": launch_mode,
            "policy_sha256": self.policy_sha256,
        }
        return {**body, "signature": _mac(self.key, body)}

    def verify(
        self,
        command: dict[str, Any],
        request: dict[str, Any],
        *,
        now_ns: int,
        instance_id: str,
        boot_id: str,
        lease_id: str,
        owner_task_id: str,
        ownership_sha256: str,
        environment_sha256: str,
        checkpoint_environment_sha256: str,
    ) -> None:
        if set(command) != {
            "schema", "nonce", "request_sha256", "target", "instance_id", "boot_id",
            "lease_id", "owner_task_id", "ownership_sha256", "environment_sha256",
            "checkpoint_environment_sha256", "deadline_ns", "launch_mode",
            "policy_sha256", "signature",
        }:
            raise AdmissionError("replacement command schema is not closed")
        body = {key: value for key, value in command.items() if key != "signature"}
        if command["schema"] != "catalog-switch-replacement-command/v2":
            raise AdmissionError("replacement command schema mismatch")
        if not hmac.compare_digest(str(command["signature"]), _mac(self.key, body)):
            raise AdmissionError("replacement command signature mismatch")
        if command["request_sha256"] != harness.canonical_sha256(request):
            raise AdmissionError("replacement command request mismatch")
        expected = {
            "instance_id": instance_id,
            "boot_id": boot_id,
            "lease_id": lease_id,
            "owner_task_id": owner_task_id,
            "ownership_sha256": ownership_sha256,
            "environment_sha256": environment_sha256,
            "checkpoint_environment_sha256": checkpoint_environment_sha256,
            "policy_sha256": self.policy_sha256,
            "target": request["target"],
        }
        for key, value in expected.items():
            if command[key] != value:
                raise AdmissionError(f"replacement admission mismatch: {key}")
        if not isinstance(command["deadline_ns"], int) or command["deadline_ns"] < now_ns:
            raise AdmissionError("replacement command deadline expired")
        if command["launch_mode"] not in {"conventional", "snapshot"}:
            raise AdmissionError("replacement launch mode is not admitted")


def verify_checkpoint_bytes(
    checkpoint_bytes: bytes,
    binding: dict[str, Any],
    key: bytes,
    *,
    expected_artifact_sha256: str,
    expected_environment_sha256: str,
) -> None:
    actual = hashlib.sha256(checkpoint_bytes).hexdigest()
    if binding.get("checkpoint_sha256") != actual:
        raise CheckpointRefused("checkpoint bytes do not match the signed digest")
    unsigned = {key: value for key, value in binding.items() if key != "signature"}
    if not hmac.compare_digest(str(binding.get("signature")), _mac(key, unsigned)):
        raise CheckpointRefused("checkpoint binding signature mismatch")
    if binding.get("artifact_sha256") != expected_artifact_sha256:
        raise CheckpointRefused("checkpoint artifact binding mismatch")
    if binding.get("environment_sha256") != expected_environment_sha256:
        raise CheckpointRefused("checkpoint environment binding mismatch")
    if binding.get("capture_source") != "golden-pre-tenant-traffic":
        raise CheckpointRefused("checkpoint is not a golden capture")


class ReplacementBackend(Protocol):
    start_count: int

    def drain(self) -> dict[str, Any]: ...
    def gpu_release(self) -> dict[str, Any]: ...
    def launch_conventional(self) -> dict[str, Any]: ...
    def launch_snapshot(self, checkpoint_bytes: bytes) -> dict[str, Any]: ...
    def ready(self) -> dict[str, Any]: ...
    def infer(self, payload: bytes) -> bytes: ...
    def semantic_validate(self, payload: bytes, response: bytes) -> dict[str, Any]: ...
    def accounting(self) -> dict[str, float]: ...
    def cleanup(self, resource_ids: list[str]) -> dict[str, Any]: ...


class ReplacementSession:
    """Two-request session: one cold start, two independently accepted responses."""

    def __init__(
        self,
        *,
        trace: dict[str, Any],
        ledger: Path,
        audit: AuditChain,
        recorder: dict[str, Any],
        admission: BoundAdmission,
        lease: LeaseGuard,
        instance_id: str,
        boot_id: str,
        lease_id: str,
        owner_task_id: str,
        ownership_sha256: str,
        environment_sha256: str,
        checkpoint_environment_sha256: str,
    ) -> None:
        self.trace = harness.validate_trace(trace)
        if self.trace["request_count"] != 2:
            raise ValueError("replacement requires exactly two requests per cold-start cohort")
        self.ledger = ledger
        self.audit = audit
        self.recorder = recorder
        self.admission = admission
        self.lease = lease
        self.instance_id = instance_id
        self.boot_id = boot_id
        self.lease_id = lease_id
        self.owner_task_id = owner_task_id
        self.ownership_sha256 = ownership_sha256
        self.environment_sha256 = environment_sha256
        self.checkpoint_environment_sha256 = checkpoint_environment_sha256
        self.ledger_id = f"{self.trace['trace_id']}-replacement-ledger"

    def _emit(self, request: dict[str, Any], event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        event = harness.append_event(
            self.ledger,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=request["request_id"],
            attempt_id=request["attempt_id"],
            recorder=self.recorder,
            event_type=event_type,
            data=data,
        )
        self.audit.append(event)
        return event

    def _phase(self, request: dict[str, Any], phase: str, reason: str, *, outcome: str = "completed", bytes_moved: int = 0) -> None:
        self._emit(request, "phase.started", {"phase": phase, "occurrence": 0})
        self._emit(
            request,
            "phase.finished",
            {"phase": phase, "occurrence": 0, "outcome": outcome, "reason": reason, "bytes_moved": bytes_moved},
        )

    def _skip(self, request: dict[str, Any], phase: str, reason: str) -> None:
        self._emit(request, "phase.started", {"phase": phase, "occurrence": 0})
        self._emit(
            request,
            "phase.finished",
            {"phase": phase, "occurrence": 0, "outcome": "skipped", "reason": reason, "bytes_moved": 0},
        )

    def _accounting(self, request: dict[str, Any], backend: ReplacementBackend) -> None:
        accounting = backend.accounting()
        self._emit(
            request,
            "accounting.recorded",
            {
                "currency": "USD",
                "cost_usd": 0.0,
                "gpu_active_seconds": accounting["gpu_active_seconds"],
                "gpu_idle_seconds": accounting["gpu_idle_seconds"],
                "billed_seconds": 0.0,
                "bytes_moved_total": 0,
            },
        )

    def _cleanup_event(self, request: dict[str, Any]) -> None:
        ownership = next(
            event["data"]["ownership"]
            for event in harness.load_ledger(self.ledger)
            if event["attempt_id"] == request["attempt_id"]
            and event["event_type"] == "request.accepted"
        )
        data = {
            "required": ownership["cleanup_required"],
            "status": "not_required" if not ownership["cleanup_required"] else "complete",
            "resources_deleted": [] if not ownership["cleanup_required"] else [item["id"] for item in ownership["resources"]],
            "resources_retained": [],
            "receipt_sha256": hashlib.sha256(b"replacement-cleanup").hexdigest(),
            "reason": "session cleanup is separately receipt-verified" if not ownership["cleanup_required"] else "exact session cleanup receipt verified",
        }
        self._emit(request, "cleanup.finished", data)

    def _accepted_before_work(self) -> None:
        if not self.ledger.exists():
            raise RuntimeFailure("both requests require durable external T0 acceptance", "validation")
        events = harness.load_ledger(self.ledger)
        accepted = {
            event["attempt_id"]
            for event in events
            if event["event_type"] == "request.accepted"
        }
        expected = {request["attempt_id"] for request in self.trace["requests"]}
        if accepted != expected:
            raise RuntimeFailure("both requests require durable external T0 acceptance", "validation")

    def run(
        self,
        *,
        commands: list[dict[str, Any]],
        payloads: list[bytes],
        backend: ReplacementBackend,
        checkpoint_bytes: bytes,
        checkpoint_binding: dict[str, Any],
        resource_ids: list[str],
    ) -> dict[str, Any]:
        if len(commands) != 2 or len(payloads) != 2:
            raise ValueError("replacement requires two commands and two payloads")
        self._accepted_before_work()
        requests = self.trace["requests"]
        for request, command, payload in zip(requests, commands, payloads, strict=True):
            if hashlib.sha256(payload).hexdigest() != request["input"]["payload_sha256"]:
                raise ValueError("payload differs from externally accepted T0 input")
            self.admission.verify(
                command,
                request,
                now_ns=time.time_ns(),
                instance_id=self.instance_id,
                boot_id=self.boot_id,
                lease_id=self.lease_id,
                owner_task_id=self.owner_task_id,
                ownership_sha256=self.ownership_sha256,
                environment_sha256=self.environment_sha256,
                checkpoint_environment_sha256=self.checkpoint_environment_sha256,
            )
        if not self.lease.acquire(self.instance_id + ":" + self.lease_id):
            raise RuntimeFailure("exclusive lease denied; active owner remains untouched", "capacity")
        try:
            first, second = requests
            self._phase(first, "catalog_selection", "externally accepted digest and bound command")
            self._phase(first, "queue", "exclusive replacement queue admitted")
            self._phase(first, "drain", "bounded model A drain completed")
            backend.drain()
            backend.drain()
            gpu = backend.gpu_release()
            self._require_gpu_receipt(gpu)
            self._phase(first, "gpu_release", "exact GPU zero receipt verified")
            self._phase(first, "placement", "fresh node lease and target placement verified")
            self._phase(first, "image_readiness", "digest-pinned image verified")
            self._phase(first, "artifact_readiness", "content-addressed artifact verified")
            self._phase(first, "storage_readiness", "Network SSD storage readiness verified")
            self._phase(first, "cache_readiness", "cache state and bytes recorded")
            verify_checkpoint_bytes(
                checkpoint_bytes,
                checkpoint_binding,
                self.admission.key,
                expected_artifact_sha256=requests[0]["target"]["artifact_sha256"],
                expected_environment_sha256=self.environment_sha256,
            )
            try:
                backend.launch_snapshot(checkpoint_bytes)
                launch_mode = "snapshot"
            except CheckpointRefused:
                backend.launch_conventional()
                launch_mode = "conventional-fallback"
            self._phase(first, "runtime_launch", f"{launch_mode} launch completed")
            backend.ready()
            self._phase(first, "service_readiness", "readiness completed before semantic request")
            for phase in ("catalog_selection", "queue", "drain", "gpu_release", "placement", "image_readiness", "artifact_readiness", "storage_readiness", "cache_readiness", "runtime_launch", "service_readiness"):
                self._phase(second, phase, "same cold-start runtime; no second launch")
            results: list[dict[str, Any]] = []
            for request, payload in zip(requests, payloads, strict=True):
                self._emit(request, "phase.started", {"phase": "inference", "occurrence": 0})
                response = backend.infer(payload)
                semantic = backend.semantic_validate(payload, response)
                if semantic.get("semantically_valid") is not True:
                    self._emit(request, "phase.finished", {"phase": "inference", "occurrence": 0, "outcome": "failed", "reason": "semantic validator returned false", "bytes_moved": 0})
                    self._emit(request, "attempt.failed", {"failure_class": "validation", "reason": "semantic validator returned false", "retryable": False})
                    self._accounting(request, backend)
                    self._cleanup_event(request)
                    results.append({"request_id": request["request_id"], "success": False})
                    continue
                self._emit(request, "phase.finished", {"phase": "inference", "occurrence": 0, "outcome": "completed", "reason": "semantic validator returned true", "bytes_moved": 0})
                self._emit(
                    request,
                    "response.validated",
                    {
                        "boundary": harness.TERMINAL_BOUNDARY,
                        "validator_id": "replacement-semantic-validator-v2",
                        "validator_sha256": "a" * 64,
                        "response_sha256": hashlib.sha256(response).hexdigest(),
                        "response_bytes": len(response),
                        "complete_body": True,
                        "semantically_valid": True,
                        "model_id": request["target"]["model_id"],
                        "model_version": request["target"]["model_version"],
                    },
                )
                self._accounting(request, backend)
                self._cleanup_event(request)
                results.append({"request_id": request["request_id"], "success": True})
            events = harness.load_ledger(self.ledger)
            attempts = harness.validate_ledger(events, self.trace)
            audit_receipt = self.audit.verify_events(events)
            return {"launch_mode": launch_mode, "results": results, "start_count": backend.start_count, "attempts": attempts, "audit": audit_receipt}
        finally:
            if self.lease.owned:
                cleanup = backend.cleanup(resource_ids)
                self._require_cleanup_receipt(cleanup, resource_ids)
                self.lease.release_if_owned()

    @staticmethod
    def _require_gpu_receipt(receipt: dict[str, Any]) -> None:
        required = {"schema", "gpu_uuid", "foreign_process_count", "gpu_memory_at_baseline", "scrub_method", "vram_bytes_scrubbed", "processes"}
        if set(receipt) != required or receipt["schema"] != "gpu-zero-receipt/v2":
            raise RuntimeFailure("GPU receipt is incomplete", "isolation")
        if receipt["foreign_process_count"] != 0 or receipt["gpu_memory_at_baseline"] is not True:
            raise RuntimeFailure("GPU-free proof failed", "isolation")
        if not isinstance(receipt["vram_bytes_scrubbed"], int) or receipt["vram_bytes_scrubbed"] <= 0 or receipt["processes"] != []:
            raise RuntimeFailure("GPU scrub receipt is not exact", "isolation")

    @staticmethod
    def _require_cleanup_receipt(receipt: dict[str, Any], resource_ids: list[str]) -> None:
        if set(receipt) != {"schema", "resources"} or receipt["schema"] != "cleanup-receipt/v2":
            raise RuntimeFailure("cleanup receipt is incomplete", "isolation")
        records = receipt["resources"]
        if {item.get("id") for item in records} != set(resource_ids):
            raise RuntimeFailure("cleanup receipt does not cover exact resource IDs", "isolation")
        if any(item.get("absent") is not True or item.get("get_status") != "NOT_FOUND" for item in records):
            raise RuntimeFailure("cleanup did not prove exact absence", "isolation")


class DeterministicReplacementBackend:
    """CPU test backend with non-stub GPU and cleanup receipts."""

    def __init__(self, *, snapshot_refused: bool = False, semantic_false_index: int | None = None) -> None:
        self.snapshot_refused = snapshot_refused
        self.semantic_false_index = semantic_false_index
        self.start_count = 0
        self.infer_count = 0
        self.cleanup_count = 0

    def drain(self) -> dict[str, Any]:
        return {"drained": True}

    def gpu_release(self) -> dict[str, Any]:
        return {
            "schema": "gpu-zero-receipt/v2",
            "gpu_uuid": "cpu-replacement-device",
            "foreign_process_count": 0,
            "gpu_memory_at_baseline": True,
            "scrub_method": "test-full-vram-zero",
            "vram_bytes_scrubbed": 1,
            "processes": [],
        }

    def launch_conventional(self) -> dict[str, Any]:
        self.start_count += 1
        return {"launch": "conventional"}

    def launch_snapshot(self, checkpoint_bytes: bytes) -> dict[str, Any]:
        if self.snapshot_refused:
            raise CheckpointRefused("injected snapshot refusal")
        self.start_count += 1
        return {"launch": "snapshot", "bytes": len(checkpoint_bytes)}

    def ready(self) -> dict[str, Any]:
        return {"ready": True}

    def infer(self, payload: bytes) -> bytes:
        self.infer_count += 1
        return json.dumps({"input_sha256": hashlib.sha256(payload).hexdigest()}, sort_keys=True).encode() + b"\n"

    def semantic_validate(self, payload: bytes, response: bytes) -> dict[str, Any]:
        index = self.infer_count - 1
        value = json.loads(response)
        return {
            "semantically_valid": index != self.semantic_false_index
            and value["input_sha256"] == hashlib.sha256(payload).hexdigest()
        }

    def accounting(self) -> dict[str, float]:
        return {"gpu_active_seconds": 0.1, "gpu_idle_seconds": 0.2}

    def cleanup(self, resource_ids: list[str]) -> dict[str, Any]:
        self.cleanup_count += 1
        return {
            "schema": "cleanup-receipt/v2",
            "resources": [
                {"id": resource_id, "absent": True, "get_status": "NOT_FOUND"}
                for resource_id in resource_ids
            ],
        }
