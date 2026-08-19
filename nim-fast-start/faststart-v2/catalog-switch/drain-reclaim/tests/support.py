from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FASTSTART = ROOT.parents[1]
for path in (ROOT, FASTSTART):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from performance.request_slo.harness import (  # noqa: E402
    SCENARIOS,
    TRACE_SCHEMA,
    T0_BOUNDARY,
    append_event,
    canonical_sha256 as harness_sha256,
)
from state_machine import (  # noqa: E402
    ABSENCE_SCHEMA,
    ACTION_RECEIPT_SCHEMA,
    GPU_RELEASE_SCHEMA,
    OPERATION_ABSENCE_SCHEMA,
    RECYCLE_SCHEMA,
    REQUALIFICATION_SCHEMA,
    SCRUB_SCHEMA,
    ActionReceipt,
    ControllerFence,
    EvidenceTrustStore,
    GpuReleaseProof,
    LaunchOperationAbsenceProof,
    LaunchReservation,
    ModelRef,
    NodeRecycleProof,
    NvmlObservation,
    RequalificationProof,
    RuntimeAbsenceProof,
    RuntimeAuthority,
    RuntimeIdentity,
    ScrubReceipt,
    ValidatorRef,
    canonical_sha256,
    key_sha256,
    sign_payload,
)


GPU_UUID = "GPU-00000000-0000-0000-0000-000000000001"
TOTAL_BYTES = 80 * 1024 * 1024 * 1024
NODE_KEY = b"node-agent-test-key-32-bytes!!"
NEW_NODE_KEY = b"new-node-agent-key-32-bytes!!!"
BROKER_KEY = b"resource-broker-test-key-32b"
CONTROLLER_KEY = b"controller-test-key-32-bytes!"
SINK_KEY = b"offnode-sink-test-key-32bytes"
MODEL_A = ModelRef("model-a", "1", "a" * 64)
MODEL_B = ModelRef("model-b", "2", "b" * 64)


