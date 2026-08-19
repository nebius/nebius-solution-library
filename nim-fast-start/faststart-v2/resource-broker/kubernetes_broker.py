#!/usr/bin/env python3
"""Versioned, fail-closed Nebius Managed Kubernetes experiment lease broker.

The existing ``broker.py`` VM v1 contract intentionally remains independent.
This backend owns only fresh Managed Kubernetes resources and splits target-
neutral support creation from demand-gated GPU node-group creation.
"""

from __future__ import annotations

import argparse
import base64
import functools
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import broker as common  # noqa: E402


REQUEST_SCHEMA_VERSION = "catalog-switch-kubernetes-lease-request/v3"
LEASE_SCHEMA_VERSION = "catalog-switch-kubernetes-resource-lease/v4"
PROFILE_SCHEMA_VERSION = "catalog-switch-kubernetes-resource-profiles/v1"
REGISTRY_SCHEMA_VERSION = "catalog-switch-kubernetes-lease-registry/v1"
DEMAND_SCHEMA_VERSION = "catalog-switch-kubernetes-node-demand/v3"
EVENT_SCHEMA_VERSION = "catalog-switch-kubernetes-lifecycle-events/v1"
BACKEND_VERSION = "nebius-managed-kubernetes/v3"
KUBECTL = "/usr/local/bin/kubectl"
KUBECONFIG_ROOT = ROOT / "kubeconfigs"
LEASE_KEY_ROOT = ROOT / "lease-keys"
K8S_REGISTRY = ROOT / "kubernetes-leases" / "registry.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
BASELINE_EVENT_SCHEMA = "archvteams.nebius.ai/catalog-switch-ledger-event/v1"
T0_BOUNDARY = "external-client-request-accepted/v1"
EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA = "catalog-switch-external-accepted-event-receipt/v1"
PRIVATE_RUNNER_RECEIPT_SCHEMA = "catalog-switch-kubernetes-private-runner-receipt/v1"
NO_CREATE_RECEIPT_SCHEMA = "catalog-switch-kubernetes-no-create-absence-receipt/v1"
ACCEPTED_SCENARIOS = {
    "same_model_hot",
    "idle_local",
    "a_to_b_local",
    "a_to_b_remote",
    "checkpoint_fallback",
    "capacity_miss",
}
GIB = 1024**3


def lease_lock_path(lease_path: Path) -> Path:
    return lease_path.with_suffix(lease_path.suffix + ".mutation.lock")


