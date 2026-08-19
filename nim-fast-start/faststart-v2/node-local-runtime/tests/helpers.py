from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from performance.request_slo import harness

from node_runtime.cache import ContentAddressedCache
from node_runtime.security import (
    AdmissionPolicy,
    CommandAuthenticator,
    NonceJournal,
    sign_checkpoint_binding,
)
from node_runtime.supervisor import ExclusiveNodeLease, SwitchSupervisor


MODEL_A = {"model_id": "cpu-fixture-a", "model_version": "v1"}
MODEL_B = "cpu-fixture-b"
VERSION_B = "v1"
PAYLOAD = b'{"value":"catalog-switch-cpu-fixture"}\n'
ARTIFACT = b"immutable-cpu-fixture-artifact\n"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT).hexdigest()
IMAGE = "cpu-fixture@sha256:" + "4" * 64
AUTH_KEY = b"a" * 32
CHECKPOINT_KEY = b"b" * 32
PROFILES = {
    "egress_policy_sha256": "5" * 64,
    "privilege_profile_sha256": "6" * 64,
    "mount_policy_sha256": "7" * 64,
}


def target() -> dict[str, str]:
    return {
        "model_id": MODEL_B,
        "model_version": VERSION_B,
        "artifact_id": "cpu-fixture-artifact-b",
        "artifact_version": "v1",
        "artifact_sha256": ARTIFACT_SHA,
    }


def precondition(scenario: str) -> dict[str, Any]:
    cache = {
        "image": "local_verified",
        "artifact": "attached_storage_hit",
        "checkpoint": "compatible_hit",
        "storage": "ready",
    }
    occupant: dict[str, str] | None = MODEL_A
    capacity = "allocated"
    queue_depth = 0
    if scenario == "idle_local":
        occupant = None
    elif scenario == "same_model_hot":
        occupant = {"model_id": MODEL_B, "model_version": VERSION_B}
        cache["artifact"] = "memory_hit"
        cache["checkpoint"] = "not_applicable"
    elif scenario == "a_to_b_remote":
        cache = {
            "image": "remote_required",
            "artifact": "remote_miss",
            "checkpoint": "missing",
            "storage": "localization_required",
        }
        capacity = "queued"
        queue_depth = 2
    elif scenario == "checkpoint_fallback":
        cache["checkpoint"] = "stale_version"
    elif scenario == "capacity_miss":
        occupant = None
        cache = {
            "image": "unavailable",
            "artifact": "unavailable",
            "checkpoint": "missing",
            "storage": "unavailable",
        }
        capacity = "unavailable"
        queue_depth = 3
    return {
        "current_node_occupant": occupant,
        "cache": cache,
        "capacity": capacity,
        "queue_depth": queue_depth,
    }


def trace(scenario: str = "a_to_b_local", suffix: str = "001") -> dict[str, Any]:
    request = {
        "sequence": 0,
        "request_id": f"node-local-request-{suffix}",
        "attempt_id": f"node-local-attempt-{suffix}",
        "offered_at_offset_ms": 0,
        "scenario": scenario,
        "target": target(),
        "input": {
            "workload_id": "cpu-semantic-fixture",
            "input_id": "cpu-input-v1",
            "payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
            "input_bytes": len(PAYLOAD),
        },
        "precondition": precondition(scenario),
    }
    value = {
        "schema": harness.TRACE_SCHEMA,
        "trace_id": f"node-local-trace-{suffix}",
        "distribution": "adversarial",
        "seed": 2407,
        "catalog_sha256": "8" * 64,
        "request_count": 1,
        "scenario_labels": list(harness.SCENARIOS),
        "requests": [request],
    }
    value["trace_sha256"] = harness.canonical_sha256(value)
    return harness.validate_trace(value)


def environment() -> dict[str, Any]:
    return {
        "backend": "node-vm-cpu-fixture",
        "backend_version": "v1",
        "provider": "local",
        "project_id": "local-cpu-integration",
        "region": "local",
        "node_id": "local-test-node",
        "gpu_type": "cpu-fixture",
        "gpu_count": 0,
        "image_digest": IMAGE,
        "code_revision": "0" * 40,
        "config_sha256": "9" * 64,
        "experiment_id": "node-local-cpu-integration",
    }


def checkpoint_environment() -> dict[str, Any]:
    return {
        "image_digest": IMAGE,
        "driver_version": "cpu-none",
        "cuda_version": "cpu-none",
        "runtime_version": "deterministic-fixture-v1",
        "gpu_type": "cpu-fixture",
        "gpu_topology_sha256": "a" * 64,
    }


def ownership(required: bool = False) -> dict[str, Any]:
    resources = (
        [
            {
                "kind": "scratch",
                "id": "node-local-attempt-scratch",
                "project_id": "local-cpu-integration",
                "region": "local",
            }
        ]
        if required
        else []
    )
    return {
        "owner_task_id": "catalog-switch-node-local-runtime",
        "resource_prefix": "mlsp-csw-node-local-cpu",
        "dedicated": True,
        "cleanup_required": required,
        "resources": resources,
    }


def binding(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "catalog-switch-checkpoint-binding/v1",
        "checkpoint_sha256": "b" * 64,
        "artifact_sha256": ARTIFACT_SHA,
        "image_digest": IMAGE,
        "driver_version": "cpu-none",
        "cuda_version": "cpu-none",
        "runtime_version": "deterministic-fixture-v1",
        "gpu_type": "cpu-fixture",
        "gpu_topology_sha256": "a" * 64,
        "capture_environment_id": "fresh-golden-cpu-fixture",
        "capture_source": "golden-pre-tenant-traffic",
        "capture_time": "2026-08-19T00:00:00Z",
        "capture_state_classes": {
            "established_external_sockets": 0,
            "secret_bearing_fds": 0,
        },
        **PROFILES,
        "checkpoint_encrypted": True,
        "checkpoint_key_id": "cpu-test-envelope-key",
        "signature_key_id": "cpu-test-binding-key",
    }
    value.update(overrides)
    return sign_checkpoint_binding(value, CHECKPOINT_KEY)


def setup(tmp: Path, scenario: str = "a_to_b_local", suffix: str = "001") -> dict[str, Any]:
    cache = ContentAddressedCache(tmp / "cache", require_fsverity=False)
    source = tmp / "artifact-source"
    source.write_bytes(ARTIFACT)
    cache.ingest(source, ARTIFACT_SHA, expected_size=len(ARTIFACT))
    policy = AdmissionPolicy(((MODEL_B, VERSION_B, ARTIFACT_SHA),))
    auth = CommandAuthenticator(AUTH_KEY, "cpu-test-command-key", policy, NonceJournal(tmp / "nonces"))
    supervisor = SwitchSupervisor(
        cache=cache,
        authenticator=auth,
        node_lease=ExclusiveNodeLease(tmp / "state" / "exclusive.lock"),
        checkpoint_key=CHECKPOINT_KEY,
        checkpoint_profiles=PROFILES,
        validator_id="cpu-semantic-validator-v1",
        validator_sha256="c" * 64,
    )
    run_trace = trace(scenario, suffix)
    now = time.time_ns()
    command = auth.sign(
        run_trace["requests"][0],
        nonce=f"nonce-{suffix}-0123456789",
        launch_mode="snapshot",
        issued_at_unix_ns=now - 1_000_000,
        expires_at_unix_ns=now + 30_000_000_000,
    )
    return {
        "cache": cache,
        "source": source,
        "auth": auth,
        "supervisor": supervisor,
        "trace": run_trace,
        "command": command,
    }
