#!/usr/bin/env python3
"""Versioned, fail-closed Nebius Managed Kubernetes experiment lease broker.

The existing ``broker.py`` VM v1 contract intentionally remains independent.
This backend owns only fresh Managed Kubernetes resources and splits target-
neutral support creation from demand-gated GPU node-group creation.
"""

from __future__ import annotations

import argparse
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


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import broker as common  # noqa: E402


REQUEST_SCHEMA_VERSION = "catalog-switch-kubernetes-lease-request/v1"
LEASE_SCHEMA_VERSION = "catalog-switch-kubernetes-resource-lease/v2"
PROFILE_SCHEMA_VERSION = "catalog-switch-kubernetes-resource-profiles/v1"
REGISTRY_SCHEMA_VERSION = "catalog-switch-kubernetes-lease-registry/v1"
DEMAND_SCHEMA_VERSION = "catalog-switch-kubernetes-node-demand/v1"
EVENT_SCHEMA_VERSION = "catalog-switch-kubernetes-lifecycle-events/v1"
BACKEND_VERSION = "nebius-managed-kubernetes/v1"
KUBECTL = "/usr/local/bin/kubectl"
KUBECONFIG_ROOT = ROOT / "kubeconfigs"
K8S_REGISTRY = ROOT / "kubernetes-leases" / "registry.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


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
        "cluster_version",
        "node_group_profile",
        "expected_duration_hours",
        "ttl_hours",
        "cleanup_deadline_utc",
        "hard_cost_cap_usd",
        "artifact_storage",
        "metric_contract_sha256",
        "trace_sha256",
        "model_input_sha256s",
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
    try:
        profile = profiles["profiles"][request["node_group_profile"]]
    except KeyError as exc:
        raise common.BrokerError("unknown Kubernetes node-group profile") from exc
    if request["region"] not in profile["regions"]:
        raise common.BrokerError("Kubernetes profile is unavailable in the requested region")
    if request["cluster_version"] != profile["kubernetes_version"]:
        raise common.BrokerError("cluster version differs from the pinned profile")
    gpu = profile["gpu_node_group"]
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
    model_hashes = request["model_input_sha256s"]
    if not isinstance(model_hashes, dict) or not model_hashes:
        raise common.BrokerError("at least one frozen model input digest is required")
    for model_id, digest in model_hashes.items():
        common.sanitize_label(str(model_id), "model_id")
        if not HEX64.fullmatch(str(digest)):
            raise common.BrokerError("model input values must be SHA-256 digests")
    normalized.update(
        {
            "expected_duration_hours": str(duration),
            "ttl_hours": ttl,
            "hard_cost_cap_usd": common.decimal_string(cap),
            "cleanup_deadline_utc": common.iso(deadline),
            "artifact_storage": {"max_size_gib": int(artifact["max_size_gib"])},
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


def build_lease(request: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    request_hash = common.sha256_json(request)
    task_slug = request["task_id"][:18].rstrip("-._")
    prefix = f"{common.PROGRAM_PREFIX}-{task_slug}-{request_hash[:8]}"
    profile = profiles["profiles"][request["node_group_profile"]]
    estimate = cost_estimate(request, profile)
    labels = {
        "program": common.PROGRAM,
        "broker": "resource-broker-k8s-v2",
        "lease": request["lease_id"],
        "task": request["task_id"],
        "owner": request["owner"],
        "expires": common.parse_utc(request["cleanup_deadline_utc"]).strftime("%Y%m%dt%H%M%Sz").lower(),
    }
    for key, value in labels.items():
        common.sanitize_label(key, "label key")
        common.sanitize_label(value, f"label {key}")
    now = common.utc_now()
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
        "profile_snapshot": profile,
        "profile_sha256": common.sha256_json(profile),
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
        "request_sha256": lease["request_sha256"],
        "profile_sha256": lease["profile_sha256"],
        "prefix": lease["prefix"],
        "project_id": lease["project_id"],
        "region": lease["region"],
        "expires_at": lease["expires_at"],
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
    if common.sha256_json(immutable_plan_material(lease)) != lease.get("plan_sha256"):
        raise common.BrokerError("immutable resource plan hash mismatch")
    if lease.get("project_id") != lease["request"]["project_id"] or lease.get("region") != lease["request"]["region"]:
        raise common.BrokerError("lease identity differs from immutable request")


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


def plan(request_path: Path, lease_path: Path, registry_path: Path, profiles_path: Path) -> dict[str, Any]:
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
        "get": ["compute", "instance", "get"],
    },
    "pool": {"get": ["vpc", "pool", "get"]},
    "route_table": {"get": ["vpc", "route-table", "get"]},
}


def resource_payload(name: str, parent_id: str, labels: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {"name": name, "parent_id": parent_id, "labels": labels}, "spec": spec}


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
) -> dict[str, Any]:
    resource_id = common.metadata_id(value, kind)
    existing = next((item for item in lease["resources"] if item.get("id") == resource_id), None)
    if existing:
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
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
    }
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
    operation_id = f"create:{kind}:{name}"
    recorded = find_resource(lease, kind, name)
    if recorded:
        value = cli.run([*RESOURCE_COMMANDS[kind]["get"], recorded["id"]])
        validate_owned_metadata(lease, kind, value, name, parent_id)
        return recorded
    operation = operation_for(lease, operation_id)
    listed = cli.run([*RESOURCE_COMMANDS[kind]["list"], "--parent-id", parent_id, "--all"])
    exact = [item for item in listed.get("items", []) if item.get("metadata", {}).get("name") == name]
    if len(exact) > 1:
        raise common.BrokerError(f"multiple exact-name {kind} resources exist; manual review required")
    if exact:
        if operation is None or operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
            raise common.BrokerError(f"foreign or pre-existing {kind} name collision; preserve it")
        validate_owned_metadata(lease, kind, exact[0], name, parent_id)
        created_at = exact[0].get("metadata", {}).get("created_at")
        if created_at and common.parse_utc(created_at) < common.parse_utc(operation["started_at_utc"]):
            raise common.BrokerError(f"{kind} predates the persisted create intent; preserve it")
        resource = add_resource(lease, kind, name, exact[0], depends_on, operation_id)
        operation["status"] = "RECONCILED_AFTER_INTERRUPTION"
        operation["completed_at_utc"] = common.iso(common.utc_now())
        operation["resource_id"] = resource["id"]
        event(lease, "resource.create.reconciled", "PASS", kind=kind, resource_id=resource["id"])
        save(lease_path, registry_path, lease)
        return resource
    if operation is None:
        operation = {
            "operation_id": operation_id,
            "kind": kind,
            "name": name,
            "parent_id": parent_id,
            "depends_on": depends_on,
            "status": "INTENT_RECORDED",
            "started_at_utc": common.iso(common.utc_now()),
            "started_monotonic_ns": time.monotonic_ns(),
            "completed_at_utc": None,
            "resource_id": None,
            "failure": None,
        }
        lease["resource_create_operations"].append(operation)
        event(lease, "resource.create.started", "PASS", kind=kind, name=name)
        save(lease_path, registry_path, lease)
    elif operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
        raise common.BrokerError(f"unexpected create operation state for {kind}: {operation['status']}")
    try:
        value = cli.run(
            RESOURCE_COMMANDS[kind]["create"],
            payload=resource_payload(name, parent_id, lease["labels"], spec),
            timeout=timeout,
        )
        validate_owned_metadata(lease, kind, value, name, parent_id)
        resource = add_resource(lease, kind, name, value, depends_on, operation_id)
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