def lease_mutation_locked(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Serialize every lease mutation, including provider reconciliation."""

    @functools.wraps(function)
    def wrapped(lease_path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        with common.locked(lease_lock_path(lease_path)):
            return function(lease_path, *args, **kwargs)

    return wrapped


def precise_utc_now() -> common.dt.datetime:
    return common.dt.datetime.now(common.dt.timezone.utc)


class KubeCTL:
    """Small kubectl wrapper that never logs kubeconfig contents."""

    def __init__(self, binary: str = KUBECTL) -> None:
        self.binary = binary

    def run(self, kubeconfig: Path, args: list[str], timeout: int = 90) -> dict[str, Any]:
        command = [self.binary, "--kubeconfig", str(kubeconfig), *args, "-o", "json"]
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        combined = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode:
            lowered = combined.lower()
            if any(marker in lowered for marker in common.AUTH_FAILURES):
                raise common.AuthenticationError(
                    "Kubernetes authentication/authorization failed; do not switch authority: "
                    + combined[:1000]
                )
            raise common.BrokerError(f"kubectl failed: {combined[:1500]}")
        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise common.BrokerError("kubectl returned non-JSON output") from exc


def load_profiles(path: Path) -> dict[str, Any]:
    profiles = common.load_json(path)
    if profiles.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise common.BrokerError("unsupported Kubernetes profile schema")
    return profiles


def required_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    if missing or extra:
        raise common.BrokerError(f"{label} fields mismatch; missing={missing}, extra={extra}")


def validate_private_runner_receipt(
    value: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    required_keys(value, {"status", "path", "sha256", "reviewed_commit"}, "private_runner_receipt")
    status_value = value["status"]
    if status_value == "PENDING_CONSUMER_PROOF":
        if any(value[field] is not None for field in ("path", "sha256", "reviewed_commit")):
            raise common.BrokerError("pending private runner receipt must not claim review evidence")
        return dict(value)
    if status_value != "REVIEWED_ACTIVE":
        raise common.BrokerError("private runner receipt has an unsupported status")
    path = Path(str(value["path"]))
    if not path.is_absolute() or path.resolve() != path:
        raise common.BrokerError("private runner receipt path must be absolute and canonical")
    try:
        details = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise common.BrokerError("reviewed private runner receipt is missing") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise common.BrokerError("private runner receipt must be a regular non-symlink file")
    if not HEX64.fullmatch(str(value["sha256"])) or hashlib.sha256(raw).hexdigest() != value["sha256"]:
        raise common.BrokerError("private runner receipt digest mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(value["reviewed_commit"])):
        raise common.BrokerError("private runner receipt must pin an exact reviewed commit")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise common.BrokerError("private runner receipt is not valid JSON") from exc
    required_keys(
        receipt,
        {
            "schema_version",
            "status",
            "consumer_task_id",
            "lease_id",
            "project_id",
            "region",
            "runner_owner_task",
            "network_path",
            "api_server_access",
            "public_ip",
            "public_ingress",
            "implementation_sha256",
            "source_commit",
            "reviewed_at_utc",
        },
        "private runner receipt material",
    )
    expected = {
        "schema_version": PRIVATE_RUNNER_RECEIPT_SCHEMA,
        "status": "PASS",
        "consumer_task_id": request["task_id"],
        "lease_id": request["lease_id"],
        "project_id": request["project_id"],
        "region": request["region"],
        "runner_owner_task": request["task_id"],
        "network_path": "task-owned-private-subnet",
        "api_server_access": "internal-only",
        "public_ip": False,
        "public_ingress": False,
        "implementation_sha256": receipt["implementation_sha256"],
        "source_commit": value["reviewed_commit"],
        "reviewed_at_utc": receipt["reviewed_at_utc"],
    }
    if receipt != expected or not HEX64.fullmatch(str(receipt["implementation_sha256"])):
        raise common.BrokerError("private runner receipt does not prove the exact isolated path")
    common.parse_utc(str(receipt["reviewed_at_utc"]))
    return {**value, "path": str(path)}


def validate_request(request: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "lease_id",
        "task_id",
        "owner",
        "cleanup_owner",
        "purpose",
        "campaign_arm",
        "project_id",
        "region",
        "nebius_profile",
        "authority_identity",
        "cluster_version",
        "node_group_profile",
        "expected_duration_hours",
        "ttl_hours",
        "cleanup_deadline_utc",
        "hard_cost_cap_usd",
        "artifact_storage",
        "metric_contract_sha256",
        "trace_id",
        "trace_sha256",
        "allowed_scenarios",
        "model_input_sha256s",
        "model_request_bindings",
        "accepted_event_authority_id",
        "private_runner_receipt",
        "cleanup_plan",
    }
    required_keys(request, required, "request")
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise common.BrokerError("unsupported Kubernetes request schema")
    normalized = dict(request)
    for field in ("lease_id", "task_id", "owner", "cleanup_owner"):
        normalized[field] = common.sanitize_label(str(request[field]), field)
    if request["campaign_arm"] not in {"A_prepared_node", "B_new_preemptible_node"}:
        raise common.BrokerError("campaign_arm must be A_prepared_node or B_new_preemptible_node")
    if request["project_id"] not in common.AUTHORIZED_PROJECTS:
        raise common.BrokerError("project is outside the epic allowlist")
    expected_region = common.AUTHORIZED_PROJECTS[request["project_id"]]
    if request["region"] != expected_region:
        raise common.BrokerError("region does not match the authorized project")
    if request["nebius_profile"] != "sandbox":
        raise common.BrokerError("only the audited Nebius profile 'sandbox' is allowed")
    authority = request["authority_identity"]
    required_keys(authority, {"type", "id", "parent_id"}, "authority_identity")
    for field in ("type", "id", "parent_id"):
        if not isinstance(authority[field], str) or not authority[field].strip():
            raise common.BrokerError(f"authority_identity.{field} must be a non-empty string")
    if authority["parent_id"] not in common.AUTHORIZED_PROJECTS:
        raise common.BrokerError("frozen authority identity is outside the epic allowlist")
    try:
        profile = profiles["profiles"][request["node_group_profile"]]
    except KeyError as exc:
        raise common.BrokerError("unknown Kubernetes node-group profile") from exc
    if request["region"] not in profile["regions"]:
        raise common.BrokerError("Kubernetes profile is unavailable in the requested region")
    if request["cluster_version"] != profile["kubernetes_version"]:
        raise common.BrokerError("cluster version differs from the pinned profile")
    gpu = profile["gpu_node_group"]
    if profile.get("public_control_plane_endpoint") is not False or profile.get("karpenter") is not False:
        raise common.BrokerError("Kubernetes profile must pin a private control plane and omit Karpenter")
    if gpu["mode"] != "preemptible" or gpu["node_count"] != 1 or gpu["gpu_count_per_node"] != 1:
        raise common.BrokerError("profile must be an exact single-node preemptible GPU profile")
    duration = Decimal(str(request["expected_duration_hours"]))
    ttl = int(request["ttl_hours"])
    if duration <= 0 or duration > Decimal(str(profile["max_duration_hours"])):
        raise common.BrokerError("expected duration is outside Kubernetes profile policy")
    if ttl < 1 or ttl > int(profile["max_ttl_hours"]):
        raise common.BrokerError("TTL is outside Kubernetes profile policy")
    if duration > Decimal(ttl):
        raise common.BrokerError("expected duration cannot exceed TTL")
    deadline = common.parse_utc(str(request["cleanup_deadline_utc"]))
    now = common.utc_now()
    if deadline <= now:
        raise common.BrokerError("cleanup deadline has already passed")
    if deadline > now + common.dt.timedelta(hours=ttl, minutes=5):
        raise common.BrokerError("cleanup deadline exceeds the requested TTL")
    cap = Decimal(str(request["hard_cost_cap_usd"]))
    if cap <= 0:
        raise common.BrokerError("hard cost cap must be positive")
    if len(str(request["purpose"]).strip()) < 20 or len(str(request["cleanup_plan"]).strip()) < 20:
        raise common.BrokerError("purpose and cleanup_plan must each be at least 20 characters")
    artifact = request["artifact_storage"]
    required_keys(artifact, {"max_size_gib"}, "artifact_storage")
    if not 1 <= int(artifact["max_size_gib"]) <= 1024:
        raise common.BrokerError("artifact quota must be between 1 and 1024 GiB")
    for field in ("metric_contract_sha256", "trace_sha256"):
        if not HEX64.fullmatch(str(request[field])):
            raise common.BrokerError(f"{field} must be a SHA-256 digest")
    if not isinstance(request["trace_id"], str) or not request["trace_id"]:
        raise common.BrokerError("trace_id must be a non-empty frozen identity")
    scenarios = request["allowed_scenarios"]
    if (
        not isinstance(scenarios, list)
        or not scenarios
        or len(set(scenarios)) != len(scenarios)
        or any(item not in ACCEPTED_SCENARIOS for item in scenarios)
    ):
        raise common.BrokerError("allowed_scenarios must be unique reviewed request-SLO scenarios")
    model_hashes = request["model_input_sha256s"]
    if not isinstance(model_hashes, dict) or not model_hashes:
        raise common.BrokerError("at least one frozen model input digest is required")
    for model_id, digest in model_hashes.items():
        common.sanitize_label(str(model_id), "model_id")
        if not HEX64.fullmatch(str(digest)):
            raise common.BrokerError("model input values must be SHA-256 digests")
    bindings = request["model_request_bindings"]
    if not isinstance(bindings, dict) or set(bindings) != set(model_hashes):
        raise common.BrokerError("model_request_bindings must exactly cover frozen model inputs")
    for model_id, binding in bindings.items():
        required_keys(binding, {"target", "input"}, f"model_request_bindings.{model_id}")
        target = binding["target"]
        request_input = binding["input"]
        required_keys(
            target,
            {"model_id", "model_version", "artifact_id", "artifact_version", "artifact_sha256"},
            f"model_request_bindings.{model_id}.target",
        )
        required_keys(
            request_input,
            {"workload_id", "input_id", "payload_sha256", "input_bytes"},
            f"model_request_bindings.{model_id}.input",
        )
        if target["model_id"] != model_id:
            raise common.BrokerError("model binding target identity differs from its key")
        if not HEX64.fullmatch(str(target["artifact_sha256"])):
            raise common.BrokerError("model binding artifact digest is invalid")
        if request_input["payload_sha256"] != model_hashes[model_id]:
            raise common.BrokerError("model binding input digest differs from frozen input map")
        if isinstance(request_input["input_bytes"], bool) or int(request_input["input_bytes"]) < 0:
            raise common.BrokerError("model binding input_bytes must be nonnegative")
    authority_id = request["accepted_event_authority_id"]
    authorities = profiles.get("accepted_event_authorities", {})
    if authority_id not in authorities:
        raise common.BrokerError("accepted-event authority is not in the reviewed profile registry")
    accepted_authority = authorities[authority_id]
    required_keys(
        accepted_authority,
        {
            "status",
            "recorder_id",
            "receipt_schema_version",
            "validator_id",
            "validator_sha256",
            "validator_reviewed_commit",
            "public_key_base64",
        },
        "accepted-event authority",
    )
    if accepted_authority["receipt_schema_version"] != EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA:
        raise common.BrokerError("accepted-event authority receipt schema is unsupported")
    if not all(
        isinstance(accepted_authority[field], str) and accepted_authority[field]
        for field in ("recorder_id", "validator_id")
    ):
        raise common.BrokerError("accepted-event recorder/validator IDs must be non-empty")
    authority_status = accepted_authority["status"]
    if authority_status == "PENDING_CONSUMER_REVIEW":
        if any(
            accepted_authority[field] is not None
            for field in ("validator_sha256", "validator_reviewed_commit", "public_key_base64")
        ):
            raise common.BrokerError("pending accepted-event authority must not claim review evidence")
    elif authority_status == "REVIEWED_ACTIVE":
        if (
            not HEX64.fullmatch(str(accepted_authority["validator_sha256"]))
            or not re.fullmatch(r"[0-9a-f]{40}", str(accepted_authority["validator_reviewed_commit"]))
        ):
            raise common.BrokerError("reviewed accepted-event validator provenance is incomplete")
        try:
            authority_key = base64.b64decode(
                str(accepted_authority["public_key_base64"]), validate=True
            )
            Ed25519PublicKey.from_public_bytes(authority_key)
        except (ValueError, TypeError) as exc:
            raise common.BrokerError("reviewed accepted-event authority key is invalid") from exc
        if len(authority_key) != 32:
            raise common.BrokerError("reviewed accepted-event authority key has invalid length")
    else:
        raise common.BrokerError("accepted-event authority has an unsupported review status")
    runner = validate_private_runner_receipt(request["private_runner_receipt"], request)
    normalized.update(
        {
            "expected_duration_hours": str(duration),
            "ttl_hours": ttl,
            "hard_cost_cap_usd": common.decimal_string(cap),
            "cleanup_deadline_utc": common.iso(deadline),
            "artifact_storage": {"max_size_gib": int(artifact["max_size_gib"])},
            "authority_identity": dict(authority),
            "allowed_scenarios": list(scenarios),
            "model_request_bindings": json.loads(json.dumps(bindings)),
            "private_runner_receipt": runner,
        }
    )
    return normalized


def cost_estimate(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    system = profile["system_node_group"]
    gpu = profile["gpu_node_group"]
    disk_gib = Decimal(str(system["boot_disk_gib"] + gpu["boot_disk_gib"]))
    disk_hourly = disk_gib * Decimal(profile["network_ssd_usd_per_gib_month"]) / Decimal("730")
    artifact_hourly = (
        Decimal(request["artifact_storage"]["max_size_gib"])
        * Decimal(profile["object_storage_usd_per_gib_month"])
        / Decimal("730")
    )
    support_rate = Decimal(system["compute_usd_per_hour"]) + (
        Decimal(system["boot_disk_gib"])
        * Decimal(profile["network_ssd_usd_per_gib_month"])
        / Decimal("730")
    ) + artifact_hourly
    active_rate = (
        Decimal(system["compute_usd_per_hour"])
        + Decimal(gpu["compute_usd_per_hour"])
        + disk_hourly
        + artifact_hourly
    )
    duration = Decimal(request["expected_duration_hours"])
    ttl = Decimal(request["ttl_hours"])
    expected = active_rate * duration
    ceiling = active_rate * ttl
    hard_cap = Decimal(request["hard_cost_cap_usd"])
    if ceiling > hard_cap:
        raise common.BrokerError(
            f"hard cost cap {hard_cap} is below TTL ceiling {common.decimal_string(ceiling)}"
        )
    return {
        "currency": "USD",
        "support_only_usd_per_hour": common.decimal_string(support_rate),
        "one_gpu_active_usd_per_hour": common.decimal_string(active_rate),
        "expected_duration_hours": str(duration),
        "expected_cost_usd": common.decimal_string(expected),
        "ttl_hours": str(ttl),
        "ttl_cost_ceiling_usd": common.decimal_string(ceiling),
        "hard_cost_cap_usd": common.decimal_string(hard_cap),
        "price_observed_at": profile["price_observed_at"],
        "price_sources": profile["price_sources"],
        "assumptions": profile["cost_assumptions"],
    }


def planned_graph(prefix: str, request: dict[str, Any]) -> list[dict[str, Any]]:
    gpu_name = f"{prefix}-gpu" if request["campaign_arm"] == "A_prepared_node" else f"{prefix}-gpu-{{demand_sha256_8}}"
    graph = [
        ("network", f"{prefix}-net", [], "cloud"),
        ("subnet", f"{prefix}-subnet", ["network"], "cloud"),
        ("security_group", f"{prefix}-sg", ["network"], "cloud"),
        ("service_account", f"{prefix}-nodes-sa", [], "cloud"),
        ("iam_group", f"{prefix}-nodes-group", [], "cloud"),
        ("group_membership", f"{prefix}-nodes-member", ["iam_group", "service_account"], "cloud"),
        ("registry", f"{prefix}-registry", [], "cloud"),
        ("registry_access_permit", f"{prefix}-registry-view", ["iam_group", "registry"], "cloud"),
        ("bucket", f"{prefix}-artifacts", [], "cloud"),
        ("bucket_access_permit", f"{prefix}-artifact-edit", ["iam_group", "bucket"], "cloud"),
        ("cluster", f"{prefix}-cluster", ["subnet"], "cloud"),
        (
            "system_node_group",
            f"{prefix}-system",
            ["cluster", "subnet", "service_account", "registry_access_permit", "bucket_access_permit"],
            "cloud",
        ),
        ("system_node", f"{prefix}-system-provider-node", ["system_node_group"], "provider_cascade"),
        (
            "kubeconfig_authority",
            f"{request['lease_id']}.yaml",
            ["cluster"],
            "local_secret",
        ),
        (
            "gpu_node_group",
            gpu_name,
            ["cluster", "subnet", "service_account", "registry_access_permit", "bucket_access_permit"],
            "demand_gated_cloud" if request["campaign_arm"] == "B_new_preemptible_node" else "cloud",
        ),
        ("gpu_node", f"{gpu_name}-provider-node", ["gpu_node_group"], "provider_cascade"),
    ]
    return [
        {
            "key": key,
            "resource_type": key,
            "resource_name": name,
            "depends_on": depends_on,
            "authority": authority,
            "desired_final_state": "ABSENT",
        }
        for key, name, depends_on, authority in graph
    ]


def event(
    lease: dict[str, Any], event_name: str, outcome: str, **attributes: Any
) -> dict[str, Any]:
    item = {
        "sequence": len(lease["lifecycle_events"]),
        "observed_at_utc": common.iso(precise_utc_now()),
        "observed_monotonic_ns": time.monotonic_ns(),
        "event": event_name,
        "outcome": outcome,
        "attributes": attributes,
    }
    lease["lifecycle_events"].append(item)
    return item


def signing_key_path(lease_id: str) -> Path:
    return (LEASE_KEY_ROOT / f"{lease_id}.ed25519").resolve()


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise common.BrokerError("invalid lease signing-key encoding") from exc


def create_signing_authority(lease_id: str) -> dict[str, Any]:
    """Create one task-local signing key without ever placing it in the ledger."""

    path = signing_key_path(lease_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise common.BrokerError("lease signing-key directory cannot be a symlink")
    if path.exists():
        raise common.BrokerError("lease signing-key path collision; preserve it")
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        written = os.write(descriptor, private_bytes)
        if written != len(private_bytes):
            raise common.BrokerError("short write creating lease signing authority")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    common.fsync_directory(path.parent)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "algorithm": "ed25519",
        "public_key_base64": _b64(public_bytes),
        "private_key_path": str(path),
        "private_key_contents_recorded": False,
    }


def load_private_key(lease: dict[str, Any]) -> Ed25519PrivateKey:
    path = Path(lease["signing_authority"]["private_key_path"])
    if path != signing_key_path(lease["lease_id"]):
        raise common.BrokerError("lease signing-key path differs from immutable authority")
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise common.BrokerError("lease signing authority is not a regular file")
    if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) != 0o600:
        raise common.BrokerError("lease signing authority owner/mode mismatch")
    raw = path.read_bytes()
    if len(raw) != 32:
        raise common.BrokerError("lease signing authority has an invalid length")
    key = Ed25519PrivateKey.from_private_bytes(raw)
    actual_public = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    if _b64(actual_public) != lease["signing_authority"]["public_key_base64"]:
        raise common.BrokerError("lease signing authority does not match immutable public key")
    return key


def destroy_signing_authority(lease: dict[str, Any]) -> None:
    path = Path(lease["signing_authority"]["private_key_path"])
    if path.exists():
        load_private_key(lease)
        path.unlink()
        common.fsync_directory(path.parent)
    if path.exists():
        raise common.BrokerError("lease signing authority still exists after exact unlink")
    lease["signing_key_cleanup"] = {
        "absence_verified_at": common.iso(precise_utc_now()),
        "evidence": f"lstat({path}) -> absent after exact signed-authority unlink",
    }


def signed_message(kind: str, lease: dict[str, Any], material: dict[str, Any]) -> bytes:
    return common.canonical(
        {
            "domain": f"catalog-switch-kubernetes-{kind}/v1",
            "plan_sha256": lease["plan_sha256"],
            "material": material,
        }
    ).encode("ascii")


def sign_material(kind: str, lease: dict[str, Any], material: dict[str, Any]) -> str:
    return _b64(load_private_key(lease).sign(signed_message(kind, lease, material)))


def verify_signature(kind: str, lease: dict[str, Any], material: dict[str, Any], signature: str) -> None:
    try:
        key = Ed25519PublicKey.from_public_bytes(
            _unb64(lease["signing_authority"]["public_key_base64"])
        )
        key.verify(_unb64(signature), signed_message(kind, lease, material))
    except (InvalidSignature, ValueError) as exc:
        raise common.BrokerError(f"{kind} ownership signature mismatch; preserve resources") from exc


def operation_auth_material(operation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: operation[key]
        for key in (
            "operation_id",
            "kind",
            "name",
            "parent_id",
            "depends_on",
            "payload_sha256",
            "spec_sha256",
            "requested_spec",
            "started_at_utc",
            "started_monotonic_ns",
        )
    }


def authenticate_operation(lease: dict[str, Any], operation: dict[str, Any]) -> None:
    operation["intent_signature"] = sign_material(
        "create-intent", lease, operation_auth_material(operation)
    )


def verify_operation(lease: dict[str, Any], operation: dict[str, Any]) -> None:
    verify_signature(
        "create-intent",
        lease,
        operation_auth_material(operation),
        str(operation.get("intent_signature", "")),
    )


def record_operation_absence(
    lease: dict[str, Any], operation: dict[str, Any], evidence: str
) -> None:
    receipt = {
        "operation_id": operation["operation_id"],
        "verified_at_utc": common.iso(precise_utc_now()),
        "evidence": evidence,
    }
    operation["absence_receipt"] = receipt
    operation["absence_receipt_signature"] = sign_material(
        "create-absence", lease, receipt
    )


def verify_operation_absence(lease: dict[str, Any], operation: dict[str, Any]) -> None:
    receipt = operation.get("absence_receipt")
    signature = operation.get("absence_receipt_signature")
    if not receipt or not signature:
        raise common.BrokerError("create-operation absence lacks a signed receipt")
    verify_signature("create-absence", lease, receipt, signature)
    if receipt.get("operation_id") != operation["operation_id"]:
        raise common.BrokerError("create-operation absence receipt identity mismatch")


def resource_auth_material(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        key: resource.get(key)
        for key in (
            "kind",
            "name",
            "id",
            "project_id",
            "region",
            "parent_id",
            "depends_on",
            "created_at",
            "create_operation_id",
            "deletion_mode",
            "managed_by_resource_id",
            "intended_spec_sha256",
            "provider_spec_sha256",
            "desired_final_state",
            "provider_metadata",
        )
    }


def authenticate_resource(lease: dict[str, Any], resource: dict[str, Any]) -> None:
    resource["ownership_signature"] = sign_material(
        "resource-row", lease, resource_auth_material(resource)
    )


def verify_resource(lease: dict[str, Any], resource: dict[str, Any]) -> None:
    verify_signature(
        "resource-row",
        lease,
        resource_auth_material(resource),
        str(resource.get("ownership_signature", "")),
    )


def demand_auth_material(demand: dict[str, Any]) -> dict[str, Any]:
    return {
        key: demand[key]
        for key in (
            "schema_version",
            "lease_id",
            "attempt_id",
            "accepted_event_path",
            "accepted_event_sha256",
            "accepted_event_receipt_path",
            "accepted_event_receipt_sha256",
            "ledger_id",
            "ledger_sequence",
            "trace_id",
            "request_id",
            "event_id",
            "scenario",
            "target",
            "input",
            "accepted_event_source_receipt",
            "t0_observed_at_utc",
            "t0_observed_monotonic_ns",
            "demand_sha256",
            "demand_received_at_utc",
            "demand_received_monotonic_ns",
            "causal_order_pass",
        )
    }


def authenticate_demand(lease: dict[str, Any]) -> None:
    demand = lease["demand"]
    demand["authority_signature"] = sign_material(
        "accepted-demand", lease, demand_auth_material(demand)
    )


def verify_demand(lease: dict[str, Any]) -> None:
    demand = lease.get("demand")
    if not demand:
        return
    verify_signature(
        "accepted-demand",
        lease,
        demand_auth_material(demand),
        str(demand.get("authority_signature", "")),
    )


def build_lease(request: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    request_hash = common.sha256_json(request)
    task_slug = request["task_id"][:18].rstrip("-._")
    prefix = f"{common.PROGRAM_PREFIX}-{task_slug}-{request_hash[:8]}"
    profile = profiles["profiles"][request["node_group_profile"]]
    accepted_event_authority = profiles["accepted_event_authorities"][
        request["accepted_event_authority_id"]
    ]
    estimate = cost_estimate(request, profile)
    labels = {
        "program": common.PROGRAM,
        "broker": "resource-broker-k8s-v3",
        "lease": request["lease_id"],
        "task": request["task_id"],
        "owner": request["owner"],
        "expires": common.parse_utc(request["cleanup_deadline_utc"]).strftime("%Y%m%dt%H%M%Sz").lower(),
    }
    for key, value in labels.items():
        common.sanitize_label(key, "label key")
        common.sanitize_label(value, f"label {key}")
    now = common.utc_now()
    signing_authority = create_signing_authority(request["lease_id"])
    lease: dict[str, Any] = {
        "schema_version": LEASE_SCHEMA_VERSION,
        "backend_version": BACKEND_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "lease_id": request["lease_id"],
        "request_sha256": request_hash,
        "request": request,
        "prefix": prefix,
        "project_id": request["project_id"],
        "region": request["region"],
        "state": "PLANNED",
        "created_at": common.iso(now),
        "expires_at": request["cleanup_deadline_utc"],
        "labels": labels,
        "signing_authority": signing_authority,
        "profile_snapshot": profile,
        "profile_sha256": common.sha256_json(profile),
        "accepted_event_authority": accepted_event_authority,
        "accepted_event_authority_sha256": common.sha256_json(accepted_event_authority),
        "live_creation_gates": {
            "external_accepted_event_authority": accepted_event_authority["status"],
            "private_runner_network_path": request["private_runner_receipt"]["status"],
            "admitted": (
                accepted_event_authority["status"] == "REVIEWED_ACTIVE"
                and request["private_runner_receipt"]["status"] == "REVIEWED_ACTIVE"
            ),
        },
        "cost_estimate": estimate,
        "resource_graph": planned_graph(prefix, request),
        "resources": [],
        "resource_create_operations": [],
        "cluster_id": None,
        "node_group_ids": [],
        "node_ids": [],
        "kubeconfig_path": str((KUBECONFIG_ROOT / f"{request['lease_id']}.yaml").resolve()),
        "kubernetes_context": prefix,
        "api_server": None,
        "gpu_product": profile["gpu_node_group"]["gpu_product"],
        "preemptible": True,
        "readiness_timestamps": {},
        "isolation_proof": None,
        "demand": None,
        "attempts": [],
        "failures": [],
        "lifecycle_events": [],
        "cleanup_plan": {
            "policy": "delete exact recorded IDs only in reverse dependency order; verify NotFound/absence after every deletion",
            "cleanup_owner": request["cleanup_owner"],
            "deadline_utc": request["cleanup_deadline_utc"],
            "desired_final_state": "ABSENT",
            "foreign_resource_policy": "report and preserve; never adopt or delete",
            "order": [
                "kubeconfig_authority",
                "gpu_node_group",
                "gpu_node",
                "system_node_group",
                "system_node",
                "cluster",
                "registry_access_permit",
                "bucket_access_permit",
                "group_membership",
                "registry",
                "bucket",
                "iam_group",
                "service_account",
                "security_group",
                "subnet",
                "network",
                "provider_network_children",
            ],
        },
    }
    lease["plan_sha256"] = common.sha256_json(immutable_plan_material(lease))
    event(lease, "lease.plan.created", "PASS", request_sha256=request_hash, prefix=prefix)
    return lease


def immutable_plan_material(lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": lease["schema_version"],
        "backend_version": lease["backend_version"],
        "event_schema_version": lease["event_schema_version"],
        "lease_id": lease["lease_id"],
        "request_sha256": lease["request_sha256"],
        "profile_sha256": lease["profile_sha256"],
        "accepted_event_authority": lease["accepted_event_authority"],
        "accepted_event_authority_sha256": lease["accepted_event_authority_sha256"],
        "live_creation_gates": lease["live_creation_gates"],
        "prefix": lease["prefix"],
        "project_id": lease["project_id"],
        "region": lease["region"],
        "created_at": lease["created_at"],
        "expires_at": lease["expires_at"],
        "labels": lease["labels"],
        "signing_authority": lease["signing_authority"],
        "cost_estimate": lease["cost_estimate"],
        "resource_graph": lease["resource_graph"],
        "kubeconfig_path": lease["kubeconfig_path"],
        "kubernetes_context": lease["kubernetes_context"],
        "gpu_product": lease["gpu_product"],
        "preemptible": lease["preemptible"],
        "cleanup_plan": lease["cleanup_plan"],
    }


def assert_integrity(lease: dict[str, Any]) -> None:
    if lease.get("schema_version") != LEASE_SCHEMA_VERSION:
        raise common.BrokerError("unsupported Kubernetes lease schema")
    if common.sha256_json(lease.get("request")) != lease.get("request_sha256"):
        raise common.BrokerError("immutable request hash mismatch")
    if common.sha256_json(lease.get("profile_snapshot")) != lease.get("profile_sha256"):
        raise common.BrokerError("immutable profile hash mismatch")
    if common.sha256_json(lease.get("accepted_event_authority")) != lease.get(
        "accepted_event_authority_sha256"
    ):
        raise common.BrokerError("immutable accepted-event authority hash mismatch")
    if common.sha256_json(immutable_plan_material(lease)) != lease.get("plan_sha256"):
        raise common.BrokerError("immutable resource plan hash mismatch")
    if lease.get("project_id") != lease["request"]["project_id"] or lease.get("region") != lease["request"]["region"]:
        raise common.BrokerError("lease identity differs from immutable request")
    if lease.get("lease_id") != lease["request"]["lease_id"]:
        raise common.BrokerError("lease ID differs from immutable request")
    if lease.get("expires_at") != lease["request"]["cleanup_deadline_utc"]:
        raise common.BrokerError("lease deadline differs from immutable request")
    if lease.get("cleanup_plan", {}).get("cleanup_owner") != lease["request"]["cleanup_owner"]:
        raise common.BrokerError("cleanup owner differs from immutable request")
    operations = lease.get("resource_create_operations", [])
    resources = lease.get("resources", [])
    for operation in operations:
        verify_operation(lease, operation)
        if operation.get("kubeconfig_content_authority"):
            verify_signature(
                "kubeconfig-content",
                lease,
                operation["kubeconfig_content_authority"],
                str(operation.get("kubeconfig_content_signature", "")),
            )
        if operation.get("resource_id"):
            linked = [
                resource
                for resource in resources
                if resource.get("id") == operation["resource_id"]
                and resource.get("create_operation_id") == operation["operation_id"]
            ]
            if len(linked) != 1:
                raise common.BrokerError("create operation resource ID lacks one signed linked row")
        if operation.get("status") == "ABSENCE_VERIFIED_AFTER_INTERRUPTION":
            verify_operation_absence(lease, operation)
    for resource in resources:
        verify_resource(lease, resource)
    for attempt in lease.get("attempts", []):
        verify_no_create_absence_receipt(lease, attempt)
    verify_demand(lease)


def assert_live_creation_prerequisites(lease: dict[str, Any]) -> None:
    """Refuse every create until both external trust and private API reachability are reviewed."""

    authority = lease["accepted_event_authority"]
    gates = lease["live_creation_gates"]
    if (
        authority.get("status") != "REVIEWED_ACTIVE"
        or gates.get("external_accepted_event_authority") != "REVIEWED_ACTIVE"
    ):
        raise common.BrokerError(
            "live creation blocked: external accepted-event recorder/validator authority is unreviewed"
        )
    if (
        not HEX64.fullmatch(str(authority.get("validator_sha256")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(authority.get("validator_reviewed_commit")))
    ):
        raise common.BrokerError("live creation blocked: external validator provenance is incomplete")
    try:
        public_key = _unb64(str(authority.get("public_key_base64")))
        Ed25519PublicKey.from_public_bytes(public_key)
    except (ValueError, TypeError) as exc:
        raise common.BrokerError("live creation blocked: external receipt public key is invalid") from exc
    if len(public_key) != 32:
        raise common.BrokerError("live creation blocked: external receipt public key length is invalid")
    runner = validate_private_runner_receipt(lease["request"]["private_runner_receipt"], lease["request"])
    if runner.get("status") != "REVIEWED_ACTIVE" or not gates.get("admitted"):
        raise common.BrokerError(
            "live creation blocked: consumer has no reviewed task-owned private API runner path"
        )


def registry_summary(lease: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "lease_id": lease["lease_id"],
        "lease_file": str(path.resolve()),
        "schema_version": lease["schema_version"],
        "plan_sha256": lease["plan_sha256"],
        "task_id": lease["request"]["task_id"],
        "campaign_arm": lease["request"]["campaign_arm"],
        "project_id": lease["project_id"],
        "region": lease["region"],
        "prefix": lease["prefix"],
        "state": lease["state"],
        "expires_at": lease["expires_at"],
        "cleanup_owner": lease["request"]["cleanup_owner"],
    }


def update_registry(registry_path: Path, lease_path: Path, lease: dict[str, Any]) -> None:
    assert_integrity(lease)
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    with common.locked(lock_path):
        if registry_path.exists():
            registry = common.load_json(registry_path)
            if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
                raise common.BrokerError("unsupported Kubernetes registry schema")
        else:
            registry = {"schema_version": REGISTRY_SCHEMA_VERSION, "updated_at": None, "leases": []}
        by_id = {item["lease_id"]: item for item in registry["leases"]}
        old = by_id.get(lease["lease_id"])
        if old and Path(old["lease_file"]).resolve() != lease_path.resolve():
            raise common.BrokerError("lease ID is already registered at a different canonical path")
        collision = next(
            (
                item
                for item in registry["leases"]
                if item["prefix"] == lease["prefix"] and item["lease_id"] != lease["lease_id"]
            ),
            None,
        )
        if collision:
            raise common.BrokerError(f"resource prefix collision with {collision['lease_id']}")
        by_id[lease["lease_id"]] = registry_summary(lease, lease_path)
        registry["leases"] = sorted(by_id.values(), key=lambda item: item["lease_id"])
        registry["updated_at"] = common.iso(common.utc_now())
        common.atomic_json(registry_path, registry)


def save(lease_path: Path, registry_path: Path, lease: dict[str, Any]) -> None:
    assert_integrity(lease)
    common.atomic_json(lease_path, lease)
    update_registry(registry_path, lease_path, lease)


def _plan(request_path: Path, lease_path: Path, registry_path: Path, profiles_path: Path) -> dict[str, Any]:
    profiles = load_profiles(profiles_path)
    request = validate_request(common.load_json(request_path), profiles)
    request_hash = common.sha256_json(request)
    if lease_path.exists():
        lease = common.load_json(lease_path)
        assert_integrity(lease)
        if lease["request_sha256"] != request_hash:
            raise common.BrokerError("lease ID collision: existing lease has a different request hash")
        update_registry(registry_path, lease_path, lease)
        return lease
    lease = build_lease(request, profiles)
    save(lease_path, registry_path, lease)
    return lease


def plan(request_path: Path, lease_path: Path, registry_path: Path, profiles_path: Path) -> dict[str, Any]:
    with common.locked(lease_lock_path(lease_path)):
        return _plan(request_path, lease_path, registry_path, profiles_path)


RESOURCE_COMMANDS: dict[str, dict[str, list[str]]] = {
    "network": {
        "list": ["vpc", "network", "list"],
        "get": ["vpc", "network", "get"],
        "create": ["vpc", "network", "create"],
        "delete": ["vpc", "network", "delete"],
    },
    "subnet": {
        "list": ["vpc", "subnet", "list"],
        "get": ["vpc", "subnet", "get"],
        "create": ["vpc", "subnet", "create"],
        "delete": ["vpc", "subnet", "delete"],
    },
    "security_group": {
        "list": ["vpc", "security-group", "list"],
        "get": ["vpc", "security-group", "get"],
        "create": ["vpc", "security-group", "create"],
        "delete": ["vpc", "security-group", "delete"],
    },
    "service_account": {
        "list": ["iam", "service-account", "list"],
        "get": ["iam", "service-account", "get"],
        "create": ["iam", "service-account", "create"],
        "delete": ["iam", "service-account", "delete"],
    },
    "iam_group": {
        "list": ["iam", "group", "list"],
        "get": ["iam", "group", "get"],
        "create": ["iam", "group", "create"],
        "delete": ["iam", "group", "delete"],
    },
    "group_membership": {
        "list": ["iam", "group-membership", "list"],
        "get": ["iam", "group-membership", "get"],
        "create": ["iam", "group-membership", "create"],
        "delete": ["iam", "group-membership", "delete"],
    },
    "registry": {
        "list": ["registry", "list"],
        "get": ["registry", "get"],
        "create": ["registry", "create"],
        "delete": ["registry", "delete"],
    },
    "registry_access_permit": {
        "list": ["iam", "access-permit", "list"],
        "get": ["iam", "access-permit", "get"],
        "create": ["iam", "access-permit", "create"],
        "delete": ["iam", "access-permit", "delete"],
    },
    "bucket": {
        "list": ["storage", "bucket", "list"],
        "get": ["storage", "bucket", "get"],
        "create": ["storage", "bucket", "create"],
        "delete": ["storage", "bucket", "delete"],
    },
    "bucket_access_permit": {
        "list": ["iam", "access-permit", "list"],
        "get": ["iam", "access-permit", "get"],
        "create": ["iam", "access-permit", "create"],
        "delete": ["iam", "access-permit", "delete"],
    },
    "cluster": {
        "list": ["mk8s", "v1", "cluster", "list"],
        "get": ["mk8s", "v1", "cluster", "get"],
        "create": ["mk8s", "v1", "cluster", "create"],
        "delete": ["mk8s", "v1", "cluster", "delete"],
    },
    "system_node_group": {
        "list": ["mk8s", "v1", "node-group", "list"],
        "get": ["mk8s", "v1", "node-group", "get"],
        "create": ["mk8s", "v1", "node-group", "create"],
        "delete": ["mk8s", "v1", "node-group", "delete"],
    },
    "gpu_node_group": {
        "list": ["mk8s", "v1", "node-group", "list"],
        "get": ["mk8s", "v1", "node-group", "get"],
        "create": ["mk8s", "v1", "node-group", "create"],
        "delete": ["mk8s", "v1", "node-group", "delete"],
    },
    "node": {
        "list": ["compute", "instance", "list"],
        "get": ["compute", "instance", "get"],
    },
    "pool": {"get": ["vpc", "pool", "get"]},
    "route_table": {"get": ["vpc", "route-table", "get"]},
}


def resource_payload(name: str, parent_id: str, labels: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {"name": name, "parent_id": parent_id, "labels": labels}, "spec": spec}


def _strict_fields(
    value: dict[str, Any], *, allowed: set[str], required: set[str], label: str
) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown or missing:
        raise common.BrokerError(
            f"installed provider schema mismatch at {label}; missing={missing}, unknown={unknown}"
        )


def validate_provider_create_payload(kind: str, payload: dict[str, Any]) -> None:
    """Strict subset of the installed Nebius CLI 0.12.206 input schema."""

    _strict_fields(payload, allowed={"metadata", "spec"}, required={"metadata", "spec"}, label=kind)
    _strict_fields(
        payload["metadata"],
        allowed={"name", "parent_id", "labels"},
        required={"name", "parent_id", "labels"},
        label=f"{kind}.metadata",
    )
    if kind == "cluster":
        _strict_fields(
            payload["spec"],
            allowed={"control_plane", "kube_network"},
            required={"control_plane", "kube_network"},
            label="cluster.spec",
        )
        control_plane = payload["spec"]["control_plane"]
        _strict_fields(
            control_plane,
            allowed={"audit_logs", "etcd_cluster_size", "subnet_id", "version"},
            required={"subnet_id", "version"},
            label="cluster.spec.control_plane",
        )
        if "endpoints" in control_plane or "karpenter" in control_plane:
            raise common.BrokerError("private cluster must omit endpoints and disabled karpenter")
    elif kind in {"system_node_group", "gpu_node_group"}:
        spec = payload["spec"]
        _strict_fields(
            spec,
            allowed={"version", "fixed_node_count", "template"},
            required={"version", "fixed_node_count", "template"},
            label=f"{kind}.spec",
        )
        template = spec["template"]
        allowed_template = {
            "metadata",
            "taints",
            "resources",
            "boot_disk",
            "gpu_settings",
            "os",
            "network_interfaces",
            "service_account_id",
            "preemptible",
            "reservation_policy",
        }
        required_template = {
            "metadata",
            "resources",
            "boot_disk",
            "os",
            "network_interfaces",
            "service_account_id",
            "reservation_policy",
        }
        _strict_fields(
            template,
            allowed=allowed_template,
            required=required_template,
            label=f"{kind}.spec.template",
        )
        _strict_fields(
            template["boot_disk"],
            allowed={"size_bytes", "block_size_bytes", "type"},
            required={"size_bytes", "block_size_bytes", "type"},
            label=f"{kind}.spec.template.boot_disk",
        )
        size_bytes = template["boot_disk"]["size_bytes"]
        if not isinstance(size_bytes, int) or size_bytes <= 0 or size_bytes % GIB:
            raise common.BrokerError("boot_disk.size_bytes must be an exact positive GiB conversion")
        if kind == "gpu_node_group":
            if "preemptible" not in template or template["preemptible"] != {}:
                raise common.BrokerError("GPU provider payload must enable preemptible with an object")
            if "gpu_settings" not in template:
                raise common.BrokerError("GPU provider payload must pin driver ownership")
        elif "preemptible" in template:
            raise common.BrokerError("system node-group payload must omit preemptible")


def project_requested_spec(live: Any, requested: Any, path: str = "spec") -> Any:
    """Project a provider response onto exactly the signed requested shape."""

    if isinstance(requested, dict):
        if not isinstance(live, dict):
            raise common.BrokerError(f"provider object differs from create intent at {path}")
        missing = sorted(set(requested) - set(live))
        if missing:
            raise common.BrokerError(f"provider object is missing signed fields at {path}: {missing}")
        return {
            key: project_requested_spec(live[key], value, f"{path}.{key}")
            for key, value in requested.items()
        }
    if isinstance(requested, list):
        if not isinstance(live, list) or len(live) != len(requested):
            raise common.BrokerError(f"provider list differs from create intent at {path}")
        return [
            project_requested_spec(live[index], value, f"{path}[{index}]")
            for index, value in enumerate(requested)
        ]
    if live != requested:
        raise common.BrokerError(f"provider value differs from create intent at {path}")
    return live


def find_resource(lease: dict[str, Any], kind: str, name: str | None = None) -> dict[str, Any] | None:
    matches = [
        item
        for item in lease["resources"]
        if item["kind"] == kind and not item.get("deleted_at") and (name is None or item["name"] == name)
    ]
    if len(matches) > 1 and name is None:
        raise common.BrokerError(f"multiple live {kind} resources require an exact name")
    return matches[0] if matches else None


def validate_owned_metadata(
    lease: dict[str, Any], kind: str, value: dict[str, Any], name: str, parent_id: str
) -> None:
    metadata = value.get("metadata", {})
    if metadata.get("name") != name or metadata.get("parent_id") != parent_id:
        raise common.BrokerError(f"{kind} identity differs from the immutable resource graph")
    labels = metadata.get("labels", {}) or {}
    if any(labels.get(key) != expected for key, expected in lease["labels"].items()):
        raise common.BrokerError(f"{kind} is not owned by this exact lease; preserve it")


def add_resource(
    lease: dict[str, Any],
    kind: str,
    name: str,
    value: dict[str, Any],
    depends_on: list[str],
    operation_id: str,
    intended_spec: dict[str, Any],
) -> dict[str, Any]:
    resource_id = common.metadata_id(value, kind)
    existing = next((item for item in lease["resources"] if item.get("id") == resource_id), None)
    if existing:
        verify_resource(lease, existing)
        if existing["kind"] != kind or existing["name"] != name:
            raise common.BrokerError("provider resource ID conflicts with signed ownership row")
        return existing
    resource = {
        "kind": kind,
        "name": name,
        "id": resource_id,
        "project_id": lease["project_id"],
        "region": lease["region"],
        "parent_id": value.get("metadata", {}).get("parent_id"),
        "depends_on": depends_on,
        "created_at": value.get("metadata", {}).get("created_at") or common.iso(common.utc_now()),
        "create_operation_id": operation_id,
        "deletion_mode": None,
        "managed_by_resource_id": None,
        "intended_spec_sha256": common.sha256_json(intended_spec),
        "provider_spec_sha256": common.sha256_json(
            project_requested_spec(value.get("spec", {}), intended_spec)
        ),
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
        "provider_metadata": {},
    }
    authenticate_resource(lease, resource)
    lease["resources"].append(resource)
    event(lease, "resource.created", "PASS", kind=kind, resource_id=resource_id, name=name)
    return resource


def operation_for(lease: dict[str, Any], operation_id: str) -> dict[str, Any] | None:
    return next(
        (item for item in lease["resource_create_operations"] if item["operation_id"] == operation_id),
        None,
    )


def ensure_resource(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    *,
    kind: str,
    name: str,
    parent_id: str,
    spec: dict[str, Any],
    depends_on: list[str],
    timeout: int = 600,
) -> dict[str, Any]:
    assert_integrity(lease)
    payload = resource_payload(name, parent_id, lease["labels"], spec)
    if kind in {"cluster", "system_node_group", "gpu_node_group"}:
        validate_provider_create_payload(kind, payload)
    operation_id = f"create:{kind}:{name}"
    recorded = find_resource(lease, kind, name)
    if recorded:
        verify_resource(lease, recorded)
        value = cli.run([*RESOURCE_COMMANDS[kind]["get"], recorded["id"]])
        validate_owned_metadata(lease, kind, value, name, parent_id)
        project_requested_spec(value.get("spec", {}), spec)
        return recorded
    operation = operation_for(lease, operation_id)
    if operation:
        verify_operation(lease, operation)
        if operation["payload_sha256"] != common.sha256_json(payload):
            raise common.BrokerError(f"{kind} create payload differs from signed intent")
    listed = cli.run([*RESOURCE_COMMANDS[kind]["list"], "--parent-id", parent_id, "--all"])
    exact = [item for item in listed.get("items", []) if item.get("metadata", {}).get("name") == name]
    if len(exact) > 1:
        raise common.BrokerError(f"multiple exact-name {kind} resources exist; manual review required")
    if exact:
        if operation is None or operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
            raise common.BrokerError(f"foreign or pre-existing {kind} name collision; preserve it")
        operation["status"] = "AMBIGUOUS_FOREIGN_PRESERVED"
        operation["completed_at_utc"] = common.iso(common.utc_now())
        operation["failure"] = (
            "exact-name object exists after an unreceipted create window; installed provider "
            "create API exposes no request correlation token, so labels/spec cannot prove actor ownership"
        )
        event(
            lease,
            "resource.create.ambiguous",
            "FAIL",
            kind=kind,
            name=name,
            candidate_id=exact[0].get("metadata", {}).get("id"),
            foreign_preserved=True,
        )
        save(lease_path, registry_path, lease)
        raise common.BrokerError(
            f"interrupted {kind} create has no provider correlation/audit receipt; preserve exact-name object"
        )
    if operation is None:
        operation = {
            "operation_id": operation_id,
            "kind": kind,
            "name": name,
            "parent_id": parent_id,
            "depends_on": depends_on,
            "payload_sha256": common.sha256_json(payload),
            "spec_sha256": common.sha256_json(spec),
            "requested_spec": spec,
            "status": "INTENT_RECORDED",
            "started_at_utc": common.iso(common.utc_now()),
            "started_monotonic_ns": time.monotonic_ns(),
            "completed_at_utc": None,
            "resource_id": None,
            "failure": None,
        }
        authenticate_operation(lease, operation)
        lease["resource_create_operations"].append(operation)
        event(lease, "resource.create.started", "PASS", kind=kind, name=name)
        save(lease_path, registry_path, lease)
    elif operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
        raise common.BrokerError(f"unexpected create operation state for {kind}: {operation['status']}")
    try:
        value = cli.run(
            RESOURCE_COMMANDS[kind]["create"],
            payload=payload,
            timeout=timeout,
        )
        validate_owned_metadata(lease, kind, value, name, parent_id)
        project_requested_spec(value.get("spec", {}), spec)
        resource = add_resource(lease, kind, name, value, depends_on, operation_id, spec)
        operation["status"] = "CREATED"
        operation["completed_at_utc"] = common.iso(common.utc_now())
        operation["completed_monotonic_ns"] = time.monotonic_ns()
        operation["resource_id"] = resource["id"]
        operation["failure"] = None
        save(lease_path, registry_path, lease)
        return resource
    except Exception as exc:
        operation["status"] = "CREATE_FAILED"
        operation["completed_at_utc"] = common.iso(common.utc_now())
        operation["completed_monotonic_ns"] = time.monotonic_ns()
        operation["failure"] = str(exc)[:1500]
        lease["failures"].append(
            {
                "at": operation["completed_at_utc"],
                "stage": f"create:{kind}",
                "attempt_id": lease.get("demand", {}).get("attempt_id") if lease.get("demand") else None,
                "error": str(exc)[:1500],
            }
        )
        event(lease, "resource.create.failed", "FAIL", kind=kind, error=str(exc)[:1000])
        save(lease_path, registry_path, lease)
        raise


def identity_from_whoami(whoami: dict[str, Any]) -> dict[str, str | None]:
    if len(whoami) != 1:
        raise common.BrokerError("Nebius whoami returned an ambiguous authority identity")
    identity_type = next(iter(whoami))
    metadata = whoami.get(identity_type, {}).get("info", {}).get("metadata", {})
    return {
        "type": identity_type,
        "id": metadata.get("id"),
        "parent_id": metadata.get("parent_id"),
    }


def assert_frozen_authority(
    lease: dict[str, Any], cli: common.NebiusCLI, whoami: dict[str, Any] | None = None
) -> dict[str, str | None]:
    expected_profile = lease["request"]["nebius_profile"]
    if cli.profile != expected_profile:
        raise common.BrokerError(
            f"Nebius profile mismatch: frozen={expected_profile}, observed={cli.profile}"
        )
    observed = identity_from_whoami(whoami or cli.run(["iam", "whoami"]))
    if observed != lease["request"]["authority_identity"]:
        raise common.AuthenticationError(
            "Nebius authority identity differs from the immutable lease; do not switch credentials"
        )
    return observed


def run_read_only_preflight(lease: dict[str, Any], cli: common.NebiusCLI) -> dict[str, Any]:
    request = lease["request"]
    profile = lease["profile_snapshot"]
    whoami = cli.run(["iam", "whoami"])
    identity = assert_frozen_authority(lease, cli, whoami)
    identity_type = str(identity["type"])
    project = cli.run(["iam", "project", "get", request["project_id"]])
    if common.project_region(project) != request["region"]:
        raise common.BrokerError("live project region differs from the immutable request")
    if project.get("status", {}).get("container_state") != "ACTIVE":
        raise common.BrokerError("project is not ACTIVE")
    versions = cli.run(["mk8s", "v1", "cluster", "list-control-plane-versions"])
    version_strings = json.dumps(versions)
    if request["cluster_version"] not in version_strings:
        raise common.BrokerError("pinned Kubernetes version is not currently advertised")
    compatibility = {}
    for node_kind in ("system_node_group", "gpu_node_group"):
        node = profile[node_kind]
        value = cli.run(
            [
                "mk8s",
                "v1",
                "node-group",
                "get-compatibility-matrix",
                "--cluster-kubernetes-version",
                request["cluster_version"],
                "--platform",
                node["platform"],
            ]
        )
        text = json.dumps(value)
        if node["os"] not in text or (node.get("driver_preset") and node["driver_preset"] not in text):
            raise common.BrokerError(f"{node_kind} OS/driver combination is not compatible")
        compatibility[node_kind] = value
    platforms = cli.run(["compute", "platform", "list", "--parent-id", request["project_id"], "--all"])
    advertised = {
        item.get("metadata", {}).get("name"): {
            preset.get("name") for preset in item.get("spec", {}).get("presets", [])
        }
        for item in platforms.get("items", [])
    }
    for node_kind in ("system_node_group", "gpu_node_group"):
        node = profile[node_kind]
        if node["preset"] not in advertised.get(node["platform"], set()):
            raise common.BrokerError(f"{node_kind} platform/preset is not advertised")
    quotas = cli.run(["quotas", "quota-allowance", "list", "--parent-id", request["project_id"], "--all"])
    advice: dict[str, Any]
    try:
        capacity = cli.run(
            [
                "capacity",
                "resource-advice",
                "list",
                "--parent-id",
                project.get("metadata", {}).get("parent_id"),
                "--all",
            ]
        )
        gpu_profile = profile["gpu_node_group"]
        matched = [
            item
            for item in capacity.get("items", [])
            if item.get("spec", {}).get("region") == request["region"]
            and item.get("spec", {}).get("compute_instance", {}).get("platform")
            == gpu_profile["platform"]
            and item.get("spec", {}).get("compute_instance", {}).get("preset", {}).get("name")
            == gpu_profile["preset"]
        ]
        advice = {"status": "AVAILABLE", "matched": matched}
    except common.AuthenticationError:
        raise
    except common.BrokerError as exc:
        advice = {"status": "UNAVAILABLE", "failure": str(exc)[:1200], "matched": []}
    return {
        "checked_at": common.iso(common.utc_now()),
        "mutation_count": 0,
        "nebius_profile": cli.profile,
        "identity": identity,
        "project": {
            "id": request["project_id"],
            "tenant_id": project.get("metadata", {}).get("parent_id"),
            "region": common.project_region(project),
            "state": project.get("status", {}).get("container_state"),
        },
        "kubernetes_version": request["cluster_version"],
        "compatibility": compatibility,
        "quota_usage": [
            {
                "name": item.get("metadata", {}).get("name"),
                "region": item.get("spec", {}).get("region"),
                "usage": item.get("status", {}).get("usage"),
                "unit": item.get("status", {}).get("unit"),
                "allowance": item.get("spec", {}).get("allowance"),
            }
            for item in quotas.get("items", [])
            if item.get("metadata", {}).get("name", "").startswith(("compute.", "mk8s.", "vpc.", "registry.", "storage."))
        ],
        "planning_capacity_advice": advice,
        "capacity_note": "Planning advice is non-authoritative; Arm B repeats advice after durable T0 before every GPU create.",
        "secrets_recorded": False,
    }


def graph_name(lease: dict[str, Any], key: str) -> str:
    return next(item["resource_name"] for item in lease["resource_graph"] if item["key"] == key)


def wait_running(
    cli: common.NebiusCLI,
    kind: str,
    resource_id: str,
    *,
    ready_nodes: int | None = None,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = cli.run([*RESOURCE_COMMANDS[kind]["get"], resource_id], timeout=60)
        status = last.get("status", {})
        if status.get("state") == "RUNNING" and (
            ready_nodes is None or int(status.get("ready_node_count", 0)) == ready_nodes
        ):
            return last
        events = status.get("events", [])
        if any(
            item.get("last_occurrence", {}).get("level") == "ERROR" for item in events
        ):
            raise common.BrokerError(f"{kind} reported a provider error: {json.dumps(events)[:1200]}")
        time.sleep(5)
    raise common.BrokerError(
        f"{kind}:{resource_id} did not become RUNNING/Ready; last_status={json.dumps(last.get('status', {}))[:1200]}"
    )


def add_provider_resource(
    lease: dict[str, Any],
    *,
    kind: str,
    resource_id: str,
    name: str,
    managed_by_resource_id: str,
    created_at: str | None,
    parent_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = next((item for item in lease["resources"] if item.get("id") == resource_id), None)
    if existing:
        verify_resource(lease, existing)
        if (
            existing.get("kind") != kind
            or existing.get("managed_by_resource_id") != managed_by_resource_id
        ):
            raise common.BrokerError("provider child identity conflicts with signed resource row")
        return existing
    item = {
        "kind": kind,
        "name": name,
        "id": resource_id,
        "project_id": lease["project_id"],
        "region": lease["region"],
        "parent_id": parent_id,
        "depends_on": [managed_by_resource_id],
        "created_at": created_at or common.iso(common.utc_now()),
        "create_operation_id": None,
        "deletion_mode": "PROVIDER_CASCADE",
        "managed_by_resource_id": managed_by_resource_id,
        "intended_spec_sha256": None,
        "provider_spec_sha256": common.sha256_json((metadata or {}).get("compute_spec", {})),
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
        "provider_metadata": metadata or {},
    }
    authenticate_resource(lease, item)
    lease["resources"].append(item)
    event(
        lease,
        "resource.provider_child.reconciled",
        "PASS",
        kind=kind,
        resource_id=resource_id,
        managed_by_resource_id=managed_by_resource_id,
    )
    return item


def reconcile_network_children(lease: dict[str, Any], cli: common.NebiusCLI) -> None:
    network = find_resource(lease, "network")
    if not network:
        return
    value = cli.run([*RESOURCE_COMMANDS["network"]["get"], network["id"]])
    public_pools = value.get("spec", {}).get("ipv4_public_pools", {}).get("pools", [])
    if public_pools:
        raise common.BrokerError("fresh Kubernetes VPC unexpectedly contains a public address pool")
    for ref in value.get("spec", {}).get("ipv4_private_pools", {}).get("pools", []):
        child = cli.run(["vpc", "pool", "get", ref["id"]])
        created = child.get("metadata", {}).get("created_at")
        if created and common.parse_utc(created) < common.parse_utc(lease["created_at"]):
            raise common.BrokerError("VPC references a pool that predates the lease; preserve and stop")
        add_provider_resource(
            lease,
            kind="pool",
            resource_id=common.metadata_id(child, "pool"),
            name=child.get("metadata", {}).get("name", "provider-private-pool"),
            managed_by_resource_id=network["id"],
            created_at=created,
            parent_id=child.get("metadata", {}).get("parent_id"),
        )
    route_id = value.get("status", {}).get("default_route_table_id")
    if route_id:
        child = cli.run(["vpc", "route-table", "get", route_id])
        created = child.get("metadata", {}).get("created_at")
        if created and common.parse_utc(created) < common.parse_utc(lease["created_at"]):
            raise common.BrokerError("VPC references a route table that predates the lease")
        add_provider_resource(
            lease,
            kind="route_table",
            resource_id=common.metadata_id(child, "route_table"),
            name=child.get("metadata", {}).get("name", "provider-route-table"),
            managed_by_resource_id=network["id"],
            created_at=created,
            parent_id=child.get("metadata", {}).get("parent_id"),
        )


def kubeconfig_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_regular_file(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise common.BrokerError("durability target is not a regular file")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_replace(source: Path, destination: Path) -> None:
    if source.parent.resolve() != destination.parent.resolve():
        raise common.BrokerError("durable replace must remain in one task-owned directory")
    fsync_regular_file(source)
    os.replace(source, destination)
    common.fsync_directory(destination.parent)


def durable_unlink(path: Path) -> None:
    path.unlink()
    common.fsync_directory(path.parent)


def validate_kubeconfig_file(path: Path) -> None:
    staging_name = path.name.startswith(".") and ".yaml." in path.name and path.name.endswith(
        ".broker-staging"
    )
    if path.parent.resolve() != KUBECONFIG_ROOT.resolve() or not (
        path.suffix == ".yaml" or staging_name
    ):
        raise common.BrokerError("kubeconfig path is outside the task-owned authority directory")
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise common.BrokerError("kubeconfig authority cannot be a symlink or non-regular file")
    if details.st_uid != os.getuid():
        raise common.BrokerError("kubeconfig authority is not owned by the current task user")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise common.BrokerError("kubeconfig authority permissions are broader than 0600")


def cluster_internal_endpoint(cluster_value: dict[str, Any]) -> str:
    endpoints = cluster_value.get("status", {}).get("control_plane", {}).get("endpoints", {})
    if endpoints.get("public_endpoint"):
        raise common.BrokerError("public control-plane endpoint violates the immutable isolation gate")
    endpoint = endpoints.get("internal_endpoint") or endpoints.get("private_endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise common.BrokerError("cluster has no exact private control-plane endpoint")
    return endpoint


def kubeconfig_content_authority(
    path: Path, *, cluster_id: str, context: str, endpoint: str
) -> dict[str, Any]:
    validate_kubeconfig_file(path)
    try:
        value = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise common.BrokerError("kubeconfig authority is not valid YAML") from exc
    if not isinstance(value, dict) or value.get("current-context") != context:
        raise common.BrokerError("kubeconfig current context differs from immutable authority")
    contexts = [
        item for item in value.get("contexts", []) if item.get("name") == context
    ]
    if len(contexts) != 1:
        raise common.BrokerError("kubeconfig does not contain one exact immutable context")
    context_value = contexts[0].get("context", {})
    cluster_name = context_value.get("cluster")
    user_name = context_value.get("user")
    clusters = [
        item for item in value.get("clusters", []) if item.get("name") == cluster_name
    ]
    users = [item for item in value.get("users", []) if item.get("name") == user_name]
    if len(clusters) != 1 or len(users) != 1:
        raise common.BrokerError("kubeconfig cluster/user authority is missing or ambiguous")
    cluster = clusters[0].get("cluster", {})
    if cluster.get("server") != endpoint:
        raise common.BrokerError("kubeconfig server differs from the private cluster endpoint")
    ca_data = cluster.get("certificate-authority-data")
    if not isinstance(ca_data, str) or not ca_data.strip():
        raise common.BrokerError("kubeconfig lacks embedded certificate authority data")
    return {
        "path": str(path),
        "sha256": kubeconfig_file_sha256(path),
        "mode": "0600",
        "cluster_id": cluster_id,
        "api_server": endpoint,
        "context": context,
        "cluster_entry": cluster_name,
        "user_entry": user_name,
        "ca_data_sha256": hashlib.sha256(ca_data.encode()).hexdigest(),
        "contents_recorded": False,
    }


def verify_kubeconfig_content(
    path: Path, expected: dict[str, Any]
) -> dict[str, Any]:
    authority_keys = {
        "path",
        "sha256",
        "mode",
        "cluster_id",
        "api_server",
        "context",
        "cluster_entry",
        "user_entry",
        "ca_data_sha256",
        "contents_recorded",
    }
    authority = {key: expected[key] for key in authority_keys}
    actual = kubeconfig_content_authority(
        path,
        cluster_id=authority["cluster_id"],
        context=authority["context"],
        endpoint=authority["api_server"],
    )
    if actual != authority:
        raise common.BrokerError("kubeconfig content authority mismatch; preserve file")
    return actual


def ensure_kubeconfig(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
    cluster_value: dict[str, Any],
) -> dict[str, Any]:
    path = Path(lease["kubeconfig_path"])
    operation_id = f"create:kubeconfig_authority:{path.name}"
    operation = operation_for(lease, operation_id)
    existing = find_resource(lease, "kubeconfig_authority")
    cluster_id = common.metadata_id(cluster_value, "cluster")
    endpoint = cluster_internal_endpoint(cluster_value)
    if existing:
        verify_resource(lease, existing)
        verify_kubeconfig_content(path, existing["provider_metadata"])
        return existing
    local_spec = {
        "cluster_id": cluster_id,
        "context": lease["kubernetes_context"],
        "endpoint": endpoint,
        "access": "internal",
    }
    staging = path.with_name(f".{path.name}.{lease['plan_sha256'][:16]}.broker-staging")
    if path.exists():
        if operation is None or operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
            raise common.BrokerError("pre-existing kubeconfig path collision; preserve it")
        verify_operation(lease, operation)
        expected = operation.get("kubeconfig_content_authority")
        signature = operation.get("kubeconfig_content_signature")
        if not expected or not signature:
            raise common.BrokerError(
                "unknown kubeconfig appeared before signed content authority; preserve it"
            )
        verify_signature("kubeconfig-content", lease, expected, signature)
        verify_kubeconfig_content(path, expected)
    elif operation and operation.get("kubeconfig_content_authority"):
        verify_operation(lease, operation)
        expected = operation["kubeconfig_content_authority"]
        verify_signature(
            "kubeconfig-content",
            lease,
            expected,
            operation["kubeconfig_content_signature"],
        )
        if not staging.exists():
            raise common.BrokerError("signed kubeconfig staging receipt exists but file is absent")
        verify_kubeconfig_content(staging, {**expected, "path": str(staging)})
        durable_replace(staging, path)
    elif operation:
        verify_operation(lease, operation)
        if staging.exists():
            raise common.BrokerError(
                "unreceipted kubeconfig staging file is ambiguous; preserve it"
            )
    if not path.exists():
        if operation is None:
            operation = {
                "operation_id": operation_id,
                "kind": "kubeconfig_authority",
                "name": path.name,
                "parent_id": cluster_id,
                "depends_on": [cluster_id],
                "payload_sha256": common.sha256_json(local_spec),
                "spec_sha256": common.sha256_json(local_spec),
                "requested_spec": local_spec,
                "status": "INTENT_RECORDED",
                "started_at_utc": common.iso(common.utc_now()),
                "started_monotonic_ns": time.monotonic_ns(),
                "completed_at_utc": None,
                "resource_id": None,
                "failure": None,
            }
            authenticate_operation(lease, operation)
            lease["resource_create_operations"].append(operation)
            event(lease, "kubeconfig.authority.started", "PASS", path=str(path))
            save(lease_path, registry_path, lease)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or staging.exists():
            raise common.BrokerError("kubeconfig staging authority is unsafe or ambiguous")
        cli.run(
            [
                "mk8s",
                "v1",
                "cluster",
                "get-credentials",
                "--id",
                cluster_id,
                "--internal",
                "--context-name",
                lease["kubernetes_context"],
                "--kubeconfig",
                str(staging),
            ],
            json_output=False,
            timeout=180,
        )
        os.chmod(staging, 0o600)
        fsync_regular_file(staging)
        generated = kubeconfig_content_authority(
            staging,
            cluster_id=cluster_id,
            context=lease["kubernetes_context"],
            endpoint=endpoint,
        )
        expected = {**generated, "path": str(path)}
        operation["kubeconfig_content_authority"] = expected
        operation["kubeconfig_content_signature"] = sign_material(
            "kubeconfig-content", lease, expected
        )
        save(lease_path, registry_path, lease)
        durable_replace(staging, path)
        os.chmod(path, 0o600)
    expected = operation.get("kubeconfig_content_authority")
    if not expected:
        raise common.BrokerError("kubeconfig lacks a signed content-authority receipt")
    verify_signature(
        "kubeconfig-content", lease, expected, operation["kubeconfig_content_signature"]
    )
    verify_kubeconfig_content(path, expected)
    digest = expected["sha256"]
    identity = lease["preflight"]["identity"]
    item = {
        "kind": "kubeconfig_authority",
        "name": path.name,
        "id": f"local-kubeconfig-sha256:{digest}",
        "project_id": lease["project_id"],
        "region": lease["region"],
        "parent_id": lease["cluster_id"],
        "depends_on": [lease["cluster_id"]],
        "created_at": common.iso(common.utc_now()),
        "create_operation_id": operation_id,
        "deletion_mode": None,
        "managed_by_resource_id": None,
        "intended_spec_sha256": common.sha256_json(local_spec),
        "provider_spec_sha256": common.sha256_json(local_spec),
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
        "provider_metadata": {**expected, "identity_id": identity["id"]},
    }
    authenticate_resource(lease, item)
    lease["resources"].append(item)
    operation["status"] = "CREATED" if operation["status"] == "INTENT_RECORDED" else "RECONCILED_AFTER_INTERRUPTION"
    operation["completed_at_utc"] = common.iso(common.utc_now())
    operation["completed_monotonic_ns"] = time.monotonic_ns()
    operation["resource_id"] = item["id"]
    lease["api_server"] = endpoint
    event(lease, "kubeconfig.authority.ready", "PASS", path=str(path), sha256=digest)
    save(lease_path, registry_path, lease)
    return item


def compute_id_from_provider_id(provider_id: str) -> str | None:
    match = re.search(r"(computeinstance-[a-z0-9]+)", provider_id)
    return match.group(1) if match else None


def node_belongs_to_group(node: dict[str, Any], node_group_id: str) -> bool:
    metadata = node.get("metadata", {})
    labels = metadata.get("labels", {}) or {}
    label_values = {
        labels.get("nebius.com/node-group-id"),
        labels.get("mk8s.nebius.com/node-group-id"),
        labels.get("node-group-id"),
    }
    return node_group_id in label_values or str(metadata.get("name", "")).startswith(node_group_id)


def provider_instance_group_id(instance: dict[str, Any]) -> str | None:
    """Extract only documented/provider-emitted exact node-group ownership markers."""

    metadata = instance.get("metadata", {})
    labels = metadata.get("labels", {}) or {}
    for key in (
        "nebius.com/node-group-id",
        "mk8s.nebius.com/node-group-id",
        "node-group-id",
    ):
        if labels.get(key):
            return str(labels[key])
    for container in (instance.get("spec", {}), instance.get("status", {})):
        for key in ("node_group_id", "nodegroup_id", "managed_kubernetes_node_group_id"):
            if container.get(key):
                return str(container[key])
    return None


def reconcile_provider_nodes(
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    node_group: dict[str, Any],
    node_kind: str,
) -> list[dict[str, Any]]:
    """Discover provider Compute children without depending on kubeconfig access."""

    verify_resource(lease, node_group)
    values = cli.run(
        [*RESOURCE_COMMANDS["node"]["list"], "--parent-id", lease["project_id"], "--all"]
    )
    matching = [
        value
        for value in values.get("items", [])
        if provider_instance_group_id(value) == node_group["id"]
    ]
    current_ids = {common.metadata_id(value, "node") for value in matching}
    for old in [
        item
        for item in lease["resources"]
        if item["kind"] == node_kind
        and item.get("managed_by_resource_id") == node_group["id"]
        and not item.get("deleted_at")
        and item["id"] not in current_ids
    ]:
        if cli.run(get_args(node_kind, old["id"]), allow_not_found=True) is None:
            verified = common.iso(precise_utc_now())
            old["deleted_at"] = verified
            old["absence_verified_at"] = verified
            old["cleanup_evidence"] = (
                f"{get_args(node_kind, old['id'])} -> NotFound during replacement reconciliation"
            )
            event(
                lease,
                "resource.provider_child.replaced",
                "PASS",
                kind=node_kind,
                resource_id=old["id"],
                managed_by_resource_id=node_group["id"],
            )
    resources = []
    for value in matching:
        metadata = value.get("metadata", {})
        resource_id = common.metadata_id(value, "node")
        created = metadata.get("created_at")
        if created and common.parse_utc(created) < common.parse_utc(node_group["created_at"]):
            raise common.BrokerError("provider node predates its signed node-group receipt")
        compute_spec = value.get("spec", {})
        profile_key = "gpu_node_group" if node_kind == "gpu_node" else "system_node_group"
        profile = lease["profile_snapshot"][profile_key]
        compute_resources = compute_spec.get("resources", {})
        if (
            compute_resources.get("platform") != profile["platform"]
            or compute_resources.get("preset") != profile["preset"]
        ):
            raise common.BrokerError("provider child Compute shape differs from signed node-group plan")
        if node_kind == "gpu_node" and compute_spec.get("preemptible") != {}:
            raise common.BrokerError("provider child GPU node is not preemptible")
        if node_kind == "system_node" and "preemptible" in compute_spec:
            raise common.BrokerError("provider child system node unexpectedly is preemptible")
        resource = add_provider_resource(
            lease,
            kind=node_kind,
            resource_id=resource_id,
            name=metadata.get("name", resource_id),
            managed_by_resource_id=node_group["id"],
            created_at=created,
            parent_id=metadata.get("parent_id"),
            metadata={
                "node_group_id": node_group["id"],
                "compute_spec": compute_spec,
                "compute_spec_sha256": common.sha256_json(compute_spec),
                "discovery": "compute.instance.list",
            },
        )
        resources.append(resource)
    return resources


def reconcile_nodes(
    lease: dict[str, Any], kubectl: KubeCTL, node_group: dict[str, Any], node_kind: str
) -> list[dict[str, Any]]:
    path = Path(lease["kubeconfig_path"])
    value = kubectl.run(path, ["get", "nodes"])
    group_id = node_group["id"]
    matching = [item for item in value.get("items", []) if node_belongs_to_group(item, group_id)]
    expected = lease["profile_snapshot"][
        "gpu_node_group" if node_kind == "gpu_node" else "system_node_group"
    ]["node_count"]
    if len(matching) != expected:
        raise common.BrokerError(
            f"expected {expected} exact Kubernetes nodes for {group_id}, observed {len(matching)}"
        )
    provider_resources = {
        item["id"]: item
        for item in lease["resources"]
        if item["kind"] == node_kind
        and item.get("managed_by_resource_id") == group_id
        and not item.get("deleted_at")
    }
    resources = []
    for node in matching:
        ready = next(
            (
                condition.get("status")
                for condition in node.get("status", {}).get("conditions", [])
                if condition.get("type") == "Ready"
            ),
            None,
        )
        if ready != "True":
            raise common.BrokerError(f"node {node.get('metadata', {}).get('name')} is not Ready")
        provider_id = node.get("spec", {}).get("providerID", "")
        compute_id = compute_id_from_provider_id(provider_id)
        if not compute_id:
            raise common.BrokerError("Kubernetes node lacks an exact Nebius Compute provider ID")
        resource = provider_resources.get(compute_id)
        if not resource:
            raise common.BrokerError(
                "Kubernetes node was not first reconciled through the provider Compute API"
            )
        resources.append(resource)
    return resources


def capture_support_isolation(lease: dict[str, Any], cli: common.NebiusCLI) -> dict[str, Any]:
    resources = {item["kind"]: item for item in lease["resources"] if not item.get("deleted_at")}
    network = cli.run([*RESOURCE_COMMANDS["network"]["get"], resources["network"]["id"]])
    rules = cli.run(
        ["vpc", "security-rule", "list", "--parent-id", resources["security_group"]["id"], "--all"]
    )
    cluster = cli.run([*RESOURCE_COMMANDS["cluster"]["get"], resources["cluster"]["id"]])
    system = cli.run(
        [*RESOURCE_COMMANDS["system_node_group"]["get"], resources["system_node_group"]["id"]]
    )
    template = system.get("spec", {}).get("template", {})
    control_plane_spec = cluster.get("spec", {}).get("control_plane", {})
    control_plane_endpoints = cluster.get("status", {}).get("control_plane", {}).get(
        "endpoints", {}
    )
    interfaces = template.get("network_interfaces", [])
    failures = []
    if network.get("spec", {}).get("ipv4_public_pools", {}).get("pools", []):
        failures.append("task VPC has a public address pool")
    if rules.get("items"):
        failures.append("task security group is not deny-all")
    if cluster.get("status", {}).get("state") != "RUNNING":
        failures.append("cluster is not RUNNING")
    if "endpoints" in control_plane_spec or control_plane_endpoints.get("public_endpoint"):
        failures.append("cluster exposes or requests a public control-plane endpoint")
    if "karpenter" in control_plane_spec:
        failures.append("disabled Karpenter must be omitted from provider schema")
    if (
        control_plane_endpoints.get("internal_endpoint")
        or control_plane_endpoints.get("private_endpoint")
    ) != lease["api_server"]:
        failures.append("cluster private endpoint differs from kubeconfig authority")
    if system.get("status", {}).get("state") != "RUNNING" or int(
        system.get("status", {}).get("ready_node_count", 0)
    ) != 1:
        failures.append("system node group is not exactly one Ready node")
    if template.get("preemptible"):
        failures.append("system node group must be normal, not preemptible")
    if any(item.get("public_ip_address") for item in interfaces):
        failures.append("system node has a public IP request")
    if template.get("service_account_id") != resources["service_account"]["id"]:
        failures.append("system node group does not use the task-owned service account")
    if interfaces != [{"subnet_id": resources["subnet"]["id"]}]:
        failures.append("system node network interface differs from the task-owned subnet")
    if failures:
        raise common.BrokerError("support isolation proof failed: " + "; ".join(failures))
    return {
        "verified_at": common.iso(common.utc_now()),
        "project_id": lease["project_id"],
        "region": lease["region"],
        "fresh_task_owned": True,
        "resource_prefix": lease["prefix"],
        "cluster": {
            "id": resources["cluster"]["id"],
            "state": cluster.get("status", {}).get("state"),
            "version": cluster.get("status", {}).get("control_plane", {}).get("version"),
            "private_control_plane_endpoint": lease["api_server"],
            "public_control_plane_endpoint": None,
            "public_worker_ips": [],
            "karpenter": False,
        },
        "network": {
            "id": resources["network"]["id"],
            "subnet_id": resources["subnet"]["id"],
            "public_pool_ids": [],
        },
        "security_group": {
            "id": resources["security_group"]["id"],
            "rule_count": 0,
            "attachment": "NOT_SUPPORTED_BY_MANAGED_K8S_NODE_GROUP_V1_API",
            "role": "task-owned deny-all lifecycle sentinel; not claimed as node enforcement",
        },
        "iam": {
            "service_account_id": resources["service_account"]["id"],
            "group_id": resources["iam_group"]["id"],
            "membership_id": resources["group_membership"]["id"],
            "registry_access_permit_id": resources["registry_access_permit"]["id"],
            "artifact_access_permit_id": resources["bucket_access_permit"]["id"],
            "pre_existing_group_reused": False,
        },
        "artifact_dependencies": {
            "registry_id": resources["registry"]["id"],
            "bucket_id": resources["bucket"]["id"],
        },
        "system_node_group": {
            "id": resources["system_node_group"]["id"],
            "node_count": 1,
            "ready_node_count": 1,
            "preemptible": False,
            "node_ids": [
                item["id"]
                for item in lease["resources"]
                if item["kind"] == "system_node" and not item.get("deleted_at")
            ],
        },
        "kubeconfig_authority": resources["kubeconfig_authority"]["provider_metadata"],
        "target_neutral": not any(
            item["kind"] in {"gpu_node_group", "gpu_node"} and not item.get("deleted_at")
            for item in lease["resources"]
        ),
        "secrets_recorded": False,
    }


@lease_mutation_locked
def provision_control_plane(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    assert_live_creation_prerequisites(lease)
    if lease["state"] in {"SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", "ACTIVE", "ACTIVE_ATTEMPT"}:
        assert_frozen_authority(lease, cli)
        for group_kind, node_kind in (
            ("system_node_group", "system_node"),
            ("gpu_node_group", "gpu_node"),
        ):
            for group in [
                item
                for item in lease["resources"]
                if item["kind"] == group_kind and not item.get("deleted_at")
            ]:
                reconcile_provider_nodes(lease, cli, group, node_kind)
                if Path(lease["kubeconfig_path"]).exists():
                    reconcile_nodes(lease, kubectl, group, node_kind)
        save(lease_path, registry_path, lease)
        return lease
    if lease["state"] not in {"PLANNED", "CONTROL_PLANE_CREATING", "CONTROL_PLANE_FAILED"}:
        raise common.BrokerError(f"control-plane provisioning is not admitted from {lease['state']}")
    if common.utc_now() >= common.parse_utc(lease["expires_at"]):
        raise common.BrokerError("cannot provision an expired Kubernetes lease")
    request = lease["request"]
    profile = lease["profile_snapshot"]
    names = {item["key"]: item["resource_name"] for item in lease["resource_graph"]}
    try:
        event(lease, "preflight.read_only.started", "PASS", mutation_count=0)
        lease["preflight"] = run_read_only_preflight(lease, cli)
        event(
            lease,
            "preflight.read_only.completed",
            "PASS",
            mutation_count=0,
            planning_capacity_status=lease["preflight"]["planning_capacity_advice"]["status"],
        )
        lease["state"] = "CONTROL_PLANE_CREATING"
        save(lease_path, registry_path, lease)
        project_id = lease["project_id"]
        tenant_id = lease["preflight"]["project"]["tenant_id"]
        network = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="network",
            name=names["network"],
            parent_id=project_id,
            spec={"ipv4_public_pools": {"pools": []}},
            depends_on=[],
            timeout=180,
        )
        subnet = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="subnet",
            name=names["subnet"],
            parent_id=project_id,
            spec={
                "network_id": network["id"],
                "ipv4_private_pools": {"use_network_pools": True},
                "ipv4_public_pools": {"use_network_pools": False},
            },
            depends_on=[network["id"]],
            timeout=180,
        )
        security_group = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="security_group",
            name=names["security_group"],
            parent_id=project_id,
            spec={"network_id": network["id"]},
            depends_on=[network["id"]],
            timeout=180,
        )
        service_account = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="service_account",
            name=names["service_account"],
            parent_id=project_id,
            spec={},
            depends_on=[],
            timeout=180,
        )
        iam_group = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="iam_group",
            name=names["iam_group"],
            parent_id=tenant_id,
            spec={},
            depends_on=[],
            timeout=180,
        )
        membership = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="group_membership",
            name=names["group_membership"],
            parent_id=iam_group["id"],
            spec={"member_id": service_account["id"]},
            depends_on=[iam_group["id"], service_account["id"]],
            timeout=180,
        )
        registry = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="registry",
            name=names["registry"],
            parent_id=project_id,
            spec={},
            depends_on=[],
            timeout=180,
        )
        registry_permit = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="registry_access_permit",
            name=names["registry_access_permit"],
            parent_id=iam_group["id"],
            spec={"resource_id": registry["id"], "role": "viewer"},
            depends_on=[iam_group["id"], registry["id"]],
            timeout=180,
        )
        bucket = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="bucket",
            name=names["bucket"],
            parent_id=project_id,
            spec={
                "default_storage_class": "STANDARD",
                "force_storage_class": True,
                "max_size_bytes": int(request["artifact_storage"]["max_size_gib"]) * 1024**3,
                "object_audit_logging": "ALL",
                "versioning_policy": "DISABLED",
            },
            depends_on=[],
            timeout=180,
        )
        bucket_permit = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="bucket_access_permit",
            name=names["bucket_access_permit"],
            parent_id=iam_group["id"],
            spec={"resource_id": bucket["id"], "role": "storage.editor"},
            depends_on=[iam_group["id"], bucket["id"]],
            timeout=180,
        )
        cluster = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="cluster",
            name=names["cluster"],
            parent_id=project_id,
            spec={
                "control_plane": {
                    "audit_logs": {},
                    "etcd_cluster_size": 3,
                    "subnet_id": subnet["id"],
                    "version": request["cluster_version"],
                },
                "kube_network": {"service_cidrs": [profile["service_cidr"]]},
            },
            depends_on=[subnet["id"]],
            timeout=1200,
        )
        lease["cluster_id"] = cluster["id"]
        cluster_value = wait_running(cli, "cluster", cluster["id"], timeout_seconds=1200)
        lease["readiness_timestamps"]["cluster_running_at_utc"] = common.iso(common.utc_now())
        system_profile = profile["system_node_group"]
        system_group = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="system_node_group",
            name=names["system_node_group"],
            parent_id=cluster["id"],
            spec={
                "version": request["cluster_version"],
                "fixed_node_count": system_profile["node_count"],
                "template": {
                    "metadata": {
                        "labels": {
                            "mlsp.nebius.ai/resource-prefix": lease["prefix"],
                            "mlsp.nebius.ai/node-role": "system",
                        }
                    },
                    "resources": {
                        "platform": system_profile["platform"],
                        "preset": system_profile["preset"],
                    },
                    "boot_disk": {
                        "size_bytes": int(system_profile["boot_disk_gib"]) * GIB,
                        "block_size_bytes": 4096,
                        "type": "NETWORK_SSD",
                    },
                    "os": system_profile["os"],
                    "network_interfaces": [{"subnet_id": subnet["id"]}],
                    "service_account_id": service_account["id"],
                    "reservation_policy": {"policy": "forbid"},
                },
            },
            depends_on=[
                cluster["id"],
                subnet["id"],
                service_account["id"],
                registry_permit["id"],
                bucket_permit["id"],
            ],
            timeout=1200,
        )
        wait_running(
            cli,
            "system_node_group",
            system_group["id"],
            ready_nodes=system_profile["node_count"],
            timeout_seconds=1200,
        )
        lease["readiness_timestamps"]["system_node_group_ready_at_utc"] = common.iso(
            common.utc_now()
        )
        system_nodes = reconcile_provider_nodes(
            lease, cli, system_group, "system_node"
        )
        if len(system_nodes) != system_profile["node_count"]:
            raise common.BrokerError("provider API did not expose the exact system node child")
        save(lease_path, registry_path, lease)
        ensure_kubeconfig(lease_path, registry_path, lease, cli, kubectl, cluster_value)
        reconcile_nodes(lease, kubectl, system_group, "system_node")
        reconcile_network_children(lease, cli)
        lease["isolation_proof"] = capture_support_isolation(lease, cli)
        lease["state"] = "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"
        event(
            lease,
            "support.ready",
            "PASS",
            cluster_id=cluster["id"],
            gpu_node_group_count=0,
            request_specific_work_started=False,
        )
        save(lease_path, registry_path, lease)
        return lease
    except Exception as exc:
        lease = common.load_json(lease_path)
        assert_integrity(lease)
        lease["state"] = "CONTROL_PLANE_FAILED"
        failure = {
            "at": common.iso(common.utc_now()),
            "stage": "control_plane",
            "attempt_id": None,
            "error": str(exc)[:1500],
        }
        if failure not in lease["failures"]:
            lease["failures"].append(failure)
        event(lease, "support.failed", "FAIL", error=str(exc)[:1000])
        save(lease_path, registry_path, lease)
        raise


def validate_demand(value: dict[str, Any], lease: dict[str, Any]) -> dict[str, Any]:
    required_keys(
        value,
        {
            "schema_version",
            "lease_id",
            "attempt_id",
            "accepted_event_path",
            "accepted_event_sha256",
            "accepted_event_receipt_path",
            "accepted_event_receipt_sha256",
            "ledger_id",
            "ledger_sequence",
            "trace_id",
            "request_id",
            "event_id",
            "scenario",
            "target",
            "input",
        },
        "demand",
    )
    if value["schema_version"] != DEMAND_SCHEMA_VERSION:
        raise common.BrokerError("unsupported Kubernetes demand schema")
    if value["lease_id"] != lease["lease_id"]:
        raise common.BrokerError("demand lease_id differs from the target lease")
    if not ATTEMPT_ID.fullmatch(str(value["attempt_id"])):
        raise common.BrokerError("attempt_id contains unsafe characters")
    if not HEX64.fullmatch(str(value["accepted_event_sha256"])):
        raise common.BrokerError("accepted_event_sha256 must be a SHA-256 digest")
    if not HEX64.fullmatch(str(value["accepted_event_receipt_sha256"])):
        raise common.BrokerError("accepted_event_receipt_sha256 must be a SHA-256 digest")
    for field in ("ledger_id", "trace_id", "request_id", "event_id"):
        if not isinstance(value[field], str) or not value[field]:
            raise common.BrokerError(f"{field} must be a non-empty string")
    if value["scenario"] not in lease["request"]["allowed_scenarios"]:
        raise common.BrokerError("demand scenario is outside the frozen lease")
    model_id = value.get("target", {}).get("model_id")
    binding = lease["request"]["model_request_bindings"].get(model_id)
    if not binding or value["target"] != binding["target"] or value["input"] != binding["input"]:
        raise common.BrokerError("demand target/input identity differs from the frozen lease")
    if int(value["ledger_sequence"]) < 0:
        raise common.BrokerError("ledger_sequence must be nonnegative")
    path = Path(str(value["accepted_event_path"]))
    if not path.is_absolute():
        raise common.BrokerError("accepted_event_path must be absolute")
    receipt_path = Path(str(value["accepted_event_receipt_path"]))
    if not receipt_path.is_absolute():
        raise common.BrokerError("accepted_event_receipt_path must be absolute")
    normalized = dict(value)
    normalized["accepted_event_path"] = str(path)
    normalized["accepted_event_receipt_path"] = str(receipt_path)
    normalized["ledger_sequence"] = int(value["ledger_sequence"])
    return normalized


def current_boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError as exc:
        raise common.BrokerError("cannot bind accepted-event monotonic clock to host boot") from exc


def external_acceptance_message(material: dict[str, Any]) -> bytes:
    return common.canonical(
        {
            "domain": EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA,
            "authority_id": material.get("authority_id"),
            "material": material,
        }
    ).encode("ascii")


def read_external_acceptance_receipt(
    demand: dict[str, Any], lease: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(demand["accepted_event_receipt_path"])
    try:
        details = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise common.BrokerError("trusted external accepted-event receipt is missing") from exc
    if (
        path.resolve() != path
        or stat.S_ISLNK(details.st_mode)
        or not stat.S_ISREG(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) & 0o077
    ):
        raise common.BrokerError("trusted external accepted-event receipt path/owner/mode is unsafe")
    if hashlib.sha256(raw).hexdigest() != demand["accepted_event_receipt_sha256"]:
        raise common.BrokerError("trusted external accepted-event receipt file digest mismatch")
    try:
        envelope = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise common.BrokerError("trusted external accepted-event receipt is invalid JSON") from exc
    required_keys(envelope, {"material", "signature_base64"}, "external accepted-event receipt")
    material = envelope["material"]
    if not isinstance(material, dict):
        raise common.BrokerError("external accepted-event receipt material must be an object")
    required_keys(
        material,
        {
            "schema_version",
            "authority_id",
            "recorder_id",
            "validator_id",
            "validator_sha256",
            "validator_reviewed_commit",
            "ledger_path",
            "ledger_sha256",
            "ledger_device",
            "ledger_inode",
            "ledger_mode",
            "ledger_size_bytes",
            "ledger_mtime_ns",
            "line_index",
            "canonical_event_sha256",
            "metric_contract_sha256",
            "trace_id",
            "trace_sha256",
            "trace_request_sha256",
            "ledger_id",
            "ledger_sequence",
            "request_id",
            "attempt_id",
            "event_id",
            "scenario",
            "target",
            "input",
            "observed_at_utc",
            "observed_monotonic_ns",
            "recorder",
            "validated_at_utc",
        },
        "external accepted-event receipt material",
    )
    authority = lease["accepted_event_authority"]
    if (
        material["schema_version"] != EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA
        or material["authority_id"] != lease["request"]["accepted_event_authority_id"]
        or material["recorder_id"] != authority["recorder_id"]
        or material["validator_id"] != authority["validator_id"]
        or material["validator_sha256"] != authority["validator_sha256"]
        or material["validator_reviewed_commit"] != authority["validator_reviewed_commit"]
    ):
        raise common.BrokerError("external accepted-event receipt provenance differs from reviewed authority")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(_unb64(authority["public_key_base64"]))
        public_key.verify(
            _unb64(str(envelope["signature_base64"])),
            external_acceptance_message(material),
        )
    except (InvalidSignature, ValueError) as exc:
        raise common.BrokerError("external accepted-event receipt signature is invalid") from exc
    validated_at = common.parse_utc(str(material["validated_at_utc"]))
    observed_at = common.parse_utc(str(material["observed_at_utc"]))
    if validated_at < observed_at:
        raise common.BrokerError("external accepted-event validation predates T0")
    return material, {
        "path": str(path),
        "sha256": demand["accepted_event_receipt_sha256"],
        "mode": format(stat.S_IMODE(details.st_mode), "04o"),
        "authority_id": material["authority_id"],
        "validator_id": material["validator_id"],
        "validator_sha256": material["validator_sha256"],
        "validator_reviewed_commit": material["validator_reviewed_commit"],
        "signature_verified": True,
        "validated_at_utc": common.iso(validated_at),
    }


def read_bound_accepted_event(demand: dict[str, Any], lease: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_material, trusted_receipt = read_external_acceptance_receipt(demand, lease)
    path = Path(demand["accepted_event_path"])
    try:
        details = path.lstat()
    except OSError as exc:
        raise common.BrokerError("accepted-event ledger is missing") from exc
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise common.BrokerError("accepted-event ledger must be a regular non-symlink file")
    if path.resolve() != path:
        raise common.BrokerError("accepted-event ledger path cannot traverse symlinks")
    if details.st_uid != os.getuid() or stat.S_IMODE(details.st_mode) & 0o077:
        raise common.BrokerError("accepted-event ledger owner/mode is not durable private authority")
    raw = path.read_bytes()
    matches: list[tuple[int, dict[str, Any]]] = []
    parsed: list[dict[str, Any]] = []
    for index, line in enumerate(raw.splitlines()):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise common.BrokerError("accepted-event ledger contains malformed JSONL") from exc
        if not isinstance(item, dict):
            raise common.BrokerError("accepted-event ledger contains a non-object row")
        parsed.append(item)
        if common.sha256_json(item) == demand["accepted_event_sha256"]:
            matches.append((index, item))
    if len(matches) != 1:
        raise common.BrokerError("accepted-event canonical digest is missing or ambiguous")
    line_index, accepted = matches[0]
    exact_identity = {
        "ledger_id": demand["ledger_id"],
        "ledger_sequence": demand["ledger_sequence"],
        "trace_id": demand["trace_id"],
        "request_id": demand["request_id"],
        "attempt_id": demand["attempt_id"],
        "event_id": demand["event_id"],
    }
    if any(accepted.get(key) != expected for key, expected in exact_identity.items()):
        raise common.BrokerError("accepted event does not join the exact demand identity")
    if accepted.get("schema") != BASELINE_EVENT_SCHEMA or accepted.get("event_type") != "request.accepted":
        raise common.BrokerError("accepted-event source is not a canonical request.accepted event")
    if accepted.get("attempt_sequence") != 0:
        raise common.BrokerError("request.accepted must be the first event for its attempt")
    earlier_same_attempt = [
        item
        for item in parsed
        if item is not accepted
        and item.get("attempt_id") == demand["attempt_id"]
        and int(item.get("ledger_sequence", 2**63 - 1)) < demand["ledger_sequence"]
    ]
    if earlier_same_attempt:
        raise common.BrokerError("accepted event is stale: an earlier attempt event exists")
    data = accepted.get("data", {})
    if data.get("boundary") != T0_BOUNDARY:
        raise common.BrokerError("accepted event has the wrong external T0 boundary")
    if accepted.get("trace_id") != lease["request"]["trace_id"]:
        raise common.BrokerError("accepted event trace identity differs from the frozen lease")
    if data.get("trace_request_sha256") != lease["request"]["trace_sha256"]:
        raise common.BrokerError("accepted event trace request digest differs from the frozen trace")
    if data.get("scenario") != demand["scenario"] or data.get("scenario") not in lease["request"]["allowed_scenarios"]:
        raise common.BrokerError("accepted event scenario differs from the frozen demand")
    target = data.get("target", {})
    request_input = data.get("input", {})
    model_id = target.get("model_id")
    binding = lease["request"]["model_request_bindings"].get(model_id)
    if (
        binding is None
        or target != demand["target"]
        or request_input != demand["input"]
        or target != binding["target"]
        or request_input != binding["input"]
    ):
        raise common.BrokerError("accepted event target/input identity differs from the frozen demand")
    recorder = accepted.get("recorder", {})
    boot_id = current_boot_id()
    if (
        recorder.get("recorder_id") != lease["accepted_event_authority"]["recorder_id"]
        or recorder.get("boot_id") != boot_id
        or recorder.get("clock_id") != f"linux-boottime:{boot_id}"
    ):
        raise common.BrokerError("accepted event clock/recorder authority differs from this host")
    accepted_at = common.parse_utc(str(accepted.get("observed_at_utc")))
    accepted_mono = int(accepted.get("observed_monotonic_ns", 0))
    if accepted_mono <= 0:
        raise common.BrokerError("accepted event monotonic clock is invalid")
    receipt_expected = {
        "ledger_path": str(path.resolve()),
        "ledger_sha256": hashlib.sha256(raw).hexdigest(),
        "ledger_device": details.st_dev,
        "ledger_inode": details.st_ino,
        "ledger_mode": format(stat.S_IMODE(details.st_mode), "04o"),
        "ledger_size_bytes": len(raw),
        "ledger_mtime_ns": details.st_mtime_ns,
        "line_index": line_index,
        "canonical_event_sha256": demand["accepted_event_sha256"],
        "metric_contract_sha256": lease["request"]["metric_contract_sha256"],
        "trace_id": lease["request"]["trace_id"],
        "trace_sha256": lease["request"]["trace_sha256"],
        "trace_request_sha256": lease["request"]["trace_sha256"],
        "ledger_id": accepted["ledger_id"],
        "ledger_sequence": accepted["ledger_sequence"],
        "request_id": accepted["request_id"],
        "attempt_id": accepted["attempt_id"],
        "event_id": accepted["event_id"],
        "scenario": demand["scenario"],
        "target": demand["target"],
        "input": demand["input"],
        "observed_at_utc": common.iso(accepted_at),
        "observed_monotonic_ns": accepted_mono,
        "recorder": recorder,
    }
    if any(receipt_material.get(key) != value for key, value in receipt_expected.items()):
        raise common.BrokerError(
            "trusted external receipt does not bind the exact ledger/metric/trace/scenario/target"
        )
    receipt = {
        "path": str(path.resolve()),
        "device": details.st_dev,
        "inode": details.st_ino,
        "mode": format(stat.S_IMODE(details.st_mode), "04o"),
        "size_bytes": len(raw),
        "mtime_ns": details.st_mtime_ns,
        "file_sha256_at_read": hashlib.sha256(raw).hexdigest(),
        "line_index": line_index,
        "canonical_event_sha256": demand["accepted_event_sha256"],
        "ledger_id": accepted["ledger_id"],
        "ledger_sequence": accepted["ledger_sequence"],
        "event_id": accepted["event_id"],
        "request_id": accepted["request_id"],
        "trace_id": accepted["trace_id"],
        "attempt_id": accepted["attempt_id"],
        "scenario": demand["scenario"],
        "target": demand["target"],
        "input": demand["input"],
        "metric_contract_sha256": lease["request"]["metric_contract_sha256"],
        "trace_sha256": lease["request"]["trace_sha256"],
        "external_validation_receipt": trusted_receipt,
        "recorder": recorder,
        "observed_at_utc": common.iso(accepted_at),
        "observed_monotonic_ns": accepted_mono,
    }
    return accepted, receipt


@lease_mutation_locked
def record_demand(
    lease_path: Path, registry_path: Path, demand_path: Path
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    assert_live_creation_prerequisites(lease)
    if lease["request"]["campaign_arm"] != "B_new_preemptible_node":
        raise common.BrokerError("post-T0 demand is valid only for B_new_preemptible_node")
    demand = validate_demand(common.load_json(demand_path), lease)
    _accepted_event, source_receipt = read_bound_accepted_event(demand, lease)
    demand_hash = common.sha256_json(demand)
    if lease.get("demand"):
        if lease["demand"]["demand_sha256"] != demand_hash:
            raise common.BrokerError("another demand is active; exact attempt cleanup is required")
        return lease
    if lease["state"] != "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP":
        raise common.BrokerError("demand requires target-neutral support with zero GPU node groups")
    if any(
        item["kind"] in {"gpu_node_group", "gpu_node"} and not item.get("deleted_at")
        for item in lease["resources"]
    ):
        raise common.BrokerError("a GPU node-group resource is already live")
    if any(item["attempt_id"] == demand["attempt_id"] for item in lease["attempts"]):
        raise common.BrokerError("attempt_id was already consumed; a retry must keep its active demand")
    received_at = precise_utc_now()
    received_mono = time.monotonic_ns()
    accepted_at = common.parse_utc(source_receipt["observed_at_utc"])
    accepted_mono = source_receipt["observed_monotonic_ns"]
    if accepted_at > received_at:
        raise common.BrokerError("demand appears to precede its accepted T0 wall clock")
    if accepted_mono > received_mono:
        raise common.BrokerError("demand appears to precede its accepted T0 monotonic clock")
    support_event = next(
        (item for item in reversed(lease["lifecycle_events"]) if item["event"] == "support.ready"),
        None,
    )
    if (
        not support_event
        or accepted_at < common.parse_utc(support_event["observed_at_utc"])
        or accepted_mono < int(support_event["observed_monotonic_ns"])
    ):
        raise common.BrokerError("request T0 predates the target-neutral support-ready boundary")
    lease["demand"] = {
        **demand,
        "accepted_event_source_receipt": source_receipt,
        "t0_observed_at_utc": source_receipt["observed_at_utc"],
        "t0_observed_monotonic_ns": accepted_mono,
        "demand_sha256": demand_hash,
        "demand_received_at_utc": common.iso(received_at),
        "demand_received_monotonic_ns": received_mono,
        "causal_order_pass": True,
    }
    authenticate_demand(lease)
    attempt = {
        "attempt_id": demand["attempt_id"],
        "demand_sha256": demand_hash,
        "state": "DEMAND_RECORDED",
        "receipt": {
            "schema_version": "catalog-switch-kubernetes-node-demand-receipt/v1",
            "attempt_id": demand["attempt_id"],
            "accepted_event_sha256": demand["accepted_event_sha256"],
            "accepted_event_source_receipt": source_receipt,
            "t0_observed_at_utc": source_receipt["observed_at_utc"],
            "t0_observed_monotonic_ns": accepted_mono,
            "demand_received_at_utc": common.iso(received_at),
            "demand_received_monotonic_ns": received_mono,
            "capacity_advice_started_at_utc": None,
            "capacity_advice": None,
            "capacity_advice_attempts": [],
            "no_create_absence_receipt": None,
            "no_create_absence_signature": None,
            "create_operation_started_at_utc": None,
            "create_operation_started_monotonic_ns": None,
            "create_attempts": [],
            "node_group_id": None,
            "node_id": None,
            "node_ready_at_utc": None,
            "gpu_product": lease["gpu_product"],
            "gpu_count": 1,
            "preemptible": True,
            "causal_order_pass": True,
            "failure": None,
            "cleanup": None,
        },
    }
    lease["attempts"].append(attempt)
    lease["state"] = "DEMAND_RECORDED"
    event(
        lease,
        "gpu.demand.received",
        "PASS",
        attempt_id=demand["attempt_id"],
        accepted_event_sha256=demand["accepted_event_sha256"],
        causal_order_pass=True,
    )
    save(lease_path, registry_path, lease)
    return lease


def current_attempt(lease: dict[str, Any]) -> dict[str, Any]:
    demand = lease.get("demand")
    if not demand:
        raise common.BrokerError("no active post-T0 demand exists")
    return next(item for item in lease["attempts"] if item["attempt_id"] == demand["attempt_id"])


def verify_no_create_absence_receipt(lease: dict[str, Any], attempt: dict[str, Any]) -> None:
    receipt = attempt.get("receipt", {}).get("no_create_absence_receipt")
    signature = attempt.get("receipt", {}).get("no_create_absence_signature")
    if receipt is None and signature is None:
        return
    if not isinstance(receipt, dict) or not isinstance(signature, str):
        raise common.BrokerError("capacity-miss no-create evidence is incomplete")
    verify_signature("attempt-no-create-absence", lease, receipt, signature)
    expected_operations = sorted(
        item["operation_id"]
        for item in lease["resource_create_operations"]
        if item["kind"] == "gpu_node_group" and item["name"] == receipt.get("resource_name")
    )
    if (
        receipt.get("schema_version") != NO_CREATE_RECEIPT_SCHEMA
        or receipt.get("lease_id") != lease["lease_id"]
        or receipt.get("attempt_id") != attempt["attempt_id"]
        or receipt.get("demand_sha256") != attempt["demand_sha256"]
        or receipt.get("result") != "NO_PREEMPTIBLE_CAPACITY"
        or receipt.get("create_admitted") is not False
        or receipt.get("exact_provider_matches") != 0
        or receipt.get("create_intent_operation_ids") != expected_operations
        or expected_operations
    ):
        raise common.BrokerError("capacity-miss no-create receipt is not canonical durable absence")


def record_no_create_absence_receipt(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    attempt: dict[str, Any],
    capacity_response: dict[str, Any],
) -> dict[str, Any]:
    cluster = find_resource(lease, "cluster")
    if not cluster:
        raise common.BrokerError("cannot prove a capacity miss without the exact support cluster")
    name = gpu_group_name(lease, attempt)
    operations = sorted(
        item["operation_id"]
        for item in lease["resource_create_operations"]
        if item["kind"] == "gpu_node_group" and item["name"] == name
    )
    if operations:
        raise common.BrokerError("capacity miss occurred after a GPU create intent; no-create proof refused")
    provider_list = cli.run(
        [
            *RESOURCE_COMMANDS["gpu_node_group"]["list"],
            "--parent-id",
            cluster["id"],
            "--all",
        ]
    )
    exact = [
        item
        for item in provider_list.get("items", [])
        if item.get("metadata", {}).get("name") == name
    ]
    if exact:
        raise common.BrokerError(
            "capacity-miss exact-name provider object is ambiguous; preserve and require reconciliation"
        )
    receipt = {
        "schema_version": NO_CREATE_RECEIPT_SCHEMA,
        "lease_id": lease["lease_id"],
        "attempt_id": attempt["attempt_id"],
        "demand_sha256": attempt["demand_sha256"],
        "result": "NO_PREEMPTIBLE_CAPACITY",
        "resource_type": "gpu_node_group",
        "resource_name": name,
        "parent_id": cluster["id"],
        "capacity_response_sha256": common.sha256_json(capacity_response),
        "provider_list_response_sha256": common.sha256_json(provider_list),
        "exact_provider_matches": 0,
        "create_intent_operation_ids": operations,
        "create_admitted": False,
        "provider_absence_verified_at_utc": common.iso(precise_utc_now()),
        "evidence": (
            "post-T0 Capacity Advisor returned no fresh preemptible capacity; exact parent/name "
            "node-group list returned zero matches before any create intent or create call"
        ),
    }
    attempt["receipt"]["no_create_absence_receipt"] = receipt
    attempt["receipt"]["no_create_absence_signature"] = sign_material(
        "attempt-no-create-absence", lease, receipt
    )
    verify_no_create_absence_receipt(lease, attempt)
    event(
        lease,
        "gpu.capacity_miss.no_create_absence",
        "PASS",
        attempt_id=attempt["attempt_id"],
        resource_name=name,
        exact_provider_matches=0,
    )
    save(lease_path, registry_path, lease)
    return receipt


def post_t0_capacity_advice(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    attempt: dict[str, Any],
) -> list[dict[str, Any]]:
    started_at = precise_utc_now()
    started_mono = time.monotonic_ns()
    if lease["request"]["campaign_arm"] == "B_new_preemptible_node":
        t0_mono = lease["demand"]["t0_observed_monotonic_ns"]
        if started_mono < t0_mono:
            raise common.BrokerError("capacity advice started before request T0")
    if attempt["receipt"]["capacity_advice_started_at_utc"] is None:
        attempt["receipt"]["capacity_advice_started_at_utc"] = common.iso(started_at)
    advice_attempt = {
        "started_at_utc": common.iso(started_at),
        "started_monotonic_ns": started_mono,
        "completed_at_utc": None,
        "outcome": None,
        "failure": None,
    }
    attempt["receipt"].setdefault("capacity_advice_attempts", []).append(advice_attempt)
    event(lease, "gpu.capacity_advice.started", "PASS", attempt_id=attempt["attempt_id"])
    save(lease_path, registry_path, lease)
    try:
        response = cli.run(
            [
                "capacity",
                "resource-advice",
                "list",
                "--parent-id",
                lease["preflight"]["project"]["tenant_id"],
                "--all",
            ]
        )
        profile = lease["profile_snapshot"]["gpu_node_group"]
        matched = [
            item
            for item in response.get("items", [])
            if item.get("spec", {}).get("region") == lease["region"]
            and item.get("spec", {}).get("compute_instance", {}).get("platform")
            == profile["platform"]
            and item.get("spec", {}).get("compute_instance", {}).get("preset", {}).get("name")
            == profile["preset"]
        ]
        usable = [
            item
            for item in matched
            if item.get("status", {}).get("preemptible", {}).get("data_state") == "DATA_STATE_FRESH"
            and int(item.get("status", {}).get("preemptible", {}).get("available", 0)) >= 1
            and item.get("status", {}).get("preemptible", {}).get("availability_level")
            != "AVAILABILITY_LEVEL_LIMIT_REACHED"
        ]
        snapshot = {
            "observed_at_utc": common.iso(precise_utc_now()),
            "matched": matched,
            "usable_fabrics": [item.get("spec", {}).get("fabric") for item in usable],
            "result": "PASS" if usable else "NO_PREEMPTIBLE_CAPACITY",
        }
        attempt["receipt"]["capacity_advice"] = snapshot
        advice_attempt["completed_at_utc"] = snapshot["observed_at_utc"]
        advice_attempt["outcome"] = snapshot["result"]
        if not usable:
            record_no_create_absence_receipt(
                lease_path,
                registry_path,
                lease,
                cli,
                attempt,
                response,
            )
            raise common.BrokerError("capacity advice reports no fresh preemptible capacity")
        event(
            lease,
            "gpu.capacity_advice.completed",
            "PASS",
            attempt_id=attempt["attempt_id"],
            usable_fabrics=snapshot["usable_fabrics"],
        )
        save(lease_path, registry_path, lease)
        return usable
    except Exception as exc:
        advice_attempt["completed_at_utc"] = common.iso(precise_utc_now())
        if advice_attempt["outcome"] is None:
            advice_attempt["outcome"] = "FAIL"
        advice_attempt["failure"] = str(exc)[:1500]
        attempt["state"] = "CAPACITY_FAILED"
        attempt["receipt"]["failure"] = {"stage": "capacity_advice", "error": str(exc)[:1500]}
        lease["state"] = "GPU_CAPACITY_FAILED"
        lease["failures"].append(
            {
                "at": common.iso(precise_utc_now()),
                "stage": "gpu_capacity_advice",
                "attempt_id": attempt["attempt_id"],
                "error": str(exc)[:1500],
            }
        )
        event(
            lease,
            "gpu.capacity_advice.failed",
            "FAIL",
            attempt_id=attempt["attempt_id"],
            error=str(exc)[:1000],
        )
        save(lease_path, registry_path, lease)
        raise


def gpu_group_name(lease: dict[str, Any], attempt: dict[str, Any]) -> str:
    if lease["request"]["campaign_arm"] == "A_prepared_node":
        return graph_name(lease, "gpu_node_group")
    return f"{lease['prefix']}-gpu-{attempt['demand_sha256'][:8]}"


def verify_gpu_group(
    lease: dict[str, Any], value: dict[str, Any], service_account_id: str, subnet_id: str
) -> None:
    profile = lease["profile_snapshot"]["gpu_node_group"]
    spec = value.get("spec", {})
    template = spec.get("template", {})
    failures = []
    if int(spec.get("fixed_node_count", 0)) != 1:
        failures.append("node group is not fixed at one node")
    if template.get("resources", {}).get("platform") != profile["platform"]:
        failures.append("GPU platform differs from plan")
    if template.get("resources", {}).get("preset") != profile["preset"]:
        failures.append("GPU preset differs from plan")
    if template.get("preemptible") != {}:
        failures.append("GPU node group is not preemptible")
    if template.get("service_account_id") != service_account_id:
        failures.append("GPU node group does not use the task-owned service account")
    if template.get("network_interfaces") != [{"subnet_id": subnet_id}]:
        failures.append("GPU node group does not use only the task-owned private subnet")
    if any(item.get("public_ip_address") for item in template.get("network_interfaces", [])):
        failures.append("GPU node group requests a public IP")
    if failures:
        raise common.BrokerError("GPU isolation proof failed: " + "; ".join(failures))


def attest_gpu_node(
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
    node_group: dict[str, Any],
    provider_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    if len(provider_nodes) != 1:
        raise common.BrokerError("live GPU attestation requires exactly one provider node")
    path = Path(lease["kubeconfig_path"])
    nodes = kubectl.run(path, ["get", "nodes"])
    matching = [
        item for item in nodes.get("items", []) if node_belongs_to_group(item, node_group["id"])
    ]
    if len(matching) != 1:
        raise common.BrokerError("live GPU attestation found an ambiguous Kubernetes node")
    node = matching[0]
    provider_id = node.get("spec", {}).get("providerID", "")
    compute_id = compute_id_from_provider_id(provider_id)
    if compute_id != provider_nodes[0]["id"]:
        raise common.BrokerError("Kubernetes/provider node identities do not join")
    labels = node.get("metadata", {}).get("labels", {}) or {}
    allocatable = node.get("status", {}).get("allocatable", {}) or {}
    profile = lease["profile_snapshot"]["gpu_node_group"]
    expected_product = profile["kubernetes_gpu_product_label"]
    if labels.get("nvidia.com/gpu.product") != expected_product:
        raise common.BrokerError("live Kubernetes gpu.product differs from the frozen profile")
    if int(allocatable.get("nvidia.com/gpu", 0)) != profile["gpu_count_per_node"]:
        raise common.BrokerError("live Kubernetes allocatable GPU count differs from the plan")
    instance = cli.run([*RESOURCE_COMMANDS["node"]["get"], compute_id])
    if provider_instance_group_id(instance) != node_group["id"]:
        raise common.BrokerError("live Compute node is not owned by the exact node group")
    instance_spec = instance.get("spec", {})
    instance_resources = instance_spec.get("resources", {})
    if (
        instance_resources.get("platform") != profile["platform"]
        or instance_resources.get("preset") != profile["preset"]
        or instance_spec.get("preemptible") != {}
    ):
        raise common.BrokerError("live Compute GPU shape/preemptible state differs from plan")
    ready = next(
        (
            condition.get("status")
            for condition in node.get("status", {}).get("conditions", [])
            if condition.get("type") == "Ready"
        ),
        None,
    )
    if ready != "True":
        raise common.BrokerError("live GPU node is not Ready")
    return {
        "verified_at_utc": common.iso(precise_utc_now()),
        "node_group_id": node_group["id"],
        "node_id": compute_id,
        "provider_id": provider_id,
        "kubernetes_uid": node.get("metadata", {}).get("uid"),
        "gpu_product_label": expected_product,
        "allocatable_nvidia_com_gpu": profile["gpu_count_per_node"],
        "platform": profile["platform"],
        "preset": profile["preset"],
        "preemptible": True,
        "compute_spec_sha256": common.sha256_json(instance_spec),
    }


@lease_mutation_locked
def provision_gpu_node_group(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    assert_live_creation_prerequisites(lease)
    assert_frozen_authority(lease, cli)
    arm = lease["request"]["campaign_arm"]
    if lease["state"] in {"ACTIVE", "ACTIVE_ATTEMPT"}:
        group = find_resource(lease, "gpu_node_group")
        if not group:
            raise common.BrokerError("active lease lacks a signed GPU node-group row")
        provider_nodes = reconcile_provider_nodes(lease, cli, group, "gpu_node")
        save(lease_path, registry_path, lease)
        reconcile_nodes(lease, kubectl, group, "gpu_node")
        attestation = attest_gpu_node(lease, cli, kubectl, group, provider_nodes)
        attempt = (
            current_attempt(lease)
            if arm == "B_new_preemptible_node"
            else next(item for item in lease["attempts"] if item["attempt_id"] == "prepared-node")
        )
        attempt["receipt"].setdefault("replacement_reconciliations", []).append(attestation)
        attempt["receipt"]["live_gpu_attestation"] = attestation
        lease["node_ids"] = [attestation["node_id"]]
        save(lease_path, registry_path, lease)
        return lease
    if arm == "B_new_preemptible_node":
        if lease["state"] not in {"DEMAND_RECORDED", "GPU_CAPACITY_FAILED", "GPU_CREATE_FAILED"}:
            raise common.BrokerError("Arm B GPU creation requires a recorded durable post-T0 demand")
        attempt = current_attempt(lease)
    else:
        if lease["state"] not in {
            "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP",
            "GPU_CAPACITY_FAILED",
            "GPU_CREATE_FAILED",
        }:
            raise common.BrokerError("prepared-node GPU creation requires active target-neutral support")
        attempt = next((item for item in lease["attempts"] if item["attempt_id"] == "prepared-node"), None)
        if not attempt:
            attempt = {
                "attempt_id": "prepared-node",
                "demand_sha256": common.sha256_json(
                    {"lease_id": lease["lease_id"], "mode": "prepared-node"}
                ),
                "state": "PLAN_AUTHORIZED",
                "receipt": {
                    "schema_version": "catalog-switch-kubernetes-prepared-node-receipt/v1",
                    "attempt_id": "prepared-node",
                    "accepted_event_sha256": None,
                    "demand_received_at_utc": None,
                    "capacity_advice_started_at_utc": None,
                    "capacity_advice": None,
                    "capacity_advice_attempts": [],
                    "no_create_absence_receipt": None,
                    "no_create_absence_signature": None,
                    "create_operation_started_at_utc": None,
                    "create_operation_started_monotonic_ns": None,
                    "create_attempts": [],
                    "node_group_id": None,
                    "node_id": None,
                    "node_ready_at_utc": None,
                    "gpu_product": lease["gpu_product"],
                    "gpu_count": 1,
                    "preemptible": True,
                    "causal_order_pass": None,
                    "failure": None,
                    "cleanup": None,
                },
            }
            lease["attempts"].append(attempt)
            save(lease_path, registry_path, lease)
    if common.utc_now() >= common.parse_utc(lease["expires_at"]):
        raise common.BrokerError("cannot create a GPU node group for an expired lease")
    try:
        post_t0_capacity_advice(lease_path, registry_path, lease, cli, attempt)
        attempt["receipt"]["no_create_absence_receipt"] = None
        attempt["receipt"]["no_create_absence_signature"] = None
        save(lease_path, registry_path, lease)
        resources = {item["kind"]: item for item in lease["resources"] if not item.get("deleted_at")}
        required = {"cluster", "subnet", "service_account", "registry_access_permit", "bucket_access_permit"}
        if not required.issubset(resources):
            raise common.BrokerError("support resource graph is incomplete")
        profile = lease["profile_snapshot"]["gpu_node_group"]
        name = gpu_group_name(lease, attempt)
        started = precise_utc_now()
        started_mono = time.monotonic_ns()
        if arm == "B_new_preemptible_node" and started_mono < lease["demand"]["t0_observed_monotonic_ns"]:
            raise common.BrokerError("GPU node-group create started before request T0")
        if attempt["receipt"]["create_operation_started_at_utc"] is None:
            attempt["receipt"]["create_operation_started_at_utc"] = common.iso(started)
            attempt["receipt"]["create_operation_started_monotonic_ns"] = started_mono
        create_attempt = {
            "started_at_utc": common.iso(started),
            "started_monotonic_ns": started_mono,
            "completed_at_utc": None,
            "outcome": None,
            "resource_id": None,
            "failure": None,
        }
        attempt["receipt"].setdefault("create_attempts", []).append(create_attempt)
        event(lease, "gpu.node_group.create.started", "PASS", attempt_id=attempt["attempt_id"], name=name)
        save(lease_path, registry_path, lease)
        node_group = ensure_resource(
            lease_path,
            registry_path,
            lease,
            cli,
            kind="gpu_node_group",
            name=name,
            parent_id=resources["cluster"]["id"],
            spec={
                "version": lease["request"]["cluster_version"],
                "fixed_node_count": 1,
                "template": {
                    "metadata": {
                        "labels": {
                            "mlsp.nebius.ai/resource-prefix": lease["prefix"],
                            "mlsp.nebius.ai/node-role": "gpu",
                            "mlsp.nebius.ai/attempt-hash": attempt["demand_sha256"][:16],
                        }
                    },
                    "taints": [
                        {
                            "key": "mlsp.nebius.ai/gpu",
                            "value": "h100",
                            "effect": "no_schedule",
                        }
                    ],
                    "resources": {"platform": profile["platform"], "preset": profile["preset"]},
                    "boot_disk": {
                        "size_bytes": int(profile["boot_disk_gib"]) * GIB,
                        "block_size_bytes": 4096,
                        "type": "NETWORK_SSD",
                    },
                    "gpu_settings": {"drivers_preset": profile["driver_preset"]},
                    "os": profile["os"],
                    "network_interfaces": [{"subnet_id": resources["subnet"]["id"]}],
                    "service_account_id": resources["service_account"]["id"],
                    "preemptible": {},
                    "reservation_policy": {"policy": "forbid"},
                },
            },
            depends_on=[
                resources["cluster"]["id"],
                resources["subnet"]["id"],
                resources["service_account"]["id"],
                resources["registry_access_permit"]["id"],
                resources["bucket_access_permit"]["id"],
            ],
            timeout=1800,
        )
        attempt["receipt"]["node_group_id"] = node_group["id"]
        create_attempt["completed_at_utc"] = common.iso(precise_utc_now())
        create_attempt["outcome"] = "CREATED_OR_RECONCILED"
        create_attempt["resource_id"] = node_group["id"]
        group_value = wait_running(
            cli,
            "gpu_node_group",
            node_group["id"],
            ready_nodes=1,
            timeout_seconds=1800,
        )
        verify_gpu_group(
            lease, group_value, resources["service_account"]["id"], resources["subnet"]["id"]
        )
        provider_nodes = reconcile_provider_nodes(lease, cli, node_group, "gpu_node")
        if len(provider_nodes) != 1:
            raise common.BrokerError("provider API did not expose exactly one GPU node child")
        save(lease_path, registry_path, lease)
        nodes = reconcile_nodes(lease, kubectl, node_group, "gpu_node")
        if len(nodes) != 1:
            raise common.BrokerError("GPU node group did not yield exactly one node identity")
        ready_at = precise_utc_now()
        attestation = attest_gpu_node(lease, cli, kubectl, node_group, provider_nodes)
        attempt["receipt"].update(
            {
                "node_group_id": node_group["id"],
                "node_id": nodes[0]["id"],
                "node_ready_at_utc": common.iso(ready_at),
                "gpu_product": profile["gpu_product"],
                "gpu_count": profile["gpu_count_per_node"],
                "preemptible": True,
                "live_gpu_attestation": attestation,
                "replacement_reconciliations": [],
                "causal_order_pass": (
                    True
                    if arm == "B_new_preemptible_node"
                    and started_mono >= lease["demand"]["t0_observed_monotonic_ns"]
                    else None
                    if arm == "A_prepared_node"
                    else False
                ),
                "failure": None,
            }
        )
        attempt["state"] = "READY"
        lease["node_group_ids"] = [node_group["id"]]
        lease["node_ids"] = [nodes[0]["id"]]
        lease["readiness_timestamps"]["gpu_node_group_ready_at_utc"] = common.iso(ready_at)
        lease["isolation_proof"]["target_neutral"] = False
        lease["isolation_proof"]["gpu_node_group"] = {
            "id": node_group["id"],
            "node_id": nodes[0]["id"],
            "platform": profile["platform"],
            "preset": profile["preset"],
            "gpu_product": profile["gpu_product"],
            "gpu_product_label": profile["kubernetes_gpu_product_label"],
            "gpu_count": profile["gpu_count_per_node"],
            "preemptible": True,
            "public_worker_ips": [],
            "attempt_id": attempt["attempt_id"],
            "live_attestation": attestation,
        }
        lease["state"] = "ACTIVE" if arm == "A_prepared_node" else "ACTIVE_ATTEMPT"
        event(
            lease,
            "gpu.node.ready",
            "PASS",
            attempt_id=attempt["attempt_id"],
            node_group_id=node_group["id"],
            node_id=nodes[0]["id"],
            causal_order_pass=attempt["receipt"]["causal_order_pass"],
        )
        save(lease_path, registry_path, lease)
        return lease
    except Exception as exc:
        lease = common.load_json(lease_path)
        assert_integrity(lease)
        if lease["state"] != "GPU_CAPACITY_FAILED":
            lease["state"] = "GPU_CREATE_FAILED"
        attempt = (
            current_attempt(lease)
            if arm == "B_new_preemptible_node"
            else next(item for item in lease["attempts"] if item["attempt_id"] == "prepared-node")
        )
        attempt["state"] = "CREATE_FAILED" if lease["state"] == "GPU_CREATE_FAILED" else "CAPACITY_FAILED"
        if attempt["receipt"].get("failure") is None:
            attempt["receipt"]["failure"] = {"stage": "node_group_create", "error": str(exc)[:1500]}
        if attempt["receipt"].get("create_attempts"):
            last_create = attempt["receipt"]["create_attempts"][-1]
            if last_create.get("outcome") is None:
                last_create["completed_at_utc"] = common.iso(precise_utc_now())
                last_create["outcome"] = "FAIL"
                last_create["failure"] = str(exc)[:1500]
        if not any(
            item["attempt_id"] == attempt["attempt_id"] and item["error"] == str(exc)[:1500]
            for item in lease["failures"]
        ):
            lease["failures"].append(
                {
                    "at": common.iso(precise_utc_now()),
                    "stage": "gpu_node_group",
                    "attempt_id": attempt["attempt_id"],
                    "error": str(exc)[:1500],
                }
            )
        event(
            lease,
            "gpu.node_group.failed",
            "FAIL",
            attempt_id=attempt["attempt_id"],
            error=str(exc)[:1000],
        )
        save(lease_path, registry_path, lease)
        raise


CLEANUP_PRIORITY = {
    "kubeconfig_authority": 300,
    "gpu_node_group": 290,
    "gpu_node": 280,
    "system_node_group": 270,
    "system_node": 260,
    "cluster": 250,
    "registry_access_permit": 240,
    "bucket_access_permit": 240,
    "group_membership": 230,
    "registry": 220,
    "bucket": 220,
    "iam_group": 210,
    "service_account": 200,
    "security_group": 190,
    "subnet": 180,
    "network": 170,
    "route_table": 160,
    "pool": 160,
}


def get_args(kind: str, resource_id: str) -> list[str]:
    command_kind = "node" if kind in {"gpu_node", "system_node"} else kind
    return [*RESOURCE_COMMANDS[command_kind]["get"], resource_id]


def delete_args(kind: str, resource_id: str) -> list[str]:
    args = [*RESOURCE_COMMANDS[kind]["delete"], resource_id]
    if kind == "bucket":
        args.extend(["--ttl", "0s"])
    return args


def wait_absent(
    cli: common.NebiusCLI, kind: str, resource_id: str, timeout_seconds: int = 600
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if cli.run(get_args(kind, resource_id), allow_not_found=True, timeout=60) is None:
            return True
        time.sleep(5)
    return False


def reconcile_create_intents_for_cleanup(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
) -> None:
    for operation in lease["resource_create_operations"]:
        verify_operation(lease, operation)
        if operation.get("resource_id") or operation["status"] not in {
            "INTENT_RECORDED",
            "CREATE_FAILED",
        }:
            continue
        kind = operation["kind"]
        if kind == "kubeconfig_authority":
            path = Path(lease["kubeconfig_path"])
            staging = path.with_name(
                f".{path.name}.{lease['plan_sha256'][:16]}.broker-staging"
            )
            expected = operation.get("kubeconfig_content_authority")
            signature = operation.get("kubeconfig_content_signature")
            if not path.exists() and not staging.exists():
                operation["status"] = "ABSENCE_VERIFIED_AFTER_INTERRUPTION"
                operation["completed_at_utc"] = common.iso(precise_utc_now())
                operation["reconciliation_evidence"] = (
                    f"lstat({path}) and lstat({staging}) -> absent"
                )
                record_operation_absence(
                    lease, operation, operation["reconciliation_evidence"]
                )
                continue
            if not expected or not signature:
                operation["status"] = "AMBIGUOUS_FOREIGN_PRESERVED"
                operation["failure"] = "file exists without signed kubeconfig content authority"
                save(lease_path, registry_path, lease)
                raise common.BrokerError(
                    "interrupted kubeconfig file has no signed content authority; preserve it"
                )
            verify_signature("kubeconfig-content", lease, expected, signature)
            if path.exists() and staging.exists():
                operation["status"] = "AMBIGUOUS_FOREIGN_PRESERVED"
                operation["failure"] = "both final and staging kubeconfig paths exist"
                save(lease_path, registry_path, lease)
                raise common.BrokerError(
                    "both kubeconfig paths exist after interruption; preserve both"
                )
            owned_path = path if path.exists() else staging
            verify_kubeconfig_content(
                owned_path,
                expected if owned_path == path else {**expected, "path": str(staging)},
            )
            if owned_path == staging:
                durable_replace(staging, path)
            digest = expected["sha256"]
            item = {
                "kind": "kubeconfig_authority",
                "name": path.name,
                "id": f"local-kubeconfig-sha256:{digest}",
                "project_id": lease["project_id"],
                "region": lease["region"],
                "parent_id": operation["parent_id"],
                "depends_on": operation.get("depends_on", []),
                "created_at": operation["started_at_utc"],
                "create_operation_id": operation["operation_id"],
                "deletion_mode": None,
                "managed_by_resource_id": None,
                "intended_spec_sha256": operation["spec_sha256"],
                "provider_spec_sha256": operation["spec_sha256"],
                "desired_final_state": "ABSENT",
                "deleted_at": None,
                "absence_verified_at": None,
                "cleanup_evidence": None,
                "provider_metadata": {
                    **expected,
                    "identity_id": lease["request"]["authority_identity"]["id"],
                    "reconciled_for_cleanup": True,
                },
            }
            authenticate_resource(lease, item)
            lease["resources"].append(item)
            operation["resource_id"] = item["id"]
            operation["status"] = "RECONCILED_FOR_CLEANUP"
            continue
        listed = cli.run(
            [*RESOURCE_COMMANDS[kind]["list"], "--parent-id", operation["parent_id"], "--all"]
        )
        exact = [
            item
            for item in listed.get("items", [])
            if item.get("metadata", {}).get("name") == operation["name"]
        ]
        if len(exact) > 1:
            raise common.BrokerError(f"multiple interrupted {kind} candidates require manual review")
        if not exact:
            operation["status"] = "ABSENCE_VERIFIED_AFTER_INTERRUPTION"
            operation["completed_at_utc"] = common.iso(precise_utc_now())
            operation["reconciliation_evidence"] = (
                f"{RESOURCE_COMMANDS[kind]['list']} parent={operation['parent_id']} "
                f"name={operation['name']} -> no exact match"
            )
            record_operation_absence(
                lease, operation, operation["reconciliation_evidence"]
            )
            continue
        operation["status"] = "AMBIGUOUS_FOREIGN_PRESERVED"
        operation["completed_at_utc"] = common.iso(precise_utc_now())
        operation["failure"] = (
            "exact-name object exists after an unreceipted create window; preserve until "
            "provider correlation/audit evidence proves this operation created the exact ID"
        )
        save(lease_path, registry_path, lease)
        raise common.BrokerError(
            f"interrupted {kind} candidate lacks provider correlation/audit evidence; preserve it"
        )
    save(lease_path, registry_path, lease)


def delete_one(
    lease_path: Path,
    registry_path: Path,
    lease: dict[str, Any],
    cli: common.NebiusCLI,
    resource: dict[str, Any],
) -> None:
    kind = resource["kind"]
    resource_id = resource["id"]
    verify_resource(lease, resource)
    delete_operation = resource.setdefault(
        "delete_operation",
        {
            "status": "INTENT_RECORDED",
            "started_at_utc": common.iso(precise_utc_now()),
            "attempt_count": 0,
            "last_failure": None,
        },
    )
    if delete_operation["status"] != "INTENT_RECORDED":
        delete_operation["status"] = "INTENT_RECORDED"
    save(lease_path, registry_path, lease)
    if kind == "kubeconfig_authority":
        path = Path(resource["provider_metadata"]["path"])
        if path.exists():
            verify_kubeconfig_content(path, resource["provider_metadata"])
            durable_unlink(path)
        if path.exists():
            raise common.BrokerError("kubeconfig authority still exists after exact unlink")
        evidence = f"lstat({path}) -> absent after exact owned-file unlink"
    elif resource.get("deletion_mode") == "PROVIDER_CASCADE":
        if not wait_absent(cli, kind, resource_id, timeout_seconds=900):
            raise common.BrokerError("provider-cascade child is still present")
        evidence = (
            f"{get_args(kind, resource_id)} -> NotFound after parent "
            f"{resource['managed_by_resource_id']} deletion"
        )
    else:
        operation = operation_for(lease, resource["create_operation_id"])
        if not operation:
            raise common.BrokerError("signed resource row lacks its create intent; preserve it")
        verify_operation(lease, operation)
        live = cli.run(get_args(kind, resource_id), allow_not_found=True, timeout=60)
        if live is not None:
            validate_owned_metadata(
                lease, kind, live, resource["name"], resource["parent_id"]
            )
            projected = project_requested_spec(
                live.get("spec", {}), operation["requested_spec"]
            )
            if common.sha256_json(projected) != resource["provider_spec_sha256"]:
                raise common.BrokerError("live provider spec differs from signed resource row")
            delete_operation["attempt_count"] += 1
            save(lease_path, registry_path, lease)
            try:
                cli.run(delete_args(kind, resource_id), json_output=False, timeout=1200)
            except Exception as exc:
                if cli.run(get_args(kind, resource_id), allow_not_found=True, timeout=60) is not None:
                    delete_operation["last_failure"] = str(exc)[:1500]
                    save(lease_path, registry_path, lease)
                    raise
        if not wait_absent(cli, kind, resource_id, timeout_seconds=1200):
            raise common.BrokerError("resource is still present after exact-ID deletion")
        evidence = (
            f"pre-delete {get_args(kind, resource_id)} ownership verified when present; "
            f"{delete_args(kind, resource_id)} at most once per observed presence; "
            f"post-delete {get_args(kind, resource_id)} -> NotFound"
        )
    verified = common.iso(precise_utc_now())
    resource["deleted_at"] = verified
    resource["absence_verified_at"] = verified
    resource["cleanup_evidence"] = evidence
    delete_operation["status"] = "ABSENCE_VERIFIED"
    delete_operation["completed_at_utc"] = verified
    event(lease, "resource.absence.verified", "PASS", kind=kind, resource_id=resource_id)
    save(lease_path, registry_path, lease)


def dependency_closure(lease: dict[str, Any], resource: dict[str, Any]) -> set[str]:
    by_id = {item["id"]: item for item in lease["resources"]}
    pending = list(resource.get("depends_on", []))
    result: set[str] = set()
    while pending:
        resource_id = pending.pop()
        if resource_id in result:
            continue
        result.add(resource_id)
        if resource_id in by_id:
            pending.extend(by_id[resource_id].get("depends_on", []))
    return result


@lease_mutation_locked
def cleanup_attempt(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL | None = None,
    *,
    execute: bool,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    if lease["request"]["campaign_arm"] != "B_new_preemptible_node":
        raise common.BrokerError("attempt cleanup is valid only for B_new_preemptible_node")
    attempt = current_attempt(lease)
    if execute:
        assert_frozen_authority(lease, cli)
        reconcile_create_intents_for_cleanup(lease_path, registry_path, lease, cli)
        lease = common.load_json(lease_path)
        attempt = current_attempt(lease)
        live_group = find_resource(lease, "gpu_node_group")
        live_nodes = [
            item
            for item in lease["resources"]
            if item["kind"] == "gpu_node"
            and not item.get("deleted_at")
            and live_group
            and item.get("managed_by_resource_id") == live_group["id"]
        ]
        if live_group and not live_nodes:
            live_nodes = reconcile_provider_nodes(
                lease, cli, live_group, "gpu_node"
            )
            attempt["receipt"]["node_group_id"] = live_group["id"]
            if live_nodes:
                attempt["receipt"]["node_id"] = live_nodes[0]["id"]
            save(lease_path, registry_path, lease)
    node_group_id = attempt["receipt"].get("node_group_id")
    pending = [
        item
        for item in lease["resources"]
        if not item.get("deleted_at")
        and (
            (item["kind"] == "gpu_node_group" and (not node_group_id or item["id"] == node_group_id))
            or (item["kind"] == "gpu_node" and (not node_group_id or item.get("managed_by_resource_id") == node_group_id))
        )
    ]
    pending.sort(key=lambda item: CLEANUP_PRIORITY[item["kind"]], reverse=True)
    dry_run = [
        {
            "kind": item["kind"],
            "id": item["id"],
            "action": "VERIFY_PROVIDER_CASCADE_ABSENCE"
            if item.get("deletion_mode") == "PROVIDER_CASCADE"
            else "DELETE_EXACT_ID_THEN_VERIFY_NOT_FOUND",
        }
        for item in pending
    ]
    if not execute:
        return {"mode": "DRY_RUN", "attempt_id": attempt["attempt_id"], "delete_plan": dry_run}
    lease["state"] = "ATTEMPT_CLEANING"
    event(lease, "gpu.attempt.cleanup.started", "PASS", attempt_id=attempt["attempt_id"])
    save(lease_path, registry_path, lease)
    failures = []
    for item in pending:
        try:
            delete_one(lease_path, registry_path, lease, cli, item)
        except Exception as exc:
            failures.append(f"{item['kind']}:{item['id']}: {str(exc)[:1000]}")
            event(
                lease,
                "resource.cleanup.failed",
                "FAIL",
                kind=item["kind"],
                resource_id=item["id"],
                error=str(exc)[:1000],
            )
            save(lease_path, registry_path, lease)
            break
    if failures:
        lease["state"] = "ATTEMPT_CLEANUP_FAILED"
        attempt["state"] = "CLEANUP_FAILED"
        save(lease_path, registry_path, lease)
        raise common.BrokerError("attempt cleanup incomplete: " + "; ".join(failures))
    verified_at = common.iso(precise_utc_now())
    attempt["state"] = "RELEASED"
    group_ids = {
        item["id"]
        for item in lease["resources"]
        if item["kind"] == "gpu_node_group"
        and (
            item["name"] == gpu_group_name(lease, attempt)
            or item["id"] == attempt["receipt"].get("node_group_id")
        )
    }
    receipt_rows = [
        item
        for item in lease["resources"]
        if (
            item["kind"] == "gpu_node_group" and item["id"] in group_ids
        )
        or (
            item["kind"] == "gpu_node" and item.get("managed_by_resource_id") in group_ids
        )
    ]
    no_create_receipt = attempt["receipt"].get("no_create_absence_receipt")
    no_create_signature = attempt["receipt"].get("no_create_absence_signature")
    if receipt_rows:
        if any(not item.get("absence_verified_at") for item in receipt_rows):
            raise common.BrokerError("attempt cleanup lacks canonical durable absence evidence")
    else:
        verify_no_create_absence_receipt(lease, attempt)
        if not no_create_receipt or not no_create_signature:
            raise common.BrokerError("attempt cleanup lacks canonical durable absence evidence")
    attempt["receipt"]["cleanup"] = {
        "verified_at_utc": verified_at,
        "node_group_absent": True,
        "node_absent": True,
        "exact_id_receipts": [
            {
                "kind": item["kind"],
                "id": item["id"],
                "absence_verified_at": item["absence_verified_at"],
                "evidence": item["cleanup_evidence"],
            }
            for item in sorted(receipt_rows, key=lambda value: (value["kind"], value["id"]))
        ],
        "no_create_absence_receipt": no_create_receipt,
        "no_create_absence_signature": no_create_signature,
    }
    lease["demand"] = None
    lease["node_group_ids"] = []
    lease["node_ids"] = []
    lease["isolation_proof"].pop("gpu_node_group", None)
    lease["isolation_proof"]["target_neutral"] = True
    lease["state"] = "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"
    event(lease, "gpu.attempt.cleanup.completed", "PASS", attempt_id=attempt["attempt_id"])
    save(lease_path, registry_path, lease)
    return lease


@lease_mutation_locked
def cleanup(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL | None = None,
    *,
    execute: bool,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    pending = sorted(
        [item for item in lease["resources"] if not item.get("deleted_at")],
        key=lambda item: CLEANUP_PRIORITY.get(item["kind"], 0),
        reverse=True,
    )
    plan_value = [
        {
            "kind": item["kind"],
            "id": item["id"],
            "action": "VERIFY_PROVIDER_CASCADE_ABSENCE"
            if item.get("deletion_mode") == "PROVIDER_CASCADE"
            else "UNLINK_EXACT_OWNED_FILE"
            if item["kind"] == "kubeconfig_authority"
            else "DELETE_EXACT_ID_THEN_VERIFY_NOT_FOUND",
        }
        for item in pending
    ]
    if not execute:
        return {
            "mode": "DRY_RUN",
            "lease_id": lease["lease_id"],
            "delete_plan": plan_value,
            "unfinished_create_intents": [
                item["operation_id"]
                for item in lease["resource_create_operations"]
                if not item.get("resource_id")
                and item["status"] in {"INTENT_RECORDED", "CREATE_FAILED"}
            ],
        }
    if lease["state"] == "RELEASED" and not pending:
        return lease
    assert_frozen_authority(lease, cli)
    try:
        reconcile_create_intents_for_cleanup(lease_path, registry_path, lease, cli)
    except Exception as exc:
        lease = common.load_json(lease_path)
        assert_integrity(lease)
        lease["state"] = "CLEANUP_FAILED"
        event(lease, "lease.cleanup.reconciliation_failed", "FAIL", error=str(exc)[:1000])
        save(lease_path, registry_path, lease)
        raise
    lease = common.load_json(lease_path)
    unresolved = [
        item
        for item in lease["resource_create_operations"]
        if not item.get("resource_id")
        and item["status"]
        not in {"ABSENCE_VERIFIED_AFTER_INTERRUPTION"}
    ]
    if unresolved:
        lease["state"] = "CLEANUP_FAILED"
        event(
            lease,
            "lease.cleanup.blocked",
            "FAIL",
            unresolved_operations=[item["operation_id"] for item in unresolved],
        )
        save(lease_path, registry_path, lease)
        raise common.BrokerError("cleanup blocked by ambiguous create operations")
    reconcile_network_children(lease, cli)
    for group_kind, node_kind in (
        ("gpu_node_group", "gpu_node"),
        ("system_node_group", "system_node"),
    ):
        for group in [
            item
            for item in lease["resources"]
            if item["kind"] == group_kind and not item.get("deleted_at")
        ]:
            reconcile_provider_nodes(lease, cli, group, node_kind)
    save(lease_path, registry_path, lease)
    pending = sorted(
        [item for item in lease["resources"] if not item.get("deleted_at")],
        key=lambda item: CLEANUP_PRIORITY.get(item["kind"], 0),
        reverse=True,
    )
    lease["state"] = "CLEANING"
    event(lease, "lease.cleanup.started", "PASS", exact_id_count=len(pending))
    save(lease_path, registry_path, lease)
    failures = []
    blocked_ids: set[str] = set()
    for item in pending:
        if item["id"] in blocked_ids or item.get("managed_by_resource_id") in blocked_ids:
            event(
                lease,
                "resource.cleanup.skipped_dependency_barrier",
                "FAIL",
                kind=item["kind"],
                resource_id=item["id"],
            )
            save(lease_path, registry_path, lease)
            continue
        try:
            delete_one(lease_path, registry_path, lease, cli, item)
        except Exception as exc:
            failures.append(f"{item['kind']}:{item['id']}: {str(exc)[:1000]}")
            event(
                lease,
                "resource.cleanup.failed",
                "FAIL",
                kind=item["kind"],
                resource_id=item["id"],
                error=str(exc)[:1000],
            )
            save(lease_path, registry_path, lease)
            blocked_ids.update(dependency_closure(lease, item))
    if failures:
        lease["state"] = "CLEANUP_FAILED"
        save(lease_path, registry_path, lease)
        raise common.BrokerError("cleanup incomplete: " + "; ".join(failures))
    lease["state"] = "RELEASED"
    destroy_signing_authority(lease)
    lease["released_at"] = common.iso(precise_utc_now())
    lease["node_group_ids"] = []
    lease["node_ids"] = []
    event(lease, "lease.cleanup.completed", "PASS", all_resources_absent=True)
    save(lease_path, registry_path, lease)
    return lease


def supervisor_ledger(registry_path: Path) -> dict[str, Any]:
    registry = common.load_json(registry_path)
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise common.BrokerError("unsupported Kubernetes registry schema")
    leases = []
    resources = []
    for summary in registry["leases"]:
        lease_path = Path(summary["lease_file"])
        lease = common.load_json(lease_path)
        assert_integrity(lease)
        leases.append(
            {
                "lease_id": lease["lease_id"],
                "schema_version": lease["schema_version"],
                "canonical_lease": str(lease_path.resolve()),
                "state": lease["state"],
                "campaign_arm": lease["request"]["campaign_arm"],
                "project": lease["project_id"],
                "region": lease["region"],
                "resource_type": "kubernetes_lease",
                "resource_name": lease["prefix"],
                "resource_id": lease["lease_id"],
                "owner_task": lease["request"]["task_id"],
                "purpose": lease["request"]["purpose"],
                "created_at": lease["created_at"],
                "expires_at": lease["expires_at"],
                "cleanup_owner": lease["request"]["cleanup_owner"],
                "desired_final_state": "ABSENT",
                "estimated_cost_usd": lease["cost_estimate"]["expected_cost_usd"],
                "ttl_cost_ceiling_usd": lease["cost_estimate"]["ttl_cost_ceiling_usd"],
                "hard_cost_cap_usd": lease["cost_estimate"]["hard_cost_cap_usd"],
            }
        )
        actual_keys: set[tuple[str, str]] = set()
        for resource in lease["resources"]:
            actual_keys.add((resource["kind"], resource["name"]))
            resources.append(
                {
                    "lease_id": lease["lease_id"],
                    "project": resource["project_id"],
                    "region": resource["region"],
                    "resource_type": resource["kind"],
                    "resource_name": resource["name"],
                    "resource_id": resource["id"],
                    "owner_task": lease["request"]["task_id"],
                    "purpose": lease["request"]["purpose"],
                    "created_at": resource.get("created_at"),
                    "expires_at": lease["expires_at"],
                    "cleanup_owner": lease["request"]["cleanup_owner"],
                    "desired_final_state": "ABSENT",
                    "cleanup_state": "ABSENCE_VERIFIED"
                    if resource.get("absence_verified_at")
                    else "PENDING",
                    "deleted_at": resource.get("deleted_at"),
                    "absence_verified_at": resource.get("absence_verified_at"),
                    "cleanup_evidence": resource.get("cleanup_evidence"),
                    "managed_by_resource_id": resource.get("managed_by_resource_id"),
                    "create_operation_status": (
                        operation_for(lease, resource["create_operation_id"])["status"]
                        if resource.get("create_operation_id")
                        and operation_for(lease, resource["create_operation_id"])
                        else None
                    ),
                    "reconciliation_required": False,
                }
            )
        for planned in lease["resource_graph"]:
            key = (planned["resource_type"], planned["resource_name"])
            if key in actual_keys:
                continue
            matching_operations = [
                operation
                for operation in lease["resource_create_operations"]
                if operation["kind"] == planned["resource_type"]
                and (
                    operation["name"] == planned["resource_name"]
                    or "{demand_sha256_8}" in planned["resource_name"]
                )
            ]
            if matching_operations:
                operation = matching_operations[-1]
                operation_status = operation["status"]
                if operation_status == "ABSENCE_VERIFIED_AFTER_INTERRUPTION":
                    cleanup_state = "ABSENCE_VERIFIED"
                    cleanup_evidence = operation.get("reconciliation_evidence") or (
                        "Provider/local reconciliation proved the interrupted create absent."
                    )
                    reconciliation_required = False
                elif operation_status == "INTENT_RECORDED":
                    cleanup_state = "CREATE_PENDING_RECONCILIATION"
                    cleanup_evidence = (
                        "Signed create intent exists without an exact resource ID; provider reconciliation is required."
                    )
                    reconciliation_required = True
                else:
                    cleanup_state = "CREATE_AMBIGUOUS_RECONCILIATION_REQUIRED"
                    cleanup_evidence = (
                        f"Create operation state {operation_status} has no exact resource ID; "
                        "absence is not claimed and reconciliation is required."
                    )
                    reconciliation_required = True
            else:
                operation_status = None
                cleanup_state = "PLAN_ONLY_CREATE_NOT_ADMITTED"
                cleanup_evidence = (
                    "Immutable plan row only; no create intent was admitted and no provider absence is claimed."
                )
                reconciliation_required = False
            resources.append(
                {
                    "lease_id": lease["lease_id"],
                    "project": lease["project_id"],
                    "region": lease["region"],
                    "resource_type": planned["resource_type"],
                    "resource_name": planned["resource_name"],
                    "resource_id": None,
                    "owner_task": lease["request"]["task_id"],
                    "purpose": lease["request"]["purpose"],
                    "created_at": None,
                    "expires_at": lease["expires_at"],
                    "cleanup_owner": lease["request"]["cleanup_owner"],
                    "desired_final_state": "ABSENT",
                    "cleanup_state": cleanup_state,
                    "deleted_at": None,
                    "absence_verified_at": None,
                    "cleanup_evidence": cleanup_evidence,
                    "create_operation_status": operation_status,
                    "reconciliation_required": reconciliation_required,
                    "managed_by_resource_id": None,
                }
            )
    return {
        "schema_version": "catalog-switch-supervisor-resource-ledger/v2",
        "updated_at": common.iso(precise_utc_now()),
        "canonical_registries": [str(registry_path.resolve())],
        "contains_secrets": False,
        "leases": leases,
        "resources": resources,
    }


def scan(registry_path: Path, cli: common.NebiusCLI | None, cloud: bool) -> dict[str, Any]:
    registry = common.load_json(registry_path)
    known_ids: set[str] = set()
    known_names: set[str] = set()
    leases = []
    for summary in registry.get("leases", []):
        lease = common.load_json(Path(summary["lease_file"]))
        assert_integrity(lease)
        known_ids.update(item["id"] for item in lease["resources"])
        known_names.update(item["name"] for item in lease["resources"])
        leases.append(
            {
                "lease_id": lease["lease_id"],
                "state": lease["state"],
                "expires_at": lease["expires_at"],
                "expired": common.parse_utc(lease["expires_at"]) <= common.utc_now()
                and lease["state"] != "RELEASED",
                "cleanup_owner": lease["request"]["cleanup_owner"],
                "live_resource_ids": [
                    item["id"] for item in lease["resources"] if not item.get("deleted_at")
                ],
            }
        )
    found: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if cloud:
        if cli is None:
            raise common.BrokerError("cloud scan requires a Nebius CLI profile")
        tenants: set[str] = set()
        top_level = {
            "network": RESOURCE_COMMANDS["network"]["list"],
            "subnet": RESOURCE_COMMANDS["subnet"]["list"],
            "security_group": RESOURCE_COMMANDS["security_group"]["list"],
            "service_account": RESOURCE_COMMANDS["service_account"]["list"],
            "registry": RESOURCE_COMMANDS["registry"]["list"],
            "bucket": RESOURCE_COMMANDS["bucket"]["list"],
            "cluster": RESOURCE_COMMANDS["cluster"]["list"],
        }
        for project_id in common.AUTHORIZED_PROJECTS:
            project = cli.run(["iam", "project", "get", project_id])
            tenants.add(project.get("metadata", {}).get("parent_id"))
            for kind, command in top_level.items():
                try:
                    values = cli.run([*command, "--parent-id", project_id, "--all"], timeout=60)
                    for value in values.get("items", []):
                        metadata = value.get("metadata", {})
                        name = metadata.get("name", "")
                        labels = metadata.get("labels", {}) or {}
                        if name.startswith(f"{common.PROGRAM_PREFIX}-") or labels.get("program") == common.PROGRAM:
                            found.append(
                                {
                                    "kind": kind,
                                    "id": metadata.get("id"),
                                    "name": name,
                                    "parent_id": metadata.get("parent_id"),
                                    "registered": metadata.get("id") in known_ids,
                                    "disposition": "LEDGER_MANAGED"
                                    if metadata.get("id") in known_ids
                                    else "MANUAL_REVIEW_PRESERVE",
                                }
                            )
                            if kind == "cluster":
                                groups = cli.run(
                                    [
                                        *RESOURCE_COMMANDS["gpu_node_group"]["list"],
                                        "--parent-id",
                                        metadata.get("id"),
                                        "--all",
                                    ]
                                )
                                for group in groups.get("items", []):
                                    group_meta = group.get("metadata", {})
                                    found.append(
                                        {
                                            "kind": "node_group",
                                            "id": group_meta.get("id"),
                                            "name": group_meta.get("name"),
                                            "parent_id": metadata.get("id"),
                                            "registered": group_meta.get("id") in known_ids,
                                            "disposition": "LEDGER_MANAGED"
                                            if group_meta.get("id") in known_ids
                                            else "MANUAL_REVIEW_PRESERVE",
                                        }
                                    )
                except common.AuthenticationError:
                    raise
                except common.BrokerError as exc:
                    errors.append({"project_id": project_id, "kind": kind, "error": str(exc)[:1000]})
        for tenant_id in sorted(item for item in tenants if item):
            try:
                values = cli.run(
                    [*RESOURCE_COMMANDS["iam_group"]["list"], "--parent-id", tenant_id, "--all"]
                )
                for value in values.get("items", []):
                    metadata = value.get("metadata", {})
                    if str(metadata.get("name", "")).startswith(f"{common.PROGRAM_PREFIX}-"):
                        found.append(
                            {
                                "kind": "iam_group",
                                "id": metadata.get("id"),
                                "name": metadata.get("name"),
                                "parent_id": tenant_id,
                                "registered": metadata.get("id") in known_ids,
                                "disposition": "LEDGER_MANAGED"
                                if metadata.get("id") in known_ids
                                else "MANUAL_REVIEW_PRESERVE",
                            }
                        )
            except common.AuthenticationError:
                raise
            except common.BrokerError as exc:
                errors.append({"project_id": "tenant-scope", "kind": "iam_group", "error": str(exc)[:1000]})
    return {
        "schema_version": "catalog-switch-kubernetes-orphan-scan/v1",
        "scanned_at": common.iso(precise_utc_now()),
        "leases": leases,
        "expired_lease_count": sum(item["expired"] for item in leases),
        "cloud_scan": cloud,
        "cloud_scan_complete": cloud and not errors,
        "cloud_scan_errors": errors,
        "cloud_resources": found,
        "unregistered_cloud_resource_count": sum(not item["registered"] for item in found),
        "policy": "unregistered or foreign resources are reported and preserved; cleanup accepts only ledgered exact IDs",
    }


def inventory(cli: common.NebiusCLI) -> dict[str, Any]:
    whoami = cli.run(["iam", "whoami"])
    identity_type = next(iter(whoami), "unknown")
    identity = whoami.get(identity_type, {}).get("info", {}).get("metadata", {})
    versions = cli.run(["mk8s", "v1", "cluster", "list-control-plane-versions"])
    projects = []
    tenant_ids: set[str] = set()
    for project_id, expected_region in common.AUTHORIZED_PROJECTS.items():
        try:
            project = cli.run(["iam", "project", "get", project_id])
            tenant_ids.add(project.get("metadata", {}).get("parent_id", ""))
            platforms = cli.run(["compute", "platform", "list", "--parent-id", project_id, "--all"])
            quotas = cli.run(
                ["quotas", "quota-allowance", "list", "--parent-id", project_id, "--all"]
            )
            projects.append(
                {
                    "project_id": project_id,
                    "expected_region": expected_region,
                    "observed_region": common.project_region(project),
                    "state": project.get("status", {}).get("container_state"),
                    "platforms": [
                        {
                            "name": item.get("metadata", {}).get("name"),
                            "presets": [
                                preset.get("name")
                                for preset in item.get("spec", {}).get("presets", [])
                            ],
                        }
                        for item in platforms.get("items", [])
                    ],
                    "quota_usage": [
                        {
                            "name": item.get("metadata", {}).get("name"),
                            "region": item.get("spec", {}).get("region"),
                            "usage": item.get("status", {}).get("usage"),
                            "unit": item.get("status", {}).get("unit"),
                            "allowance": item.get("spec", {}).get("allowance"),
                        }
                        for item in quotas.get("items", [])
                        if item.get("metadata", {}).get("name", "").startswith(
                            ("compute.", "mk8s.", "vpc.", "registry.", "storage.")
                        )
                    ],
                    "status": "PASS",
                }
            )
        except common.AuthenticationError:
            raise
        except common.BrokerError as exc:
            projects.append(
                {
                    "project_id": project_id,
                    "expected_region": expected_region,
                    "status": "ERROR",
                    "error": str(exc)[:1200],
                }
            )
    capacity = []
    for tenant_id in sorted(item for item in tenant_ids if item):
        try:
            value = cli.run(
                ["capacity", "resource-advice", "list", "--parent-id", tenant_id, "--all"]
            )
            capacity.append(
                {
                    "tenant_id": tenant_id,
                    "status": "PASS",
                    "h100_eu_north1": [
                        item
                        for item in value.get("items", [])
                        if item.get("spec", {}).get("region") == "eu-north1"
                        and item.get("spec", {}).get("compute_instance", {}).get("platform")
                        == "gpu-h100-sxm"
                    ],
                }
            )
        except common.AuthenticationError:
            raise
        except common.BrokerError as exc:
            capacity.append({"tenant_id": tenant_id, "status": "ERROR", "error": str(exc)[:1200]})
    return {
        "schema_version": "catalog-switch-kubernetes-authorized-inventory/v1",
        "observed_at": common.iso(precise_utc_now()),
        "mutation_count": 0,
        "nebius_profile": cli.profile,
        "identity": {
            "type": identity_type,
            "id": identity.get("id"),
            "parent_id": identity.get("parent_id"),
        },
        "allowed_projects": common.AUTHORIZED_PROJECTS,
        "control_plane_versions": versions,
        "projects": projects,
        "capacity_advice": capacity,
        "secrets_recorded": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profiles", type=Path, default=ROOT / "kubernetes_profiles.json"
    )
    parser.add_argument("--registry", type=Path, default=K8S_REGISTRY)
    parser.add_argument("--nebius-profile", default="sandbox")
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--request", type=Path, required=True)
    plan_parser.add_argument("--lease", type=Path, required=True)
    support_parser = sub.add_parser("provision-control-plane")
    support_parser.add_argument("--lease", type=Path, required=True)
    support_parser.add_argument("--execute", action="store_true", required=True)
    demand_parser = sub.add_parser("record-demand")
    demand_parser.add_argument("--lease", type=Path, required=True)
    demand_parser.add_argument("--demand", type=Path, required=True)
    gpu_parser = sub.add_parser("provision-gpu-node-group")
    gpu_parser.add_argument("--lease", type=Path, required=True)
    gpu_parser.add_argument("--execute", action="store_true", required=True)
    attempt_cleanup = sub.add_parser("cleanup-attempt")
    attempt_cleanup.add_argument("--lease", type=Path, required=True)
    attempt_cleanup.add_argument("--execute", action="store_true")
    cleanup_parser = sub.add_parser("cleanup")
    cleanup_parser.add_argument("--lease", type=Path, required=True)
    cleanup_parser.add_argument("--execute", action="store_true")
    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("--cloud", action="store_true")
    scan_parser.add_argument("--output", type=Path)
    inventory_parser = sub.add_parser("inventory")
    inventory_parser.add_argument("--output", type=Path, required=True)
    supervisor_parser = sub.add_parser("supervisor-ledger")
    supervisor_parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "plan":
            result = plan(args.request, args.lease, args.registry, args.profiles)
        elif args.command == "provision-control-plane":
            result = provision_control_plane(
                args.lease,
                args.registry,
                common.NebiusCLI(args.nebius_profile),
                KubeCTL(),
            )
        elif args.command == "record-demand":
            result = record_demand(args.lease, args.registry, args.demand)
        elif args.command == "provision-gpu-node-group":
            result = provision_gpu_node_group(
                args.lease,
                args.registry,
                common.NebiusCLI(args.nebius_profile),
                KubeCTL(),
            )
        elif args.command == "cleanup-attempt":
            result = cleanup_attempt(
                args.lease,
                args.registry,
                common.NebiusCLI(args.nebius_profile),
                KubeCTL(),
                execute=args.execute,
            )
        elif args.command == "cleanup":
            result = cleanup(
                args.lease,
                args.registry,
                common.NebiusCLI(args.nebius_profile),
                KubeCTL(),
                execute=args.execute,
            )
        elif args.command == "scan":
            cli = common.NebiusCLI(args.nebius_profile) if args.cloud else None
            result = scan(args.registry, cli, args.cloud)
            if args.output:
                common.atomic_json(args.output, result)
        elif args.command == "inventory":
            result = inventory(common.NebiusCLI(args.nebius_profile))
            common.atomic_json(args.output, result)
        elif args.command == "supervisor-ledger":
            result = supervisor_ledger(args.registry)
            common.atomic_json(args.output, result)
        else:  # pragma: no cover
            raise AssertionError(args.command)
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    except common.AuthenticationError as exc:
        print(f"AUTH_STOP: {exc}", file=sys.stderr)
        return 3
    except common.BrokerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