def validator_source(model: ModelRef) -> bytes:
    return (
        json.dumps(
            {
                "kind": "strict-json-response-field",
                "model_id": model.model_id,
                "model_version": model.model_version,
                "required_response_fields": ["model_id", "model_version", "valid"],
                "schema": "archvteams.nebius.ai/catalog-switch-json-semantic-validator/v1",
                "validity_field": "valid",
                "validity_value": True,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


VALIDATOR_A_SOURCE = validator_source(MODEL_A)
VALIDATOR_B_SOURCE = validator_source(MODEL_B)
VALIDATOR_A = ValidatorRef(
    "validator-a-v1",
    "artifact://validators/a.json",
    hashlib.sha256(VALIDATOR_A_SOURCE).hexdigest(),
)
VALIDATOR_B = ValidatorRef(
    "validator-b-v1",
    "artifact://validators/b.json",
    hashlib.sha256(VALIDATOR_B_SOURCE).hexdigest(),
)


def node_authority(
    *,
    boot: str = "boot-node-1",
    key: bytes = NODE_KEY,
    node_id: str = "node-1",
    node_uid: str = "node-uid-1",
) -> RuntimeAuthority:
    return RuntimeAuthority(
        backend="node-local",
        node_id=node_id,
        node_uid=node_uid,
        node_boot_id=boot,
        placement_lease_id=f"placement-{boot}",
        node_agent_id="node-agent-1" if key == NODE_KEY else "node-agent-2",
        node_agent_key_sha256=key_sha256(key),
        node_agent_source_sha256=hashlib.sha256(
            b"catalog-switch-node-agent-reference-v2"
        ).hexdigest(),
    )


def k8s_authority(
    *,
    kubeconfig_sha256: str,
    kubectl_executable_sha256: str,
    ca_data: bytes = b"test-ca",
) -> RuntimeAuthority:
    return RuntimeAuthority(
        backend="kubernetes",
        node_id="gpu-node-1",
        node_uid="k8s-node-uid-1",
        node_boot_id="k8s-boot-1",
        placement_lease_id="placement-k8s-boot-1",
        node_agent_id="k8s-node-agent-1",
        node_agent_key_sha256=key_sha256(NODE_KEY),
        node_agent_source_sha256=hashlib.sha256(
            b"catalog-switch-k8s-node-agent-reference-v2"
        ).hexdigest(),
        cluster_uid="cluster-uid-1",
        kube_context="mlspec-catswitch-k8s",
        kubeconfig_sha256=kubeconfig_sha256,
        api_server_url="https://api.fresh-cluster.example:443",
        server_ca_sha256=hashlib.sha256(ca_data).hexdigest(),
        kubectl_executable_sha256=kubectl_executable_sha256,
        namespace="mlspec-catswitch-drain",
    )


class FakeClock:
    def __init__(self, value: int = 1_000_000):
        self.value = value

    def __call__(self) -> int:
        self.value += 100
        return self.value

    def advance(self, amount: int) -> None:
        self.value += amount


def runtime(
    model: ModelRef,
    generation: int,
    *,
    operation_id: str,
    suffix: str,
    authority: RuntimeAuthority | None = None,
) -> RuntimeIdentity:
    authority = authority or node_authority()
    kwargs = {}
    if authority.backend == "kubernetes":
        kwargs = {
            "container_id": f"containerd://sha256:{suffix}",
            "pod_uid": f"pod-uid-{suffix}",
            "pod_name": f"pod-{suffix}",
        }
    return RuntimeIdentity(
        runtime_uid=f"runtime-{suffix}",
        launch_operation_id=operation_id,
        runtime_generation=generation,
        model=model,
        gpu_uuid=GPU_UUID,
        authority=authority,
        host_pid=1000 + generation,
        process_start_ticks=9000 + generation,
        cgroup_path=f"/catalog-switch/{suffix}",
        **kwargs,
    )


def signed_action(
    *,
    switch_id: str,
    operation: str,
    subject_sha256: str,
    authority: RuntimeAuthority,
    fence: ControllerFence,
    started: int,
    key: bytes = NODE_KEY,
    source_id: str | None = None,
    idempotency_key: str | None = None,
) -> ActionReceipt:
    payload = {
        "schema": ACTION_RECEIPT_SCHEMA,
        "switch_id": switch_id,
        "operation": operation,
        "subject_sha256": subject_sha256,
        "command_envelope_sha256": "3" * 64,
        "controller_id": fence.controller_id,
        "controller_lease_id": fence.lease_id,
        "controller_generation": fence.generation,
        "idempotency_key": idempotency_key or f"idem-{operation}-{started}",
        "source_authority_sha256": authority.digest,
        "source_id": source_id or authority.node_agent_id,
        "source_key_sha256": key_sha256(key),
        "started_at_ns": started,
        "finished_at_ns": started + 1,
        "outcome": "completed",
        "result_attestation": None,
        "raw_evidence_sha256": "4" * 64,
    }
    return ActionReceipt(**payload, signature_sha256=sign_payload(key, payload))


def signed_absence(
    *,
    switch_id: str,
    target: RuntimeIdentity,
    observed_at: int,
    key: bytes = NODE_KEY,
) -> RuntimeAbsenceProof:
    payload = {
        "schema": ABSENCE_SCHEMA,
        "switch_id": switch_id,
        "runtime_identity_sha256": target.digest,
        "runtime_uid": target.runtime_uid,
        "runtime_generation": target.runtime_generation,
        "authority_sha256": target.authority.digest,
        "source_id": target.authority.node_agent_id,
        "source_key_sha256": key_sha256(key),
        "observed_at_ns": observed_at,
        "process_absent": True,
        "cgroup_empty": True,
        "container_absent": True,
        "pod_absent": True if target.backend == "kubernetes" else None,
        "mounts_absent": True,
        "namespaces_absent": True,
        "credentials_revoked": True,
        "kernel_residue_safe": True,
        "logs_purged": True,
        "sockets_absent": True,
        "raw_evidence_sha256": "5" * 64,
    }
    return RuntimeAbsenceProof(**payload, signature_sha256=sign_payload(key, payload))


def signed_operation_absence(
    *,
    switch_id: str,
    reservation: LaunchReservation,
    authority: RuntimeAuthority,
    observed_at: int,
    key: bytes = NODE_KEY,
) -> LaunchOperationAbsenceProof:
    payload = {
        "schema": OPERATION_ABSENCE_SCHEMA,
        "switch_id": switch_id,
        "reservation_sha256": reservation.digest,
        "operation_id": reservation.operation_id,
        "runtime_generation": reservation.runtime_generation,
        "authority_sha256": authority.digest,
        "source_id": authority.node_agent_id,
        "source_key_sha256": key_sha256(key),
        "observed_at_ns": observed_at,
        "launch_journal_terminal": "cleaned",
        "process_absent": True,
        "cgroup_absent": True,
        "container_absent": True,
        "pod_absent": True if authority.backend == "kubernetes" else None,
        "mounts_absent": True,
        "namespaces_absent": True,
        "credentials_revoked": True,
        "kernel_residue_safe": True,
        "raw_evidence_sha256": "6" * 64,
    }
    return LaunchOperationAbsenceProof(**payload, signature_sha256=sign_payload(key, payload))


def signed_gpu_release(
    *,
    switch_id: str,
    subject_sha256: str,
    authority: RuntimeAuthority,
    absence_at: int,
    total_bytes: int = TOTAL_BYTES,
    bytes_scrubbed: int | None = None,
    used_bytes: int = 0,
    compute_pids: tuple[int, ...] = (),
    graphics_pids: tuple[int, ...] = (),
    graphics_supported: bool = True,
    key: bytes = NODE_KEY,
) -> GpuReleaseProof:
    bytes_scrubbed = total_bytes if bytes_scrubbed is None else bytes_scrubbed
    scrub = ScrubReceipt(
        SCRUB_SCHEMA,
        switch_id,
        subject_sha256,
        GPU_UUID,
        "full-vram-zero",
        bytes_scrubbed,
        total_bytes,
        absence_at + 1,
        absence_at + 2,
        True,
        "7" * 64,
    )
    observations = (
        NvmlObservation(absence_at + 3, GPU_UUID, compute_pids, graphics_pids, graphics_supported, used_bytes, total_bytes),
        NvmlObservation(absence_at + 4, GPU_UUID, (), (), graphics_supported, used_bytes, total_bytes),
    )
    payload = {
        "schema": GPU_RELEASE_SCHEMA,
        "switch_id": switch_id,
        "subject_sha256": subject_sha256,
        "authority_sha256": authority.digest,
        "gpu_uuid": GPU_UUID,
        "source_id": authority.node_agent_id,
        "source_key_sha256": key_sha256(key),
        "observations": observations,
        "scrub": scrub,
        "raw_evidence_sha256": "8" * 64,
    }
    serializable = copy.deepcopy(payload)
    serializable["observations"] = [asdict(item) for item in observations]
    serializable["scrub"] = asdict(scrub)
    return GpuReleaseProof(**payload, signature_sha256=sign_payload(key, serializable))


def reclaim_bundle(
    *,
    switch_id: str,
    target: RuntimeIdentity,
    fence: ControllerFence,
    reclaim_started: int,
) -> tuple[ActionReceipt, RuntimeAbsenceProof, GpuReleaseProof]:
    stop = signed_action(
        switch_id=switch_id,
        operation="stop-runtime",
        subject_sha256=target.digest,
        authority=target.authority,
        fence=fence,
        started=reclaim_started + 1,
    )
    absence = signed_absence(switch_id=switch_id, target=target, observed_at=reclaim_started + 3)
    gpu = signed_gpu_release(
        switch_id=switch_id,
        subject_sha256=target.digest,
        authority=target.authority,
        absence_at=absence.observed_at_ns,
    )
    return stop, absence, gpu


def trust_store(*, authority: RuntimeAuthority | None = None) -> EvidenceTrustStore:
    authority = authority or node_authority()
    keys = {
        "node-agent-1": NODE_KEY,
        "node-agent-2": NEW_NODE_KEY,
        "k8s-node-agent-1": NODE_KEY,
        "resource-broker": BROKER_KEY,
    }
    keys[authority.node_agent_id] = (
        NODE_KEY
        if authority.node_agent_key_sha256 == key_sha256(NODE_KEY)
        else NEW_NODE_KEY
    )
    return EvidenceTrustStore(keys)


def recorder() -> dict:
    return {
        "recorder_id": "external-recorder-1",
        "clock_id": "linux-boottime:test",
        "boot_id": "recorder-boot-1",
        "utc_sync_source": "test-clock",
        "max_error_ms": 1.0,
    }


def make_trace(
    raw_first_request: bytes,
    *,
    model: ModelRef = MODEL_B,
    trace_id: str = "switch-trace-1",
    request_id: str = "switch-request-1",
    attempt_id: str = "switch-attempt-1",
    occupant: ModelRef = MODEL_A,
) -> dict:
    request = {
        "sequence": 0,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "offered_at_offset_ms": 0,
        "scenario": "a_to_b_local",
        "target": {
            "model_id": model.model_id,
            "model_version": model.model_version,
            "artifact_id": f"artifact-{model.model_id}",
            "artifact_version": model.model_version,
            "artifact_sha256": model.artifact_sha256,
        },
        "input": {
            "workload_id": "semantic-call-1",
            "input_id": "input-1",
            "payload_sha256": hashlib.sha256(raw_first_request).hexdigest(),
            "input_bytes": len(raw_first_request),
        },
        "precondition": {
            "current_node_occupant": {
                "model_id": occupant.model_id,
                "model_version": occupant.model_version,
            },
            "cache": {"image": "local_verified", "artifact": "node_local_hit", "checkpoint": "compatible_hit", "storage": "ready"},
            "capacity": "allocated",
            "queue_depth": 1,
        },
    }
    trace = {
        "schema": TRACE_SCHEMA,
        "trace_id": trace_id,
        "distribution": "adversarial",
        "seed": 7,
        "catalog_sha256": "c" * 64,
        "request_count": 1,
        "scenario_labels": list(SCENARIOS),
        "requests": [request],
    }
    trace["trace_sha256"] = harness_sha256(trace)
    return trace


def acceptance_data(trace: dict) -> dict:
    request = trace["requests"][0]
    return {
        "boundary": T0_BOUNDARY,
        "trace_request_sha256": harness_sha256(request),
        "scenario": request["scenario"],
        "target": request["target"],
        "input": request["input"],
        "precondition": request["precondition"],
        "environment": {
            "backend": "node-vm",
            "backend_version": "drain-reclaim-v5",
            "provider": "local-test",
            "project_id": "local-test",
            "region": "local",
            "node_id": "node-1",
            "gpu_type": "H100",
            "gpu_count": 1,
            "image_digest": None,
            "code_revision": "0" * 40,
            "config_sha256": "d" * 64,
            "experiment_id": "drain-reclaim-v5-test",
        },
        "ownership": {
            "owner_task_id": "catalog-switch-drain-reclaim-state-machine",
            "resource_prefix": "local-test",
            "dedicated": True,
            "cleanup_required": False,
            "resources": [],
        },
    }


def write_acceptance(
    path: Path,
    trace: dict,
    *,
    ledger_id: str = "drain-reclaim-ledger-1",
) -> None:
    request = trace["requests"][0]
    append_event(
        path,
        ledger_id=ledger_id,
        trace_id=trace["trace_id"],
        request_id=request["request_id"],
        attempt_id=request["attempt_id"],
        recorder=recorder(),
        event_type="request.accepted",
        data=acceptance_data(trace),
    )


def exact_acceptance_gate(
    root: Path,
    *,
    switch_id: str = "switch-1",
    trace_id: str = "switch-trace-1",
    request_id: str = "switch-request-1",
    attempt_id: str = "switch-attempt-1",
    target: ModelRef = MODEL_B,
) -> tuple[object, object, object]:
    """Build the real shared-ledger bridge/verifier gate for state tests."""

    from ledger import (  # noqa: PLC0415 - prevents test-support import cycle
        ExactLedgerReceiptVerifier,
        FileOffNodeSink,
        SwitchLedgerBridge,
        ValidatorRuntime,
    )

    ledger_path = root / "shared.jsonl"
    audit_path = root / "audit.jsonl"
    evidence_root = root / "evidence"
    raw_request = (
        json.dumps(
            {"attempt_id": attempt_id, "input": "external-switch-request"},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")
    trace = make_trace(
        raw_request,
        model=target,
        trace_id=trace_id,
        request_id=request_id,
        attempt_id=attempt_id,
    )
    write_acceptance(ledger_path, trace)
    source = validator_source(target)
    validator_ref = VALIDATOR_B if target == MODEL_B else VALIDATOR_A
    validator_runtime = ValidatorRuntime(validator_ref, source)
    sink = FileOffNodeSink(
        root / "offnode",
        sink_id="offnode-test-sink",
        key=SINK_KEY,
    )
    bridge = SwitchLedgerBridge(
        path=ledger_path,
        audit_path=audit_path,
        evidence_root=evidence_root,
        trace=trace,
        ledger_id="drain-reclaim-ledger-1",
        switch_id=switch_id,
        request_id=request_id,
        attempt_id=attempt_id,
        recorder=recorder(),
        validator_runtime=validator_runtime,
        offnode_sink=sink,
    )
    receipt = bridge.acceptance_receipt()
    verifier = ExactLedgerReceiptVerifier(
        ledger_path=ledger_path,
        audit_path=audit_path,
        evidence_root=evidence_root,
        trace=trace,
        validator_runtimes={validator_ref.source_sha256: validator_runtime},
        durability_keys={"offnode-test-sink": SINK_KEY},
        allow_isolated_test_sink=True,
    )
    return receipt, verifier, bridge


def clean_host_assertions(_runtime_uid: str) -> dict[str, bool]:
    return {
        "mounts_absent": True,
        "namespaces_absent": True,
        "credentials_revoked": True,
        "kernel_residue_safe": True,
        "logs_purged": True,
        "sockets_absent": True,
    }


def clean_operation_assertions(_operation_id: str) -> dict[str, object]:
    return {
        "launch_journal_terminal": "cleaned",
        "process_absent": True,
        "cgroup_absent": True,
        "container_absent": True,
        "mounts_absent": True,
        "namespaces_absent": True,
        "credentials_revoked": True,
        "kernel_residue_safe": True,
    }


def complete_accounting() -> dict:
    return {"currency": "USD", "cost_usd": 0.0, "gpu_active_seconds": 0.0, "gpu_idle_seconds": 0.0, "billed_seconds": 0.0, "bytes_moved_total": 0}


def no_cleanup() -> dict:
    return {"required": False, "status": "not_required", "resources_deleted": [], "resources_retained": [], "receipt_sha256": None, "reason": "isolated offline test creates no cloud resources"}