def run_read_only_preflight(lease: dict[str, Any], cli: common.NebiusCLI) -> dict[str, Any]:
    request = lease["request"]
    profile = lease["profile_snapshot"]
    whoami = cli.run(["iam", "whoami"])
    identity_type = next(iter(whoami), "unknown")
    identity = whoami.get(identity_type, {}).get("info", {}).get("metadata", {})
    if identity.get("parent_id") not in common.AUTHORIZED_PROJECTS:
        raise common.BrokerError("authenticated identity is not rooted in an authorized epic project")
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
        "identity": {"type": identity_type, "id": identity.get("id"), "parent_id": identity.get("parent_id")},
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
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
        "provider_metadata": metadata or {},
    }
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


def validate_kubeconfig_file(path: Path) -> None:
    if path.parent.resolve() != KUBECONFIG_ROOT.resolve() or path.suffix != ".yaml":
        raise common.BrokerError("kubeconfig path is outside the task-owned authority directory")
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        raise common.BrokerError("kubeconfig authority cannot be a symlink or non-regular file")
    if details.st_uid != os.getuid():
        raise common.BrokerError("kubeconfig authority is not owned by the current task user")
    if stat.S_IMODE(details.st_mode) & 0o077:
        raise common.BrokerError("kubeconfig authority permissions are broader than 0600")


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
    endpoint = cluster_value.get("status", {}).get("control_plane", {}).get("endpoints", {}).get(
        "public_endpoint"
    )
    if not endpoint:
        raise common.BrokerError("cluster has no public control-plane endpoint for this authority")
    if existing:
        validate_kubeconfig_file(path)
        if kubeconfig_file_sha256(path) != existing["provider_metadata"]["sha256"]:
            raise common.BrokerError("kubeconfig authority changed outside the broker")
        view = kubectl.run(path, ["config", "view", "--minify"])
        if endpoint not in json.dumps(view):
            raise common.BrokerError("kubeconfig authority does not point to the leased cluster")
        return existing
    if path.exists():
        if operation is None or operation["status"] not in {"INTENT_RECORDED", "CREATE_FAILED"}:
            raise common.BrokerError("pre-existing kubeconfig path collision; preserve it")
        validate_kubeconfig_file(path)
    else:
        if operation is None:
            operation = {
                "operation_id": operation_id,
                "kind": "kubeconfig_authority",
                "name": path.name,
                "parent_id": common.metadata_id(cluster_value, "cluster"),
                "depends_on": [common.metadata_id(cluster_value, "cluster")],
                "status": "INTENT_RECORDED",
                "started_at_utc": common.iso(common.utc_now()),
                "started_monotonic_ns": time.monotonic_ns(),
                "completed_at_utc": None,
                "resource_id": None,
                "failure": None,
            }
            lease["resource_create_operations"].append(operation)
            event(lease, "kubeconfig.authority.started", "PASS", path=str(path))
            save(lease_path, registry_path, lease)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise common.BrokerError("kubeconfig authority directory cannot be a symlink")
        cli.run(
            [
                "mk8s",
                "v1",
                "cluster",
                "get-credentials",
                "--id",
                common.metadata_id(cluster_value, "cluster"),
                "--external",
                "--context-name",
                lease["kubernetes_context"],
                "--kubeconfig",
                str(path),
            ],
            json_output=False,
            timeout=180,
        )
        os.chmod(path, 0o600)
        validate_kubeconfig_file(path)
    view = kubectl.run(path, ["config", "view", "--minify"])
    if endpoint not in json.dumps(view):
        raise common.BrokerError("generated kubeconfig does not point to the leased cluster")
    digest = kubeconfig_file_sha256(path)
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
        "desired_final_state": "ABSENT",
        "deleted_at": None,
        "absence_verified_at": None,
        "cleanup_evidence": None,
        "provider_metadata": {
            "path": str(path),
            "sha256": digest,
            "mode": "0600",
            "identity_id": identity["id"],
            "cluster_id": lease["cluster_id"],
            "api_server": endpoint,
            "context": lease["kubernetes_context"],
            "contents_recorded": False,
        },
    }
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
        resource = add_provider_resource(
            lease,
            kind=node_kind,
            resource_id=compute_id,
            name=node.get("metadata", {}).get("name", compute_id),
            managed_by_resource_id=group_id,
            created_at=node.get("metadata", {}).get("creationTimestamp"),
            parent_id=lease["project_id"],
            metadata={
                "kubernetes_uid": node.get("metadata", {}).get("uid"),
                "provider_id": provider_id,
                "ready": True,
                "labels": {
                    key: value
                    for key, value in (node.get("metadata", {}).get("labels", {}) or {}).items()
                    if key.startswith(("nebius", "mk8s", "node.kubernetes.io", "nvidia.com"))
                },
            },
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
    interfaces = template.get("network_interfaces", [])
    failures = []
    if network.get("spec", {}).get("ipv4_public_pools", {}).get("pools", []):
        failures.append("task VPC has a public address pool")
    if rules.get("items"):
        failures.append("task security group is not deny-all")
    if cluster.get("status", {}).get("state") != "RUNNING":
        failures.append("cluster is not RUNNING")
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
            "public_control_plane_endpoint": lease["api_server"],
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


def provision_control_plane(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    if lease["state"] in {"SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", "ACTIVE", "ACTIVE_ATTEMPT"}:
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
                    "endpoints": {"public_endpoint": {}},
                    "etcd_cluster_size": 3,
                    "karpenter": False,
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
                        "size_gibibytes": system_profile["boot_disk_gib"],
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
            "accepted_event_sha256",
            "t0_observed_at_utc",
            "t0_observed_monotonic_ns",
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
    accepted_at = common.parse_utc(str(value["t0_observed_at_utc"]))
    monotonic_ns = int(value["t0_observed_monotonic_ns"])
    if monotonic_ns <= 0:
        raise common.BrokerError("t0_observed_monotonic_ns must be positive")
    normalized = dict(value)
    normalized["t0_observed_at_utc"] = common.iso(accepted_at)
    normalized["t0_observed_monotonic_ns"] = monotonic_ns
    return normalized


def record_demand(
    lease_path: Path, registry_path: Path, demand_path: Path
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    if lease["request"]["campaign_arm"] != "B_new_preemptible_node":
        raise common.BrokerError("post-T0 demand is valid only for B_new_preemptible_node")
    demand = validate_demand(common.load_json(demand_path), lease)
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
    accepted_at = common.parse_utc(demand["t0_observed_at_utc"])
    if accepted_at > received_at:
        raise common.BrokerError("demand appears to precede its accepted T0 wall clock")
    if demand["t0_observed_monotonic_ns"] > received_mono:
        raise common.BrokerError("demand appears to precede its accepted T0 monotonic clock")
    support_event = next(
        (item for item in reversed(lease["lifecycle_events"]) if item["event"] == "support.ready"),
        None,
    )
    if not support_event or accepted_at < common.parse_utc(support_event["observed_at_utc"]):
        raise common.BrokerError("request T0 predates the target-neutral support-ready boundary")
    lease["demand"] = {
        **demand,
        "demand_sha256": demand_hash,
        "demand_received_at_utc": common.iso(received_at),
        "demand_received_monotonic_ns": received_mono,
        "causal_order_pass": True,
    }
    attempt = {
        "attempt_id": demand["attempt_id"],
        "demand_sha256": demand_hash,
        "state": "DEMAND_RECORDED",
        "receipt": {
            "schema_version": "catalog-switch-kubernetes-node-demand-receipt/v1",
            "attempt_id": demand["attempt_id"],
            "accepted_event_sha256": demand["accepted_event_sha256"],
            "t0_observed_at_utc": demand["t0_observed_at_utc"],
            "t0_observed_monotonic_ns": demand["t0_observed_monotonic_ns"],
            "demand_received_at_utc": common.iso(received_at),
            "demand_received_monotonic_ns": received_mono,
            "capacity_advice_started_at_utc": None,
            "capacity_advice": None,
            "capacity_advice_attempts": [],
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
    if "preemptible" not in template:
        failures.append("GPU node group is not preemptible")
    if template.get("service_account_id") != service_account_id:
        failures.append("GPU node group does not use the task-owned service account")
    if template.get("network_interfaces") != [{"subnet_id": subnet_id}]:
        failures.append("GPU node group does not use only the task-owned private subnet")
    if any(item.get("public_ip_address") for item in template.get("network_interfaces", [])):
        failures.append("GPU node group requests a public IP")
    if failures:
        raise common.BrokerError("GPU isolation proof failed: " + "; ".join(failures))


def provision_gpu_node_group(
    lease_path: Path,
    registry_path: Path,
    cli: common.NebiusCLI,
    kubectl: KubeCTL,
) -> dict[str, Any]:
    lease = common.load_json(lease_path)
    assert_integrity(lease)
    arm = lease["request"]["campaign_arm"]
    if lease["state"] in {"ACTIVE", "ACTIVE_ATTEMPT"}:
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
                        "size_gibibytes": profile["boot_disk_gib"],
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
        nodes = reconcile_nodes(lease, kubectl, node_group, "gpu_node")
        if len(nodes) != 1:
            raise common.BrokerError("GPU node group did not yield exactly one node identity")
        ready_at = precise_utc_now()
        attempt["receipt"].update(
            {
                "node_group_id": node_group["id"],
                "node_id": nodes[0]["id"],
                "node_ready_at_utc": common.iso(ready_at),
                "gpu_product": profile["gpu_product"],
                "gpu_count": 1,
                "preemptible": True,
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
            "gpu_count": 1,
            "preemptible": True,
            "public_worker_ips": [],
            "attempt_id": attempt["attempt_id"],
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
        if operation.get("resource_id") or operation["status"] not in {
            "INTENT_RECORDED",
            "CREATE_FAILED",
        }:
            continue
        kind = operation["kind"]
        if kind == "kubeconfig_authority":
            path = Path(lease["kubeconfig_path"])
            if not path.exists():
                operation["status"] = "ABSENCE_VERIFIED_AFTER_INTERRUPTION"
                operation["completed_at_utc"] = common.iso(precise_utc_now())
                continue
            validate_kubeconfig_file(path)
            digest = kubeconfig_file_sha256(path)
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
                "desired_final_state": "ABSENT",
                "deleted_at": None,
                "absence_verified_at": None,
                "cleanup_evidence": None,
                "provider_metadata": {
                    "path": str(path),
                    "sha256": digest,
                    "mode": "0600",
                    "contents_recorded": False,
                    "reconciled_for_cleanup": True,
                },
            }
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
            continue
        validate_owned_metadata(lease, kind, exact[0], operation["name"], operation["parent_id"])
        created = exact[0].get("metadata", {}).get("created_at")
        if created and common.parse_utc(created) < common.parse_utc(operation["started_at_utc"]):
            raise common.BrokerError(f"interrupted {kind} candidate predates intent; preserve it")
        resource = add_resource(
            lease,
            kind,
            operation["name"],
            exact[0],
            operation.get("depends_on", []),
            operation["operation_id"],
        )
        operation["resource_id"] = resource["id"]
        operation["status"] = "RECONCILED_FOR_CLEANUP"
        operation["completed_at_utc"] = common.iso(precise_utc_now())
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
    if kind == "kubeconfig_authority":
        path = Path(resource["provider_metadata"]["path"])
        if path.exists():
            validate_kubeconfig_file(path)
            if kubeconfig_file_sha256(path) != resource["provider_metadata"]["sha256"]:
                raise common.BrokerError("kubeconfig changed outside the lease; preserve it")
            path.unlink()
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
        cli.run(delete_args(kind, resource_id), json_output=False, timeout=1200)
        if not wait_absent(cli, kind, resource_id, timeout_seconds=1200):
            raise common.BrokerError("resource is still present after exact-ID deletion")
        evidence = f"{delete_args(kind, resource_id)} then {get_args(kind, resource_id)} -> NotFound"
    verified = common.iso(precise_utc_now())
    resource["deleted_at"] = verified
    resource["absence_verified_at"] = verified
    resource["cleanup_evidence"] = evidence
    event(lease, "resource.absence.verified", "PASS", kind=kind, resource_id=resource_id)
    save(lease_path, registry_path, lease)


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
            group_value = cli.run(
                [*RESOURCE_COMMANDS["gpu_node_group"]["get"], live_group["id"]]
            )
            if int(group_value.get("status", {}).get("node_count", 0)):
                live_nodes = reconcile_nodes(
                    lease, kubectl or KubeCTL(), live_group, "gpu_node"
                )
                attempt["receipt"]["node_group_id"] = live_group["id"]
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
    if failures:
        lease["state"] = "ATTEMPT_CLEANUP_FAILED"
        attempt["state"] = "CLEANUP_FAILED"
        save(lease_path, registry_path, lease)
        raise common.BrokerError("attempt cleanup incomplete: " + "; ".join(failures))
    verified_at = common.iso(precise_utc_now())
    attempt["state"] = "RELEASED"
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
            for item in pending
        ],
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
    reconcile_create_intents_for_cleanup(lease_path, registry_path, lease, cli)
    lease = common.load_json(lease_path)
    reconcile_network_children(lease, cli)
    kubeconfig = Path(lease["kubeconfig_path"])
    if kubeconfig.exists():
        for group_kind, node_kind in (
            ("gpu_node_group", "gpu_node"),
            ("system_node_group", "system_node"),
        ):
            for group in [
                item
                for item in lease["resources"]
                if item["kind"] == group_kind and not item.get("deleted_at")
            ]:
                children = [
                    item
                    for item in lease["resources"]
                    if item["kind"] == node_kind
                    and not item.get("deleted_at")
                    and item.get("managed_by_resource_id") == group["id"]
                ]
                if not children:
                    group_value = cli.run(
                        [*RESOURCE_COMMANDS[group_kind]["get"], group["id"]]
                    )
                    if int(group_value.get("status", {}).get("node_count", 0)):
                        reconcile_nodes(lease, kubectl or KubeCTL(), group, node_kind)
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
    if failures:
        lease["state"] = "CLEANUP_FAILED"
        save(lease_path, registry_path, lease)
        raise common.BrokerError("cleanup incomplete: " + "; ".join(failures))
    lease["state"] = "RELEASED"
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
                }
            )
        for planned in lease["resource_graph"]:
            key = (planned["resource_type"], planned["resource_name"])
            if key in actual_keys:
                continue
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
                    "cleanup_state": "NOT_CREATED",
                    "deleted_at": None,
                    "absence_verified_at": None,
                    "cleanup_evidence": "No create operation admitted or resource ID recorded.",
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
