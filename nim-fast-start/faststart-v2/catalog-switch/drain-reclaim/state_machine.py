#!/usr/bin/env python3
"""Durable, backend-neutral A-to-B drain/reclaim state machine.

The state machine owns admission and generation fencing.  It accepts no
self-asserted semantic booleans or bare digests: serving transitions require a
configured ledger verifier, and teardown transitions require source-bound
receipts verified by a configured trust store.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import hmac
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


STATE_SCHEMA = "archvteams.nebius.ai/catalog-switch-drain-reclaim-state/v2"
ABSENCE_SCHEMA = "archvteams.nebius.ai/catalog-switch-runtime-absence/v2"
OPERATION_ABSENCE_SCHEMA = "archvteams.nebius.ai/catalog-switch-operation-absence/v1"
GPU_RELEASE_SCHEMA = "archvteams.nebius.ai/catalog-switch-gpu-release/v2"
SCRUB_SCHEMA = "archvteams.nebius.ai/catalog-switch-gpu-scrub/v2"
ACTION_RECEIPT_SCHEMA = "archvteams.nebius.ai/catalog-switch-action-receipt/v1"
LEDGER_GATE_SCHEMA = "archvteams.nebius.ai/catalog-switch-ledger-gate/v2"
RECYCLE_SCHEMA = "archvteams.nebius.ai/catalog-switch-node-recycle/v1"
REQUALIFICATION_SCHEMA = "archvteams.nebius.ai/catalog-switch-requalification/v1"
PLACEMENT_REVOCATION_SCHEMA = (
    "archvteams.nebius.ai/catalog-switch-placement-revocation/v1"
)
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
APPROVED_SCRUB_METHODS = ("full-vram-zero", "gpu-reset", "mig-recreate")
ZERO_MEMORY_RULE = "post-scrub-nvml-used-bytes-equals-zero"


class StateMachineError(RuntimeError):
    pass


class FenceRejected(StateMachineError):
    pass


class InvalidTransition(StateMachineError):
    pass


class ProofRejected(StateMachineError):
    pass


class ConcurrentUpdate(StateMachineError):
    pass


class ResponseTimedOut(FenceRejected):
    """Raised only after the TIMED_OUT lease state has been durably committed."""


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
    QUARANTINE_REVOKING = "QUARANTINE_REVOKING"
    RECYCLING_NODE = "RECYCLING_NODE"
    REQUALIFYING_NODE = "REQUALIFYING_NODE"


class LeaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class LedgerStage(StrEnum):
    TARGET_QUALIFIED = "TARGET_QUALIFIED"
    TARGET_FAILED = "TARGET_FAILED"
    ROLLBACK_QUALIFIED = "ROLLBACK_QUALIFIED"
    SWITCH_SEALED = "SWITCH_SEALED"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def key_sha256(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()


def sign_payload(key: bytes, value: Any) -> str:
    return hmac.new(key, canonical_json(value).encode("ascii"), hashlib.sha256).hexdigest()


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
class ValidatorRef:
    validator_id: str
    source_uri: str
    source_sha256: str

    def validate(self) -> None:
        _require_id(self.validator_id, "validator_id")
        if not self.source_uri or ":" not in self.source_uri:
            raise ValueError("validator source_uri must be an absolute authority")
        _require_digest(self.source_sha256, "validator source_sha256")


@dataclass(frozen=True)
class RuntimeAuthority:
    """Exact node/cluster authority on which observations and actions execute."""

    backend: str
    node_id: str
    node_uid: str
    node_boot_id: str
    placement_lease_id: str
    node_agent_id: str
    node_agent_key_sha256: str
    node_agent_source_sha256: str
    cluster_uid: str | None = None
    kube_context: str | None = None
    kubeconfig_sha256: str | None = None
    api_server_url: str | None = None
    server_ca_sha256: str | None = None
    kubectl_executable_sha256: str | None = None
    namespace: str | None = None

    def validate(self) -> None:
        if self.backend not in {"node-local", "kubernetes"}:
            raise ValueError("authority backend must be node-local or kubernetes")
        for value, label in (
            (self.node_id, "node_id"),
            (self.node_uid, "node_uid"),
            (self.node_boot_id, "node_boot_id"),
            (self.placement_lease_id, "placement_lease_id"),
            (self.node_agent_id, "node_agent_id"),
        ):
            _require_id(value, label)
        _require_digest(self.node_agent_key_sha256, "node_agent_key_sha256")
        _require_digest(self.node_agent_source_sha256, "node_agent_source_sha256")
        k8s_values = (
            self.cluster_uid,
            self.kube_context,
            self.kubeconfig_sha256,
            self.api_server_url,
            self.server_ca_sha256,
            self.kubectl_executable_sha256,
            self.namespace,
        )
        if self.backend == "node-local":
            if any(value is not None for value in k8s_values):
                raise ValueError("node-local authority cannot carry Kubernetes identity")
        else:
            if any(value is None for value in k8s_values):
                raise ValueError("Kubernetes authority requires cluster/context/CA/namespace")
            for value, label in (
                (self.cluster_uid, "cluster_uid"),
                (self.kube_context, "kube_context"),
                (self.namespace, "namespace"),
            ):
                _require_id(str(value), label)
            _require_digest(str(self.kubeconfig_sha256), "kubeconfig_sha256")
            _require_digest(str(self.server_ca_sha256), "server_ca_sha256")
            _require_digest(
                str(self.kubectl_executable_sha256),
                "kubectl_executable_sha256",
            )
            if not str(self.api_server_url).startswith("https://"):
                raise ValueError("Kubernetes API server must use an exact HTTPS URL")

    @property
    def digest(self) -> str:
        self.validate()
        return canonical_sha256(asdict(self))

    @property
    def placement_subject_sha256(self) -> str:
        self.validate()
        return canonical_sha256(
            {
                "authority_sha256": self.digest,
                "placement_lease_id": self.placement_lease_id,
            }
        )


@dataclass(frozen=True)
class RuntimeIdentity:
    runtime_uid: str
    launch_operation_id: str
    runtime_generation: int
    model: ModelRef
    gpu_uuid: str
    authority: RuntimeAuthority
    host_pid: int
    process_start_ticks: int
    cgroup_path: str
    container_id: str | None = None
    pod_uid: str | None = None
    pod_name: str | None = None

    @property
    def backend(self) -> str:
        return self.authority.backend

    def validate(self) -> None:
        for value, label in (
            (self.runtime_uid, "runtime_uid"),
            (self.launch_operation_id, "launch_operation_id"),
            (self.gpu_uuid, "gpu_uuid"),
        ):
            _require_id(value, label)
        if self.runtime_generation < 1:
            raise ValueError("runtime_generation must be positive")
        self.model.validate()
        self.authority.validate()
        if self.host_pid < 1 or self.process_start_ticks < 1:
            raise ValueError("host PID and process start ticks must be positive")
        if not self.cgroup_path.startswith("/") or ".." in Path(self.cgroup_path).parts:
            raise ValueError("cgroup_path must be absolute and traversal-free")
        if self.backend == "kubernetes":
            for value, label in (
                (self.container_id, "container_id"),
                (self.pod_uid, "pod_uid"),
                (self.pod_name, "pod_name"),
            ):
                if value is None:
                    raise ValueError(f"Kubernetes runtime requires {label}")
                _require_id(value, label)

    @property
    def digest(self) -> str:
        self.validate()
        return canonical_sha256(asdict(self))


@dataclass(frozen=True)
class ControllerFence:
    controller_id: str
    generation: int

    @property
    def lease_id(self) -> str:
        """Durable controller-lease identity carried by every agent command."""

        _require_id(self.controller_id, "controller_id")
        if self.generation < 1:
            raise ValueError("controller generation must be positive")
        return f"{self.controller_id}.generation-{self.generation}"


@dataclass(frozen=True)
class LaunchReservation:
    switch_id: str
    operation_id: str
    idempotency_key: str
    runtime_generation: int
    model: ModelRef
    gpu_uuid: str
    authority_sha256: str
    backend: str
    controller_id: str
    controller_generation: int
    reserved_at_ns: int

    def validate(self) -> None:
        for value, label in (
            (self.switch_id, "switch_id"),
            (self.operation_id, "operation_id"),
            (self.idempotency_key, "idempotency_key"),
            (self.gpu_uuid, "gpu_uuid"),
            (self.controller_id, "controller_id"),
        ):
            _require_id(value, label)
        if self.runtime_generation < 1 or self.controller_generation < 1:
            raise ValueError("reservation generations must be positive")
        if self.reserved_at_ns < 1 or self.backend not in {"node-local", "kubernetes"}:
            raise ValueError("reservation time/backend is invalid")
        self.model.validate()
        _require_digest(self.authority_sha256, "authority_sha256")

    @property
    def digest(self) -> str:
        self.validate()
        return canonical_sha256(asdict(self))


class EvidenceTrustStore:
    """Pinned HMAC verification keys for node/cluster/broker receipt authorities."""

    def __init__(self, keys: dict[str, bytes]):
        if not keys:
            raise ValueError("evidence trust store cannot be empty")
        self._keys = dict(keys)

    def verify(
        self,
        *,
        source_id: str,
        source_key_sha256: str,
        payload: Any,
        signature_sha256: str,
    ) -> None:
        _require_id(source_id, "evidence source_id")
        _require_digest(source_key_sha256, "evidence source key")
        _require_digest(signature_sha256, "evidence signature")
        key = self._keys.get(source_id)
        if key is None or key_sha256(key) != source_key_sha256:
            raise ProofRejected("evidence source is not in the pinned trust store")
        expected = sign_payload(key, payload)
        if not hmac.compare_digest(expected, signature_sha256):
            raise ProofRejected("evidence signature differs")


def _signed_payload(value: Any) -> dict[str, Any]:
    payload = asdict(value)
    payload.pop("signature_sha256", None)
    return payload


@dataclass(frozen=True)
class ActionReceipt:
    schema: str
    switch_id: str
    operation: str
    subject_sha256: str
    command_envelope_sha256: str
    controller_id: str
    controller_lease_id: str
    controller_generation: int
    idempotency_key: str
    source_authority_sha256: str
    source_id: str
    source_key_sha256: str
    started_at_ns: int
    finished_at_ns: int
    outcome: str
    result_attestation: dict[str, Any] | None
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        *,
        switch_id: str,
        operation: str,
        subject_sha256: str,
        authority: RuntimeAuthority,
        fence: ControllerFence,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != ACTION_RECEIPT_SCHEMA:
            raise ProofRejected("action receipt schema differs")
        if (self.switch_id, self.operation, self.subject_sha256) != (
            switch_id,
            operation,
            subject_sha256,
        ):
            raise ProofRejected("action receipt targets a different operation")
        if (
            self.controller_id,
            self.controller_lease_id,
            self.controller_generation,
            self.source_authority_sha256,
        ) != (fence.controller_id, fence.lease_id, fence.generation, authority.digest):
            raise ProofRejected("action receipt fence/source differs")
        if self.outcome != "completed" or self.started_at_ns < 1 or self.finished_at_ns <= self.started_at_ns:
            raise ProofRejected("action receipt is not a completed ordered action")
        if self.result_attestation is not None and not isinstance(
            self.result_attestation, dict
        ):
            raise ProofRejected("action result attestation is not an object")
        for value, label in (
            (self.command_envelope_sha256, "command envelope"),
            (self.raw_evidence_sha256, "action raw evidence"),
        ):
            _require_digest(value, label)
        _require_id(self.idempotency_key, "action idempotency_key")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class RuntimeAbsenceProof:
    schema: str
    switch_id: str
    runtime_identity_sha256: str
    runtime_uid: str
    runtime_generation: int
    authority_sha256: str
    source_id: str
    source_key_sha256: str
    observed_at_ns: int
    process_absent: bool
    cgroup_empty: bool
    container_absent: bool
    pod_absent: bool | None
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    logs_purged: bool
    sockets_absent: bool
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        switch_id: str,
        runtime: RuntimeIdentity,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != ABSENCE_SCHEMA:
            raise ProofRejected("runtime absence proof schema differs")
        if (
            self.switch_id,
            self.runtime_identity_sha256,
            self.runtime_uid,
            self.runtime_generation,
            self.authority_sha256,
        ) != (
            switch_id,
            runtime.digest,
            runtime.runtime_uid,
            runtime.runtime_generation,
            runtime.authority.digest,
        ):
            raise ProofRejected("runtime absence proof identity differs")
        required = {
            "process_absent": self.process_absent,
            "cgroup_empty": self.cgroup_empty,
            "container_absent": self.container_absent,
            "mounts_absent": self.mounts_absent,
            "namespaces_absent": self.namespaces_absent,
            "credentials_revoked": self.credentials_revoked,
            "kernel_residue_safe": self.kernel_residue_safe,
            "logs_purged": self.logs_purged,
            "sockets_absent": self.sockets_absent,
        }
        if runtime.backend == "kubernetes":
            required["pod_absent"] = self.pod_absent is True
        elif self.pod_absent is not None:
            raise ProofRejected("node-local proof cannot invent Pod absence")
        failed = sorted(name for name, passed in required.items() if passed is not True)
        if failed or self.observed_at_ns < 1:
            raise ProofRejected(f"runtime absence proof is incomplete: {failed}")
        _require_digest(self.raw_evidence_sha256, "absence raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class LaunchOperationAbsenceProof:
    schema: str
    switch_id: str
    reservation_sha256: str
    operation_id: str
    runtime_generation: int
    authority_sha256: str
    source_id: str
    source_key_sha256: str
    observed_at_ns: int
    launch_journal_terminal: str
    process_absent: bool
    cgroup_absent: bool
    container_absent: bool
    pod_absent: bool | None
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        switch_id: str,
        reservation: LaunchReservation,
        authority: RuntimeAuthority,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != OPERATION_ABSENCE_SCHEMA:
            raise ProofRejected("launch-operation absence schema differs")
        if (
            self.switch_id,
            self.reservation_sha256,
            self.operation_id,
            self.runtime_generation,
            self.authority_sha256,
        ) != (
            switch_id,
            reservation.digest,
            reservation.operation_id,
            reservation.runtime_generation,
            authority.digest,
        ):
            raise ProofRejected("launch-operation absence identity differs")
        required = (
            self.process_absent,
            self.cgroup_absent,
            self.container_absent,
            self.mounts_absent,
            self.namespaces_absent,
            self.credentials_revoked,
            self.kernel_residue_safe,
        )
        if any(value is not True for value in required):
            raise ProofRejected("launch-operation absence is incomplete")
        if reservation.backend == "kubernetes" and self.pod_absent is not True:
            raise ProofRejected("Kubernetes launch operation lacks Pod absence")
        if reservation.backend == "node-local" and self.pod_absent is not None:
            raise ProofRejected("node-local launch operation invents Pod absence")
        if self.launch_journal_terminal not in {"absent", "cleaned"} or self.observed_at_ns < 1:
            raise ProofRejected("launch journal is not durably absent/cleaned")
        _require_digest(self.raw_evidence_sha256, "operation absence raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class ScrubReceipt:
    schema: str
    switch_id: str
    subject_sha256: str
    gpu_uuid: str
    method: str
    bytes_scrubbed: int
    total_memory_bytes: int
    started_at_ns: int
    finished_at_ns: int
    succeeded: bool
    raw_evidence_sha256: str

    def validate_for(self, switch_id: str, subject_sha256: str, gpu_uuid: str) -> None:
        if self.schema != SCRUB_SCHEMA:
            raise ProofRejected("GPU scrub schema differs")
        if (self.switch_id, self.subject_sha256, self.gpu_uuid) != (
            switch_id,
            subject_sha256,
            gpu_uuid,
        ):
            raise ProofRejected("GPU scrub targets a different subject/GPU")
        if self.method not in APPROVED_SCRUB_METHODS:
            raise ProofRejected("GPU scrub method is not approved")
        if not self.succeeded or self.started_at_ns < 1 or self.finished_at_ns <= self.started_at_ns:
            raise ProofRejected("GPU scrub did not complete")
        if self.total_memory_bytes < 1 or self.bytes_scrubbed < 0:
            raise ProofRejected("GPU scrub byte accounting is invalid")
        if self.method == "full-vram-zero" and self.bytes_scrubbed != self.total_memory_bytes:
            raise ProofRejected("full-VRAM scrub bytes must equal exact GPU total")
        _require_digest(self.raw_evidence_sha256, "scrub raw evidence")


@dataclass(frozen=True)
class NvmlObservation:
    observed_at_ns: int
    gpu_uuid: str
    compute_pids: tuple[int, ...]
    graphics_pids: tuple[int, ...]
    graphics_query_supported: bool
    memory_used_bytes: int
    memory_total_bytes: int

    def validate(self, gpu_uuid: str, total_memory_bytes: int) -> None:
        if self.observed_at_ns < 1 or self.gpu_uuid != gpu_uuid:
            raise ProofRejected("NVML identity/time differs")
        if self.memory_total_bytes != total_memory_bytes:
            raise ProofRejected("NVML total memory differs from scrubbed GPU total")
        if self.graphics_query_supported is not True:
            raise ProofRejected("graphics contexts were not observed")
        if self.compute_pids or self.graphics_pids:
            raise ProofRejected("NVML still reports compute/graphics processes")
        if self.memory_used_bytes != 0:
            raise ProofRejected("post-scrub NVML used memory must equal zero")
        if any(pid < 1 for pid in (*self.compute_pids, *self.graphics_pids)):
            raise ProofRejected("NVML contains an invalid PID")


@dataclass(frozen=True)
class GpuReleaseProof:
    schema: str
    switch_id: str
    subject_sha256: str
    authority_sha256: str
    gpu_uuid: str
    source_id: str
    source_key_sha256: str
    observations: tuple[NvmlObservation, ...]
    scrub: ScrubReceipt
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        *,
        switch_id: str,
        subject_sha256: str,
        authority: RuntimeAuthority,
        gpu_uuid: str,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != GPU_RELEASE_SCHEMA:
            raise ProofRejected("GPU release schema differs")
        if (
            self.switch_id,
            self.subject_sha256,
            self.authority_sha256,
            self.gpu_uuid,
        ) != (switch_id, subject_sha256, authority.digest, gpu_uuid):
            raise ProofRejected("GPU release identity differs")
        self.scrub.validate_for(switch_id, subject_sha256, gpu_uuid)
        if len(self.observations) != 2:
            raise ProofRejected("GPU release requires exactly two NVML observations")
        previous = self.scrub.finished_at_ns
        for observation in self.observations:
            observation.validate(gpu_uuid, self.scrub.total_memory_bytes)
            if observation.observed_at_ns <= previous:
                raise ProofRejected("NVML observations are not strictly post-scrub ordered")
            previous = observation.observed_at_ns
        _require_digest(self.raw_evidence_sha256, "GPU release raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class LedgerGateReceipt:
    schema: str
    stage: LedgerStage
    switch_id: str
    trace_id: str
    request_id: str
    attempt_id: str
    accepted_t0_ns: int
    runtime_generation: int
    launch_operation_id: str
    launch_action_receipt_sha256: str | None
    model_id: str
    model_version: str
    artifact_sha256: str
    validator_sha256: str
    shared_ledger_sha256: str
    audit_segment_sha256: str
    audit_sequence_start: int
    audit_sequence_end: int
    audit_chain_head_sha256: str
    offnode_durability_receipt_sha256: str
    product_terminal_event_sha256: str | None
    predecessor_receipt_sha256: str | None
    first_semantic_at_ns: int | None
    second_semantic_at_ns: int | None
    receipt_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["stage"] = self.stage.value
        value.pop("receipt_sha256")
        return value

    def validate_self(self) -> None:
        if self.schema != LEDGER_GATE_SCHEMA:
            raise ProofRejected("ledger gate receipt schema differs")
        for value, label in (
            (self.switch_id, "receipt switch_id"),
            (self.trace_id, "receipt trace_id"),
            (self.request_id, "receipt request_id"),
            (self.attempt_id, "receipt attempt_id"),
            (self.launch_operation_id, "receipt launch operation"),
            (self.model_id, "receipt model_id"),
            (self.model_version, "receipt model_version"),
        ):
            _require_id(value, label)
        for value, label in (
            (self.artifact_sha256, "receipt artifact"),
            (self.validator_sha256, "receipt validator"),
            (self.shared_ledger_sha256, "receipt shared ledger"),
            (self.audit_segment_sha256, "receipt audit segment"),
            (self.audit_chain_head_sha256, "receipt audit head"),
            (self.offnode_durability_receipt_sha256, "receipt off-node durability"),
            (self.receipt_sha256, "receipt digest"),
        ):
            _require_digest(value, label)
        for optional, label in (
            (self.launch_action_receipt_sha256, "launch action receipt"),
            (self.product_terminal_event_sha256, "product terminal"),
            (self.predecessor_receipt_sha256, "predecessor receipt"),
        ):
            if optional is not None:
                _require_digest(optional, label)
        if self.accepted_t0_ns < 1 or self.runtime_generation < 1 or self.audit_sequence_start < 0:
            raise ProofRejected("ledger gate generation/sequence is invalid")
        if self.audit_sequence_end < self.audit_sequence_start:
            raise ProofRejected("ledger gate segment is empty/reversed")
        if self.receipt_sha256 != canonical_sha256(self.payload()):
            raise ProofRejected("ledger gate receipt self-digest differs")


@dataclass(frozen=True)
class LedgerExpectation:
    stage: LedgerStage
    switch_id: str
    trace_id: str
    request_id: str
    attempt_id: str
    accepted_t0_ns: int
    runtime: RuntimeIdentity
    validator: ValidatorRef
    launch_action_receipt_sha256: str | None
    runtime_identity_sha256_override: str | None = None
    predecessor_receipt_sha256: str | None = None


@dataclass(frozen=True)
class VerifiedLedgerGate:
    receipt_sha256: str
    audit_chain_head_sha256: str
    first_semantic_at_ns: int | None
    second_semantic_at_ns: int | None


class LedgerReceiptVerifier(Protocol):
    def verify(
        self, receipt: LedgerGateReceipt, expectation: LedgerExpectation
    ) -> VerifiedLedgerGate: ...


@dataclass(frozen=True)
class NodeRecycleProof:
    schema: str
    switch_id: str
    old_authority_sha256: str
    new_authority: RuntimeAuthority
    old_resource_id: str
    new_resource_id: str
    old_resource_absent: bool
    new_resource_created: bool
    old_gpu_uuid: str
    new_gpu_uuid: str
    source_id: str
    source_key_sha256: str
    completed_at_ns: int
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        switch_id: str,
        old_authority: RuntimeAuthority,
        old_gpu_uuid: str,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != RECYCLE_SCHEMA or self.switch_id != switch_id:
            raise ProofRejected("node recycle proof schema/switch differs")
        if self.old_authority_sha256 != old_authority.digest:
            raise ProofRejected("node recycle proof old authority differs")
        self.new_authority.validate()
        if self.new_authority.backend != old_authority.backend:
            raise ProofRejected("node recycle changed backend")
        if self.new_authority.node_boot_id == old_authority.node_boot_id:
            raise ProofRejected("node recycle did not produce a fresh boot identity")
        if (
            self.old_resource_id != old_authority.node_id
            or self.new_resource_id != self.new_authority.node_id
        ):
            raise ProofRejected("node recycle resource IDs differ from node authorities")
        if (
            self.old_resource_id == self.new_resource_id
            or self.new_authority.node_uid == old_authority.node_uid
            or self.new_authority.placement_lease_id
            == old_authority.placement_lease_id
        ):
            raise ProofRejected("quarantine recycle must use a newly created resource")
        if self.old_resource_absent is not True or self.new_resource_created is not True:
            raise ProofRejected("node recycle lacks old-absence/new-creation proof")
        for value, label in (
            (self.old_resource_id, "old resource"),
            (self.new_resource_id, "new resource"),
        ):
            _require_id(value, label)
        for value, label in (
            (self.old_gpu_uuid, "old GPU UUID"),
            (self.new_gpu_uuid, "new GPU UUID"),
        ):
            _require_id(value, label)
        if self.old_gpu_uuid != old_gpu_uuid:
            raise ProofRejected("node recycle old GPU UUID differs")
        if self.new_gpu_uuid == self.old_gpu_uuid:
            raise ProofRejected("node recycle did not replace the GPU identity")
        if self.completed_at_ns < 1:
            raise ProofRejected("node recycle completion time is invalid")
        _require_digest(self.raw_evidence_sha256, "recycle raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class PlacementRevocationProof:
    schema: str
    switch_id: str
    authority_sha256: str
    placement_lease_id: str
    backend: str
    source_id: str
    source_key_sha256: str
    revoked_at_ns: int
    placement_refusal_observed_at_ns: int
    lease_absent: bool
    new_placement_refused: bool
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        switch_id: str,
        authority: RuntimeAuthority,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != PLACEMENT_REVOCATION_SCHEMA:
            raise ProofRejected("placement revocation schema differs")
        if (
            self.switch_id,
            self.authority_sha256,
            self.placement_lease_id,
            self.backend,
        ) != (
            switch_id,
            authority.digest,
            authority.placement_lease_id,
            authority.backend,
        ):
            raise ProofRejected("placement revocation identity differs")
        if self.lease_absent is not True or self.new_placement_refused is not True:
            raise ProofRejected("placement lease remains eligible")
        if (
            self.revoked_at_ns < 1
            or self.placement_refusal_observed_at_ns <= self.revoked_at_ns
        ):
            raise ProofRejected("placement revocation evidence is not ordered")
        _require_digest(self.raw_evidence_sha256, "placement revocation raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


@dataclass(frozen=True)
class RequalificationProof:
    schema: str
    switch_id: str
    authority_sha256: str
    gpu_uuid: str
    source_id: str
    source_key_sha256: str
    observed_at_ns: int
    sentinel_vram_absent: bool
    host_residue_absent: bool
    exclusive_occupancy_enforced: bool
    direct_launch_refused: bool
    audit_offnode_continuity: bool
    command_replay_refused: bool
    observations: tuple[NvmlObservation, ...]
    raw_evidence_sha256: str
    signature_sha256: str

    def validate_for(
        self,
        switch_id: str,
        authority: RuntimeAuthority,
        gpu_uuid: str,
        trust: EvidenceTrustStore,
    ) -> None:
        if self.schema != REQUALIFICATION_SCHEMA:
            raise ProofRejected("requalification proof schema differs")
        if (self.switch_id, self.authority_sha256, self.gpu_uuid) != (
            switch_id,
            authority.digest,
            gpu_uuid,
        ):
            raise ProofRejected("requalification identity differs")
        gates = (
            self.sentinel_vram_absent,
            self.host_residue_absent,
            self.exclusive_occupancy_enforced,
            self.direct_launch_refused,
            self.audit_offnode_continuity,
            self.command_replay_refused,
        )
        if any(value is not True for value in gates):
            raise ProofRejected("requalification control suite is incomplete")
        if len(self.observations) != 2:
            raise ProofRejected("requalification requires two NVML observations")
        total = self.observations[0].memory_total_bytes
        previous = 0
        for observation in self.observations:
            observation.validate(gpu_uuid, total)
            if observation.observed_at_ns <= previous:
                raise ProofRejected("requalification NVML samples are unordered")
            previous = observation.observed_at_ns
        if self.observed_at_ns < previous:
            raise ProofRejected("requalification terminal predates evidence")
        _require_digest(self.raw_evidence_sha256, "requalification raw evidence")
        trust.verify(
            source_id=self.source_id,
            source_key_sha256=self.source_key_sha256,
            payload=_signed_payload(self),
            signature_sha256=self.signature_sha256,
        )


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
    trace_id: str
    request_id: str
    attempt_id: str
    source_model: ModelRef
    target_model: ModelRef
    target_validator: ValidatorRef
    source_runtime_uid: str
    source_runtime_generation: int
    accepted_t0_ns: int
    initiated_at_ns: int
    drain_deadline_ns: int
    target_runtime_generation: int | None = None
    target_launch_operation_id: str | None = None
    target_launch_receipt_sha256: str | None = None
    target_runtime_identity_sha256: str | None = None
    cancelled: bool = False
    failure_reason: str | None = None
    reclaim_proof_sha256: str | None = None
    target_qualified_receipt_sha256: str | None = None
    target_failure_receipt_sha256: str | None = None
    rollback_trace_id: str | None = None
    rollback_request_id: str | None = None
    rollback_attempt_id: str | None = None
    rollback_accepted_t0_ns: int | None = None
    rollback_validator: ValidatorRef | None = None
    rollback_runtime_generation: int | None = None
    rollback_launch_operation_id: str | None = None
    rollback_launch_receipt_sha256: str | None = None
    rollback_qualified_receipt_sha256: str | None = None
    sealed_receipt_sha256: str | None = None


@dataclass
class TransitionRecord:
    revision: int
    at_ns: int
    controller_generation: int
    operation: str
    from_state: str
    to_state: str
    state_after: dict[str, Any]
    detail_sha256: str
    previous_sha256: str
    record_sha256: str


@dataclass
class MachineSnapshot:
    schema: str
    revision: int
    authority: RuntimeAuthority
    gpu_uuid: str
    state: SwitchState
    controller_id: str | None
    controller_generation: int
    next_runtime_generation: int
    admission_open: bool
    serving_model: ModelRef | None
    active_runtime: RuntimeIdentity | None
    launch_reservation: LaunchReservation | None
    active_switch: SwitchRecord | None
    request_leases: dict[str, RequestLease] = field(default_factory=dict)
    retired_runtime_generations: list[int] = field(default_factory=list)
    last_reclaim_proof_sha256: str | None = None
    last_ledger_receipt_sha256: str | None = None
    last_completed_switch_id: str | None = None
    quarantine_reason: str | None = None
    quarantine_old_authority: RuntimeAuthority | None = None
    quarantine_revocation_proof_sha256: str | None = None
    node_recycle_proof_sha256: str | None = None
    requalification_proof_sha256: str | None = None
    transitions: list[TransitionRecord] = field(default_factory=list)

    @classmethod
    def initial(cls, authority: RuntimeAuthority, gpu_uuid: str) -> "MachineSnapshot":
        authority.validate()
        _require_id(gpu_uuid, "gpu_uuid")
        return cls(
            schema=STATE_SCHEMA,
            revision=0,
            authority=authority,
            gpu_uuid=gpu_uuid,
            state=SwitchState.IDLE,
            controller_id=None,
            controller_generation=0,
            next_runtime_generation=1,
            admission_open=False,
            serving_model=None,
            active_runtime=None,
            launch_reservation=None,
            active_switch=None,
        )


def _model_from(value: dict[str, Any] | None) -> ModelRef | None:
    return None if value is None else ModelRef(**value)


def _validator_from(value: dict[str, Any] | None) -> ValidatorRef | None:
    return None if value is None else ValidatorRef(**value)


def _authority_from(value: dict[str, Any] | None) -> RuntimeAuthority | None:
    return None if value is None else RuntimeAuthority(**value)


def _runtime_from(value: dict[str, Any] | None) -> RuntimeIdentity | None:
    if value is None:
        return None
    payload = dict(value)
    payload["model"] = ModelRef(**payload["model"])
    payload["authority"] = RuntimeAuthority(**payload["authority"])
    return RuntimeIdentity(**payload)


def _reservation_from(value: dict[str, Any] | None) -> LaunchReservation | None:
    if value is None:
        return None
    payload = dict(value)
    payload["model"] = ModelRef(**payload["model"])
    return LaunchReservation(**payload)


def snapshot_to_dict(snapshot: MachineSnapshot) -> dict[str, Any]:
    value = asdict(snapshot)
    value["state"] = snapshot.state.value
    for lease in value["request_leases"].values():
        lease["status"] = lease["status"].value if isinstance(lease["status"], LeaseStatus) else lease["status"]
    return value


def _snapshot_detail(snapshot: MachineSnapshot) -> dict[str, Any]:
    detail = snapshot_to_dict(snapshot)
    detail.pop("transitions")
    return detail


def snapshot_from_dict(value: dict[str, Any]) -> MachineSnapshot:
    payload = copy.deepcopy(value)
    if payload.get("schema") != STATE_SCHEMA:
        raise StateMachineError("state snapshot schema is not v2")
    payload["state"] = SwitchState(payload["state"])
    payload["authority"] = RuntimeAuthority(**payload["authority"])
    payload["quarantine_old_authority"] = _authority_from(payload["quarantine_old_authority"])
    payload["serving_model"] = _model_from(payload["serving_model"])
    payload["active_runtime"] = _runtime_from(payload["active_runtime"])
    payload["launch_reservation"] = _reservation_from(payload["launch_reservation"])
    if payload["active_switch"] is not None:
        switch = dict(payload["active_switch"])
        switch["source_model"] = ModelRef(**switch["source_model"])
        switch["target_model"] = ModelRef(**switch["target_model"])
        switch["target_validator"] = ValidatorRef(**switch["target_validator"])
        switch["rollback_validator"] = _validator_from(switch["rollback_validator"])
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

    def compare_and_swap(self, expected_revision: int, replacement: MachineSnapshot) -> bool: ...


class InMemoryStateStore:
    def __init__(self, initial: MachineSnapshot):
        self._snapshot = copy.deepcopy(initial)
        self._lock = threading.Lock()

    def load(self) -> MachineSnapshot:
        with self._lock:
            return copy.deepcopy(self._snapshot)

    def compare_and_swap(self, expected_revision: int, replacement: MachineSnapshot) -> bool:
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
            raise StateMachineError("state must be one canonical newline-terminated object")
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
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
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

    def _locked(self):
        self._check_paths()
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        stream = os.fdopen(descriptor, "r+")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        return stream

    def load(self) -> MachineSnapshot:
        lock = self._locked()
        try:
            return self._read_unlocked()
        finally:
            lock.close()

    def compare_and_swap(self, expected_revision: int, replacement: MachineSnapshot) -> bool:
        lock = self._locked()
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
    def __init__(
        self,
        store: StateStore,
        *,
        evidence_trust: EvidenceTrustStore,
        ledger_verifier: LedgerReceiptVerifier | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        max_cas_attempts: int = 32,
    ):
        self.store = store
        self.evidence_trust = evidence_trust
        self.ledger_verifier = ledger_verifier
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
            working.revision = original.revision + 1
            state_after = _snapshot_detail(working)
            payload = {
                "revision": working.revision,
                "at_ns": now_ns,
                "controller_generation": working.controller_generation,
                "operation": operation,
                "from_state": original.state.value,
                "to_state": working.state.value,
                "state_after": state_after,
                "detail_sha256": canonical_sha256(state_after),
                "previous_sha256": original.transitions[-1].record_sha256 if original.transitions else "0" * 64,
            }
            working.transitions.append(TransitionRecord(**payload, record_sha256=canonical_sha256(payload)))
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

    def install_serving_a(self, fence: ControllerFence, runtime: RuntimeIdentity) -> None:
        runtime.validate()

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            if snapshot.state != SwitchState.IDLE:
                raise InvalidTransition("initial runtime can only be installed from IDLE")
            if runtime.authority != snapshot.authority or runtime.gpu_uuid != snapshot.gpu_uuid:
                raise InvalidTransition("runtime authority/GPU differs from node")
            if runtime.runtime_generation != snapshot.next_runtime_generation:
                raise FenceRejected("initial runtime generation is not reserved")
            snapshot.next_runtime_generation += 1
            snapshot.state = SwitchState.SERVING_A
            snapshot.serving_model = runtime.model
            snapshot.active_runtime = runtime
            snapshot.admission_open = True

        self._commit("install_serving_a", fence, mutate)

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
        for value, label in ((lease_id, "lease_id"), (request_id, "request_id"), (attempt_id, "attempt_id")):
            _require_id(value, label)
        model.validate()

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> RequestLease:
            existing = snapshot.request_leases.get(lease_id)
            if existing is not None:
                if (existing.request_id, existing.attempt_id, existing.model, existing.deadline_ns) != (
                    request_id,
                    attempt_id,
                    model,
                    deadline_ns,
                ):
                    raise InvalidTransition("lease ID was reused with different content")
                return copy.deepcopy(existing)
            if not snapshot.admission_open or snapshot.active_runtime is None:
                raise InvalidTransition("admission is closed")
            if snapshot.serving_model != model or snapshot.active_runtime.model != model:
                raise FenceRejected("request model differs from serving generation")
            if deadline_ns <= now_ns:
                raise InvalidTransition("request deadline is not in the future")
            lease = RequestLease(
                lease_id,
                request_id,
                attempt_id,
                model,
                snapshot.active_runtime.runtime_generation,
                now_ns,
                deadline_ns,
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

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> tuple[RequestLease, bool]:
            lease = snapshot.request_leases.get(lease_id)
            if lease is None or lease.status != LeaseStatus.ACTIVE:
                raise FenceRejected("response lease is unknown or terminal")
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
            late = now_ns > lease.deadline_ns
            lease.status = LeaseStatus.TIMED_OUT if late else LeaseStatus.COMPLETED
            lease.terminal_reason = (
                "response observed after request lease deadline"
                if late
                else "complete response admitted by generation fence"
            )
            return copy.deepcopy(lease), late

        lease, late = self._commit("complete_response", fence, mutate)
        if late:
            raise ResponseTimedOut("response arrived after deadline; TIMED_OUT was persisted")
        return lease

    def cancel_request(self, fence: ControllerFence, *, lease_id: str, reason: str) -> RequestLease:
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
        trace_id: str,
        request_id: str,
        attempt_id: str,
        target: ModelRef,
        validator: ValidatorRef,
        accepted_t0_ns: int,
        drain_timeout_ns: int,
    ) -> SwitchRecord:
        for value, label in (
            (switch_id, "switch_id"),
            (trace_id, "trace_id"),
            (request_id, "request_id"),
            (attempt_id, "attempt_id"),
        ):
            _require_id(value, label)
        target.validate()
        validator.validate()
        if accepted_t0_ns < 1 or drain_timeout_ns < 1:
            raise ValueError("T0 and drain timeout must be positive")

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> SwitchRecord:
            existing = snapshot.active_switch
            if existing is not None:
                expected = (switch_id, trace_id, request_id, attempt_id, target, validator, accepted_t0_ns)
                actual = (
                    existing.switch_id,
                    existing.trace_id,
                    existing.request_id,
                    existing.attempt_id,
                    existing.target_model,
                    existing.target_validator,
                    existing.accepted_t0_ns,
                )
                if actual == expected:
                    return copy.deepcopy(existing)
                raise InvalidTransition("a different switch is already active")
            if snapshot.state != SwitchState.SERVING_A or snapshot.active_runtime is None:
                raise InvalidTransition("switch requires one serving A runtime")
            if target == snapshot.serving_model:
                raise InvalidTransition("A-to-B target must differ from A")
            if accepted_t0_ns > now_ns:
                raise InvalidTransition("external T0 cannot be in the future")
            switch = SwitchRecord(
                switch_id=switch_id,
                trace_id=trace_id,
                request_id=request_id,
                attempt_id=attempt_id,
                source_model=snapshot.active_runtime.model,
                target_model=target,
                target_validator=validator,
                source_runtime_uid=snapshot.active_runtime.runtime_uid,
                source_runtime_generation=snapshot.active_runtime.runtime_generation,
                accepted_t0_ns=accepted_t0_ns,
                initiated_at_ns=now_ns,
                drain_deadline_ns=now_ns + drain_timeout_ns,
            )
            snapshot.active_switch = switch
            snapshot.state = SwitchState.DRAINING_A
            snapshot.admission_open = False
            return copy.deepcopy(switch)

        return self._commit("begin_switch", fence, mutate)

    def cancel_switch(self, fence: ControllerFence, *, switch_id: str, reason: str) -> None:
        if not reason:
            raise ValueError("switch cancellation reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            switch.cancelled = True
            switch.failure_reason = reason
            snapshot.admission_open = False

        self._commit("cancel_switch", fence, mutate)

    def advance_drain(self, fence: ControllerFence, *, switch_id: str) -> tuple[bool, tuple[str, ...]]:
        def mutate(snapshot: MachineSnapshot, now_ns: int) -> tuple[bool, tuple[str, ...]]:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.DRAINING_A or snapshot.active_runtime is None:
                raise InvalidTransition("drain is not active")
            generation = snapshot.active_runtime.runtime_generation
            active = [
                lease
                for lease in snapshot.request_leases.values()
                if lease.status == LeaseStatus.ACTIVE and lease.runtime_generation == generation
            ]
            if active and now_ns < switch.drain_deadline_ns:
                return False, ()
            timed_out: list[str] = []
            for lease in active:
                lease.status = LeaseStatus.TIMED_OUT
                lease.terminal_reason = "A drain deadline expired before completion"
                timed_out.append(lease.lease_id)
            snapshot.retired_runtime_generations.append(generation)
            snapshot.retired_runtime_generations = sorted(set(snapshot.retired_runtime_generations))
            snapshot.state = SwitchState.RECLAIMING_A
            return True, tuple(sorted(timed_out))

        return self._commit("advance_drain", fence, mutate)

    def _validate_gpu_release_order(
        self,
        *,
        reclaim_started_at_ns: int,
        stop_finished_at_ns: int,
        absence_at_ns: int,
        gpu_release: GpuReleaseProof,
        committed_at_ns: int,
    ) -> None:
        if stop_finished_at_ns <= reclaim_started_at_ns:
            raise ProofRejected("stop action predates durable reclaim state")
        if absence_at_ns <= stop_finished_at_ns:
            raise ProofRejected("runtime/operation absence must follow stop/cleanup action")
        if gpu_release.scrub.started_at_ns <= absence_at_ns:
            raise ProofRejected("GPU scrub must start only after exact absence")
        if gpu_release.observations[-1].observed_at_ns > committed_at_ns:
            raise ProofRejected("GPU release evidence cannot be from the future")

    def record_reclaim(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        stop_receipt: ActionReceipt,
        absence: RuntimeAbsenceProof,
        gpu_release: GpuReleaseProof,
    ) -> str:
        def mutate(snapshot: MachineSnapshot, now_ns: int) -> str:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.RECLAIMING_A, SwitchState.RECLAIMING_B}:
                raise InvalidTransition("exact runtime reclaim is not pending")
            runtime = snapshot.active_runtime
            if runtime is None:
                raise ProofRejected("no exact runtime is bound for reclaim")
            active = [
                lease.lease_id
                for lease in snapshot.request_leases.values()
                if lease.status == LeaseStatus.ACTIVE
                and lease.runtime_generation == runtime.runtime_generation
            ]
            if active:
                raise ProofRejected(f"runtime still owns active leases: {sorted(active)}")
            stop_receipt.validate_for(
                switch_id=switch_id,
                operation="stop-runtime",
                subject_sha256=runtime.digest,
                authority=runtime.authority,
                fence=fence,
                trust=self.evidence_trust,
            )
            absence.validate_for(switch_id, runtime, self.evidence_trust)
            gpu_release.validate_for(
                switch_id=switch_id,
                subject_sha256=runtime.digest,
                authority=runtime.authority,
                gpu_uuid=runtime.gpu_uuid,
                trust=self.evidence_trust,
            )
            reclaim_started = self._last_entered(snapshot, snapshot.state)
            self._validate_gpu_release_order(
                reclaim_started_at_ns=reclaim_started,
                stop_finished_at_ns=stop_receipt.finished_at_ns,
                absence_at_ns=absence.observed_at_ns,
                gpu_release=gpu_release,
                committed_at_ns=now_ns,
            )
            digest = canonical_sha256(
                {
                    "stop": asdict(stop_receipt),
                    "absence": asdict(absence),
                    "gpu_release": asdict(gpu_release),
                }
            )
            snapshot.active_runtime = None
            snapshot.serving_model = None
            snapshot.launch_reservation = None
            snapshot.admission_open = False
            snapshot.state = SwitchState.GPU_FREE
            snapshot.last_reclaim_proof_sha256 = digest
            switch.reclaim_proof_sha256 = digest
            return digest

        return self._commit("record_reclaim", fence, mutate)

    def record_ambiguous_launch_cleanup(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        cleanup_receipt: ActionReceipt,
        absence: LaunchOperationAbsenceProof,
        gpu_release: GpuReleaseProof,
    ) -> str:
        def mutate(snapshot: MachineSnapshot, now_ns: int) -> str:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.RECLAIMING_B or snapshot.active_runtime is not None:
                raise InvalidTransition("ambiguous launch cleanup is not pending")
            reservation = snapshot.launch_reservation
            if reservation is None:
                raise ProofRejected("ambiguous launch lacks its durable reservation")
            cleanup_receipt.validate_for(
                switch_id=switch_id,
                operation="cleanup-launch-operation",
                subject_sha256=reservation.digest,
                authority=snapshot.authority,
                fence=fence,
                trust=self.evidence_trust,
            )
            absence.validate_for(switch_id, reservation, snapshot.authority, self.evidence_trust)
            gpu_release.validate_for(
                switch_id=switch_id,
                subject_sha256=reservation.digest,
                authority=snapshot.authority,
                gpu_uuid=snapshot.gpu_uuid,
                trust=self.evidence_trust,
            )
            self._validate_gpu_release_order(
                reclaim_started_at_ns=self._last_entered(snapshot, SwitchState.RECLAIMING_B),
                stop_finished_at_ns=cleanup_receipt.finished_at_ns,
                absence_at_ns=absence.observed_at_ns,
                gpu_release=gpu_release,
                committed_at_ns=now_ns,
            )
            digest = canonical_sha256(
                {
                    "cleanup": asdict(cleanup_receipt),
                    "operation_absence": asdict(absence),
                    "gpu_release": asdict(gpu_release),
                }
            )
            snapshot.launch_reservation = None
            snapshot.state = SwitchState.GPU_FREE
            snapshot.last_reclaim_proof_sha256 = digest
            switch.reclaim_proof_sha256 = digest
            return digest

        return self._commit("record_ambiguous_launch_cleanup", fence, mutate)

    def reject_reclaim_proof(self, fence: ControllerFence, *, switch_id: str, reason: str) -> None:
        if not reason:
            raise ValueError("quarantine reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.RECLAIMING_A, SwitchState.RECLAIMING_B}:
                raise InvalidTransition("no reclaim is pending")
            snapshot.state = SwitchState.QUARANTINED
            snapshot.admission_open = False
            snapshot.quarantine_reason = reason
            snapshot.quarantine_old_authority = snapshot.authority

        self._commit("reject_reclaim_proof", fence, mutate)

    def _reserve_launch(
        self,
        snapshot: MachineSnapshot,
        now_ns: int,
        fence: ControllerFence,
        switch: SwitchRecord,
        *,
        model: ModelRef,
        operation_id: str,
        idempotency_key: str,
        rollback: bool,
    ) -> LaunchReservation:
        for value, label in ((operation_id, "operation_id"), (idempotency_key, "idempotency_key")):
            _require_id(value, label)
        existing = snapshot.launch_reservation
        if existing is not None:
            if (existing.operation_id, existing.idempotency_key, existing.model) == (
                operation_id,
                idempotency_key,
                model,
            ):
                if (existing.controller_id, existing.controller_generation) != (
                    fence.controller_id,
                    fence.generation,
                ):
                    raise FenceRejected(
                        "launch reservation belongs to a retired controller lease"
                    )
                return existing
            raise InvalidTransition("a different launch operation is already reserved")
        generation = snapshot.next_runtime_generation
        snapshot.next_runtime_generation += 1
        reservation = LaunchReservation(
            switch.switch_id,
            operation_id,
            idempotency_key,
            generation,
            model,
            snapshot.gpu_uuid,
            snapshot.authority.digest,
            snapshot.authority.backend,
            fence.controller_id,
            fence.generation,
            now_ns,
        )
        snapshot.launch_reservation = reservation
        if rollback:
            switch.rollback_runtime_generation = generation
            switch.rollback_launch_operation_id = operation_id
        else:
            switch.target_runtime_generation = generation
            switch.target_launch_operation_id = operation_id
        return reservation

    def begin_start_b(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        operation_id: str,
        idempotency_key: str,
    ) -> LaunchReservation:
        def mutate(snapshot: MachineSnapshot, now_ns: int) -> LaunchReservation:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state == SwitchState.STARTING_B and snapshot.launch_reservation is not None:
                return copy.deepcopy(
                    self._reserve_launch(
                        snapshot,
                        now_ns,
                        fence,
                        switch,
                        model=switch.target_model,
                        operation_id=operation_id,
                        idempotency_key=idempotency_key,
                        rollback=False,
                    )
                )
            if snapshot.state != SwitchState.GPU_FREE:
                raise InvalidTransition("B can start only from GPU_FREE")
            if switch.cancelled or switch.failure_reason is not None:
                raise InvalidTransition("failed/cancelled switch cannot start B")
            if snapshot.active_runtime is not None or snapshot.last_reclaim_proof_sha256 is None:
                raise ProofRejected("B launch lacks clean GPU evidence")
            reservation = self._reserve_launch(
                snapshot,
                now_ns,
                fence,
                switch,
                model=switch.target_model,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                rollback=False,
            )
            snapshot.state = SwitchState.STARTING_B
            return copy.deepcopy(reservation)

        return self._commit("begin_start_b", fence, mutate)

    def bind_starting_runtime(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        runtime: RuntimeIdentity,
        launch_receipt: ActionReceipt,
    ) -> None:
        runtime.validate()

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.STARTING_B, SwitchState.ROLLING_BACK}:
                raise InvalidTransition("no launch is pending")
            reservation = snapshot.launch_reservation
            if reservation is None:
                raise ProofRejected("launch has no durable reservation")
            if (reservation.controller_id, reservation.controller_generation) != (
                fence.controller_id,
                fence.generation,
            ):
                raise FenceRejected(
                    "launch reservation belongs to a retired controller lease"
                )
            if snapshot.active_runtime is not None:
                if snapshot.active_runtime == runtime:
                    return
                raise InvalidTransition("second runtime allocation attempted")
            if (
                runtime.launch_operation_id,
                runtime.runtime_generation,
                runtime.model,
                runtime.gpu_uuid,
                runtime.authority.digest,
            ) != (
                reservation.operation_id,
                reservation.runtime_generation,
                reservation.model,
                reservation.gpu_uuid,
                reservation.authority_sha256,
            ):
                raise FenceRejected("runtime differs from durable launch reservation")
            launch_receipt.validate_for(
                switch_id=switch_id,
                operation="launch-runtime",
                subject_sha256=reservation.digest,
                authority=snapshot.authority,
                fence=fence,
                trust=self.evidence_trust,
            )
            if launch_receipt.idempotency_key != reservation.idempotency_key:
                raise ProofRejected("launch action idempotency key differs from reservation")
            if (
                launch_receipt.started_at_ns <= reservation.reserved_at_ns
                or launch_receipt.finished_at_ns > now_ns
            ):
                raise ProofRejected("launch action is not ordered after reservation and before bind")
            snapshot.active_runtime = runtime
            if snapshot.state == SwitchState.STARTING_B:
                switch.target_launch_receipt_sha256 = canonical_sha256(asdict(launch_receipt))
                switch.target_runtime_identity_sha256 = runtime.digest
            else:
                switch.rollback_launch_receipt_sha256 = canonical_sha256(asdict(launch_receipt))

        self._commit("bind_starting_runtime", fence, mutate)

    def _verify_ledger(
        self,
        receipt: LedgerGateReceipt,
        expectation: LedgerExpectation,
    ) -> VerifiedLedgerGate:
        if self.ledger_verifier is None:
            raise ProofRejected("no canonical ledger verifier is configured")
        receipt.validate_self()
        verified = self.ledger_verifier.verify(receipt, expectation)
        if verified.receipt_sha256 != receipt.receipt_sha256:
            raise ProofRejected("ledger verifier returned a different receipt")
        return verified

    def accept_b(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        ledger_receipt: LedgerGateReceipt,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.STARTING_B or snapshot.active_runtime is None:
                raise InvalidTransition("B runtime is not bound")
            if switch.cancelled or switch.failure_reason is not None:
                raise InvalidTransition("failed/cancelled B cannot be admitted")
            runtime = snapshot.active_runtime
            expectation = LedgerExpectation(
                LedgerStage.TARGET_QUALIFIED,
                switch.switch_id,
                switch.trace_id,
                switch.request_id,
                switch.attempt_id,
                switch.accepted_t0_ns,
                runtime,
                switch.target_validator,
                switch.target_launch_receipt_sha256,
            )
            verified = self._verify_ledger(ledger_receipt, expectation)
            bound_at = self._last_operation(snapshot, "bind_starting_runtime")
            if (
                verified.first_semantic_at_ns is None
                or verified.second_semantic_at_ns is None
                or verified.first_semantic_at_ns <= bound_at
                or verified.second_semantic_at_ns <= verified.first_semantic_at_ns
            ):
                raise ProofRejected("two semantic calls are not strictly after runtime bind")
            switch.target_qualified_receipt_sha256 = verified.receipt_sha256
            snapshot.serving_model = runtime.model
            snapshot.launch_reservation = None
            snapshot.admission_open = True
            snapshot.state = SwitchState.SERVING_B

        self._commit("accept_b", fence, mutate)

    def fail_start(self, fence: ControllerFence, *, switch_id: str, reason: str) -> None:
        if not reason:
            raise ValueError("start failure reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.STARTING_B, SwitchState.ROLLING_BACK}:
                raise InvalidTransition("no launch is pending")
            if snapshot.launch_reservation is None:
                raise ProofRejected("failed launch has no durable operation identity")
            switch.failure_reason = reason
            snapshot.admission_open = False
            snapshot.retired_runtime_generations.append(snapshot.launch_reservation.runtime_generation)
            snapshot.retired_runtime_generations = sorted(set(snapshot.retired_runtime_generations))
            snapshot.state = SwitchState.RECLAIMING_B

        self._commit("fail_start", fence, mutate)

    def mark_failed(self, fence: ControllerFence, *, switch_id: str, reason: str) -> None:
        if not reason:
            raise ValueError("failure reason must be nonempty")

        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.GPU_FREE or snapshot.launch_reservation is not None:
                raise InvalidTransition("failure requires exact clean GPU and no launch operation")
            switch.failure_reason = reason
            snapshot.state = SwitchState.FAILED

        self._commit("mark_failed", fence, mutate)

    def begin_rollback(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        failure_receipt: LedgerGateReceipt,
        recovery_trace_id: str,
        recovery_request_id: str,
        recovery_attempt_id: str,
        recovery_accepted_t0_ns: int,
        recovery_validator: ValidatorRef,
        operation_id: str,
        idempotency_key: str,
    ) -> LaunchReservation:
        recovery_validator.validate()
        for value, label in (
            (recovery_trace_id, "recovery_trace_id"),
            (recovery_request_id, "recovery_request_id"),
            (recovery_attempt_id, "recovery_attempt_id"),
        ):
            _require_id(value, label)
        if recovery_accepted_t0_ns < 1:
            raise ValueError("recovery external T0 must be positive")

        def mutate(snapshot: MachineSnapshot, now_ns: int) -> LaunchReservation:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state == SwitchState.ROLLING_BACK and snapshot.launch_reservation is not None:
                return copy.deepcopy(
                    self._reserve_launch(
                        snapshot,
                        now_ns,
                        fence,
                        switch,
                        model=switch.source_model,
                        operation_id=operation_id,
                        idempotency_key=idempotency_key,
                        rollback=True,
                    )
                )
            if snapshot.state not in {SwitchState.GPU_FREE, SwitchState.FAILED}:
                raise InvalidTransition("rollback requires clean GPU after failure")
            if snapshot.launch_reservation is not None or snapshot.active_runtime is not None:
                raise ProofRejected("rollback blocked by unresolved launch/runtime")
            if not (switch.cancelled or switch.failure_reason):
                raise InvalidTransition("successful switch cannot roll back")
            if (
                recovery_accepted_t0_ns <= switch.accepted_t0_ns
                or recovery_accepted_t0_ns > now_ns
            ):
                raise InvalidTransition(
                    "rollback recovery requires its own later external T0"
                )
            # The B failure is a separate, complete, denominator-retained trace.
            expected_runtime = RuntimeIdentity(
                runtime_uid=switch.source_runtime_uid,
                launch_operation_id=switch.target_launch_operation_id or "no-target-launch",
                runtime_generation=switch.target_runtime_generation or switch.source_runtime_generation,
                model=switch.target_model,
                gpu_uuid=snapshot.gpu_uuid,
                authority=snapshot.authority,
                host_pid=1,
                process_start_ticks=1,
                cgroup_path="/failure-receipt-placeholder",
            )
            # Ledger identity/model/generation is checked; no runtime absence is inferred from
            # this placeholder (cleanup proofs above are the sole reclaim authority).
            expectation = LedgerExpectation(
                LedgerStage.TARGET_FAILED,
                switch.switch_id,
                switch.trace_id,
                switch.request_id,
                switch.attempt_id,
                switch.accepted_t0_ns,
                expected_runtime,
                switch.target_validator,
                switch.target_launch_receipt_sha256,
                runtime_identity_sha256_override=switch.target_runtime_identity_sha256,
            )
            verified = self._verify_ledger(failure_receipt, expectation)
            switch.target_failure_receipt_sha256 = verified.receipt_sha256
            switch.rollback_trace_id = recovery_trace_id
            switch.rollback_request_id = recovery_request_id
            switch.rollback_attempt_id = recovery_attempt_id
            switch.rollback_accepted_t0_ns = recovery_accepted_t0_ns
            switch.rollback_validator = recovery_validator
            reservation = self._reserve_launch(
                snapshot,
                now_ns,
                fence,
                switch,
                model=switch.source_model,
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                rollback=True,
            )
            snapshot.state = SwitchState.ROLLING_BACK
            return copy.deepcopy(reservation)

        return self._commit("begin_rollback", fence, mutate)

    def accept_rollback(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        ledger_receipt: LedgerGateReceipt,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            runtime = snapshot.active_runtime
            if snapshot.state != SwitchState.ROLLING_BACK or runtime is None:
                raise InvalidTransition("rollback runtime is not bound")
            if runtime.model != switch.source_model or switch.rollback_validator is None:
                raise FenceRejected("rollback model/validator differs")
            if not all((switch.rollback_trace_id, switch.rollback_request_id, switch.rollback_attempt_id)):
                raise ProofRejected("rollback recovery trace identity is incomplete")
            if switch.rollback_accepted_t0_ns is None:
                raise ProofRejected("rollback recovery external T0 is missing")
            expectation = LedgerExpectation(
                LedgerStage.ROLLBACK_QUALIFIED,
                switch.switch_id,
                str(switch.rollback_trace_id),
                str(switch.rollback_request_id),
                str(switch.rollback_attempt_id),
                switch.rollback_accepted_t0_ns,
                runtime,
                switch.rollback_validator,
                switch.rollback_launch_receipt_sha256,
                predecessor_receipt_sha256=switch.target_failure_receipt_sha256,
            )
            verified = self._verify_ledger(ledger_receipt, expectation)
            bound_at = self._last_operation(snapshot, "bind_starting_runtime")
            if (
                verified.first_semantic_at_ns is None
                or verified.second_semantic_at_ns is None
                or verified.first_semantic_at_ns <= bound_at
                or verified.second_semantic_at_ns <= verified.first_semantic_at_ns
            ):
                raise ProofRejected("rollback semantic calls are not ordered after bind")
            switch.rollback_qualified_receipt_sha256 = verified.receipt_sha256
            snapshot.serving_model = runtime.model
            snapshot.launch_reservation = None
            snapshot.admission_open = True
            snapshot.state = SwitchState.ROLLBACK_SERVING

        self._commit("accept_rollback", fence, mutate)

    def seal_switch(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        ledger_receipt: LedgerGateReceipt,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state not in {SwitchState.SERVING_B, SwitchState.ROLLBACK_SERVING}:
                raise InvalidTransition("only an accepted runtime can be sealed")
            runtime = snapshot.active_runtime
            if runtime is None:
                raise ProofRejected("sealed switch lacks runtime")
            rollback = snapshot.state == SwitchState.ROLLBACK_SERVING
            validator = switch.rollback_validator if rollback else switch.target_validator
            if validator is None:
                raise ProofRejected("sealed switch lacks validator")
            predecessor = (
                switch.rollback_qualified_receipt_sha256
                if rollback
                else switch.target_qualified_receipt_sha256
            )
            expectation = LedgerExpectation(
                LedgerStage.SWITCH_SEALED,
                switch.switch_id,
                str(switch.rollback_trace_id) if rollback else switch.trace_id,
                str(switch.rollback_request_id) if rollback else switch.request_id,
                str(switch.rollback_attempt_id) if rollback else switch.attempt_id,
                (
                    switch.rollback_accepted_t0_ns
                    if rollback
                    else switch.accepted_t0_ns
                ),
                runtime,
                validator,
                switch.rollback_launch_receipt_sha256 if rollback else switch.target_launch_receipt_sha256,
                predecessor_receipt_sha256=predecessor,
            )
            verified = self._verify_ledger(ledger_receipt, expectation)
            switch.sealed_receipt_sha256 = verified.receipt_sha256
            snapshot.last_ledger_receipt_sha256 = verified.receipt_sha256
            snapshot.last_completed_switch_id = switch.switch_id
            snapshot.active_switch = None
            snapshot.state = SwitchState.SERVING_A

        self._commit("seal_switch", fence, mutate)

    def begin_quarantine_recovery(self, fence: ControllerFence, *, switch_id: str) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.QUARANTINED:
                raise InvalidTransition("node is not quarantined")
            snapshot.state = SwitchState.QUARANTINE_REVOKING

        self._commit("begin_quarantine_recovery", fence, mutate)

    def record_quarantine_revocation(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        receipt: ActionReceipt,
        proof: PlacementRevocationProof,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, now_ns: int) -> None:
            self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.QUARANTINE_REVOKING:
                raise InvalidTransition("quarantine lease revocation is not pending")
            receipt.validate_for(
                switch_id=switch_id,
                operation="revoke-placement-lease",
                subject_sha256=snapshot.authority.placement_subject_sha256,
                authority=snapshot.authority,
                fence=fence,
                trust=self.evidence_trust,
            )
            proof.validate_for(switch_id, snapshot.authority, self.evidence_trust)
            if (
                receipt.finished_at_ns >= proof.revoked_at_ns
                or proof.placement_refusal_observed_at_ns > now_ns
            ):
                raise ProofRejected(
                    "broker revocation/refusal must follow local admission closure"
                )
            snapshot.quarantine_revocation_proof_sha256 = canonical_sha256(
                {"local_action": asdict(receipt), "broker_proof": asdict(proof)}
            )
            snapshot.state = SwitchState.RECYCLING_NODE

        self._commit("record_quarantine_revocation", fence, mutate)

    def record_node_recycle(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        proof: NodeRecycleProof,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.RECYCLING_NODE:
                raise InvalidTransition("node recycle is not pending")
            old = snapshot.quarantine_old_authority or snapshot.authority
            proof.validate_for(
                switch_id, old, snapshot.gpu_uuid, self.evidence_trust
            )
            snapshot.node_recycle_proof_sha256 = canonical_sha256(asdict(proof))
            snapshot.authority = proof.new_authority
            snapshot.gpu_uuid = proof.new_gpu_uuid
            snapshot.active_runtime = None
            snapshot.serving_model = None
            snapshot.launch_reservation = None
            snapshot.state = SwitchState.REQUALIFYING_NODE

        self._commit("record_node_recycle", fence, mutate)

    def record_requalification(
        self,
        fence: ControllerFence,
        *,
        switch_id: str,
        proof: RequalificationProof,
    ) -> None:
        def mutate(snapshot: MachineSnapshot, _: int) -> None:
            switch = self._require_switch(snapshot, switch_id)
            if snapshot.state != SwitchState.REQUALIFYING_NODE:
                raise InvalidTransition("replacement node is not awaiting requalification")
            proof.validate_for(
                switch_id,
                snapshot.authority,
                snapshot.gpu_uuid,
                self.evidence_trust,
            )
            digest = canonical_sha256(asdict(proof))
            snapshot.requalification_proof_sha256 = digest
            snapshot.last_reclaim_proof_sha256 = digest
            switch.reclaim_proof_sha256 = digest
            snapshot.quarantine_reason = None
            snapshot.quarantine_old_authority = None
            snapshot.state = SwitchState.GPU_FREE

        self._commit("record_requalification", fence, mutate)

    @staticmethod
    def _require_switch(snapshot: MachineSnapshot, switch_id: str) -> SwitchRecord:
        if snapshot.active_switch is None or snapshot.active_switch.switch_id != switch_id:
            raise FenceRejected("switch identity is stale or unknown")
        return snapshot.active_switch

    @staticmethod
    def _last_entered(snapshot: MachineSnapshot, state: SwitchState) -> int:
        for transition in reversed(snapshot.transitions):
            if transition.to_state == state.value:
                return transition.at_ns
        raise ProofRejected(f"no durable transition into {state.value}")

    @staticmethod
    def _last_operation(snapshot: MachineSnapshot, operation: str) -> int:
        for transition in reversed(snapshot.transitions):
            if transition.operation == operation:
                return transition.at_ns
        raise ProofRejected(f"no durable {operation} transition")

    @staticmethod
    def _validate_snapshot(snapshot: MachineSnapshot) -> None:
        if snapshot.schema != STATE_SCHEMA or snapshot.revision < 0:
            raise StateMachineError("snapshot schema/revision is invalid")
        snapshot.authority.validate()
        _require_id(snapshot.gpu_uuid, "snapshot.gpu_uuid")
        if snapshot.controller_generation < 0 or snapshot.next_runtime_generation < 1:
            raise StateMachineError("generation counters are invalid")
        if (snapshot.controller_id is None) != (snapshot.controller_generation == 0):
            raise StateMachineError("controller identity/generation is inconsistent")
        if snapshot.active_runtime is not None:
            snapshot.active_runtime.validate()
            if snapshot.active_runtime.authority != snapshot.authority:
                raise StateMachineError("active runtime authority differs from node")
            if snapshot.active_runtime.gpu_uuid != snapshot.gpu_uuid:
                raise StateMachineError("active runtime GPU differs")
        if snapshot.launch_reservation is not None:
            snapshot.launch_reservation.validate()
            if (
                snapshot.launch_reservation.authority_sha256 != snapshot.authority.digest
                or snapshot.launch_reservation.gpu_uuid != snapshot.gpu_uuid
            ):
                raise StateMachineError("launch reservation authority/GPU differs")
        serving = {SwitchState.SERVING_A, SwitchState.SERVING_B, SwitchState.ROLLBACK_SERVING}
        if snapshot.admission_open != (snapshot.state in serving):
            raise StateMachineError("admission gate differs from serving state")
        if snapshot.state in serving and (
            snapshot.active_runtime is None
            or snapshot.serving_model != snapshot.active_runtime.model
        ):
            raise StateMachineError("serving state lacks exact runtime/model")
        if snapshot.state in {SwitchState.STARTING_B, SwitchState.ROLLING_BACK, SwitchState.RECLAIMING_B}:
            if snapshot.launch_reservation is None:
                raise StateMachineError("launch lifecycle state lacks durable reservation")
        if snapshot.state in {SwitchState.GPU_FREE, SwitchState.FAILED}:
            if snapshot.active_runtime is not None or snapshot.serving_model is not None:
                raise StateMachineError("GPU-free/failed state still owns runtime")
            if snapshot.launch_reservation is not None:
                raise StateMachineError("GPU-free/failed state has unresolved launch operation")
            if snapshot.last_reclaim_proof_sha256 is None:
                raise StateMachineError("GPU-free/failed state lacks reclaim proof")
        if snapshot.state == SwitchState.IDLE and (
            snapshot.active_runtime is not None or snapshot.active_switch is not None
        ):
            raise StateMachineError("IDLE cannot own runtime/switch")
        lifecycle = set(SwitchState) - {SwitchState.IDLE, SwitchState.SERVING_A}
        if snapshot.state in lifecycle and snapshot.active_switch is None:
            raise StateMachineError("switch lifecycle state lacks switch identity")
        active_generations = {
            lease.runtime_generation
            for lease in snapshot.request_leases.values()
            if lease.status == LeaseStatus.ACTIVE
        }
        if snapshot.active_runtime is None and active_generations:
            raise StateMachineError("active lease exists without runtime")
        if snapshot.active_runtime is not None and any(
            generation != snapshot.active_runtime.runtime_generation
            for generation in active_generations
        ):
            raise StateMachineError("active lease belongs to another generation")
        if set(snapshot.retired_runtime_generations) & active_generations:
            raise StateMachineError("retired generation still has active lease")
        for digest, label in (
            (snapshot.last_reclaim_proof_sha256, "last reclaim proof"),
            (snapshot.last_ledger_receipt_sha256, "last ledger receipt"),
            (
                snapshot.quarantine_revocation_proof_sha256,
                "quarantine revocation proof",
            ),
            (snapshot.node_recycle_proof_sha256, "node recycle proof"),
            (snapshot.requalification_proof_sha256, "requalification proof"),
        ):
            if digest is not None:
                _require_digest(digest, label)
        previous = "0" * 64
        if len(snapshot.transitions) != snapshot.revision:
            raise StateMachineError("transition chain does not cover every revision")
        for expected_revision, transition in enumerate(snapshot.transitions, 1):
            if transition.revision != expected_revision or transition.previous_sha256 != previous:
                raise StateMachineError("transition revision/predecessor differs")
            if transition.detail_sha256 != canonical_sha256(transition.state_after):
                raise StateMachineError("transition state detail digest differs")
            if transition.state_after.get("revision") != expected_revision:
                raise StateMachineError("transition state detail revision differs")
            if transition.state_after.get("state") != transition.to_state:
                raise StateMachineError("transition state detail target differs")
            payload = {
                "revision": transition.revision,
                "at_ns": transition.at_ns,
                "controller_generation": transition.controller_generation,
                "operation": transition.operation,
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "state_after": transition.state_after,
                "detail_sha256": transition.detail_sha256,
                "previous_sha256": transition.previous_sha256,
            }
            if transition.record_sha256 != canonical_sha256(payload):
                raise StateMachineError("transition record hash differs")
            previous = transition.record_sha256
        if snapshot.transitions and snapshot.transitions[-1].state_after != _snapshot_detail(snapshot):
            raise StateMachineError("current snapshot differs from hash-bound transition detail")


STATE_SEMANTICS = {
    "IDLE": {"admission": "closed", "runtime": "absent"},
    "SERVING_A": {"admission": "open", "runtime": "exactly-one-bootstrap-or-ledger-qualified"},
    "DRAINING_A": {"admission": "closed", "runtime": "exactly-one-draining"},
    "RECLAIMING_A": {"admission": "closed", "runtime": "exactly-one-until-absence-and-zero"},
    "GPU_FREE": {"admission": "closed", "runtime": "absent-with-exact-zero-proof"},
    "STARTING_B": {"admission": "closed", "runtime": "zero-or-one-with-durable-operation"},
    "SERVING_B": {"admission": "open", "runtime": "exactly-one-two-call-ledger-qualified"},
    "FAILED": {"admission": "closed", "runtime": "absent-awaiting-canonical-failure-ledger"},
    "RECLAIMING_B": {"admission": "closed", "runtime": "zero-or-one-operation-unresolved"},
    "ROLLING_BACK": {"admission": "closed", "runtime": "zero-or-one-with-durable-operation"},
    "ROLLBACK_SERVING": {"admission": "open", "runtime": "exactly-one-linked-recovery-qualified"},
    "QUARANTINED": {"admission": "closed", "runtime": "unknown-placement-revocation-required"},
    "QUARANTINE_REVOKING": {"admission": "closed", "runtime": "unknown-lease-revocation-pending"},
    "RECYCLING_NODE": {"admission": "closed", "runtime": "old-authority-revoked-new-resource-pending"},
    "REQUALIFYING_NODE": {"admission": "closed", "runtime": "new-boot-control-suite-pending"},
}
PROOF_GATE_SPEC = {
    "active_scrub_methods": list(APPROVED_SCRUB_METHODS),
    "runtime_absence_required": [
        "exact-process-generation-absent",
        "exact-cgroup-empty-or-absent",
        "exact-container-absent",
        "exact-pod-uid-absent-for-kubernetes",
        "mounts-absent",
        "namespaces-absent",
        "credentials-revoked",
        "kernel-residue-safe",
        "logs-purged",
        "sockets-absent",
    ],
    "nvml_samples": 2,
    "memory_rule": ZERO_MEMORY_RULE,
    "semantic_calls": 2,
    "quarantine_recovery_required": [
        "placement-lease-absent",
        "new-placement-refused",
        "old-resource-absent",
        "new-resource-created",
        "new-resource-identity",
        "fresh-node-boot-identity",
        "gpu-identity-rebound",
        "sentinel-vram-absent",
        "host-residue-absent",
        "exclusive-occupancy-enforced",
        "direct-launch-refused",
        "audit-offnode-continuity",
        "command-replay-refused",
        "two-zero-process-zero-graphics-zero-byte-nvml-samples",
    ],
}
TRANSITION_OPERATIONS = {
    "claim_controller",
    "install_serving_a",
    "admit_request",
    "complete_response",
    "cancel_request",
    "begin_switch",
    "cancel_switch",
    "advance_drain",
    "record_reclaim",
    "record_ambiguous_launch_cleanup",
    "reject_reclaim_proof",
    "begin_start_b",
    "bind_starting_runtime",
    "accept_b",
    "fail_start",
    "mark_failed",
    "begin_rollback",
    "accept_rollback",
    "seal_switch",
    "begin_quarantine_recovery",
    "record_quarantine_revocation",
    "record_node_recycle",
    "record_requalification",
}
TRANSITION_SPECS = {
    "install_serving_a": {"from": ["IDLE"], "to": ["SERVING_A"]},
    "begin_switch": {"from": ["SERVING_A"], "to": ["DRAINING_A"]},
    "advance_drain": {"from": ["DRAINING_A"], "to": ["DRAINING_A", "RECLAIMING_A"]},
    "record_reclaim": {"from": ["RECLAIMING_A", "RECLAIMING_B"], "to": ["GPU_FREE"]},
    "record_ambiguous_launch_cleanup": {"from": ["RECLAIMING_B"], "to": ["GPU_FREE"]},
    "reject_reclaim_proof": {"from": ["RECLAIMING_A", "RECLAIMING_B"], "to": ["QUARANTINED"]},
    "begin_start_b": {"from": ["GPU_FREE", "STARTING_B"], "to": ["STARTING_B"]},
    "bind_starting_runtime": {"from": ["STARTING_B", "ROLLING_BACK"], "to": ["STARTING_B", "ROLLING_BACK"]},
    "accept_b": {"from": ["STARTING_B"], "to": ["SERVING_B"]},
    "fail_start": {"from": ["STARTING_B", "ROLLING_BACK"], "to": ["RECLAIMING_B"]},
    "mark_failed": {"from": ["GPU_FREE"], "to": ["FAILED"]},
    "begin_rollback": {"from": ["GPU_FREE", "FAILED", "ROLLING_BACK"], "to": ["ROLLING_BACK"]},
    "accept_rollback": {"from": ["ROLLING_BACK"], "to": ["ROLLBACK_SERVING"]},
    "seal_switch": {"from": ["SERVING_B", "ROLLBACK_SERVING"], "to": ["SERVING_A"]},
    "begin_quarantine_recovery": {"from": ["QUARANTINED"], "to": ["QUARANTINE_REVOKING"]},
    "record_quarantine_revocation": {"from": ["QUARANTINE_REVOKING"], "to": ["RECYCLING_NODE"]},
    "record_node_recycle": {"from": ["RECYCLING_NODE"], "to": ["REQUALIFYING_NODE"]},
    "record_requalification": {"from": ["REQUALIFYING_NODE"], "to": ["GPU_FREE"]},
}


__all__ = [name for name in globals() if not name.startswith("_")]
