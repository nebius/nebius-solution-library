#!/usr/bin/env python3
"""Durable, generation-fenced A-to-B drain and GPU reclaim state machine.

The implementation deliberately has no Kubernetes, container-runtime, or cloud
dependency.  Backends turn their observations into the proof types below; the
machine admits a new runtime only after those proofs pass the same invariants.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar


STATE_SCHEMA = "archvteams.nebius.ai/catalog-switch-drain-reclaim-state/v1"
ABSENCE_SCHEMA = "archvteams.nebius.ai/catalog-switch-runtime-absence/v1"
GPU_RELEASE_SCHEMA = "archvteams.nebius.ai/catalog-switch-gpu-release/v1"
SCRUB_SCHEMA = "archvteams.nebius.ai/catalog-switch-gpu-scrub/v1"
SEMANTIC_PROBE_SCHEMA = "archvteams.nebius.ai/catalog-switch-semantic-probe/v1"
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class StateMachineError(RuntimeError):
    """Base class for fail-closed state-machine errors."""


class FenceRejected(StateMachineError):
    """A controller or response used a stale generation."""


class InvalidTransition(StateMachineError):
    """The requested state transition is unsafe from the current state."""


class ProofRejected(StateMachineError):
    """Runtime absence or GPU release evidence is incomplete or mismatched."""


class ConcurrentUpdate(StateMachineError):
    """A durable compare-and-swap repeatedly lost a race."""


class SwitchState(StrEnum):
    IDLE = "IDLE"
    SERVING_A = "SERVING_A"
    DRAINING_A = "DRAINING_A"
    RECLAIMING_A = "RECLAIMING_A"
    GPU_FREE = "GPU_FREE"
    STARTING_B = "STARTING_B"
    SERVING_B = "SERVING_B"
    FAILED = "FAILED"
    RECLAIMING_B = "RECLAIMING_B"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLBACK_SERVING = "ROLLBACK_SERVING"
    QUARANTINED = "QUARANTINED"


class LeaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _require_id(value: str, label: str) -> None:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical identifier")


def _require_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} is not a lowercase SHA-256")


@dataclass(frozen=True)
class ModelRef:
    model_id: str
    model_version: str
    artifact_sha256: str

    def validate(self) -> None:
        _require_id(self.model_id, "model_id")
        _require_id(self.model_version, "model_version")
        _require_digest(self.artifact_sha256, "artifact_sha256")


@dataclass(frozen=True)
class RuntimeIdentity:
    """Immutable identity of the exact workload that must disappear.

    PID alone is not an identity because it can be reused.  Kubernetes runtime
    identities additionally pin Pod UID and full container ID.
    """

    runtime_uid: str
    backend: str
    runtime_generation: int
    model: ModelRef
    gpu_uuid: str
    host_pid: int
    process_start_ticks: int
    cgroup_path: str
    container_id: str | None = None
    pod_uid: str | None = None
    pod_namespace: str | None = None
    pod_name: str | None = None

    def validate(self) -> None:
        _require_id(self.runtime_uid, "runtime_uid")
        if self.backend not in {"node-local", "kubernetes"}:
            raise ValueError("backend must be node-local or kubernetes")
        if self.runtime_generation < 1:
            raise ValueError("runtime_generation must be positive")
        self.model.validate()
        _require_id(self.gpu_uuid, "gpu_uuid")
        if self.host_pid < 1 or self.process_start_ticks < 1:
            raise ValueError("host PID and process start ticks must be positive")
        if not self.cgroup_path.startswith("/") or ".." in Path(self.cgroup_path).parts:
            raise ValueError("cgroup_path must be an absolute traversal-free path")
        if self.backend == "kubernetes":
            for value, label in (
                (self.container_id, "container_id"),
                (self.pod_uid, "pod_uid"),
                (self.pod_namespace, "pod_namespace"),
                (self.pod_name, "pod_name"),
            ):
                if value is None:
                    raise ValueError(f"Kubernetes runtime requires {label}")
                _require_id(value, label)

    @property
    def digest(self) -> str:
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class RuntimeAbsenceProof:
    schema: str
    switch_id: str
    runtime_identity_sha256: str
    runtime_uid: str
    runtime_generation: int
    observer_id: str
    observed_at_ns: int
    process_absent: bool
    cgroup_empty: bool
    container_absent: bool
    pod_absent: bool | None
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    evidence_sha256: str

    def validate_for(self, switch_id: str, runtime: RuntimeIdentity) -> None:
        if self.schema != ABSENCE_SCHEMA:
            raise ProofRejected("runtime absence proof schema is not v1")
        if self.switch_id != switch_id:
            raise ProofRejected("runtime absence proof switch identity differs")
        if self.runtime_identity_sha256 != runtime.digest:
            raise ProofRejected("runtime absence proof targets a different runtime")
        if (self.runtime_uid, self.runtime_generation) != (
            runtime.runtime_uid,
            runtime.runtime_generation,
        ):
            raise ProofRejected("runtime absence proof generation differs")
        _require_id(self.observer_id, "observer_id")
        _require_digest(self.evidence_sha256, "absence evidence_sha256")
        if self.observed_at_ns < 1:
            raise ProofRejected("runtime absence observation time is invalid")
        required = {
            "process_absent": self.process_absent,
            "cgroup_empty": self.cgroup_empty,
            "container_absent": self.container_absent,
            "mounts_absent": self.mounts_absent,
            "namespaces_absent": self.namespaces_absent,
            "credentials_revoked": self.credentials_revoked,
            "kernel_residue_safe": self.kernel_residue_safe,
        }
        if runtime.backend == "kubernetes":
            required["pod_absent"] = self.pod_absent is True
        elif self.pod_absent is not None:
            raise ProofRejected("node-local absence proof must not invent a Pod result")
        failed = sorted(key for key, value in required.items() if value is not True)
        if failed:
            raise ProofRejected(f"runtime absence proof is incomplete: {failed}")


@dataclass(frozen=True)
class ScrubReceipt:
    schema: str
    switch_id: str
    runtime_identity_sha256: str
    gpu_uuid: str
    method: str
    bytes_scrubbed: int
    total_memory_bytes: int
    started_at_ns: int
    finished_at_ns: int
    succeeded: bool
    evidence_sha256: str

    def validate_for(self, switch_id: str, runtime: RuntimeIdentity) -> None:
        if self.schema != SCRUB_SCHEMA:
            raise ProofRejected("GPU scrub receipt schema is not v1")
        if self.switch_id != switch_id or self.runtime_identity_sha256 != runtime.digest:
            raise ProofRejected("GPU scrub receipt targets a different switch/runtime")
        if self.gpu_uuid != runtime.gpu_uuid:
            raise ProofRejected("GPU scrub receipt targets a different GPU")
        if self.method not in {"full-vram-zero", "gpu-reset", "mig-recreate"}:
            raise ProofRejected("GPU scrub method is not approved")
        if not self.succeeded or self.started_at_ns < 1 or self.finished_at_ns <= self.started_at_ns:
            raise ProofRejected("GPU scrub did not complete successfully")
        if self.total_memory_bytes < 1 or self.bytes_scrubbed < 0:
            raise ProofRejected("GPU scrub byte accounting is invalid")
        if self.method == "full-vram-zero" and self.bytes_scrubbed < self.total_memory_bytes:
            raise ProofRejected("full-VRAM scrub did not cover total GPU memory")
        _require_digest(self.evidence_sha256, "scrub evidence_sha256")


@dataclass(frozen=True)
class NvmlObservation:
    observed_at_ns: int
    gpu_uuid: str
    compute_pids: tuple[int, ...]
    graphics_pids: tuple[int, ...]
    memory_used_bytes: int
    memory_total_bytes: int

    def validate(self, gpu_uuid: str) -> None:
        if self.observed_at_ns < 1 or self.gpu_uuid != gpu_uuid:
            raise ProofRejected("NVML observation identity/time differs")
        if self.memory_total_bytes < 1:
            raise ProofRejected("NVML total memory is invalid")
        if not 0 <= self.memory_used_bytes <= self.memory_total_bytes:
            raise ProofRejected("NVML used memory is invalid")
        if any(pid < 1 for pid in (*self.compute_pids, *self.graphics_pids)):
            raise ProofRejected("NVML observation contains an invalid PID")
        if len(set(self.compute_pids)) != len(self.compute_pids) or len(
            set(self.graphics_pids)
        ) != len(self.graphics_pids):
            raise ProofRejected("NVML observation contains duplicate PIDs")


@dataclass(frozen=True)
class GpuReleaseProof:
    schema: str
    switch_id: str
    runtime_identity_sha256: str
    gpu_uuid: str
    observer_id: str
    idle_baseline_bytes: int
    observations: tuple[NvmlObservation, ...]
    scrub: ScrubReceipt
    evidence_sha256: str

    def validate_for(
        self,
        switch_id: str,
        runtime: RuntimeIdentity,
        *,
        expected_idle_baseline_bytes: int | None = None,
    ) -> None:
        if self.schema != GPU_RELEASE_SCHEMA:
            raise ProofRejected("GPU release proof schema is not v1")
        if self.switch_id != switch_id or self.runtime_identity_sha256 != runtime.digest:
            raise ProofRejected("GPU release proof targets a different switch/runtime")
        if self.gpu_uuid != runtime.gpu_uuid:
            raise ProofRejected("GPU release proof targets a different GPU")
        _require_id(self.observer_id, "GPU observer_id")
        _require_digest(self.evidence_sha256, "GPU release evidence_sha256")
        if self.idle_baseline_bytes < 0:
            raise ProofRejected("GPU idle baseline is invalid")
        if (
            expected_idle_baseline_bytes is not None
            and self.idle_baseline_bytes != expected_idle_baseline_bytes
        ):
            raise ProofRejected("GPU idle baseline differs from the node's pinned baseline")
        self.scrub.validate_for(switch_id, runtime)
        if len(self.observations) < 2:
            raise ProofRejected("GPU release requires two consecutive NVML observations")
        previous = self.scrub.finished_at_ns
        for observation in self.observations:
            observation.validate(runtime.gpu_uuid)
            if observation.observed_at_ns <= previous:
                raise ProofRejected("NVML observations must follow scrub in strict order")
            previous = observation.observed_at_ns
            if observation.compute_pids or observation.graphics_pids:
                raise ProofRejected("NVML still reports GPU processes")
            if observation.memory_used_bytes > self.idle_baseline_bytes:
                raise ProofRejected("NVML memory remains above the pinned idle baseline")


@dataclass(frozen=True)
class SemanticInferenceReceipt:
    sequence: int
    request_sha256: str
    response_sha256: str
    complete_body: bool
    semantically_valid: bool
    observed_at_ns: int

    def validate(self) -> None:
        if self.sequence not in {1, 2}:
            raise ProofRejected("semantic inference sequence must be 1 or 2")
        _require_digest(self.request_sha256, "request_sha256")
        _require_digest(self.response_sha256, "response_sha256")
        if self.complete_body is not True or self.semantically_valid is not True:
            raise ProofRejected("semantic inference is incomplete or invalid")
        if self.observed_at_ns < 1:
            raise ProofRejected("semantic inference observation time is invalid")


@dataclass(frozen=True)
class SemanticProbeProof:
    schema: str
    switch_id: str
    runtime_identity_sha256: str
    runtime_generation: int
    model_id: str
    model_version: str
    validator_sha256: str
    product_terminal_event_sha256: str
    inferences: tuple[SemanticInferenceReceipt, ...]

    @property
    def observed_at_ns(self) -> int:
        return self.inferences[-1].observed_at_ns if self.inferences else 0

    @property
    def first_valid_response_at_ns(self) -> int:
        return self.inferences[0].observed_at_ns if self.inferences else 0

    def validate_for(self, switch_id: str, runtime: RuntimeIdentity) -> None:
        if self.schema != SEMANTIC_PROBE_SCHEMA:
            raise ProofRejected("semantic probe proof schema is not v1")
        if self.switch_id != switch_id or self.runtime_identity_sha256 != runtime.digest:
            raise ProofRejected("semantic probe targets a different switch/runtime")
        if self.runtime_generation != runtime.runtime_generation:
            raise ProofRejected("semantic probe runtime generation differs")
        if (self.model_id, self.model_version) != (
            runtime.model.model_id,
            runtime.model.model_version,
        ):
            raise ProofRejected("semantic probe returned the wrong model")
        _require_digest(self.validator_sha256, "validator_sha256")
        _require_digest(
            self.product_terminal_event_sha256, "product_terminal_event_sha256"
        )
        if len(self.inferences) != 2:
            raise ProofRejected("B admission requires exactly two semantic inferences")
        for receipt in self.inferences:
            receipt.validate()
        if [receipt.sequence for receipt in self.inferences] != [1, 2]:
            raise ProofRejected("semantic inferences are not in sequence order")
        if self.inferences[0].request_sha256 == self.inferences[1].request_sha256:
            raise ProofRejected("the two semantic inference inputs must be distinct")
        if self.inferences[1].observed_at_ns <= self.inferences[0].observed_at_ns:
            raise ProofRejected("semantic inference observations are not ordered")


@dataclass(frozen=True)
class ControllerFence:
    controller_id: str
    generation: int


@dataclass
class RequestLease:
    lease_id: str
    request_id: str
    attempt_id: str
    model: ModelRef
    runtime_generation: int
    accepted_at_ns: int
    deadline_ns: int
    status: LeaseStatus = LeaseStatus.ACTIVE
    terminal_reason: str | None = None


@dataclass
class SwitchRecord:
    switch_id: str
    request_id: str
    attempt_id: str
    source_model: ModelRef
    target_model: ModelRef
    source_runtime_uid: str
    source_runtime_generation: int
    accepted_t0_ns: int
    initiated_at_ns: int
    drain_deadline_ns: int
    target_runtime_generation: int | None = None
    cancelled: bool = False
    failure_reason: str | None = None
    reclaim_proof_sha256: str | None = None
    semantic_probe_sha256: str | None = None
    terminal_ledger_sha256: str | None = None


@dataclass
class TransitionRecord:
    revision: int
    at_ns: int
    controller_generation: int
    operation: str
    from_state: str
    to_state: str
    detail_sha256: str
    previous_sha256: str
    record_sha256: str


@dataclass
class MachineSnapshot:
    schema: str
    revision: int
    node_id: str
    gpu_uuid: str
    gpu_idle_baseline_bytes: int
    state: SwitchState
    controller_id: str | None
    controller_generation: int
    next_runtime_generation: int
    admission_open: bool
    serving_model: ModelRef | None
    active_runtime: RuntimeIdentity | None
    starting_model: ModelRef | None
    starting_generation: int | None
    active_switch: SwitchRecord | None
    request_leases: dict[str, RequestLease] = field(default_factory=dict)
    retired_runtime_generations: list[int] = field(default_factory=list)
    last_reclaim_proof_sha256: str | None = None
    last_semantic_probe_sha256: str | None = None
    last_terminal_ledger_sha256: str | None = None
    last_completed_switch_id: str | None = None
    quarantine_reason: str | None = None
    transitions: list[TransitionRecord] = field(default_factory=list)

    @classmethod
    def initial(
        cls, node_id: str, gpu_uuid: str, *, gpu_idle_baseline_bytes: int = 0
    ) -> "MachineSnapshot":
        _require_id(node_id, "node_id")
        _require_id(gpu_uuid, "gpu_uuid")
        if gpu_idle_baseline_bytes < 0:
            raise ValueError("GPU idle baseline cannot be negative")
        return cls(
            schema=STATE_SCHEMA,
            revision=0,
            node_id=node_id,
            gpu_uuid=gpu_uuid,
            gpu_idle_baseline_bytes=gpu_idle_baseline_bytes,
            state=SwitchState.IDLE,
            controller_id=None,
            controller_generation=0,
            next_runtime_generation=1,
            admission_open=False,
            serving_model=None,
            active_runtime=None,
            starting_model=None,
            starting_generation=None,
            active_switch=None,
        )


def _model_from(value: dict[str, Any] | None) -> ModelRef | None:
    return None if value is None else ModelRef(**value)


def _runtime_from(value: dict[str, Any] | None) -> RuntimeIdentity | None:
    if value is None:
        return None
    payload = dict(value)
    payload["model"] = ModelRef(**payload["model"])
    return RuntimeIdentity(**payload)


def snapshot_to_dict(snapshot: MachineSnapshot) -> dict[str, Any]:
    value = asdict(snapshot)
    value["state"] = snapshot.state.value
    for lease_id, lease in snapshot.request_leases.items():
        value["request_leases"][lease_id]["status"] = lease.status.value
    return value


def snapshot_from_dict(value: dict[str, Any]) -> MachineSnapshot:
    payload = copy.deepcopy(value)
    if payload.get("schema") != STATE_SCHEMA:
        raise StateMachineError("state snapshot schema is not v1")
    payload["state"] = SwitchState(payload["state"])
    payload["serving_model"] = _model_from(payload["serving_model"])
    payload["active_runtime"] = _runtime_from(payload["active_runtime"])
    payload["starting_model"] = _model_from(payload["starting_model"])
    if payload["active_switch"] is not None:
        switch = dict(payload["active_switch"])
        switch["source_model"] = ModelRef(**switch["source_model"])
        switch["target_model"] = ModelRef(**switch["target_model"])
        payload["active_switch"] = SwitchRecord(**switch)
    leases: dict[str, RequestLease] = {}
    for lease_id, raw in payload["request_leases"].items():
        lease = dict(raw)
        lease["model"] = ModelRef(**lease["model"])
        lease["status"] = LeaseStatus(lease["status"])
        leases[lease_id] = RequestLease(**lease)
    payload["request_leases"] = leases
    payload["transitions"] = [TransitionRecord(**item) for item in payload["transitions"]]
    return MachineSnapshot(**payload)


class StateStore(Protocol):
    def load(self) -> MachineSnapshot: ...

    def compare_and_swap(
        self, expected_revision: int, replacement: MachineSnapshot
    ) -> bool: ...


class InMemoryStateStore:
    def __init__(self, initial: MachineSnapshot):
        self._snapshot = copy.deepcopy(initial)
        self._lock = threading.Lock()

    def load(self) -> MachineSnapshot:
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def compare_and_swap(
        self, expected_revision: int, replacement: MachineSnapshot
    ) -> bool:
        with self._lock:
            if self._snapshot.revision != expected_revision:
                return False
            self._snapshot = copy.deepcopy(replacement)
            return True


class JsonFileStateStore:
    """Canonical JSON store with flock, no-symlink checks, fsync, and CAS."""

    def __init__(self, path: Path, initial: MachineSnapshot | None = None):
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")
        if initial is not None and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_atomic(initial)

    def _check_paths(self) -> None:
        if self.path.exists() and (self.path.is_symlink() or not self.path.is_file()):
            raise StateMachineError("state path must be a regular non-symlink file")
        if self.lock_path.exists() and self.lock_path.is_symlink():
            raise StateMachineError("state lock path cannot be a symlink")

    def _read_unlocked(self) -> MachineSnapshot:
        self._check_paths()
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateMachineError(f"cannot read state: {type(exc).__name__}") from exc
        if not raw.endswith("\n") or raw.count("\n") != 1:
            raise StateMachineError("state must be one canonical newline-terminated JSON object")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise StateMachineError("state is not valid JSON") from exc
        if raw != canonical_json(value) + "\n":
            raise StateMachineError("state is not canonical JSON")
        return snapshot_from_dict(value)

    def _write_atomic(self, snapshot: MachineSnapshot) -> None:
        self._check_paths()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(canonical_json(snapshot_to_dict(snapshot)) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _locked(self) -> tuple[int, Any]:
        self._check_paths()
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        stream = os.fdopen(descriptor, "r+")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        return descriptor, stream

    def load(self) -> MachineSnapshot:
        _, lock = self._locked()
        try:
            return self._read_unlocked()
        finally:
            lock.close()

    def compare_and_swap(
        self, expected_revision: int, replacement: MachineSnapshot
    ) -> bool:
        _, lock = self._locked()
        try:
            current = self._read_unlocked()
            if current.revision != expected_revision:
                return False
            self._write_atomic(replacement)
            return True
        finally:
            lock.close()


T = TypeVar("T")


class DrainReclaimStateMachine:
    """Reference state machine; every mutation is durable and generation fenced."""

    def __init__(
        self,
        store: StateStore,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        max_cas_attempts: int = 32,
    ):
        self.store = store
        self.clock_ns = clock_ns
        self.max_cas_attempts = max_cas_attempts

    def snapshot(self) -> MachineSnapshot:
        snapshot = self.store.load()
        self._validate_snapshot(snapshot)
        return snapshot

    def _commit(
        self,
        operation: str,
        fence: ControllerFence | None,
        mutate: Callable[[MachineSnapshot, int], T],
    ) -> T:
        for _ in range(self.max_cas_attempts):
            original = self.store.load()
            self._validate_snapshot(original)
            if fence is not None and (
                original.controller_id != fence.controller_id
                or original.controller_generation != fence.generation
            ):
                raise FenceRejected("controller generation is stale")
            working = copy.deepcopy(original)
            now_ns = self.clock_ns()
            if now_ns < 1:
                raise StateMachineError("monotonic clock returned an invalid value")
            result = mutate(working, now_ns)
            from_state = original.state.value
            working.revision = original.revision + 1
            detail = snapshot_to_dict(working)
            detail["transitions"] = []
            transition_payload = {
                "revision": working.revision,
                "at_ns": now_ns,
                "controller_generation": working.controller_generation,
                "operation": operation,
                "from_state": from_state,
                "to_state": working.state.value,
                "detail_sha256": canonical_sha256(detail),
                "previous_sha256": (
                    original.transitions[-1].record_sha256
                    if original.transitions
                    else "0" * 64
                ),
            }
            working.transitions.append(
                TransitionRecord(
                    **transition_payload,
                    record_sha256=canonical_sha256(transition_payload),
                )
            )
            self._validate_snapshot(working)
            if self.store.compare_and_swap(original.revision, working):
                return result
        raise ConcurrentUpdate("state compare-and-swap did not converge")

    def claim_controller(self, controller_id: str) -> ControllerFence:
        _require_id(controller_id, "controller_id")

        def mutate(snapshot: MachineSnapshot, _: int) -> ControllerFence:
            snapshot.controller_generation += 1
            snapshot.controller_id = controller_id
            return ControllerFence(controller_id, snapshot.controller_generation)

        return self._commit("claim_controller", None, mutate)

    def install_serving_a(
        self, fence: ControllerFence, runtime: RuntimeIdentity
    ) -> MachineSnapshot:
        runtime.validate()

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            if snapshot.state != SwitchState.IDLE:
                raise InvalidTransition("initial runtime can only be installed from IDLE")
            if runtime.gpu_uuid != snapshot.gpu_uuid:
                raise InvalidTransition("runtime is assigned to a different GPU")
            if runtime.runtime_generation != snapshot.next_runtime_generation:
                raise FenceRejected("initial runtime generation was not reserved by this node")
            snapshot.next_runtime_generation += 1
            snapshot.state = SwitchState.SERVING_A
            snapshot.serving_model = runtime.model
            snapshot.active_runtime = runtime
            snapshot.admission_open = True

        self._commit("install_serving_a", fence, mutate)
        return self.snapshot()

    def admit_request(
        self,
        fence: ControllerFence,
        *,
        lease_id: str,
        request_id: str,
        attempt_id: str,
        model: ModelRef,
        deadline_ns: int,
    ) -> RequestLease:
        for value, label in (
            (lease_id, "lease_id"),
            (request_id, "request_id"),
            (attempt_id, "attempt_id"),
        ):
            _require_id(value, label)
        model.validate()

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> RequestLease:
            existing = snapshot.request_leases.get(lease_id)
            if existing is not None:
                if (
                    existing.request_id,
                    existing.attempt_id,
                    existing.model,
                    existing.deadline_ns,
                ) != (request_id, attempt_id, model, deadline_ns):
                    raise InvalidTransition("lease ID was reused with different content")
                return copy.deepcopy(existing)
            if not snapshot.admission_open or snapshot.state not in {
                SwitchState.SERVING_A,
                SwitchState.SERVING_B,
                SwitchState.ROLLBACK_SERVING,
            }:
                raise InvalidTransition("admission is closed")
            if snapshot.active_runtime is None or snapshot.serving_model != model:
                raise FenceRejected("request model does not match the serving generation")
            if deadline_ns <= now_ns:
                raise InvalidTransition("request lease deadline is not in the future")
            lease = RequestLease(
                lease_id=lease_id,
                request_id=request_id,
                attempt_id=attempt_id,
                model=model,
                runtime_generation=snapshot.active_runtime.runtime_generation,
                accepted_at_ns=now_ns,
                deadline_ns=deadline_ns,
            )
            snapshot.request_leases[lease_id] = lease
            return copy.deepcopy(lease)

        return self._commit("admit_request", fence, mutate)

    def complete_response(
        self,
        fence: ControllerFence,
        *,
        lease_id: str,
        runtime_generation: int,
        model: ModelRef,
    ) -> RequestLease:
        model.validate()

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> RequestLease:
            lease = snapshot.request_leases.get(lease_id)
            if lease is None:
                raise FenceRejected("response lease is unknown")
            if lease.status != LeaseStatus.ACTIVE:
                raise FenceRejected("response lease is already terminal")
            if runtime_generation in snapshot.retired_runtime_generations:
                raise FenceRejected("response runtime generation is retired")
            if (
                lease.runtime_generation != runtime_generation
                or lease.model != model
                or snapshot.active_runtime is None
                or snapshot.active_runtime.runtime_generation != runtime_generation
                or snapshot.active_runtime.model != model
            ):
                raise FenceRejected("response model/runtime generation is stale or mixed")
            if now_ns > lease.deadline_ns:
                lease.status = LeaseStatus.TIMED_OUT
                lease.terminal_reason = "response observed after request lease deadline"
                raise FenceRejected("response arrived after its lease deadline")
            lease.status = LeaseStatus.COMPLETED
            lease.terminal_reason = "complete response admitted by generation fence"
            return copy.deepcopy(lease)

        return self._commit("complete_response", fence, mutate)

    def cancel_request(
        self, fence: ControllerFence, *, lease_id: str, reason: str
    ) -> RequestLease:
        if not reason:
            raise ValueError("cancellation reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> RequestLease:
            lease = snapshot.request_leases.get(lease_id)
            if lease is None:
                raise InvalidTransition("request lease is unknown")
            if lease.status == LeaseStatus.ACTIVE:
                lease.status = LeaseStatus.CANCELLED
                lease.terminal_reason = reason
            return copy.deepcopy(lease)

        return self._commit("cancel_request", fence, mutate)

    def begin_switch(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        request_id: str,
        attempt_id: str,
        target: ModelRef,
        accepted_t0_ns: int,
        drain_timeout_ns: int,
    ) -> SwitchRecord:
        for value, label in (
            (switch_id, "switch_id"),
            (request_id, "request_id"),
            (attempt_id, "attempt_id"),
        ):
            _require_id(value, label)
        target.validate()
        if accepted_t0_ns < 1 or drain_timeout_ns < 1:
            raise ValueError("T0 and drain timeout must be positive")

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> SwitchRecord:
            existing = snapshot.active_switch
            if existing is not None and existing.switch_id == switch_id:
                if (
                    existing.request_id,
                    existing.attempt_id,
                    existing.target_model,
                    existing.accepted_t0_ns,
                ) != (request_id, attempt_id, target, accepted_t0_ns):
                    raise InvalidTransition("switch ID was reused with different content")
                return copy.deepcopy(existing)
            if existing is not None or snapshot.state not in {
                SwitchState.SERVING_A,
                SwitchState.SERVING_B,
                SwitchState.ROLLBACK_SERVING,
            }:
                raise InvalidTransition("another switch is active or node is not serving")
            if not snapshot.admission_open or snapshot.active_runtime is None:
                raise InvalidTransition("serving state lacks an admitted runtime")
            if target == snapshot.serving_model:
                raise InvalidTransition("A-to-B switch requires a distinct target model")
            if now_ns < accepted_t0_ns:
                raise InvalidTransition("switch work cannot precede external request T0")
            source = snapshot.active_runtime
            switch = SwitchRecord(
                switch_id=switch_id,
                request_id=request_id,
                attempt_id=attempt_id,
                source_model=source.model,
                target_model=target,
                source_runtime_uid=source.runtime_uid,
                source_runtime_generation=source.runtime_generation,
                accepted_t0_ns=accepted_t0_ns,
                initiated_at_ns=now_ns,
                drain_deadline_ns=now_ns + drain_timeout_ns,
            )
            snapshot.active_switch = switch
            snapshot.state = SwitchState.DRAINING_A
            snapshot.admission_open = False
            return copy.deepcopy(switch)

        return self._commit("begin_switch", fence, mutate)

    def cancel_switch(
        self, fence: ControllerFence, *, switch_id: str, reason: str
    ) -> SwitchRecord:
        if not reason:
            raise ValueError("switch cancellation reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> SwitchRecord:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state in {
                SwitchState.SERVING_B,
                SwitchState.ROLLBACK_SERVING,
            }:
                raise InvalidTransition("an accepted serving generation cannot be cancelled")
            switch.cancelled = True
            switch.failure_reason = reason
            snapshot.admission_open = False
            return copy.deepcopy(switch)

        return self._commit("cancel_switch", fence, mutate)

    def advance_drain(
        self, fence: ControllerFence, *, switch_id: str
    ) -> tuple[bool, tuple[str, ...]]:
        """Advance to reclaim when drained; timeout any remaining active leases."""

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> tuple[bool, tuple[str, ...]]:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state == SwitchState.RECLAIMING_A:
                return True, ()
            if snapshot.state != SwitchState.DRAINING_A:
                raise InvalidTransition("drain can only advance from DRAINING_A")
            active = [
                lease
                for lease in snapshot.request_leases.values()
                if lease.status == LeaseStatus.ACTIVE
                and lease.runtime_generation == switch.source_runtime_generation
            ]
            timed_out: list[str] = []
            if active and now_ns < switch.drain_deadline_ns:
                return False, ()
            for lease in active:
                lease.status = LeaseStatus.TIMED_OUT
                lease.terminal_reason = "A drain deadline expired; kill escalation required"
                timed_out.append(lease.lease_id)
            snapshot.retired_runtime_generations.append(switch.source_runtime_generation)
            snapshot.retired_runtime_generations = sorted(
                set(snapshot.retired_runtime_generations)
            )
            snapshot.state = SwitchState.RECLAIMING_A
            snapshot.admission_open = False
            return True, tuple(sorted(timed_out))

        return self._commit("advance_drain", fence, mutate)

    def record_reclaim(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        absence: RuntimeAbsenceProof,
        gpu_release: GpuReleaseProof,
    ) -> str:
        def mutate(snapshot: MachineSnapshot, _: int) -> str:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {
                SwitchState.RECLAIMING_A,
                SwitchState.RECLAIMING_B,
            }:
                raise InvalidTransition("reclaim proof is not expected in the current state")
            runtime = snapshot.active_runtime
            if runtime is None:
                raise ProofRejected("no exact runtime is registered for reclaim")
            active = [
                lease.lease_id
                for lease in snapshot.request_leases.values()
                if lease.status == LeaseStatus.ACTIVE
                and lease.runtime_generation == runtime.runtime_generation
            ]
            if active:
                raise ProofRejected(f"runtime still owns active request leases: {sorted(active)}")
            absence.validate_for(switch_id, runtime)
            gpu_release.validate_for(
                switch_id,
                runtime,
                expected_idle_baseline_bytes=snapshot.gpu_idle_baseline_bytes,
            )
            reclaim_transitions = [
                transition
                for transition in snapshot.transitions
                if transition.to_state
                in {SwitchState.RECLAIMING_A.value, SwitchState.RECLAIMING_B.value}
            ]
            if not reclaim_transitions:
                raise ProofRejected("reclaim proof has no durable reclaim transition")
            reclaim_started_at_ns = reclaim_transitions[-1].at_ns
            if (
                absence.observed_at_ns <= reclaim_started_at_ns
                or gpu_release.scrub.started_at_ns <= reclaim_started_at_ns
            ):
                raise ProofRejected("reclaim evidence predates the durable reclaim transition")
            if absence.observed_at_ns >= gpu_release.observations[0].observed_at_ns:
                raise ProofRejected("runtime absence must be observed before final NVML samples")
            proof_digest = canonical_sha256(
                {"absence": asdict(absence), "gpu_release": asdict(gpu_release)}
            )
            snapshot.active_runtime = None
            snapshot.serving_model = None
            snapshot.starting_model = None
            snapshot.starting_generation = None
            snapshot.admission_open = False
            snapshot.state = SwitchState.GPU_FREE
            snapshot.last_reclaim_proof_sha256 = proof_digest
            switch.reclaim_proof_sha256 = proof_digest
            return proof_digest

        return self._commit("record_reclaim", fence, mutate)

    def reject_reclaim_proof(
        self, fence: ControllerFence, *, switch_id: str, reason: str
    ) -> None:
        if not reason:
            raise ValueError("quarantine reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            self._require_switch(snapshot, switch_id)
            if snapshot.state not in {
                SwitchState.RECLAIMING_A,
                SwitchState.RECLAIMING_B,
            }:
                raise InvalidTransition("no reclaim is pending")
            snapshot.state = SwitchState.QUARANTINED
            snapshot.admission_open = False
            snapshot.quarantine_reason = reason

        self._commit("reject_reclaim_proof", fence, mutate)

    def begin_start_b(
        self, fence: ControllerFence, *, switch_id: str
    ) -> int:
        def mutate(snapshot: MachineSnapshot, _: int) -> int:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.GPU_FREE:
                raise InvalidTransition("B can start only from a proved GPU_FREE state")
            if switch.cancelled or switch.failure_reason is not None:
                raise InvalidTransition("cancelled/failed switch cannot start B")
            if snapshot.active_runtime is not None or snapshot.last_reclaim_proof_sha256 is None:
                raise ProofRejected("B admission lacks exact reclaim proof")
            generation = snapshot.next_runtime_generation
            snapshot.next_runtime_generation += 1
            snapshot.starting_generation = generation
            snapshot.starting_model = switch.target_model
            switch.target_runtime_generation = generation
            snapshot.state = SwitchState.STARTING_B
            return generation

        return self._commit("begin_start_b", fence, mutate)

    def bind_starting_runtime(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        runtime: RuntimeIdentity,
    ) -> None:
        runtime.validate()

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.STARTING_B, SwitchState.ROLLING_BACK}:
                raise InvalidTransition("no target runtime launch is pending")
            if snapshot.active_runtime is not None:
                if snapshot.active_runtime == runtime:
                    return
                raise InvalidTransition("a second runtime allocation was attempted")
            if (
                runtime.gpu_uuid != snapshot.gpu_uuid
                or runtime.runtime_generation != snapshot.starting_generation
                or runtime.model != snapshot.starting_model
            ):
                raise FenceRejected("launched runtime differs from reserved model/generation/GPU")
            if snapshot.state == SwitchState.STARTING_B and runtime.model != switch.target_model:
                raise FenceRejected("B launch returned the wrong model")
            snapshot.active_runtime = runtime

        self._commit("bind_starting_runtime", fence, mutate)

    def accept_b(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        semantic_probe: SemanticProbeProof,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.STARTING_B or snapshot.active_runtime is None:
                raise InvalidTransition("B cannot be admitted before its exact runtime is bound")
            runtime = snapshot.active_runtime
            if switch.cancelled or switch.failure_reason is not None:
                raise InvalidTransition("cancelled/failed B cannot be admitted")
            if (
                runtime.model != switch.target_model
                or runtime.runtime_generation != switch.target_runtime_generation
            ):
                raise FenceRejected("B semantic acceptance targets a stale generation")
            semantic_probe.validate_for(switch_id, runtime)
            bound_at = snapshot.transitions[-1].at_ns if snapshot.transitions else 0
            if semantic_probe.observed_at_ns <= bound_at:
                raise ProofRejected("semantic probe predates the bound runtime generation")
            switch.semantic_probe_sha256 = canonical_sha256(asdict(semantic_probe))
            snapshot.serving_model = runtime.model
            snapshot.starting_model = None
            snapshot.starting_generation = None
            snapshot.admission_open = True
            snapshot.state = SwitchState.SERVING_B

        self._commit("accept_b", fence, mutate)

    def fail_start(
        self, fence: ControllerFence, *, switch_id: str, reason: str
    ) -> None:
        if not reason:
            raise ValueError("start failure reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.STARTING_B, SwitchState.ROLLING_BACK}:
                raise InvalidTransition("no runtime start is pending")
            switch.failure_reason = reason
            snapshot.admission_open = False
            if snapshot.active_runtime is None:
                snapshot.starting_model = None
                snapshot.starting_generation = None
                snapshot.state = SwitchState.FAILED
            else:
                snapshot.retired_runtime_generations.append(
                    snapshot.active_runtime.runtime_generation
                )
                snapshot.retired_runtime_generations = sorted(
                    set(snapshot.retired_runtime_generations)
                )
                snapshot.state = SwitchState.RECLAIMING_B

        self._commit("fail_start", fence, mutate)

    def mark_failed(
        self, fence: ControllerFence, *, switch_id: str, reason: str
    ) -> None:
        if not reason:
            raise ValueError("failure reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.GPU_FREE:
                raise InvalidTransition("failure can be sealed only from GPU_FREE")
            switch.failure_reason = reason
            snapshot.state = SwitchState.FAILED

        self._commit("mark_failed", fence, mutate)

    def begin_rollback(
        self, fence: ControllerFence, *, switch_id: str
    ) -> int:
        def mutate(snapshot: MachineSnapshot, _: int) -> int:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.GPU_FREE, SwitchState.FAILED}:
                raise InvalidTransition("rollback requires a clean GPU and failed/cancelled switch")
            if not (switch.cancelled or switch.failure_reason is not None):
                raise InvalidTransition("successful switch cannot enter rollback")
            if snapshot.active_runtime is not None or snapshot.last_reclaim_proof_sha256 is None:
                raise ProofRejected("rollback lacks a clean GPU receipt")
            generation = snapshot.next_runtime_generation
            snapshot.next_runtime_generation += 1
            snapshot.starting_generation = generation
            snapshot.starting_model = switch.source_model
            snapshot.state = SwitchState.ROLLING_BACK
            return generation

        return self._commit("begin_rollback", fence, mutate)

    def accept_rollback(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        semantic_probe: SemanticProbeProof,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.ROLLING_BACK or snapshot.active_runtime is None:
                raise InvalidTransition("rollback runtime is not ready for acceptance")
            if snapshot.active_runtime.model != switch.source_model:
                raise FenceRejected("rollback restored the wrong model")
            semantic_probe.validate_for(switch_id, snapshot.active_runtime)
            bound_at = snapshot.transitions[-1].at_ns if snapshot.transitions else 0
            if semantic_probe.observed_at_ns <= bound_at:
                raise ProofRejected("rollback semantic probe predates bound runtime")
            switch.semantic_probe_sha256 = canonical_sha256(asdict(semantic_probe))
            snapshot.serving_model = switch.source_model
            snapshot.starting_model = None
            snapshot.starting_generation = None
            snapshot.admission_open = True
            snapshot.state = SwitchState.ROLLBACK_SERVING

        self._commit("accept_rollback", fence, mutate)

    def seal_switch(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        terminal_ledger_sha256: str,
    ) -> None:
        """Seal terminal audit work and make the serving runtime the next A.

        SERVING_B and ROLLBACK_SERVING remain explicit observable states until
        the caller has durably written its product terminal/accounting records.
        Sealing then releases the switch ID without changing the runtime or
        reopening anything that was not already admitted.
        """

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {
                SwitchState.SERVING_B,
                SwitchState.ROLLBACK_SERVING,
            }:
                raise InvalidTransition("only an accepted serving switch can be sealed")
            _require_digest(terminal_ledger_sha256, "terminal_ledger_sha256")
            if switch.semantic_probe_sha256 is None:
                raise ProofRejected("serving switch lacks a semantic probe receipt")
            switch.terminal_ledger_sha256 = terminal_ledger_sha256
            snapshot.last_semantic_probe_sha256 = switch.semantic_probe_sha256
            snapshot.last_terminal_ledger_sha256 = terminal_ledger_sha256
            snapshot.last_completed_switch_id = switch.switch_id
            snapshot.active_switch = None
            snapshot.state = SwitchState.SERVING_A

        self._commit("seal_switch", fence, mutate)

    @staticmethod
    def _require_switch(snapshot: MachineSnapshot, switch_id: str) -> SwitchRecord:
        if snapshot.active_switch is None or snapshot.active_switch.switch_id != switch_id:
            raise FenceRejected("switch identity is stale or unknown")
        return snapshot.active_switch

    @staticmethod
    def _validate_snapshot(snapshot: MachineSnapshot) -> None:
        if snapshot.schema != STATE_SCHEMA or snapshot.revision < 0:
            raise StateMachineError("snapshot schema/revision is invalid")
        _require_id(snapshot.node_id, "snapshot.node_id")
        _require_id(snapshot.gpu_uuid, "snapshot.gpu_uuid")
        if snapshot.controller_generation < 0 or snapshot.next_runtime_generation < 1:
            raise StateMachineError("snapshot generation counters are invalid")
        if snapshot.gpu_idle_baseline_bytes < 0:
            raise StateMachineError("snapshot GPU idle baseline is invalid")
        if (snapshot.controller_id is None) != (snapshot.controller_generation == 0):
            raise StateMachineError("controller identity/generation is inconsistent")
        if snapshot.active_runtime is not None:
            snapshot.active_runtime.validate()
            if snapshot.active_runtime.gpu_uuid != snapshot.gpu_uuid:
                raise StateMachineError("active runtime uses a different GPU")
        serving = {
            SwitchState.SERVING_A,
            SwitchState.SERVING_B,
            SwitchState.ROLLBACK_SERVING,
        }
        if snapshot.admission_open != (snapshot.state in serving):
            raise StateMachineError("admission gate does not match serving state")
        if snapshot.state in serving:
            if snapshot.active_runtime is None or snapshot.serving_model != snapshot.active_runtime.model:
                raise StateMachineError("serving state lacks one exact runtime/model")
        if snapshot.state in {SwitchState.GPU_FREE, SwitchState.FAILED}:
            if snapshot.active_runtime is not None or snapshot.serving_model is not None:
                raise StateMachineError("clean/failed state still owns a runtime")
            if snapshot.last_reclaim_proof_sha256 is None:
                raise StateMachineError("clean/failed state lacks reclaim evidence")
        if snapshot.state == SwitchState.IDLE and (
            snapshot.active_runtime is not None or snapshot.active_switch is not None
        ):
            raise StateMachineError("IDLE cannot own a runtime or switch")
        if snapshot.state != SwitchState.IDLE and snapshot.state != SwitchState.SERVING_A:
            if snapshot.active_switch is None:
                raise StateMachineError("switch lifecycle state lacks switch identity")
        active_generations: set[int] = set()
        for lease_id, lease in snapshot.request_leases.items():
            _require_id(lease_id, "lease map key")
            if lease.lease_id != lease_id:
                raise StateMachineError("lease map key differs from lease identity")
            lease.model.validate()
            if lease.deadline_ns <= lease.accepted_at_ns:
                raise StateMachineError("request lease deadline is not after acceptance")
            if lease.status == LeaseStatus.ACTIVE:
                active_generations.add(lease.runtime_generation)
        if snapshot.active_runtime is None and active_generations:
            raise StateMachineError("active request lease exists without a runtime")
        if snapshot.active_runtime is not None and any(
            generation != snapshot.active_runtime.runtime_generation
            for generation in active_generations
        ):
            raise StateMachineError("active lease belongs to a non-current runtime")
        if set(snapshot.retired_runtime_generations) & active_generations:
            raise StateMachineError("retired runtime generation still has active leases")
        if snapshot.last_reclaim_proof_sha256 is not None:
            _require_digest(snapshot.last_reclaim_proof_sha256, "last reclaim proof")
        for value, label in (
            (snapshot.last_semantic_probe_sha256, "last semantic probe"),
            (snapshot.last_terminal_ledger_sha256, "last terminal ledger"),
        ):
            if value is not None:
                _require_digest(value, label)
        if snapshot.last_completed_switch_id is not None:
            _require_id(snapshot.last_completed_switch_id, "last completed switch")
        previous = "0" * 64
        if len(snapshot.transitions) != snapshot.revision:
            raise StateMachineError("transition chain does not cover every revision")
        for expected_revision, transition in enumerate(snapshot.transitions, 1):
            if transition.revision != expected_revision:
                raise StateMachineError("transition revisions are not contiguous")
            if transition.previous_sha256 != previous:
                raise StateMachineError("transition predecessor hash differs")
            payload = {
                "revision": transition.revision,
                "at_ns": transition.at_ns,
                "controller_generation": transition.controller_generation,
                "operation": transition.operation,
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "detail_sha256": transition.detail_sha256,
                "previous_sha256": transition.previous_sha256,
            }
            if transition.record_sha256 != canonical_sha256(payload):
                raise StateMachineError("transition record hash differs")
            previous = transition.record_sha256


__all__ = [
    "ABSENCE_SCHEMA",
    "GPU_RELEASE_SCHEMA",
    "SCRUB_SCHEMA",
    "SEMANTIC_PROBE_SCHEMA",
    "STATE_SCHEMA",
    "ConcurrentUpdate",
    "ControllerFence",
    "DrainReclaimStateMachine",
    "FenceRejected",
    "GpuReleaseProof",
    "InMemoryStateStore",
    "InvalidTransition",
    "JsonFileStateStore",
    "LeaseStatus",
    "MachineSnapshot",
    "ModelRef",
    "NvmlObservation",
    "ProofRejected",
    "RequestLease",
    "RuntimeAbsenceProof",
    "RuntimeIdentity",
    "ScrubReceipt",
    "SemanticInferenceReceipt",
    "SemanticProbeProof",
    "StateMachineError",
    "SwitchState",
    "canonical_sha256",
    "snapshot_from_dict",
    "snapshot_to_dict",
]
