#!/usr/bin/env python3
"""Crash-safe bridge from the shared external-T0 ledger to switch admission.

The reviewed request-SLO ledger remains the product denominator.  This module
adds the missing append-only predecessor-hash chain, raw semantic evidence,
validator replay, and signed off-node durability gate required by switch
acceptance.  The shared schema is not weakened or silently extended.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from performance.request_slo.harness import (
    PHASES,
    T0_BOUNDARY,
    TERMINAL_BOUNDARY,
    HarnessError,
    append_event,
    canonical_json as harness_canonical_json,
    canonical_sha256 as harness_canonical_sha256,
    load_ledger,
    validate_ledger,
    validate_trace,
)
from state_machine import (
    LEDGER_GATE_SCHEMA,
    LedgerExpectation,
    LedgerGateReceipt,
    LedgerStage,
    LaunchReservation,
    ProofRejected,
    RuntimeIdentity,
    ValidatorRef,
    VerifiedLedgerGate,
    canonical_json,
    canonical_sha256,
    key_sha256,
    sign_payload,
)


AUDIT_EVENT_SCHEMA = "archvteams.nebius.ai/catalog-switch-audit-event/v1"
OFFNODE_RECEIPT_SCHEMA = "archvteams.nebius.ai/catalog-switch-offnode-durability/v1"
VALIDATOR_OUTPUT_KEYS = {"model_id", "model_version", "semantically_valid"}


def _atomic_write(path: Path, content: bytes) -> None:
    if path.exists() and path.is_symlink():
        raise HarnessError("durable evidence path cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"evidence must be a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AuditChainStore:
    """Canonical append-only chain with idempotent event identities."""

    def __init__(self, path: Path, *, clock_ns: Callable[[], int] = time.monotonic_ns):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")
        self.clock_ns = clock_ns

    @staticmethod
    def _payload(event: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in event.items() if key != "record_sha256"}

    @classmethod
    def validate_events(cls, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        previous = "0" * 64
        seen: set[str] = set()
        expected_keys = {
            "schema",
            "sequence",
            "event_id",
            "previous_sha256",
            "event_type",
            "switch_id",
            "trace_id",
            "request_id",
            "attempt_id",
            "observed_monotonic_ns",
            "payload",
            "record_sha256",
        }
        for sequence, event in enumerate(events):
            if set(event) != expected_keys or event["schema"] != AUDIT_EVENT_SCHEMA:
                raise HarnessError("audit event shape/schema differs")
            if event["sequence"] != sequence or event["previous_sha256"] != previous:
                raise HarnessError("audit sequence/predecessor hash differs")
            if event["event_id"] in seen:
                raise HarnessError("audit event identity is duplicated")
            if not isinstance(event["payload"], dict) or event["observed_monotonic_ns"] < 1:
                raise HarnessError("audit event payload/time is invalid")
            expected = canonical_sha256(cls._payload(event))
            if event["record_sha256"] != expected:
                raise HarnessError("audit record hash differs")
            seen.add(event["event_id"])
            previous = expected
        return events

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if self.path.is_symlink() or not self.path.is_file():
            raise HarnessError("audit chain must be a regular non-symlink file")
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise HarnessError("audit chain is not newline terminated")
        events: list[dict[str, Any]] = []
        for line in raw.decode("utf-8").splitlines():
            value = json.loads(line)
            if line != canonical_json(value):
                raise HarnessError("audit chain line is not canonical JSON")
            events.append(value)
        return self.validate_events(events)

    def append(
        self,
        *,
        event_id: str,
        event_type: str,
        switch_id: str,
        trace_id: str,
        request_id: str,
        attempt_id: str,
        payload: dict[str, Any],
        observed_monotonic_ns: int | None = None,
    ) -> dict[str, Any]:
        if self.path.exists() and self.path.is_symlink():
            raise HarnessError("audit chain cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with os.fdopen(descriptor, "r+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                events = self.load()
                expected_identity = {
                    "event_type": event_type,
                    "switch_id": switch_id,
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "attempt_id": attempt_id,
                    "payload": payload,
                }
                matches = [event for event in events if event["event_id"] == event_id]
                if matches:
                    if len(matches) != 1 or any(
                        matches[0][key] != value for key, value in expected_identity.items()
                    ):
                        raise HarnessError("audit event replay differs from durable event")
                    return matches[0]
                now_ns = observed_monotonic_ns or self.clock_ns()
                if now_ns < 1:
                    raise HarnessError("audit clock returned invalid time")
                if events and now_ns <= events[-1]["observed_monotonic_ns"]:
                    now_ns = events[-1]["observed_monotonic_ns"] + 1
                event = {
                    "schema": AUDIT_EVENT_SCHEMA,
                    "sequence": len(events),
                    "event_id": event_id,
                    "previous_sha256": events[-1]["record_sha256"] if events else "0" * 64,
                    "event_type": event_type,
                    "switch_id": switch_id,
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "attempt_id": attempt_id,
                    "observed_monotonic_ns": now_ns,
                    "payload": payload,
                }
                event["record_sha256"] = canonical_sha256(event)
                flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                out_fd = os.open(self.path, flags, 0o600)
                try:
                    with os.fdopen(out_fd, "a", encoding="utf-8", closefd=False) as stream:
                        stream.write(canonical_json(event) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    os.close(out_fd)
                return event
        finally:
            # fd is closed by fdopen on the normal path.
            pass


class EvidenceBlobStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, *, label: str, content: bytes) -> dict[str, Any]:
        if not content:
            raise HarnessError(f"{label} evidence cannot be empty")
        digest = hashlib.sha256(content).hexdigest()
        path = self.root / "blobs" / digest
        if path.exists():
            if path.read_bytes() != content:
                raise HarnessError("content-addressed evidence collision")
        else:
            _atomic_write(path, content)
        return {
            "authority": path.resolve().as_uri(),
            "sha256": digest,
            "bytes": len(content),
            "media_type": "application/octet-stream",
        }

    @staticmethod
    def verify(authority: dict[str, Any]) -> bytes:
        expected = {"authority", "sha256", "bytes", "media_type"}
        if set(authority) != expected or authority["media_type"] != "application/octet-stream":
            raise ProofRejected("raw evidence authority shape differs")
        uri = authority["authority"]
        if not isinstance(uri, str) or not uri.startswith("file://"):
            raise ProofRejected("raw evidence authority is not a local canonical file")
        path = Path(uri.removeprefix("file://"))
        if path.is_symlink() or not path.is_file():
            raise ProofRejected("raw evidence authority is unavailable")
        content = path.read_bytes()
        if len(content) != authority["bytes"] or hashlib.sha256(content).hexdigest() != authority["sha256"]:
            raise ProofRejected("raw evidence byte count/digest differs")
        return content


@dataclass(frozen=True)
class ValidatorRuntime:
    contract: ValidatorRef
    replay: Callable[[bytes, bytes], dict[str, Any]]
    source_bytes: bytes

    def __post_init__(self) -> None:
        self.contract.validate()
        if not self.source_bytes:
            raise ValueError("validator executable source cannot be empty")
        if hashlib.sha256(self.source_bytes).hexdigest() != self.contract.source_sha256:
            raise ValueError("validator executable source differs from pinned contract")

    def validate(self, request: bytes, response: bytes) -> bytes:
        result = self.replay(request, response)
        if not isinstance(result, dict) or set(result) != VALIDATOR_OUTPUT_KEYS:
            raise ProofRejected("validator replay output shape differs")
        if result["semantically_valid"] is not True:
            raise ProofRejected("validator rejected semantic response")
        if (result["model_id"], result["model_version"]) == (None, None):
            raise ProofRejected("validator did not identify a model")
        return canonical_json(result).encode("ascii") + b"\n"


@dataclass(frozen=True)
class OffNodeDurabilityReceipt:
    schema: str
    sink_id: str
    sink_key_sha256: str
    sink_class: str
    object_uri: str
    object_version: str
    switch_id: str
    audit_sequence_start: int
    audit_sequence_end: int
    audit_chain_head_sha256: str
    audit_segment_sha256: str
    uploaded_bytes: int
    persisted_at_ns: int
    signature_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("signature_sha256")
        return value

    @property
    def digest(self) -> str:
        return canonical_sha256(asdict(self))


class FileOffNodeSink:
    """Executable isolated test double; live plans require immutable-object-store."""

    def __init__(self, root: Path, *, sink_id: str, key: bytes, clock_ns=time.monotonic_ns):
        self.root = root
        self.sink_id = sink_id
        self.key = key
        self.clock_ns = clock_ns

    def persist(self, *, switch_id: str, events: list[dict[str, Any]]) -> OffNodeDurabilityReceipt:
        AuditChainStore.validate_events(events)
        if not events:
            raise HarnessError("cannot persist an empty audit segment")
        content = b"".join((canonical_json(event) + "\n").encode("ascii") for event in events)
        segment_sha = hashlib.sha256(content).hexdigest()
        path = self.root / switch_id / f"{segment_sha}.jsonl"
        if path.exists() and path.read_bytes() != content:
            raise HarnessError("off-node immutable object version changed")
        if not path.exists():
            _atomic_write(path, content)
        payload = {
            "schema": OFFNODE_RECEIPT_SCHEMA,
            "sink_id": self.sink_id,
            "sink_key_sha256": key_sha256(self.key),
            "sink_class": "isolated-test-double",
            "object_uri": path.resolve().as_uri(),
            "object_version": segment_sha,
            "switch_id": switch_id,
            "audit_sequence_start": 0,
            "audit_sequence_end": len(events) - 1,
            "audit_chain_head_sha256": events[-1]["record_sha256"],
            "audit_segment_sha256": segment_sha,
            "uploaded_bytes": len(content),
            "persisted_at_ns": self.clock_ns(),
        }
        return OffNodeDurabilityReceipt(**payload, signature_sha256=sign_payload(self.key, payload))


class ImmutableObjectClient(Protocol):
    def put_if_absent(
        self, *, object_key: str, content: bytes, content_sha256: str
    ) -> tuple[str, str]:
        """Return immutable object URI and provider version/generation."""


class ImmutableObjectReader(Protocol):
    def get_exact(self, *, object_uri: str, object_version: str) -> bytes:
        """Read the exact immutable provider version named by the receipt."""


class OffNodeSink(Protocol):
    def persist(
        self, *, switch_id: str, events: list[dict[str, Any]]
    ) -> OffNodeDurabilityReceipt: ...


class ImmutableObjectStoreSink:
    """Production-shaped off-node sink backed by create-if-absent object writes."""

    def __init__(
        self,
        *,
        client: ImmutableObjectClient,
        object_prefix: str,
        sink_id: str,
        receipt_signing_key: bytes,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ):
        if not object_prefix or object_prefix.startswith("/") or ".." in Path(object_prefix).parts:
            raise ValueError("off-node object prefix must be relative and traversal-free")
        self.client = client
        self.object_prefix = object_prefix.rstrip("/")
        self.sink_id = sink_id
        self.receipt_signing_key = receipt_signing_key
        self.clock_ns = clock_ns

    def persist(
        self, *, switch_id: str, events: list[dict[str, Any]]
    ) -> OffNodeDurabilityReceipt:
        AuditChainStore.validate_events(events)
        if not events:
            raise HarnessError("cannot persist an empty audit segment")
        content = b"".join(
            (canonical_json(event) + "\n").encode("ascii") for event in events
        )
        segment_sha = hashlib.sha256(content).hexdigest()
        object_key = f"{self.object_prefix}/{switch_id}/{segment_sha}.jsonl"
        object_uri, object_version = self.client.put_if_absent(
            object_key=object_key,
            content=content,
            content_sha256=segment_sha,
        )
        if not isinstance(object_uri, str) or not object_uri.startswith(
            ("s3://", "https://", "nebius-object://")
        ):
            raise HarnessError("object client returned a non-off-node authority")
        if not isinstance(object_version, str) or not object_version:
            raise HarnessError("object client omitted immutable version/generation")
        payload = {
            "schema": OFFNODE_RECEIPT_SCHEMA,
            "sink_id": self.sink_id,
            "sink_key_sha256": key_sha256(self.receipt_signing_key),
            "sink_class": "immutable-object-store",
            "object_uri": object_uri,
            "object_version": object_version,
            "switch_id": switch_id,
            "audit_sequence_start": 0,
            "audit_sequence_end": len(events) - 1,
            "audit_chain_head_sha256": events[-1]["record_sha256"],
            "audit_segment_sha256": segment_sha,
            "uploaded_bytes": len(content),
            "persisted_at_ns": self.clock_ns(),
        }
        return OffNodeDurabilityReceipt(
            **payload,
            signature_sha256=sign_payload(self.receipt_signing_key, payload),
        )


class DurabilityReceiptStore:
    def __init__(self, root: Path):
        self.root = root

    def put(self, receipt: OffNodeDurabilityReceipt) -> str:
        digest = receipt.digest
        path = self.root / "durability" / f"{digest}.json"
        content = (canonical_json(asdict(receipt)) + "\n").encode("ascii")
        if path.exists() and path.read_bytes() != content:
            raise HarnessError("durability receipt digest collision")
        if not path.exists():
            _atomic_write(path, content)
        return digest

    def get(self, digest: str) -> OffNodeDurabilityReceipt:
        path = self.root / "durability" / f"{digest}.json"
        if file_sha256(path) == "":  # pragma: no cover - makes regular-file check explicit
            raise ProofRejected("durability receipt is unavailable")
        return OffNodeDurabilityReceipt(**json.loads(path.read_text(encoding="ascii")))


@dataclass(frozen=True)
class RecoverySpec:
    trace_id: str
    request_id: str
    attempt_id: str
    accepted_t0_ns: int
    ledger_id: str
    trace_request_sha256: str
    input_payload_sha256: str
    predecessor_failure_receipt_sha256: str
    model_id: str
    model_version: str
    artifact_sha256: str
    validator: ValidatorRef


class SwitchLedgerBridge:
    """Idempotent staged writer for product failure/success and recovery evidence."""

    def __init__(
        self,
        *,
        path: Path,
        audit_path: Path,
        evidence_root: Path,
        trace: dict[str, Any],
        ledger_id: str,
        switch_id: str,
        request_id: str,
        attempt_id: str,
        recorder: dict[str, Any],
        validator_runtime: ValidatorRuntime,
        offnode_sink: OffNodeSink,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ):
        self.path = path
        self.audit = AuditChainStore(audit_path, clock_ns=clock_ns)
        self.blobs = EvidenceBlobStore(evidence_root)
        self.durability = DurabilityReceiptStore(evidence_root)
        self.trace = validate_trace(trace)
        self.ledger_id = ledger_id
        self.switch_id = switch_id
        self.request_id = request_id
        self.attempt_id = attempt_id
        self.recorder = recorder
        self.validator_runtime = validator_runtime
        self.offnode_sink = offnode_sink
        self.clock_ns = clock_ns
        self.runtime: RuntimeIdentity | None = None
        self.reservation: LaunchReservation | None = None
        self.launch_receipt_sha256: str | None = None
        self.recovery: RecoverySpec | None = None
        self.recovery_path: Path | None = None
        self.recovery_trace: dict[str, Any] | None = None
        self.recovery_recorder: dict[str, Any] | None = None
        self.recovery_trace_request: dict[str, Any] | None = None
        matching = [
            item
            for item in self.trace["requests"]
            if item["request_id"] == request_id and item["attempt_id"] == attempt_id
        ]
        if len(matching) != 1:
            raise HarnessError("bridge request/attempt is not unique in trace")
        self.trace_request = matching[0]
        accepted = self._accepted_event()
        if accepted["data"].get("boundary") != T0_BOUNDARY:
            raise HarnessError("bridge does not use frozen external T0")
        if accepted["data"].get("trace_request_sha256") != harness_canonical_sha256(self.trace_request):
            raise HarnessError("external T0 differs from trace request")
        if (
            self.trace_request["target"]["model_id"],
            self.trace_request["target"]["model_version"],
            self.trace_request["target"]["artifact_sha256"],
        ) == (None, None, None):
            raise HarnessError("trace target is incomplete")
        self._mirror_shared_events()

    @property
    def accepted_t0_ns(self) -> int:
        return int(self._accepted_event()["observed_monotonic_ns"])

    def _all_events(self) -> list[dict[str, Any]]:
        events = load_ledger(self.path)
        if any(event["ledger_id"] != self.ledger_id for event in events):
            raise HarnessError("bridge found mixed ledger identity")
        if any(event["trace_id"] != self.trace["trace_id"] for event in events):
            raise HarnessError("bridge found mixed trace identity")
        if any(event["recorder"] != self.recorder for event in events):
            raise HarnessError("bridge found mixed external recorder")
        return events

    def _attempt_events(self) -> list[dict[str, Any]]:
        return [
            event
            for event in self._all_events()
            if event["request_id"] == self.request_id and event["attempt_id"] == self.attempt_id
        ]

    def _accepted_event(self) -> dict[str, Any]:
        attempt = self._attempt_events()
        accepted = [event for event in attempt if event["event_type"] == "request.accepted"]
        if len(accepted) != 1 or attempt[0] != accepted[0]:
            raise HarnessError("switch work cannot start before one external T0")
        return accepted[0]

    def _mirror_shared_events(self) -> None:
        for event in self._attempt_events():
            self.audit.append(
                event_id=f"shared:{event['event_id']}",
                event_type="shared.event",
                switch_id=self.switch_id,
                trace_id=event["trace_id"],
                request_id=event["request_id"],
                attempt_id=event["attempt_id"],
                observed_monotonic_ns=event["observed_monotonic_ns"],
                payload={"event": event, "event_sha256": harness_canonical_sha256(event)},
            )

    def _recovery_all_events(self) -> list[dict[str, Any]]:
        if self.recovery is None or self.recovery_path is None or self.recovery_trace is None:
            raise HarnessError("recovery shared ledger is not configured")
        events = load_ledger(self.recovery_path)
        if any(event["ledger_id"] != self.recovery.ledger_id for event in events):
            raise HarnessError("recovery bridge found mixed ledger identity")
        if any(event["trace_id"] != self.recovery.trace_id for event in events):
            raise HarnessError("recovery bridge found mixed trace identity")
        if any(event["recorder"] != self.recovery_recorder for event in events):
            raise HarnessError("recovery bridge found mixed external recorder")
        return events

    def _recovery_attempt_events(self) -> list[dict[str, Any]]:
        if self.recovery is None:
            raise HarnessError("recovery trace is not configured")
        return [
            event
            for event in self._recovery_all_events()
            if event["request_id"] == self.recovery.request_id
            and event["attempt_id"] == self.recovery.attempt_id
        ]

    def _recovery_accepted_event(self) -> dict[str, Any]:
        attempt = self._recovery_attempt_events()
        accepted = [event for event in attempt if event["event_type"] == "request.accepted"]
        if len(accepted) != 1 or attempt[0] != accepted[0]:
            raise HarnessError("rollback work cannot start before its own external T0")
        return accepted[0]

    def _mirror_recovery_shared_events(self) -> None:
        for event in self._recovery_attempt_events():
            self.audit.append(
                event_id=f"recovery-shared:{event['event_id']}",
                event_type="shared.event",
                switch_id=self.switch_id,
                trace_id=event["trace_id"],
                request_id=event["request_id"],
                attempt_id=event["attempt_id"],
                observed_monotonic_ns=event["observed_monotonic_ns"],
                payload={"event": event, "event_sha256": harness_canonical_sha256(event)},
            )

    def _append_recovery_shared_idempotent(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        identity: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        if (
            self.recovery is None
            or self.recovery_path is None
            or self.recovery_trace is None
            or self.recovery_recorder is None
        ):
            raise HarnessError("recovery shared ledger is not configured")
        existing = [event for event in self._recovery_attempt_events() if identity(event)]
        if existing:
            if (
                len(existing) != 1
                or existing[0]["event_type"] != event_type
                or existing[0]["data"] != data
            ):
                raise HarnessError(f"recovery {event_type} replay differs")
            self._mirror_recovery_shared_events()
            return existing[0]
        event = append_event(
            self.recovery_path,
            ledger_id=self.recovery.ledger_id,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            recorder=self.recovery_recorder,
            event_type=event_type,
            data=data,
        )
        self._mirror_recovery_shared_events()
        return event

    def _append_shared_idempotent(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        identity: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        existing = [event for event in self._attempt_events() if identity(event)]
        if existing:
            if len(existing) != 1 or existing[0]["event_type"] != event_type or existing[0]["data"] != data:
                raise HarnessError(f"{event_type} replay differs from durable event")
            self._mirror_shared_events()
            return existing[0]
        event = append_event(
            self.path,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            recorder=self.recorder,
            event_type=event_type,
            data=data,
        )
        self._mirror_shared_events()
        return event

    def start_phase(self, phase: str, *, occurrence: int = 0) -> dict[str, Any]:
        if phase not in PHASES:
            raise HarnessError("unknown canonical phase")
        data = {"phase": phase, "occurrence": occurrence}
        return self._append_shared_idempotent(
            "phase.started",
            data,
            identity=lambda event: event["event_type"] == "phase.started"
            and event["data"].get("phase") == phase
            and event["data"].get("occurrence") == occurrence,
        )

    def finish_phase(
        self,
        phase: str,
        *,
        outcome: str,
        reason: str,
        bytes_moved: int = 0,
        occurrence: int = 0,
    ) -> dict[str, Any]:
        data = {
            "phase": phase,
            "occurrence": occurrence,
            "outcome": outcome,
            "reason": reason,
            "bytes_moved": bytes_moved,
        }
        return self._append_shared_idempotent(
            "phase.finished",
            data,
            identity=lambda event: event["event_type"] == "phase.finished"
            and event["data"].get("phase") == phase
            and event["data"].get("occurrence") == occurrence,
        )

    def record_launch_reservation(self, reservation: LaunchReservation) -> None:
        reservation.validate()
        if reservation.switch_id != self.switch_id:
            raise HarnessError("launch reservation targets another switch")
        target = self.trace_request["target"]
        if (reservation.model.model_id, reservation.model.model_version, reservation.model.artifact_sha256) != (
            target["model_id"],
            target["model_version"],
            target["artifact_sha256"],
        ):
            raise HarnessError("launch reservation differs from trace target")
        self.reservation = reservation
        self.audit.append(
            event_id=f"launch-reserved:{reservation.operation_id}",
            event_type="launch.reserved",
            switch_id=self.switch_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            payload={"reservation": asdict(reservation), "reservation_sha256": reservation.digest},
        )

    def bind_runtime(self, runtime: RuntimeIdentity, launch_receipt) -> None:
        runtime.validate()
        if self.reservation is None:
            raise HarnessError("runtime cannot bind before durable launch reservation")
        if (
            runtime.launch_operation_id,
            runtime.runtime_generation,
            runtime.model,
            runtime.gpu_uuid,
            runtime.authority.digest,
        ) != (
            self.reservation.operation_id,
            self.reservation.runtime_generation,
            self.reservation.model,
            self.reservation.gpu_uuid,
            self.reservation.authority_sha256,
        ):
            raise HarnessError("runtime differs from launch reservation")
        if (
            launch_receipt.switch_id,
            launch_receipt.operation,
            launch_receipt.subject_sha256,
            launch_receipt.controller_id,
            launch_receipt.controller_lease_id,
            launch_receipt.controller_generation,
            launch_receipt.idempotency_key,
        ) != (
            self.switch_id,
            "launch-runtime",
            self.reservation.digest,
            self.reservation.controller_id,
            f"{self.reservation.controller_id}.generation-{self.reservation.controller_generation}",
            self.reservation.controller_generation,
            self.reservation.idempotency_key,
        ):
            raise HarnessError("launch action receipt differs from reservation/fence")
        self.runtime = runtime
        self.launch_receipt_sha256 = canonical_sha256(asdict(launch_receipt))
        self.audit.append(
            event_id=f"runtime-bound:{self.attempt_id}",
            event_type="runtime.bound",
            switch_id=self.switch_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            payload={
                "runtime": asdict(runtime),
                "runtime_sha256": runtime.digest,
                "launch_action_receipt": asdict(launch_receipt),
                "launch_action_receipt_sha256": self.launch_receipt_sha256,
            },
        )

    def _validate_output_model(self, output: bytes, runtime: RuntimeIdentity) -> None:
        value = json.loads(output)
        if (value["model_id"], value["model_version"]) != (
            runtime.model.model_id,
            runtime.model.model_version,
        ):
            raise ProofRejected("validator output model differs from runtime")

    def _record_semantic(
        self,
        *,
        sequence: int,
        raw_request: bytes,
        raw_response: bytes,
        runtime: RuntimeIdentity,
        trace_id: str,
        request_id: str,
        attempt_id: str,
        recovery: bool,
        request_started_at_ns: int,
        response_completed_at_ns: int,
    ) -> dict[str, Any]:
        if sequence not in {1, 2}:
            raise HarnessError("semantic call sequence must be 1 or 2")
        if request_started_at_ns < 1 or response_completed_at_ns <= request_started_at_ns:
            raise HarnessError("semantic inference clocks are not strictly ordered")
        request_authority = self.blobs.put(label=f"request-{sequence}", content=raw_request)
        response_authority = self.blobs.put(label=f"response-{sequence}", content=raw_response)
        output = self.validator_runtime.validate(raw_request, raw_response)
        self._validate_output_model(output, runtime)
        validator_authority = self.blobs.put(label=f"validator-output-{sequence}", content=output)
        validator_source_authority = self.blobs.put(
            label=f"validator-source-{sequence}",
            content=self.validator_runtime.source_bytes,
        )
        existing_calls = [
            event
            for event in self.audit.load()
            if event["event_type"] == "semantic.call" and event["attempt_id"] == attempt_id
        ]
        if any(event["payload"]["sequence"] not in {1, 2} for event in existing_calls):
            raise HarnessError("prior unrecognized semantic call exists")
        if sequence == 2 and not any(event["payload"]["sequence"] == 1 for event in existing_calls):
            raise HarnessError("semantic call 2 cannot precede call 1")
        if sequence == 2:
            first = next(
                event for event in existing_calls if event["payload"]["sequence"] == 1
            )
            if request_started_at_ns <= first["payload"]["response_completed_at_ns"]:
                raise HarnessError(
                    "semantic call 2 must start strictly after call 1 completes"
                )
        if sequence == 1 and existing_calls and not any(event["payload"]["sequence"] == 1 for event in existing_calls):
            raise HarnessError("prior semantic calls exist before call 1")
        terminal: dict[str, Any] | None = None
        trace_request = self.recovery_trace_request if recovery else self.trace_request
        if trace_request is None:
            raise HarnessError("semantic call lacks its canonical trace request")
        if sequence == 1:
            expected_input_sha = trace_request["input"]["payload_sha256"]
            if request_authority["sha256"] != expected_input_sha:
                raise HarnessError("first semantic request bytes differ from external trace input")
            response_data = {
                "boundary": TERMINAL_BOUNDARY,
                "validator_id": self.validator_runtime.contract.validator_id,
                "validator_sha256": self.validator_runtime.contract.source_sha256,
                "response_sha256": response_authority["sha256"],
                "response_bytes": response_authority["bytes"],
                "complete_body": True,
                "semantically_valid": True,
                "model_id": runtime.model.model_id,
                "model_version": runtime.model.model_version,
            }
            append_terminal = (
                self._append_recovery_shared_idempotent
                if recovery
                else self._append_shared_idempotent
            )
            terminal = append_terminal(
                "response.validated",
                response_data,
                identity=lambda event: event["event_type"]
                in {"response.validated", "attempt.failed"},
            )
        else:
            attempt_events = (
                self._recovery_attempt_events() if recovery else self._attempt_events()
            )
            terminals = [
                event
                for event in attempt_events
                if event["event_type"] == "response.validated"
            ]
            if len(terminals) != 1:
                raise HarnessError("semantic call 2 requires one product terminal")
            terminal = terminals[0]
        payload = {
            "sequence": sequence,
            "request_started_at_ns": request_started_at_ns,
            "response_completed_at_ns": response_completed_at_ns,
            "request_authority": request_authority,
            "response_authority": response_authority,
            "validator_output_authority": validator_authority,
            "validator_source_authority": validator_source_authority,
            "validator": asdict(self.validator_runtime.contract),
            "runtime_sha256": runtime.digest,
            "runtime_uid": runtime.runtime_uid,
            "runtime_generation": runtime.runtime_generation,
            "launch_operation_id": runtime.launch_operation_id,
            "node_boot_id": runtime.authority.node_boot_id,
            "model_id": runtime.model.model_id,
            "model_version": runtime.model.model_version,
            "artifact_sha256": runtime.model.artifact_sha256,
            "product_terminal_event_sha256": harness_canonical_sha256(terminal),
            "recovery": recovery,
        }
        return self.audit.append(
            event_id=f"semantic:{attempt_id}:{sequence}",
            event_type="semantic.call",
            switch_id=self.switch_id,
            trace_id=trace_id,
            request_id=request_id,
            attempt_id=attempt_id,
            payload=payload,
        )

    def execute_semantic_call(
        self,
        *,
        sequence: int,
        raw_request: bytes,
        inference: Callable[[bytes, str], bytes],
    ) -> dict[str, Any]:
        if self.runtime is None:
            raise HarnessError("target semantic call requires bound runtime")
        existing = self._semantic_calls(self.attempt_id)
        completed = [
            event for event in existing if event["payload"]["sequence"] == sequence
        ]
        if completed:
            if len(completed) != 1 or EvidenceBlobStore.verify(
                completed[0]["payload"]["request_authority"]
            ) != raw_request:
                raise HarnessError("semantic inference replay differs from durable call")
            return completed[0]
        if sequence == 2 and (
            len(existing) != 1 or existing[0]["payload"]["sequence"] != 1
        ):
            raise HarnessError("semantic call 2 cannot precede call 1")
        intent = self._prepare_semantic_intent(
            sequence=sequence,
            raw_request=raw_request,
            runtime=self.runtime,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            label_prefix="semantic-intent-request",
        )
        started_at_ns = intent["payload"]["request_started_at_ns"]
        idempotency_key = intent["payload"]["idempotency_key"]
        raw_response = inference(raw_request, idempotency_key)
        completed_at_ns = self.clock_ns()
        if not isinstance(raw_response, bytes):
            raise HarnessError("semantic inference must return the complete raw bytes")
        return self._record_semantic(
            sequence=sequence,
            raw_request=raw_request,
            raw_response=raw_response,
            runtime=self.runtime,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            recovery=False,
            request_started_at_ns=started_at_ns,
            response_completed_at_ns=completed_at_ns,
        )

    def _record_accounting(self, accounting: dict[str, Any]) -> dict[str, Any]:
        return self._append_shared_idempotent(
            "accounting.recorded",
            accounting,
            identity=lambda event: event["event_type"] == "accounting.recorded",
        )

    def _record_cleanup(self, cleanup: dict[str, Any]) -> dict[str, Any]:
        return self._append_shared_idempotent(
            "cleanup.finished",
            cleanup,
            identity=lambda event: event["event_type"] == "cleanup.finished",
        )

    def close_success(self, *, accounting: dict[str, Any], cleanup: dict[str, Any]) -> None:
        calls = [
            event
            for event in self.audit.load()
            if event["event_type"] == "semantic.call" and event["attempt_id"] == self.attempt_id
        ]
        if [event["payload"]["sequence"] for event in calls] != [1, 2]:
            raise HarnessError("success closure requires exact semantic calls 1 and 2")
        terminals = [event for event in self._attempt_events() if event["event_type"] in {"response.validated", "attempt.failed"}]
        if len(terminals) != 1 or terminals[0]["event_type"] != "response.validated":
            raise HarnessError("success closure lacks one response terminal")
        self._record_accounting(accounting)
        self._record_cleanup(cleanup)
        validate_ledger(self._all_events(), self.trace)

    def fail_attempt(
        self,
        *,
        failed_phase: str,
        failure_class: str,
        reason: str,
        retryable: bool,
        accounting: dict[str, Any],
        cleanup: dict[str, Any],
    ) -> None:
        if failed_phase not in PHASES:
            raise HarnessError("failure phase is not canonical")
        events = self._attempt_events()
        terminal_data = {"failure_class": failure_class, "reason": reason, "retryable": retryable}
        terminals = [event for event in events if event["event_type"] in {"response.validated", "attempt.failed"}]
        if terminals:
            if len(terminals) != 1 or terminals[0]["event_type"] != "attempt.failed" or terminals[0]["data"] != terminal_data:
                raise HarnessError("failure replay differs from durable terminal")
        else:
            finished = {
                (event["data"]["phase"], event["data"]["occurrence"])
                for event in events
                if event["event_type"] == "phase.finished"
            }
            started = {
                (event["data"]["phase"], event["data"]["occurrence"])
                for event in events
                if event["event_type"] == "phase.started"
            }
            for phase in PHASES:
                key = (phase, 0)
                if key in finished:
                    continue
                if phase == failed_phase:
                    if key not in started:
                        self.start_phase(phase)
                    self.finish_phase(phase, outcome="failed", reason=reason)
                else:
                    if key in started:
                        raise HarnessError(f"open phase {phase} must be explicitly closed")
                    self.finish_phase(
                        phase,
                        outcome="skipped",
                        reason=f"skipped after {failed_phase} failure: {reason}",
                    )
            self._append_shared_idempotent(
                "attempt.failed",
                terminal_data,
                identity=lambda event: event["event_type"] in {"response.validated", "attempt.failed"},
            )
        # These two stages intentionally run even when recovering after a crash
        # that happened immediately after attempt.failed was fsynced.
        self._record_accounting(accounting)
        self._record_cleanup(cleanup)
        validate_ledger(self._all_events(), self.trace)

    def begin_recovery(
        self,
        *,
        failure_receipt: LedgerGateReceipt,
        path: Path,
        trace: dict[str, Any],
        ledger_id: str,
        recorder: dict[str, Any],
        trace_id: str,
        request_id: str,
        attempt_id: str,
        model_id: str,
        model_version: str,
        artifact_sha256: str,
        validator_runtime: ValidatorRuntime,
    ) -> None:
        failure_receipt.validate_self()
        if failure_receipt.stage != LedgerStage.TARGET_FAILED:
            raise HarnessError("rollback recovery must link a B failure receipt")
        if (trace_id, request_id, attempt_id) == (
            self.trace["trace_id"],
            self.request_id,
            self.attempt_id,
        ):
            raise HarnessError("rollback recovery must use a distinct trace and attempt")
        recovery_trace = validate_trace(trace)
        if recovery_trace["trace_id"] != trace_id:
            raise HarnessError("recovery trace identity differs")
        matching = [
            item
            for item in recovery_trace["requests"]
            if item["request_id"] == request_id and item["attempt_id"] == attempt_id
        ]
        if len(matching) != 1:
            raise HarnessError("recovery request/attempt is not unique in trace")
        trace_request = matching[0]
        target = trace_request["target"]
        if (target["model_id"], target["model_version"], target["artifact_sha256"]) != (
            model_id,
            model_version,
            artifact_sha256,
        ):
            raise HarnessError("recovery trace target differs from rollback A")
        events = load_ledger(path)
        if any(event["ledger_id"] != ledger_id for event in events):
            raise HarnessError("recovery ledger identity differs")
        if any(event["trace_id"] != trace_id for event in events):
            raise HarnessError("recovery ledger trace differs")
        if any(event["recorder"] != recorder for event in events):
            raise HarnessError("recovery external recorder differs")
        attempt_events = [
            event
            for event in events
            if event["request_id"] == request_id and event["attempt_id"] == attempt_id
        ]
        accepted = [event for event in attempt_events if event["event_type"] == "request.accepted"]
        if len(accepted) != 1 or not attempt_events or attempt_events[0] != accepted[0]:
            raise HarnessError("recovery requires its own first durable request.accepted")
        if (
            accepted[0]["data"].get("boundary") != T0_BOUNDARY
            or accepted[0]["data"].get("trace_request_sha256")
            != harness_canonical_sha256(trace_request)
        ):
            raise HarnessError("recovery request.accepted differs from its trace")
        failure_terminals = [
            event
            for event in self.audit.load()
            if event["event_type"] == "target.failure.terminal"
            and event["attempt_id"] == self.attempt_id
        ]
        if len(failure_terminals) != 1:
            raise HarnessError("recovery cannot begin before the B failure terminal")
        accepted_t0_ns = int(accepted[0]["observed_monotonic_ns"])
        if accepted_t0_ns <= failure_terminals[0]["observed_monotonic_ns"]:
            raise HarnessError("recovery external T0 must follow the B failure terminal")
        spec = RecoverySpec(
            trace_id,
            request_id,
            attempt_id,
            accepted_t0_ns,
            ledger_id,
            harness_canonical_sha256(trace_request),
            trace_request["input"]["payload_sha256"],
            failure_receipt.receipt_sha256,
            model_id,
            model_version,
            artifact_sha256,
            validator_runtime.contract,
        )
        self.recovery = spec
        self.recovery_path = path
        self.recovery_trace = recovery_trace
        self.recovery_recorder = recorder
        self.recovery_trace_request = trace_request
        self.validator_runtime = validator_runtime
        self.reservation = None
        self.runtime = None
        self.launch_receipt_sha256 = None
        self._mirror_recovery_shared_events()
        self.audit.append(
            event_id=f"recovery-started:{attempt_id}",
            event_type="recovery.started",
            switch_id=self.switch_id,
            trace_id=trace_id,
            request_id=request_id,
            attempt_id=attempt_id,
            payload={"recovery": asdict(spec)},
        )

    def record_recovery_reservation(self, reservation: LaunchReservation) -> None:
        if self.recovery is None:
            raise HarnessError("recovery trace is not started")
        target = self.recovery
        if (reservation.model.model_id, reservation.model.model_version, reservation.model.artifact_sha256) != (
            target.model_id,
            target.model_version,
            target.artifact_sha256,
        ):
            raise HarnessError("rollback reservation differs from recovery target")
        self.reservation = reservation
        self.audit.append(
            event_id=f"recovery-launch-reserved:{reservation.operation_id}",
            event_type="launch.reserved",
            switch_id=self.switch_id,
            trace_id=target.trace_id,
            request_id=target.request_id,
            attempt_id=target.attempt_id,
            payload={"reservation": asdict(reservation), "reservation_sha256": reservation.digest},
        )

    def bind_recovery_runtime(self, runtime: RuntimeIdentity, launch_receipt) -> None:
        if self.recovery is None or self.reservation is None:
            raise HarnessError("recovery runtime lacks trace/reservation")
        if (
            runtime.launch_operation_id,
            runtime.runtime_generation,
            runtime.model,
            runtime.authority.digest,
        ) != (
            self.reservation.operation_id,
            self.reservation.runtime_generation,
            self.reservation.model,
            self.reservation.authority_sha256,
        ):
            raise HarnessError("recovery runtime differs from reservation")
        if (
            launch_receipt.switch_id,
            launch_receipt.operation,
            launch_receipt.subject_sha256,
            launch_receipt.controller_id,
            launch_receipt.controller_lease_id,
            launch_receipt.controller_generation,
            launch_receipt.idempotency_key,
        ) != (
            self.switch_id,
            "launch-runtime",
            self.reservation.digest,
            self.reservation.controller_id,
            f"{self.reservation.controller_id}.generation-{self.reservation.controller_generation}",
            self.reservation.controller_generation,
            self.reservation.idempotency_key,
        ):
            raise HarnessError("recovery launch action receipt differs")
        self.runtime = runtime
        self.launch_receipt_sha256 = canonical_sha256(asdict(launch_receipt))
        self.audit.append(
            event_id=f"runtime-bound:{self.recovery.attempt_id}",
            event_type="runtime.bound",
            switch_id=self.switch_id,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            payload={
                "runtime": asdict(runtime),
                "runtime_sha256": runtime.digest,
                "launch_action_receipt": asdict(launch_receipt),
                "launch_action_receipt_sha256": self.launch_receipt_sha256,
            },
        )

    def execute_recovery_semantic_call(
        self,
        *,
        sequence: int,
        raw_request: bytes,
        inference: Callable[[bytes, str], bytes],
    ) -> dict[str, Any]:
        if self.recovery is None or self.runtime is None:
            raise HarnessError("recovery semantic call lacks recovery runtime")
        existing = self._semantic_calls(self.recovery.attempt_id)
        completed = [
            event for event in existing if event["payload"]["sequence"] == sequence
        ]
        if completed:
            if len(completed) != 1 or EvidenceBlobStore.verify(
                completed[0]["payload"]["request_authority"]
            ) != raw_request:
                raise HarnessError("recovery inference replay differs from durable call")
            return completed[0]
        if sequence == 2 and (
            len(existing) != 1 or existing[0]["payload"]["sequence"] != 1
        ):
            raise HarnessError("recovery semantic call 2 cannot precede call 1")
        intent = self._prepare_semantic_intent(
            sequence=sequence,
            raw_request=raw_request,
            runtime=self.runtime,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            label_prefix="recovery-intent-request",
        )
        started_at_ns = intent["payload"]["request_started_at_ns"]
        idempotency_key = intent["payload"]["idempotency_key"]
        raw_response = inference(raw_request, idempotency_key)
        completed_at_ns = self.clock_ns()
        if not isinstance(raw_response, bytes):
            raise HarnessError("recovery inference must return complete raw bytes")
        return self._record_semantic(
            sequence=sequence,
            raw_request=raw_request,
            raw_response=raw_response,
            runtime=self.runtime,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            recovery=True,
            request_started_at_ns=started_at_ns,
            response_completed_at_ns=completed_at_ns,
        )

    def start_recovery_phase(self, phase: str, *, occurrence: int = 0) -> dict[str, Any]:
        if phase not in PHASES:
            raise HarnessError("unknown canonical recovery phase")
        data = {"phase": phase, "occurrence": occurrence}
        return self._append_recovery_shared_idempotent(
            "phase.started",
            data,
            identity=lambda event: event["event_type"] == "phase.started"
            and event["data"].get("phase") == phase
            and event["data"].get("occurrence") == occurrence,
        )

    def finish_recovery_phase(
        self,
        phase: str,
        *,
        outcome: str,
        reason: str,
        bytes_moved: int = 0,
        occurrence: int = 0,
    ) -> dict[str, Any]:
        if phase not in PHASES:
            raise HarnessError("unknown canonical recovery phase")
        data = {
            "phase": phase,
            "occurrence": occurrence,
            "outcome": outcome,
            "reason": reason,
            "bytes_moved": bytes_moved,
        }
        return self._append_recovery_shared_idempotent(
            "phase.finished",
            data,
            identity=lambda event: event["event_type"] == "phase.finished"
            and event["data"].get("phase") == phase
            and event["data"].get("occurrence") == occurrence,
        )

    def close_recovery_success(
        self, *, accounting: dict[str, Any], cleanup: dict[str, Any]
    ) -> None:
        if self.recovery is None or self.recovery_trace is None:
            raise HarnessError("recovery success closure lacks recovery trace")
        calls = self._semantic_calls(self.recovery.attempt_id)
        if [event["payload"]["sequence"] for event in calls] != [1, 2]:
            raise HarnessError("recovery closure requires exact semantic calls 1 and 2")
        terminals = [
            event
            for event in self._recovery_attempt_events()
            if event["event_type"] in {"response.validated", "attempt.failed"}
        ]
        if len(terminals) != 1 or terminals[0]["event_type"] != "response.validated":
            raise HarnessError("recovery closure lacks one response terminal")
        self._append_recovery_shared_idempotent(
            "accounting.recorded",
            accounting,
            identity=lambda event: event["event_type"] == "accounting.recorded",
        )
        self._append_recovery_shared_idempotent(
            "cleanup.finished",
            cleanup,
            identity=lambda event: event["event_type"] == "cleanup.finished",
        )
        validate_ledger(self._recovery_all_events(), self.recovery_trace)

    def _make_receipt(
        self,
        *,
        stage: LedgerStage,
        trace_id: str,
        request_id: str,
        attempt_id: str,
        runtime_generation: int,
        launch_operation_id: str,
        launch_action_receipt_sha256: str | None,
        model_id: str,
        model_version: str,
        artifact_sha256: str,
        validator_sha256: str,
        predecessor_receipt_sha256: str | None,
        product_terminal_event_sha256: str | None,
        first_semantic_at_ns: int | None,
        second_semantic_at_ns: int | None,
        accepted_t0_ns: int | None = None,
        shared_ledger_path: Path | None = None,
    ) -> LedgerGateReceipt:
        events = self.audit.load()
        if not events:
            raise HarnessError("audit chain is empty")
        durability = self.offnode_sink.persist(switch_id=self.switch_id, events=events)
        durability_digest = self.durability.put(durability)
        audit_bytes = b"".join((canonical_json(event) + "\n").encode("ascii") for event in events)
        shared_sha = file_sha256(shared_ledger_path or self.path)
        payload = {
            "schema": LEDGER_GATE_SCHEMA,
            "stage": stage,
            "switch_id": self.switch_id,
            "trace_id": trace_id,
            "request_id": request_id,
            "attempt_id": attempt_id,
            "accepted_t0_ns": accepted_t0_ns or self.accepted_t0_ns,
            "runtime_generation": runtime_generation,
            "launch_operation_id": launch_operation_id,
            "launch_action_receipt_sha256": launch_action_receipt_sha256,
            "model_id": model_id,
            "model_version": model_version,
            "artifact_sha256": artifact_sha256,
            "validator_sha256": validator_sha256,
            "shared_ledger_sha256": shared_sha,
            "audit_segment_sha256": hashlib.sha256(audit_bytes).hexdigest(),
            "audit_sequence_start": 0,
            "audit_sequence_end": len(events) - 1,
            "audit_chain_head_sha256": events[-1]["record_sha256"],
            "offnode_durability_receipt_sha256": durability_digest,
            "product_terminal_event_sha256": product_terminal_event_sha256,
            "predecessor_receipt_sha256": predecessor_receipt_sha256,
            "first_semantic_at_ns": first_semantic_at_ns,
            "second_semantic_at_ns": second_semantic_at_ns,
        }
        serializable = dict(payload)
        serializable["stage"] = stage.value
        receipt = LedgerGateReceipt(**payload, receipt_sha256=canonical_sha256(serializable))
        receipt.validate_self()
        return receipt

    def qualification_receipt(self) -> LedgerGateReceipt:
        if self.runtime is None:
            raise HarnessError("qualification lacks target runtime")
        validate_ledger(self._all_events(), self.trace)
        calls = self._semantic_calls(self.attempt_id)
        self._validate_calls(
            calls,
            self.runtime,
            self.validator_runtime,
            self._semantic_intents(self.attempt_id),
        )
        terminal = [event for event in self._attempt_events() if event["event_type"] == "response.validated"]
        if len(terminal) != 1:
            raise HarnessError("qualification lacks one product terminal")
        self.audit.append(
            event_id=f"qualification-terminal:{self.attempt_id}",
            event_type="qualification.terminal",
            switch_id=self.switch_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            payload={
                "call_record_sha256": [event["record_sha256"] for event in calls],
                "product_terminal_event_sha256": harness_canonical_sha256(terminal[0]),
            },
        )
        return self._make_receipt(
            stage=LedgerStage.TARGET_QUALIFIED,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            runtime_generation=self.runtime.runtime_generation,
            launch_operation_id=self.runtime.launch_operation_id,
            launch_action_receipt_sha256=self.launch_receipt_sha256,
            model_id=self.runtime.model.model_id,
            model_version=self.runtime.model.model_version,
            artifact_sha256=self.runtime.model.artifact_sha256,
            validator_sha256=self.validator_runtime.contract.source_sha256,
            predecessor_receipt_sha256=None,
            product_terminal_event_sha256=harness_canonical_sha256(terminal[0]),
            first_semantic_at_ns=calls[0]["observed_monotonic_ns"],
            second_semantic_at_ns=calls[1]["observed_monotonic_ns"],
        )

    def failure_receipt(self) -> LedgerGateReceipt:
        if self.reservation is None:
            raise HarnessError("failure receipt lacks launch reservation")
        validate_ledger(self._all_events(), self.trace)
        terminals = [event for event in self._attempt_events() if event["event_type"] == "attempt.failed"]
        if len(terminals) != 1:
            raise HarnessError("failure receipt lacks one failed terminal")
        self.audit.append(
            event_id=f"target-failure-terminal:{self.attempt_id}",
            event_type="target.failure.terminal",
            switch_id=self.switch_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            payload={"product_terminal_event_sha256": harness_canonical_sha256(terminals[0])},
        )
        return self._make_receipt(
            stage=LedgerStage.TARGET_FAILED,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            runtime_generation=self.reservation.runtime_generation,
            launch_operation_id=self.reservation.operation_id,
            launch_action_receipt_sha256=self.launch_receipt_sha256,
            model_id=self.reservation.model.model_id,
            model_version=self.reservation.model.model_version,
            artifact_sha256=self.reservation.model.artifact_sha256,
            validator_sha256=self.validator_runtime.contract.source_sha256,
            predecessor_receipt_sha256=None,
            product_terminal_event_sha256=harness_canonical_sha256(terminals[0]),
            first_semantic_at_ns=None,
            second_semantic_at_ns=None,
        )

    def rollback_qualification_receipt(self) -> LedgerGateReceipt:
        if self.recovery is None or self.runtime is None:
            raise HarnessError("rollback qualification lacks recovery/runtime")
        if self.recovery_trace is None or self.recovery_path is None:
            raise HarnessError("rollback qualification lacks recovery shared ledger")
        validate_ledger(self._recovery_all_events(), self.recovery_trace)
        calls = self._semantic_calls(self.recovery.attempt_id)
        self._validate_calls(
            calls,
            self.runtime,
            self.validator_runtime,
            self._semantic_intents(self.recovery.attempt_id),
        )
        terminal = [
            event
            for event in self._recovery_attempt_events()
            if event["event_type"] == "response.validated"
        ]
        if len(terminal) != 1:
            raise HarnessError("rollback qualification lacks its recovery terminal")
        self.audit.append(
            event_id=f"rollback-qualification-terminal:{self.recovery.attempt_id}",
            event_type="rollback.qualification.terminal",
            switch_id=self.switch_id,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            payload={
                "predecessor_failure_receipt_sha256": self.recovery.predecessor_failure_receipt_sha256,
                "call_record_sha256": [event["record_sha256"] for event in calls],
                "product_terminal_event_sha256": harness_canonical_sha256(terminal[0]),
            },
        )
        return self._make_receipt(
            stage=LedgerStage.ROLLBACK_QUALIFIED,
            trace_id=self.recovery.trace_id,
            request_id=self.recovery.request_id,
            attempt_id=self.recovery.attempt_id,
            runtime_generation=self.runtime.runtime_generation,
            launch_operation_id=self.runtime.launch_operation_id,
            launch_action_receipt_sha256=self.launch_receipt_sha256,
            model_id=self.runtime.model.model_id,
            model_version=self.runtime.model.model_version,
            artifact_sha256=self.runtime.model.artifact_sha256,
            validator_sha256=self.validator_runtime.contract.source_sha256,
            predecessor_receipt_sha256=self.recovery.predecessor_failure_receipt_sha256,
            product_terminal_event_sha256=harness_canonical_sha256(terminal[0]),
            first_semantic_at_ns=calls[0]["observed_monotonic_ns"],
            second_semantic_at_ns=calls[1]["observed_monotonic_ns"],
            accepted_t0_ns=self.recovery.accepted_t0_ns,
            shared_ledger_path=self.recovery_path,
        )

    def seal_receipt(
        self,
        *,
        qualified_receipt: LedgerGateReceipt,
        recovery_accounting: dict[str, Any] | None = None,
        recovery_cleanup: dict[str, Any] | None = None,
    ) -> LedgerGateReceipt:
        if qualified_receipt.stage not in {LedgerStage.TARGET_QUALIFIED, LedgerStage.ROLLBACK_QUALIFIED}:
            raise HarnessError("seal requires a qualified predecessor receipt")
        if qualified_receipt.stage == LedgerStage.TARGET_QUALIFIED:
            if self.runtime is None:
                raise HarnessError("target seal lacks runtime")
            trace_id, request_id, attempt_id = self.trace["trace_id"], self.request_id, self.attempt_id
            runtime = self.runtime
            validator = self.validator_runtime.contract
        else:
            if self.recovery is None or self.runtime is None:
                raise HarnessError("rollback seal lacks recovery runtime")
            trace_id, request_id, attempt_id = (
                self.recovery.trace_id,
                self.recovery.request_id,
                self.recovery.attempt_id,
            )
            runtime = self.runtime
            validator = self.recovery.validator
            if self.recovery_trace is None:
                raise HarnessError("rollback seal lacks recovery trace")
            if (recovery_accounting is None) != (recovery_cleanup is None):
                raise HarnessError("rollback seal optional closure replay must be complete")
            if recovery_accounting is not None and recovery_cleanup is not None:
                self.close_recovery_success(
                    accounting=recovery_accounting, cleanup=recovery_cleanup
                )
            validate_ledger(self._recovery_all_events(), self.recovery_trace)
        self.audit.append(
            event_id=f"switch-sealed:{attempt_id}",
            event_type="switch.sealed",
            switch_id=self.switch_id,
            trace_id=trace_id,
            request_id=request_id,
            attempt_id=attempt_id,
            payload={"qualified_receipt_sha256": qualified_receipt.receipt_sha256},
        )
        return self._make_receipt(
            stage=LedgerStage.SWITCH_SEALED,
            trace_id=trace_id,
            request_id=request_id,
            attempt_id=attempt_id,
            runtime_generation=runtime.runtime_generation,
            launch_operation_id=runtime.launch_operation_id,
            launch_action_receipt_sha256=qualified_receipt.launch_action_receipt_sha256,
            model_id=runtime.model.model_id,
            model_version=runtime.model.model_version,
            artifact_sha256=runtime.model.artifact_sha256,
            validator_sha256=validator.source_sha256,
            predecessor_receipt_sha256=qualified_receipt.receipt_sha256,
            product_terminal_event_sha256=qualified_receipt.product_terminal_event_sha256,
            first_semantic_at_ns=qualified_receipt.first_semantic_at_ns,
            second_semantic_at_ns=qualified_receipt.second_semantic_at_ns,
            accepted_t0_ns=(
                self.recovery.accepted_t0_ns
                if qualified_receipt.stage == LedgerStage.ROLLBACK_QUALIFIED
                and self.recovery is not None
                else self.accepted_t0_ns
            ),
            shared_ledger_path=(
                self.recovery_path
                if qualified_receipt.stage == LedgerStage.ROLLBACK_QUALIFIED
                else self.path
            ),
        )

    def _semantic_calls(self, attempt_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self.audit.load()
            if event["event_type"] == "semantic.call" and event["attempt_id"] == attempt_id
        ]

    def _semantic_intents(self, attempt_id: str) -> list[dict[str, Any]]:
        return [
            event
            for event in self.audit.load()
            if event["event_type"] == "semantic.call.intent"
            and event["attempt_id"] == attempt_id
        ]

    def _prepare_semantic_intent(
        self,
        *,
        sequence: int,
        raw_request: bytes,
        runtime: RuntimeIdentity,
        trace_id: str,
        request_id: str,
        attempt_id: str,
        label_prefix: str,
    ) -> dict[str, Any]:
        """Fsync once; retries reuse the exact clock and backend idempotency key."""

        if sequence not in {1, 2}:
            raise HarnessError("semantic intent sequence must be 1 or 2")
        intents = self._semantic_intents(attempt_id)
        if any(item["payload"].get("sequence") not in {1, 2} for item in intents):
            raise HarnessError("unrecognized prior semantic intent exists")
        matches = [
            item for item in intents if item["payload"].get("sequence") == sequence
        ]
        if len(matches) > 1:
            raise HarnessError("semantic intent is duplicated")
        request_authority = self.blobs.put(
            label=f"{label_prefix}-{sequence}", content=raw_request
        )
        idempotency_key = f"{attempt_id}.semantic-{sequence}"
        if matches:
            intent = matches[0]
            expected = {
                "sequence": sequence,
                "idempotency_key": idempotency_key,
                "request_authority": request_authority,
                "runtime_sha256": runtime.digest,
                "runtime_generation": runtime.runtime_generation,
                "launch_operation_id": runtime.launch_operation_id,
                "validator_source_sha256": self.validator_runtime.contract.source_sha256,
                "request_started_at_ns": intent["payload"].get(
                    "request_started_at_ns"
                ),
            }
            if (
                intent["switch_id"] != self.switch_id
                or intent["trace_id"] != trace_id
                or intent["request_id"] != request_id
                or intent["attempt_id"] != attempt_id
                or intent["payload"] != expected
                or not isinstance(expected["request_started_at_ns"], int)
                or expected["request_started_at_ns"] < 1
                or EvidenceBlobStore.verify(intent["payload"]["request_authority"])
                != raw_request
            ):
                raise HarnessError("semantic intent retry differs from durable intent")
            return intent
        if sequence == 1 and intents:
            raise HarnessError("prior semantic intent exists before call 1")
        started_at_ns = self.clock_ns()
        return self.audit.append(
            event_id=f"semantic-intent:{attempt_id}:{sequence}",
            event_type="semantic.call.intent",
            switch_id=self.switch_id,
            trace_id=trace_id,
            request_id=request_id,
            attempt_id=attempt_id,
            payload={
                "sequence": sequence,
                "idempotency_key": idempotency_key,
                "request_authority": request_authority,
                "runtime_sha256": runtime.digest,
                "runtime_generation": runtime.runtime_generation,
                "launch_operation_id": runtime.launch_operation_id,
                "validator_source_sha256": self.validator_runtime.contract.source_sha256,
                "request_started_at_ns": started_at_ns,
            },
        )

    @staticmethod
    def _validate_calls(
        calls: list[dict[str, Any]],
        runtime: RuntimeIdentity,
        validator: ValidatorRuntime,
        intents: list[dict[str, Any]],
    ) -> None:
        if len(calls) != 2 or [event["payload"]["sequence"] for event in calls] != [1, 2]:
            raise ProofRejected("exactly semantic calls 1 and 2 are required")
        if len(intents) != 2 or [event["payload"]["sequence"] for event in intents] != [1, 2]:
            raise ProofRejected("exactly semantic intents 1 and 2 are required")
        if calls[1]["observed_monotonic_ns"] <= calls[0]["observed_monotonic_ns"]:
            raise ProofRejected("semantic call 2 is not strictly after call 1")
        if (
            calls[0]["payload"]["response_completed_at_ns"]
            <= calls[0]["payload"]["request_started_at_ns"]
            or calls[1]["payload"]["request_started_at_ns"]
            <= calls[0]["payload"]["response_completed_at_ns"]
            or calls[1]["payload"]["response_completed_at_ns"]
            <= calls[1]["payload"]["request_started_at_ns"]
            or calls[0]["observed_monotonic_ns"]
            < calls[0]["payload"]["response_completed_at_ns"]
            or calls[1]["observed_monotonic_ns"]
            < calls[1]["payload"]["response_completed_at_ns"]
        ):
            raise ProofRejected("semantic inference start/completion causality differs")
        requests: list[str] = []
        responses: list[str] = []
        for event, intent in zip(calls, intents, strict=True):
            payload = event["payload"]
            intent_payload = intent["payload"]
            request = EvidenceBlobStore.verify(payload["request_authority"])
            intent_request = EvidenceBlobStore.verify(intent_payload["request_authority"])
            if (
                intent["sequence"] >= event["sequence"]
                or intent_payload["sequence"] != payload["sequence"]
                or intent_payload["idempotency_key"]
                != f"{event['attempt_id']}.semantic-{payload['sequence']}"
                or intent_payload["runtime_sha256"] != runtime.digest
                or intent_payload["runtime_generation"] != runtime.runtime_generation
                or intent_payload["launch_operation_id"]
                != runtime.launch_operation_id
                or intent_payload["validator_source_sha256"]
                != validator.contract.source_sha256
                or intent_payload["request_started_at_ns"]
                != payload["request_started_at_ns"]
                or intent["observed_monotonic_ns"]
                < payload["request_started_at_ns"]
                or intent_request != request
            ):
                raise ProofRejected("semantic inference intent/call binding differs")
            if (
                payload["runtime_sha256"],
                payload["runtime_generation"],
                payload["launch_operation_id"],
                payload["node_boot_id"],
                payload["model_id"],
                payload["model_version"],
                payload["artifact_sha256"],
                payload["validator"],
            ) != (
                runtime.digest,
                runtime.runtime_generation,
                runtime.launch_operation_id,
                runtime.authority.node_boot_id,
                runtime.model.model_id,
                runtime.model.model_version,
                runtime.model.artifact_sha256,
                asdict(validator.contract),
            ):
                raise ProofRejected("semantic call runtime/model/artifact/validator differs")
            response = EvidenceBlobStore.verify(payload["response_authority"])
            output = EvidenceBlobStore.verify(payload["validator_output_authority"])
            validator_source = EvidenceBlobStore.verify(
                payload["validator_source_authority"]
            )
            if (
                validator_source != validator.source_bytes
                or hashlib.sha256(validator_source).hexdigest()
                != validator.contract.source_sha256
            ):
                raise ProofRejected("validator executable source authority differs")
            replayed = validator.validate(request, response)
            if output != replayed:
                raise ProofRejected("stored validator output differs from exact replay")
            requests.append(payload["request_authority"]["sha256"])
            responses.append(payload["response_authority"]["sha256"])
        if len(set(requests)) != 2:
            raise ProofRejected("semantic request bodies are not distinct")
        if len(set(responses)) != 2:
            raise ProofRejected("semantic response bodies are not distinct")


class ExactLedgerReceiptVerifier:
    """Reconstruct and verify the exact receipt from canonical durable sources."""

    def __init__(
        self,
        *,
        ledger_path: Path,
        audit_path: Path,
        evidence_root: Path,
        trace: dict[str, Any],
        validator_runtimes: dict[str, ValidatorRuntime],
        durability_keys: dict[str, bytes],
        recovery_ledgers: dict[str, tuple[Path, dict[str, Any]]] | None = None,
        immutable_object_reader: ImmutableObjectReader | None = None,
        allow_isolated_test_sink: bool = False,
    ):
        self.ledger_path = ledger_path
        self.audit_path = audit_path
        self.evidence_root = evidence_root
        self.trace = validate_trace(trace)
        self.validator_runtimes = validator_runtimes
        self.durability_keys = durability_keys
        self.recovery_ledgers = recovery_ledgers or {}
        self.immutable_object_reader = immutable_object_reader
        self.allow_isolated_test_sink = allow_isolated_test_sink

    def _verify_durability(
        self,
        receipt_digest: str,
        audit_events: list[dict[str, Any]],
    ) -> None:
        receipt = DurabilityReceiptStore(self.evidence_root).get(receipt_digest)
        if receipt.digest != receipt_digest or receipt.schema != OFFNODE_RECEIPT_SCHEMA:
            raise ProofRejected("off-node durability receipt digest/schema differs")
        key = self.durability_keys.get(receipt.sink_id)
        if key is None or key_sha256(key) != receipt.sink_key_sha256:
            raise ProofRejected("off-node durability signer is untrusted")
        if not hmac.compare_digest(sign_payload(key, receipt.payload()), receipt.signature_sha256):
            raise ProofRejected("off-node durability signature differs")
        if receipt.sink_class == "isolated-test-double" and not self.allow_isolated_test_sink:
            raise ProofRejected("isolated test sink is forbidden for live admission")
        if receipt.sink_class not in {"isolated-test-double", "immutable-object-store"}:
            raise ProofRejected("off-node durability sink class is unsupported")
        segment = audit_events[: receipt.audit_sequence_end + 1]
        if not segment:
            raise ProofRejected("off-node durability segment is empty")
        content = b"".join((canonical_json(event) + "\n").encode("ascii") for event in segment)
        if (
            receipt.audit_sequence_start != 0
            or receipt.audit_sequence_end >= len(audit_events)
            or receipt.audit_chain_head_sha256 != segment[-1]["record_sha256"]
            or receipt.audit_segment_sha256 != hashlib.sha256(content).hexdigest()
            or receipt.uploaded_bytes != len(content)
            or receipt.persisted_at_ns < audit_events[-1]["observed_monotonic_ns"]
        ):
            raise ProofRejected("off-node durability segment differs from local audit chain")
        if receipt.object_uri.startswith("file://"):
            path = Path(receipt.object_uri.removeprefix("file://"))
            if path.read_bytes() != content or receipt.object_version != receipt.audit_segment_sha256:
                raise ProofRejected("off-node stored bytes/version differ")
        elif receipt.sink_class == "immutable-object-store":
            if self.immutable_object_reader is None:
                raise ProofRejected("immutable off-node bytes cannot be independently read")
            stored = self.immutable_object_reader.get_exact(
                object_uri=receipt.object_uri,
                object_version=receipt.object_version,
            )
            if stored != content:
                raise ProofRejected("immutable off-node stored bytes differ")

    def verify(
        self, receipt: LedgerGateReceipt, expectation: LedgerExpectation
    ) -> VerifiedLedgerGate:
        receipt.validate_self()
        runtime = expectation.runtime
        if expectation.trace_id == self.trace["trace_id"]:
            shared_path = self.ledger_path
            shared_trace = self.trace
        else:
            recovery_source = self.recovery_ledgers.get(expectation.trace_id)
            if recovery_source is None:
                raise ProofRejected("recovery shared ledger/trace is not pinned")
            shared_path, raw_recovery_trace = recovery_source
            shared_trace = validate_trace(raw_recovery_trace)
            if shared_trace["trace_id"] != expectation.trace_id:
                raise ProofRejected("pinned recovery trace identity differs")
        expected = (
            expectation.stage,
            expectation.switch_id,
            expectation.trace_id,
            expectation.request_id,
            expectation.attempt_id,
            expectation.accepted_t0_ns,
            runtime.runtime_generation,
            runtime.launch_operation_id,
            expectation.launch_action_receipt_sha256,
            runtime.model.model_id,
            runtime.model.model_version,
            runtime.model.artifact_sha256,
            expectation.validator.source_sha256,
            expectation.predecessor_receipt_sha256,
        )
        actual = (
            receipt.stage,
            receipt.switch_id,
            receipt.trace_id,
            receipt.request_id,
            receipt.attempt_id,
            receipt.accepted_t0_ns,
            receipt.runtime_generation,
            receipt.launch_operation_id,
            receipt.launch_action_receipt_sha256,
            receipt.model_id,
            receipt.model_version,
            receipt.artifact_sha256,
            receipt.validator_sha256,
            receipt.predecessor_receipt_sha256,
        )
        if actual != expected:
            raise ProofRejected("ledger receipt switch/attempt/generation/model binding differs")
        if file_sha256(shared_path) != receipt.shared_ledger_sha256:
            raise ProofRejected("shared ledger bytes differ from receipt")
        shared_events = load_ledger(shared_path)
        validate_ledger(shared_events, shared_trace)
        attempt_events = [
            event
            for event in shared_events
            if event["request_id"] == expectation.request_id
            and event["attempt_id"] == expectation.attempt_id
        ]
        accepted = [
            event for event in attempt_events if event["event_type"] == "request.accepted"
        ]
        if (
            len(accepted) != 1
            or not attempt_events
            or attempt_events[0] != accepted[0]
            or accepted[0]["observed_monotonic_ns"] != expectation.accepted_t0_ns
            or accepted[0]["data"].get("boundary") != T0_BOUNDARY
        ):
            raise ProofRejected("receipt lacks its exact external request acceptance")
        trace_requests = [
            item
            for item in shared_trace["requests"]
            if item["request_id"] == expectation.request_id
            and item["attempt_id"] == expectation.attempt_id
        ]
        if len(trace_requests) != 1:
            raise ProofRejected("receipt request/attempt is not unique in pinned trace")
        trace_request = trace_requests[0]
        if (
            accepted[0]["data"].get("trace_request_sha256")
            != harness_canonical_sha256(trace_request)
            or (
                trace_request["target"]["model_id"],
                trace_request["target"]["model_version"],
                trace_request["target"]["artifact_sha256"],
            )
            != (
                runtime.model.model_id,
                runtime.model.model_version,
                runtime.model.artifact_sha256,
            )
        ):
            raise ProofRejected("external T0 trace target differs from expected runtime")
        audit_events = AuditChainStore(self.audit_path).load()
        if not audit_events or receipt.audit_sequence_end >= len(audit_events):
            raise ProofRejected("audit segment is incomplete")
        segment_events = audit_events[: receipt.audit_sequence_end + 1]
        audit_content = b"".join(
            (canonical_json(event) + "\n").encode("ascii")
            for event in segment_events
        )
        if (
            receipt.audit_sequence_start != 0
            or receipt.audit_segment_sha256 != hashlib.sha256(audit_content).hexdigest()
            or receipt.audit_chain_head_sha256 != segment_events[-1]["record_sha256"]
        ):
            raise ProofRejected("audit chain receipt differs")
        self._verify_durability(
            receipt.offnode_durability_receipt_sha256, segment_events
        )
        mirrored = [
            event
            for event in segment_events
            if event["event_type"] == "shared.event"
            and event["trace_id"] == expectation.trace_id
            and event["request_id"] == expectation.request_id
            and event["attempt_id"] == expectation.attempt_id
        ]
        if len(mirrored) != len(attempt_events):
            raise ProofRejected("audit chain has a shared-ledger event gap")
        for shared, mirror in zip(attempt_events, mirrored, strict=True):
            if (
                mirror["payload"].get("event") != shared
                or mirror["payload"].get("event_sha256")
                != harness_canonical_sha256(shared)
            ):
                raise ProofRejected("audit chain shared-event mirror differs or is reordered")
        terminal_type = {
            LedgerStage.TARGET_QUALIFIED: "qualification.terminal",
            LedgerStage.TARGET_FAILED: "target.failure.terminal",
            LedgerStage.ROLLBACK_QUALIFIED: "rollback.qualification.terminal",
            LedgerStage.SWITCH_SEALED: "switch.sealed",
        }[receipt.stage]
        terminals = [
            event
            for event in segment_events
            if event["event_type"] == terminal_type
            and event["attempt_id"] == expectation.attempt_id
        ]
        if len(terminals) != 1:
            raise ProofRejected("audit chain lacks exact stage terminal")
        reservations = [
            event
            for event in segment_events
            if event["event_type"] == "launch.reserved"
            and event["attempt_id"] == expectation.attempt_id
        ]
        if len(reservations) != 1:
            raise ProofRejected("audit chain lacks one durable launch reservation")
        reserved = reservations[0]["payload"].get("reservation", {})
        if reservations[0]["payload"].get("reservation_sha256") != canonical_sha256(
            reserved
        ):
            raise ProofRejected("durable launch reservation self-digest differs")
        if (
            reserved.get("switch_id"),
            reserved.get("operation_id"),
            reserved.get("runtime_generation"),
            reserved.get("model", {}).get("model_id"),
            reserved.get("model", {}).get("model_version"),
            reserved.get("model", {}).get("artifact_sha256"),
            reserved.get("authority_sha256"),
        ) != (
            expectation.switch_id,
            runtime.launch_operation_id,
            runtime.runtime_generation,
            runtime.model.model_id,
            runtime.model.model_version,
            runtime.model.artifact_sha256,
            runtime.authority.digest,
        ):
            raise ProofRejected("durable launch reservation differs from expected operation")
        bound = [
            event
            for event in segment_events
            if event["event_type"] == "runtime.bound"
            and event["attempt_id"] == expectation.attempt_id
        ]
        if expectation.launch_action_receipt_sha256 is None:
            if bound:
                raise ProofRejected("unbound failure receipt contains an unexpected runtime")
        elif (
            len(bound) != 1
            or bound[0]["payload"].get("runtime_sha256")
            != (expectation.runtime_identity_sha256_override or runtime.digest)
            or bound[0]["payload"].get("runtime_sha256")
            != canonical_sha256(bound[0]["payload"].get("runtime"))
            or bound[0]["payload"].get("launch_action_receipt_sha256")
            != expectation.launch_action_receipt_sha256
            or bound[0]["payload"].get("launch_action_receipt_sha256")
            != canonical_sha256(
                bound[0]["payload"].get("launch_action_receipt")
            )
        ):
            raise ProofRejected("runtime bind/launch action receipt differs")
        if receipt.stage != LedgerStage.TARGET_FAILED:
            validator = self.validator_runtimes.get(expectation.validator.source_sha256)
            if validator is None or validator.contract != expectation.validator:
                raise ProofRejected("exact pinned validator runtime is unavailable")
            calls = [
                event
                for event in segment_events
                if event["event_type"] == "semantic.call"
                and event["attempt_id"] == expectation.attempt_id
            ]
            intents = [
                event
                for event in segment_events
                if event["event_type"] == "semantic.call.intent"
                and event["attempt_id"] == expectation.attempt_id
            ]
            SwitchLedgerBridge._validate_calls(calls, runtime, validator, intents)
            if bound[0]["sequence"] >= calls[0]["sequence"]:
                raise ProofRejected("semantic calls precede durable runtime bind")
            if (
                receipt.first_semantic_at_ns,
                receipt.second_semantic_at_ns,
            ) != (
                calls[0]["observed_monotonic_ns"],
                calls[1]["observed_monotonic_ns"],
            ):
                raise ProofRejected("semantic timestamps differ from canonical audit calls")
            prior = [
                event
                for event in audit_events
                if event["event_type"] in {"semantic.call", "runtime.restart"}
                and event["attempt_id"] == expectation.attempt_id
                and event["sequence"] < calls[0]["sequence"]
            ]
            if prior:
                raise ProofRejected("prior semantic call or runtime restart exists")
            expected_call_hashes = [call["record_sha256"] for call in calls]
            if receipt.stage in {
                LedgerStage.TARGET_QUALIFIED,
                LedgerStage.ROLLBACK_QUALIFIED,
            } and terminals[0]["payload"].get("call_record_sha256") != expected_call_hashes:
                raise ProofRejected("qualification terminal semantic-call hashes differ")
        else:
            if receipt.first_semantic_at_ns is not None or receipt.second_semantic_at_ns is not None:
                raise ProofRejected("failed target receipt invents semantic calls")
        if receipt.stage in {
            LedgerStage.TARGET_QUALIFIED,
            LedgerStage.ROLLBACK_QUALIFIED,
            LedgerStage.SWITCH_SEALED,
        }:
            if receipt.product_terminal_event_sha256 is None:
                raise ProofRejected("qualified runtime lacks its shared product terminal")
            shared_terminal = [
                event
                for event in shared_events
                if event["request_id"] == expectation.request_id
                and event["attempt_id"] == expectation.attempt_id
                and event["event_type"] == "response.validated"
            ]
            if len(shared_terminal) != 1:
                raise ProofRejected("qualified target lacks shared product terminal")
            if receipt.product_terminal_event_sha256 != harness_canonical_sha256(shared_terminal[0]):
                raise ProofRejected("product terminal digest differs")
            if shared_terminal[0]["data"]["validator_sha256"] != expectation.validator.source_sha256:
                raise ProofRejected("product terminal validator differs")
            if any(
                call["payload"].get("product_terminal_event_sha256")
                != receipt.product_terminal_event_sha256
                for call in calls
            ):
                raise ProofRejected("semantic calls do not join the exact product terminal")
        if receipt.stage == LedgerStage.TARGET_FAILED:
            shared_failure = [
                event
                for event in shared_events
                if event["request_id"] == expectation.request_id
                and event["attempt_id"] == expectation.attempt_id
                and event["event_type"] == "attempt.failed"
            ]
            if len(shared_failure) != 1:
                raise ProofRejected("failed target lacks one shared failure terminal")
            failure_sha = harness_canonical_sha256(shared_failure[0])
            if (
                receipt.product_terminal_event_sha256 != failure_sha
                or terminals[0]["payload"].get("product_terminal_event_sha256")
                != failure_sha
            ):
                raise ProofRejected("B failure audit terminal differs from shared denominator")
        if receipt.stage == LedgerStage.ROLLBACK_QUALIFIED:
            starts = [event for event in segment_events if event["event_type"] == "recovery.started" and event["attempt_id"] == expectation.attempt_id]
            if len(starts) != 1 or starts[0]["payload"]["recovery"]["predecessor_failure_receipt_sha256"] != expectation.predecessor_receipt_sha256:
                raise ProofRejected("rollback trace is not causally linked to B failure")
        if receipt.stage == LedgerStage.SWITCH_SEALED:
            if terminals[0]["payload"].get("qualified_receipt_sha256") != expectation.predecessor_receipt_sha256:
                raise ProofRejected("sealed segment does not link qualified receipt")
        return VerifiedLedgerGate(
            receipt.receipt_sha256,
            receipt.audit_chain_head_sha256,
            receipt.first_semantic_at_ns,
            receipt.second_semantic_at_ns,
        )


__all__ = [name for name in globals() if not name.startswith("_")]
