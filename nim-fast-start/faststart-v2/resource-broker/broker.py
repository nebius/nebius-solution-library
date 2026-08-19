#!/usr/bin/env python3
"""Fail-closed Nebius experiment lease broker for catalog-switch work."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parent
FASTSTART_ROOT = ROOT.parent
NEBIUS = "/usr/local/bin/nebius"
SCHEMA_VERSION = "catalog-switch-resource-lease/v1"
REQUEST_SCHEMA_VERSION = "catalog-switch-lease-request/v1"
REGISTRY_SCHEMA_VERSION = "catalog-switch-lease-registry/v1"
PROGRAM = "catalog-switch"
PROGRAM_PREFIX = "mlsp-csw"
DEFAULT_SUPERVISOR_LEDGER = Path(
    "/home/tux/dashboard/data/epics/ml-specialist-tasks/tasks/"
    "catalog-switch-resource-broker/docs/supervision/resources.json"
)
AUTHORIZED_PROJECTS = {
    "project-e00z6b02t8ddk96c49": "eu-north1",
    "project-u00tds8vpr00jaxa76s22d": "us-central1",
    "project-i00xz31gpr00xp9jhp982v": "me-west1",
}
AUTH_FAILURES = (
    "unauthenticated",
    "permissiondenied",
    "permission denied",
    "unauthorized",
    "login required",
)
NOT_FOUND_MARKERS = ("notfound", "not found", "code = not_found")
SAFE_LABEL = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
GPU_PLATFORM_PREFIX = "gpu-"
LIVE_AUTH_SCHEMA_VERSION = "catalog-switch-internal-live-authorization/v2"
QWEN_SCOUT_AUTHORIZATION_ID = "internal-qwen3-h100-scout-v2-20260819"
QWEN_SCOUT_LEASE_ID = "catswitch-qwen3-h100-scout-20260819"
QWEN_SCOUT_TASK_ID = "catalog-switch-cerebrium-qwen3-glm52-benchmark"
QWEN_SCOUT_IMAGE_DIGEST = (
    "sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d"
)
QWEN_SCOUT_MODEL = "Qwen/Qwen3-8B"
QWEN_SCOUT_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
RECORDER_IP_ENDPOINT = "https://api.ipify.org"
LIVE_AUTH_TOP_KEYS = {
    "authorization_id",
    "authorized_at",
    "authorized_by",
    "bearer_token_sha256",
    "bootstrap_artifacts",
    "campaign",
    "cleanup",
    "expires_at",
    "frozen",
    "implementation",
    "network",
    "schema",
    "scope",
    "secret_values_published",
    "state",
}


class BrokerError(RuntimeError):
    """Expected fail-closed broker error."""


class AuthenticationError(BrokerError):
    """Authentication/authorization stop condition."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BrokerError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(dt.timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BrokerError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BrokerError(f"expected JSON object in {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def observe_recorder_cidr() -> str:
    """Return the current recorder /32 without logging or persisting the address."""
    try:
        with urllib.request.urlopen(RECORDER_IP_ENDPOINT, timeout=20) as response:
            raw = response.read(128).decode().strip()
        address = ipaddress.IPv4Address(raw)
    except Exception as exc:
        raise BrokerError("cannot independently observe the recorder IPv4 address") from exc
    return f"{address}/32"


def _load_runtime_bearer(path: Path) -> str:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BrokerError("runtime bearer-token file is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BrokerError("runtime bearer-token path must be a regular non-symlink file")
    if info.st_mode & 0o077:
        raise BrokerError("runtime bearer-token file must not be group/world accessible")
    value = path.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BrokerError("runtime bearer token must be a 32-byte lowercase hex value")
    return value


def validate_live_authorization(
    authorization_path: Path,
    lease_path: Path,
    bearer_token_path: Path,
    *,
    observed_recorder_cidr: str | None = None,
    require_cleared: bool = False,
    clearance_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the task-scoped bootstrap exception and return a private context.

    The returned `_recorder_cidr` and `_bearer_token` keys are runtime-only and
    must never be written to the lease, registry, command output, or evidence.
    """
    authorization = load_json(authorization_path)
    if set(authorization) != LIVE_AUTH_TOP_KEYS:
        raise BrokerError("live authorization top-level fields differ from v2")
    if authorization.get("schema") != LIVE_AUTH_SCHEMA_VERSION:
        raise BrokerError("unsupported live authorization schema")
    if authorization.get("authorization_id") != QWEN_SCOUT_AUTHORIZATION_ID:
        raise BrokerError("authorization is not scoped to the internal Qwen scout")
    if authorization.get("state") != "PRE_CREATION_REVIEW":
        raise BrokerError("versioned authorization candidate must remain PRE_CREATION_REVIEW")
    if authorization.get("secret_values_published") is not False:
        raise BrokerError("authorization must declare that no secret values are published")
    if authorization.get("authorized_by") != "explicit-user-manager-intervention-20260819":
        raise BrokerError("authorization provenance differs")
    if any(
        re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}/32", value)
        for value in _strings(authorization)
    ):
        raise BrokerError("publishable authorization embeds the recorder /32")

    lease = load_json(lease_path)
    if lease.get("schema_version") != SCHEMA_VERSION:
        raise BrokerError("authorization references an unsupported lease")
    if lease.get("state") != "PLANNED" or lease.get("resources"):
        raise BrokerError("authorization review requires a clean PLANNED zero-resource lease")
    if utc_now() >= parse_utc(lease["expires_at"]):
        raise BrokerError("authorization or lease is expired")
    if authorization.get("expires_at") != lease.get("expires_at"):
        raise BrokerError("authorization expiry differs from the lease")

    scope = authorization.get("scope")
    expected_scope = {
        "backend": "internal-nebius",
        "forbidden_backends": ["cerebrium", "modal"],
        "forbidden_models": ["zai-org/GLM-5.2", "zai-org/GLM-5.2-FP8"],
        "gpu_count": 1,
        "gpu_type": "H100",
        "lease_id": QWEN_SCOUT_LEASE_ID,
        "mode": "preemptible",
        "profile": "h100-single",
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "task_id": QWEN_SCOUT_TASK_ID,
    }
    if scope != expected_scope:
        raise BrokerError("authorization scope differs from the exact internal Qwen scout")
    request = lease["request"]
    for key in ("lease_id", "mode", "profile", "project_id", "region", "task_id"):
        if request.get(key) != scope[key]:
            raise BrokerError(f"authorization/lease scope differs: {key}")

    frozen = authorization.get("frozen")
    if not isinstance(frozen, dict):
        raise BrokerError("authorization frozen section is missing")
    expected_frozen = {
        "campaign_sha256": request["experiment"]["metric_contract_sha256"],
        "expected_cost_usd": lease["cost_estimate"]["expected_cost_usd"],
        "image_amd64_digest": QWEN_SCOUT_IMAGE_DIGEST,
        "input_sha256": request["experiment"]["input_sha256"],
        "lease_plan_sha256": file_sha256(lease_path),
        "model_id": QWEN_SCOUT_MODEL,
        "model_revision": QWEN_SCOUT_REVISION,
        "request_sha256": lease["request_sha256"],
        "source_parent_commit": "94cd1c9999dfe7ca7626661b89352b6d41727cd4",
        "ttl_cost_ceiling_usd": lease["cost_estimate"]["ttl_cost_ceiling_usd"],
    }
    if frozen != expected_frozen:
        raise BrokerError("authorization frozen hashes/cost/model differ from the lease")

    implementation = authorization.get("implementation")
    implementation_paths = {
        "broker_path": "resource-broker/broker.py",
        "broker_tests_path": "resource-broker/tests/test_broker.py",
        "schema_path": (
            "catalog-switch/cerebrium-comparator/schemas/"
            "live-authorization.schema.json"
        ),
    }
    if not isinstance(implementation, dict) or set(implementation) != {
        "broker_path",
        "broker_sha256",
        "broker_tests_path",
        "broker_tests_sha256",
        "schema_path",
        "schema_sha256",
    }:
        raise BrokerError("authorization implementation pin set differs")
    for path_key, expected_path in implementation_paths.items():
        if implementation.get(path_key) != expected_path:
            raise BrokerError("authorization implementation path differs")
        digest_key = path_key.replace("_path", "_sha256")
        if file_sha256(FASTSTART_ROOT / expected_path) != implementation.get(digest_key):
            raise BrokerError("authorization implementation digest differs")

    expected_campaign = {
        "arm_id": "internal-qwen3-new-target-matched",
        "cold_attempts": 3,
        "cold_classification": "process-cold-artifact-hit",
        "prompt_id": "qwen3-nonthinking-exact",
        "semantic_smokes": 1,
    }
    if authorization.get("campaign") != expected_campaign:
        raise BrokerError("authorization campaign permits work outside one smoke plus n=3 Qwen scouts")
    expected_cleanup = {
        "desired_final_state": "ABSENT",
        "foreign_replacement_policy": "fail-closed-no-delete",
        "idempotent": True,
        "partial_create_cleanup": True,
        "verification": "exact-id-not-found-plus-cascade-child-absence",
    }
    if authorization.get("cleanup") != expected_cleanup:
        raise BrokerError("authorization cleanup contract differs")

    network = authorization.get("network")
    expected_ingress = {
        "authentication": "bearer-sha256-pinned",
        "port": 8080,
        "protocol": "TCP",
        "source": "runtime-observed-ipv4-32-sha256-pinned",
    }
    expected_egress = [
        ("TCP", (443,), "TLS artifact and container-registry localization"),
        ("TCP", (80,), "bootstrap OS packages only when the image lacks Docker"),
        ("UDP", (53,), "DNS resolution"),
        ("TCP", (53,), "DNS fallback"),
        ("UDP", (123,), "UTC clock synchronization for external recorder evidence"),
    ]
    if not isinstance(network, dict) or set(network) != {
        "direct_container_ingress",
        "egress",
        "ingress",
        "public_ipv4_count",
        "recorder_cidr_published",
        "recorder_cidr_sha256",
        "ssh_ingress",
    }:
        raise BrokerError("authorization network fields differ")
    if (
        network["ingress"] != expected_ingress
        or network["public_ipv4_count"] != 1
        or network["recorder_cidr_published"] is not False
        or network["ssh_ingress"] is not False
        or network["direct_container_ingress"] is not False
    ):
        raise BrokerError("authorization ingress/public-IP boundary differs")
    observed_egress = [
        (item.get("protocol"), tuple(item.get("ports", [])), item.get("purpose"))
        for item in network.get("egress", [])
        if item.get("destination_cidrs") == ["0.0.0.0/0"]
    ]
    if observed_egress != expected_egress or len(network.get("egress", [])) != len(expected_egress):
        raise BrokerError("authorization egress is not the exact least-port bootstrap set")

    cidr = observed_recorder_cidr or observe_recorder_cidr()
    try:
        parsed_cidr = ipaddress.IPv4Network(cidr, strict=True)
    except ValueError as exc:
        raise BrokerError("observed recorder address is not a canonical IPv4 CIDR") from exc
    if parsed_cidr.prefixlen != 32:
        raise BrokerError("observed recorder source must be exactly one IPv4 /32")
    canonical_cidr = str(parsed_cidr)
    if hashlib.sha256(canonical_cidr.encode()).hexdigest() != network["recorder_cidr_sha256"]:
        raise BrokerError("recorder IP drift detected; live creation remains fail-closed")

    bearer_token = _load_runtime_bearer(bearer_token_path)
    if hashlib.sha256(bearer_token.encode()).hexdigest() != authorization["bearer_token_sha256"]:
        raise BrokerError("runtime bearer token differs from the pinned authorization hash")

    artifacts = authorization.get("bootstrap_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise BrokerError("authorization must pin exactly two bootstrap artifacts")
    expected_artifact_targets = {
        "catalog-switch/cerebrium-comparator/live/bootstrap_internal_qwen.sh": (
            "/opt/catswitch/bootstrap_internal_qwen.sh"
        ),
        "catalog-switch/cerebrium-comparator/live/internal_scout_server.py": (
            "/opt/catswitch/internal_scout_server.py"
        ),
    }
    if {item.get("path"): item.get("target") for item in artifacts} != expected_artifact_targets:
        raise BrokerError("authorization bootstrap artifact identity differs")
    targets = set()
    for artifact in artifacts:
        if set(artifact) != {"path", "sha256", "target"}:
            raise BrokerError("bootstrap artifact fields differ")
        relative = Path(artifact["path"])
        source = (FASTSTART_ROOT / relative).resolve()
        if FASTSTART_ROOT not in source.parents or source.is_symlink() or not source.is_file():
            raise BrokerError("bootstrap artifact escapes the task source tree")
        if file_sha256(source) != artifact["sha256"]:
            raise BrokerError("bootstrap artifact digest differs")
        target = str(artifact["target"])
        if not target.startswith("/opt/catswitch/") or target in targets:
            raise BrokerError("bootstrap target is unsafe or duplicated")
        targets.add(target)

    public_summary = {
        "schema": authorization["schema"],
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": file_sha256(authorization_path),
        "state": authorization["state"],
        "recorder_cidr_sha256": network["recorder_cidr_sha256"],
        "bearer_token_sha256": authorization["bearer_token_sha256"],
        "bootstrap_artifacts": artifacts,
        "network_policy": {
            "public_ipv4_count": 1,
            "ingress_protocol": "TCP",
            "ingress_port": 8080,
            "ingress_source_published": False,
            "ssh_ingress": False,
            "direct_container_ingress": False,
            "egress": network["egress"],
        },
        "secret_values_published": False,
    }
    clearance = None
    if clearance_path is not None:
        clearance = load_json(clearance_path)
        if set(clearance) != {
            "authorization_id",
            "authorization_sha256",
            "clearance_id",
            "decision",
            "reviewed_at",
            "reviewed_commit",
            "reviewer",
            "schema",
        }:
            raise BrokerError("independent clearance fields differ")
        if (
            clearance.get("schema") != "catalog-switch-independent-precreation-clearance/v1"
            or clearance.get("authorization_id") != authorization["authorization_id"]
            or clearance.get("authorization_sha256") != public_summary["authorization_sha256"]
            or clearance.get("decision") != "CLEARED"
            or not re.fullmatch(r"[0-9a-f]{40}", str(clearance.get("reviewed_commit", "")))
            or not str(clearance.get("reviewer", "")).strip()
        ):
            raise BrokerError("independent clearance does not clear this exact authorization candidate")
        public_summary["independent_clearance"] = clearance
    if require_cleared and clearance is None:
        raise BrokerError("live creation is blocked pending an independent PRE-CREATION REVIEW clearance")
    return {
        "public": public_summary,
        "authorization": authorization,
        "_recorder_cidr": canonical_cidr,
        "_bearer_token": bearer_token,
    }


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def sanitize_label(value: str, field: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_.-]+", "-", value.lower()).strip("-._")
    if not SAFE_LABEL.fullmatch(cleaned):
        raise BrokerError(f"{field} cannot be represented as a safe Nebius label")
    return cleaned


def decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


class NebiusCLI:
    def __init__(self, profile: str, binary: str = NEBIUS) -> None:
        if profile != "sandbox":
            raise BrokerError("only the audited Nebius profile 'sandbox' is allowed")
        self.profile = profile
        self.binary = binary

    def run(
        self,
        args: list[str],
        *,
        payload: dict[str, Any] | None = None,
        json_output: bool = True,
        timeout: int = 90,
        allow_not_found: bool = False,
    ) -> Any:
        command = [self.binary, *args]
        stdin = None
        if payload is not None:
            command.append("-")
            stdin = canonical(payload)
        command.extend(["--profile", self.profile, "--timeout", f"{timeout}s"])
        if json_output:
            command.extend(["--format", "json"])
        result = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout + 5,
            check=False,
        )
        combined = f"{result.stdout}\n{result.stderr}".strip()
        lowered = combined.lower()
        if result.returncode:
            if allow_not_found and any(marker in lowered for marker in NOT_FOUND_MARKERS):
                return None
            if any(marker in lowered for marker in AUTH_FAILURES):
                raise AuthenticationError(
                    "Nebius authentication/authorization failed; do not switch credentials or projects: "
                    + combined[:1000]
                )
            raise BrokerError(
                f"Nebius command failed ({result.returncode}): {' '.join(command[:5])}: "
                f"{combined[:2000]}"
            )
        if not json_output:
            return result.stdout
        if not result.stdout.strip():
            return {}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BrokerError(f"Nebius returned non-JSON output: {result.stdout[:1000]}") from exc


def load_profiles(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get("schema_version") != "catalog-switch-resource-profiles/v1":
        raise BrokerError("unsupported profiles schema")
    return value


def validate_request(request: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "lease_id",
        "task_id",
        "owner",
        "cleanup_owner",
        "project_id",
        "region",
        "profile",
        "mode",
        "expected_duration_hours",
        "ttl_hours",
        "purpose",
        "artifact_storage",
        "health_proof",
        "experiment",
    }
    missing = sorted(required - request.keys())
    extra = sorted(request.keys() - required)
    if missing or extra:
        raise BrokerError(f"request fields mismatch; missing={missing}, extra={extra}")
    if request["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise BrokerError("unsupported request schema")
    lease_id = sanitize_label(str(request["lease_id"]), "lease_id")
    task_id = sanitize_label(str(request["task_id"]), "task_id")
    owner = sanitize_label(str(request["owner"]), "owner")
    cleanup_owner = sanitize_label(str(request["cleanup_owner"]), "cleanup_owner")
    if request["project_id"] not in AUTHORIZED_PROJECTS:
        raise BrokerError("project is outside the epic allowlist")
    expected_region = AUTHORIZED_PROJECTS[request["project_id"]]
    if request["region"] != expected_region:
        raise BrokerError(
            f"region {request['region']} does not match authorized project region {expected_region}"
        )
    named_profiles = profiles.get("profiles", {})
    if request["profile"] not in named_profiles:
        raise BrokerError(f"unknown resource profile: {request['profile']}")
    profile = named_profiles[request["profile"]]
    if request["region"] not in profile["regions"]:
        raise BrokerError("resource profile is unavailable in the requested region")
    if request["mode"] not in {"normal", "preemptible"}:
        raise BrokerError("mode must be normal or preemptible")
    duration = Decimal(str(request["expected_duration_hours"]))
    ttl_hours = int(request["ttl_hours"])
    if duration <= 0 or duration > Decimal(str(profile["max_duration_hours"])):
        raise BrokerError("expected duration is outside profile policy")
    if ttl_hours < 1 or ttl_hours > int(profile["max_ttl_hours"]):
        raise BrokerError("TTL is outside profile policy")
    if duration > Decimal(ttl_hours):
        raise BrokerError("expected duration cannot exceed TTL")
    purpose = str(request["purpose"]).strip()
    if len(purpose) < 20:
        raise BrokerError("purpose must be at least 20 characters")
    artifact = request["artifact_storage"]
    if set(artifact) != {"enabled", "max_size_gib"}:
        raise BrokerError("artifact_storage must contain enabled and max_size_gib")
    if not isinstance(artifact["enabled"], bool):
        raise BrokerError("artifact_storage.enabled must be boolean")
    if int(artifact["max_size_gib"]) < 0 or int(artifact["max_size_gib"]) > 1024:
        raise BrokerError("artifact storage must be between 0 and 1024 GiB")
    health = request["health_proof"]
    if set(health) != {"marker", "timeout_seconds"}:
        raise BrokerError("health_proof must contain marker and timeout_seconds")
    if not re.fullmatch(r"[A-Z0-9_=-]{8,80}", str(health["marker"])):
        raise BrokerError("health marker has unsafe characters")
    if not 30 <= int(health["timeout_seconds"]) <= 1800:
        raise BrokerError("health timeout must be between 30 and 1800 seconds")
    experiment = request["experiment"]
    if profile["gpu_count"]:
        if not isinstance(experiment, dict):
            raise BrokerError("GPU leases require a frozen experiment specification")
        required_experiment = {
            "model_id",
            "input_sha256",
            "metric_contract_sha256",
            "metric_contract_path",
            "cleanup_plan",
        }
        if set(experiment) != required_experiment:
            raise BrokerError("GPU experiment gate is incomplete")
        for key in ("input_sha256", "metric_contract_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(experiment[key])):
                raise BrokerError(f"{key} must be a SHA-256 digest")
        if not all(str(experiment[key]).strip() for key in required_experiment):
            raise BrokerError("GPU experiment gate contains an empty field")
    elif experiment is not None:
        raise BrokerError("CPU leases must set experiment to null")
    local_disk = profile["local_nvme"]
    if local_disk["request"] and not local_disk["verified_supported"]:
        raise BrokerError("profile requests local NVMe without verified project/platform support")
    normalized = dict(request)
    normalized.update(
        {
            "lease_id": lease_id,
            "task_id": task_id,
            "owner": owner,
            "cleanup_owner": cleanup_owner,
            "expected_duration_hours": str(duration),
            "ttl_hours": ttl_hours,
        }
    )
    return normalized


def cost_estimate(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    rate = Decimal(str(profile["hourly_compute_usd"][request["mode"]]))
    disk_hourly = (
        Decimal(str(profile["boot_disk_gib"]))
        * Decimal(str(profile["network_ssd_usd_per_gib_month"]))
        / Decimal("730")
    )
    artifact_gib = Decimal(str(request["artifact_storage"]["max_size_gib"]))
    artifact_hourly = (
        artifact_gib * Decimal(str(profile["object_storage_usd_per_gib_month"])) / Decimal("730")
        if request["artifact_storage"]["enabled"]
        else Decimal("0")
    )
    duration = Decimal(request["expected_duration_hours"])
    ttl = Decimal(request["ttl_hours"])
    expected = (rate + disk_hourly + artifact_hourly) * duration
    ttl_ceiling = (rate + disk_hourly + artifact_hourly) * ttl
    return {
        "currency": "USD",
        "compute_usd_per_hour": decimal_string(rate),
        "boot_disk_usd_per_hour": decimal_string(disk_hourly),
        "artifact_storage_full_quota_usd_per_hour": decimal_string(artifact_hourly),
        "expected_duration_hours": str(duration),
        "expected_cost_usd": decimal_string(expected),
        "ttl_cost_ceiling_usd": decimal_string(ttl_ceiling),
        "price_observed_at": profile["price_observed_at"],
        "price_source": profile["price_source"],
        "assumptions": profile["cost_assumptions"],
    }


def resource_names(prefix: str, artifact_enabled: bool) -> list[dict[str, str]]:
    values = [
        {"kind": "network", "name": f"{prefix}-net"},
        {"kind": "subnet", "name": f"{prefix}-subnet"},
        {"kind": "security_group", "name": f"{prefix}-sg"},
        {"kind": "disk", "name": f"{prefix}-boot"},
        {"kind": "instance", "name": f"{prefix}-vm"},
    ]
    if artifact_enabled:
        values.append({"kind": "bucket", "name": f"{prefix}-artifacts"})
    return values


def build_lease(request: dict[str, Any], profiles: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    profile = profiles["profiles"][request["profile"]]
    request_hash = sha256_json(request)
    task_slug = request["task_id"][:18].rstrip("-._")
    prefix = f"{PROGRAM_PREFIX}-{task_slug}-{request_hash[:8]}"
    expires_at = now + dt.timedelta(hours=request["ttl_hours"])
    labels = {
        "program": PROGRAM,
        "broker": "resource-broker-v1",
        "lease": request["lease_id"],
        "task": request["task_id"],
        "owner": request["owner"],
        "expires": expires_at.strftime("%Y%m%dt%H%M%Sz").lower(),
    }
    for key, value in labels.items():
        sanitize_label(key, f"label key {key}")
        sanitize_label(value, f"label value {key}")
    return {
        "schema_version": SCHEMA_VERSION,
        "lease_id": request["lease_id"],
        "request_sha256": request_hash,
        "request": request,
        "prefix": prefix,
        "state": "PLANNED",
        "created_at": iso(now),
        "expires_at": iso(expires_at),
        "labels": labels,
        "profile_snapshot": profile,
        "cost_estimate": cost_estimate(request, profile),
        "planned_resources": resource_names(prefix, request["artifact_storage"]["enabled"]),
        "resources": [],
        "external_references": [],
        "health_proof": None,
        "isolation_proof": None,
        "events": [
            {
                "at": iso(now),
                "type": "PLAN_CREATED",
                "status": "PASS",
                "details": "immutable request hash, TTL, budget, ownership, and cleanup owner recorded",
            }
        ],
    }


def registry_summary(lease: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "lease_id": lease["lease_id"],
        "lease_file": str(path.resolve()),
        "task_id": lease["request"]["task_id"],
        "project_id": lease["request"]["project_id"],
        "region": lease["request"]["region"],
        "profile": lease["request"]["profile"],
        "prefix": lease["prefix"],
        "state": lease["state"],
        "expires_at": lease["expires_at"],
        "cleanup_owner": lease["request"]["cleanup_owner"],
        "estimated_ttl_cost_usd": lease["cost_estimate"]["ttl_cost_ceiling_usd"],
    }


def update_registry(registry_path: Path, lease_path: Path, lease: dict[str, Any]) -> None:
    lock_path = registry_path.with_suffix(registry_path.suffix + ".lock")
    with locked(lock_path):
        if registry_path.exists():
            registry = load_json(registry_path)
            if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
                raise BrokerError("unsupported registry schema")
        else:
            registry = {"schema_version": REGISTRY_SCHEMA_VERSION, "updated_at": None, "leases": []}
        summary = registry_summary(lease, lease_path)
        existing = {item["lease_id"]: item for item in registry["leases"]}
        registered = existing.get(lease["lease_id"])
        if registered and Path(registered["lease_file"]).resolve() != lease_path.resolve():
            raise BrokerError(
                f"lease ID {lease['lease_id']} is already registered at a different canonical path"
            )
        prefix_owner = next(
            (
                item
                for item in registry["leases"]
                if item["prefix"] == lease["prefix"]
                and item["lease_id"] != lease["lease_id"]
            ),
            None,
        )
        if prefix_owner:
            raise BrokerError(
                f"resource prefix collision with lease {prefix_owner['lease_id']}"
            )
        existing[lease["lease_id"]] = summary
        registry["leases"] = sorted(existing.values(), key=lambda item: item["lease_id"])
        registry["updated_at"] = iso(utc_now())
        atomic_json(registry_path, registry)


def save_lease(lease_path: Path, registry_path: Path, lease: dict[str, Any]) -> None:
    atomic_json(lease_path, lease)
    update_registry(registry_path, lease_path, lease)


def plan(request_path: Path, lease_path: Path, registry_path: Path, profiles_path: Path) -> dict[str, Any]:
    profiles = load_profiles(profiles_path)
    request = validate_request(load_json(request_path), profiles)
    if lease_path.exists():
        existing = load_json(lease_path)
        if existing.get("request_sha256") != sha256_json(request):
            raise BrokerError("lease ID collision: existing lease has a different request hash")
        update_registry(registry_path, lease_path, existing)
        return existing
    lease = build_lease(request, profiles, utc_now())
    save_lease(lease_path, registry_path, lease)
    return lease


def metadata_id(value: dict[str, Any], kind: str) -> str:
    resource_id = value.get("metadata", {}).get("id")
    if not isinstance(resource_id, str) or not resource_id:
        raise BrokerError(f"{kind} create response did not contain metadata.id")
    return resource_id


def project_region(project: dict[str, Any]) -> str | None:
    return project.get("status", {}).get("region") or project.get("spec", {}).get("region")


def run_preflight(cli: NebiusCLI, request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    whoami = cli.run(["iam", "whoami"])
    auth_parent = (
        whoami.get("service_account_profile", {}).get("info", {}).get("metadata", {}).get("parent_id")
        or whoami.get("user_account_profile", {}).get("info", {}).get("metadata", {}).get("parent_id")
    )
    if auth_parent not in AUTHORIZED_PROJECTS:
        raise BrokerError("authenticated identity is not rooted in an authorized epic project")
    project = cli.run(["iam", "project", "get", request["project_id"]])
    if project_region(project) != request["region"]:
        raise BrokerError("live project region differs from the lease request")
    platforms = cli.run(
        ["compute", "platform", "list", "--parent-id", request["project_id"], "--all"]
    )
    matching = [
        item
        for item in platforms.get("items", [])
        if item.get("metadata", {}).get("name") == profile["platform"]
    ]
    if len(matching) != 1:
        raise BrokerError("requested compute platform is not advertised in the project")
    presets = {item.get("name") for item in matching[0].get("spec", {}).get("presets", [])}
    if profile["preset"] not in presets:
        raise BrokerError("requested compute preset is not advertised in the project")
    quotas = cli.run(
        ["quotas", "quota-allowance", "list", "--parent-id", request["project_id"], "--all"]
    )
    relevant_quota_names = {
        "compute.instance.count",
        "compute.instance.preemptible.count",
        "compute.instance.non-gpu.vcpu",
        "compute.disk.count",
        "compute.disk.size.network-ssd",
        "storage.bucket.count",
        "vpc.network.count",
        "vpc.subnet.count",
    }
    quota_name = profile.get("gpu_quota_name")
    if quota_name:
        relevant_quota_names.add(quota_name)
    relevant_quotas = []
    for item in quotas.get("items", []):
        name = item.get("metadata", {}).get("name")
        if name in relevant_quota_names:
            relevant_quotas.append(
                {
                    "name": name,
                    "region": item.get("spec", {}).get("region"),
                    "usage": item.get("status", {}).get("usage"),
                    "unit": item.get("status", {}).get("unit"),
                    "usage_state": item.get("status", {}).get("usage_state"),
                    "allowance": item.get("spec", {}).get("allowance"),
                }
            )
    capacity = {
        "status": "UNAVAILABLE",
        "reason": None,
        "requested_mode": request["mode"],
        "matched": [],
        "eligible": [],
    }
    tenant_id = project.get("metadata", {}).get("parent_id")
    try:
        advice = cli.run(["capacity", "resource-advice", "list", "--parent-id", tenant_id, "--all"])
        capacity["status"] = "AVAILABLE"
        capacity["matched"] = []
        for item in advice.get("items", []):
            spec = item.get("spec", {})
            compute = spec.get("compute_instance", {})
            preset = compute.get("preset", {})
            if (
                spec.get("region") == request["region"]
                and compute.get("platform") == profile["platform"]
                and preset.get("name") == profile["preset"]
            ):
                capacity["matched"].append(item)
        mode_key = "on_demand" if request["mode"] == "normal" else "preemptible"
        for item in capacity["matched"]:
            mode_status = item.get("status", {}).get(mode_key, {})
            level = str(mode_status.get("availability_level", ""))
            available = mode_status.get("available")
            if (
                level
                and level != "AVAILABILITY_LEVEL_LIMIT_REACHED"
                and (available is None or int(available) >= 1)
            ):
                capacity["eligible"].append(item)
    except AuthenticationError:
        raise
    except BrokerError as exc:
        capacity["reason"] = str(exc)[:1000]
    if profile["gpu_count"] and capacity["status"] != "AVAILABLE":
        raise BrokerError("GPU lease blocked: capacity advice must succeed before creation")
    if profile["gpu_count"] and not capacity["matched"]:
        raise BrokerError(
            "GPU lease blocked: capacity advice has no exact region/platform/preset match"
        )
    if profile["gpu_count"] and not capacity["eligible"]:
        raise BrokerError(
            f"GPU lease blocked: exact {profile['platform']}/{profile['preset']} "
            f"has no eligible {request['mode']} capacity"
        )
    return {
        "checked_at": iso(utc_now()),
        "profile": cli.profile,
        "auth_identity_type": next(iter(whoami), "unknown"),
        "auth_parent_id": auth_parent,
        "tenant_id": tenant_id,
        "project_id": request["project_id"],
        "project_region": project_region(project),
        "project_state": project.get("status", {}).get("container_state"),
        "platform": profile["platform"],
        "preset": profile["preset"],
        "platform_check": "PASS",
        "quota_snapshot": relevant_quotas,
        "capacity_advice": capacity,
        "note": "Quota API exposed usage but no explicit allowance in this profile; create remains provider-enforced.",
    }


LIST_COMMANDS = {
    "network": ["vpc", "network", "list"],
    "subnet": ["vpc", "subnet", "list"],
    "security_group": ["vpc", "security-group", "list"],
    "disk": ["compute", "disk", "list"],
    "instance": ["compute", "instance", "list"],
    "bucket": ["storage", "bucket", "list"],
}


GET_COMMANDS = {
    "network": ["vpc", "network", "get"],
    "subnet": ["vpc", "subnet", "get"],
    "security_group": ["vpc", "security-group", "get"],
    "disk": ["compute", "disk", "get"],
    "instance": ["compute", "instance", "get"],
    "bucket": ["storage", "bucket", "get"],
    "allocation": ["vpc", "allocation", "get"],
    "pool": ["vpc", "pool", "get"],
    "route_table": ["vpc", "route-table", "get"],
    "security_rule": ["vpc", "security-rule", "get"],
}


DELETE_COMMANDS = {
    "instance": ["compute", "instance", "delete"],
    "disk": ["compute", "disk", "delete"],
    "bucket": ["storage", "bucket", "delete"],
    "security_group": ["vpc", "security-group", "delete"],
    "subnet": ["vpc", "subnet", "delete"],
    "network": ["vpc", "network", "delete"],
}


def list_program_resources(cli: NebiusCLI, project_id: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for kind, command in LIST_COMMANDS.items():
        response = cli.run([*command, "--parent-id", project_id, "--all"])
        for item in response.get("items", []):
            metadata = item.get("metadata", {})
            labels = metadata.get("labels", {}) or {}
            name = metadata.get("name", "")
            if labels.get("program") == PROGRAM or name.startswith(f"{PROGRAM_PREFIX}-"):
                found.append(
                    {
                        "kind": kind,
                        "id": metadata.get("id"),
                        "name": name,
                        "labels": labels,
                        "parent_id": metadata.get("parent_id"),
                    }
                )
    return found


def scan_project_resources(
    cli: NebiusCLI, project_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    found: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for kind, command in LIST_COMMANDS.items():
        try:
            response = cli.run(
                [*command, "--parent-id", project_id, "--all"], timeout=30
            )
            for item in response.get("items", []):
                metadata = item.get("metadata", {})
                labels = metadata.get("labels", {}) or {}
                name = metadata.get("name", "")
                if labels.get("program") == PROGRAM or name.startswith(f"{PROGRAM_PREFIX}-"):
                    found.append(
                        {
                            "kind": kind,
                            "id": metadata.get("id"),
                            "name": name,
                            "labels": labels,
                            "parent_id": metadata.get("parent_id"),
                        }
                    )
        except AuthenticationError:
            raise
        except BrokerError as exc:
            errors.append({"project_id": project_id, "kind": kind, "error": str(exc)[:1200]})
    return found, errors


def assert_no_collisions(
    cli: NebiusCLI, project_id: str, planned_resources: list[dict[str, str]]
) -> None:
    existing = list_program_resources(cli, project_id)
    names = {item["name"] for item in planned_resources}
    collisions = [item for item in existing if item["name"] in names]
    if collisions:
        raise BrokerError(f"resource-name collision detected before create: {collisions}")


def reconcile_unledgered_direct_resources(lease: dict[str, Any], cli: NebiusCLI) -> None:
    """Recover an exact resource created before an interrupted ledger append."""
    expected = {
        (item["kind"], item["name"]): item for item in lease.get("planned_resources", [])
    }
    ledger_by_name = {item["name"]: item for item in lease.get("resources", [])}
    known_ids = {item["id"] for item in lease.get("resources", [])}
    for item in list_program_resources(cli, lease["request"]["project_id"]):
        labels = item.get("labels", {}) or {}
        if labels.get("lease") != lease["lease_id"]:
            continue
        key = (item["kind"], item["name"])
        if key not in expected:
            raise BrokerError("foreign lease-labeled resource is outside the immutable plan")
        existing = ledger_by_name.get(item["name"])
        if existing and existing["id"] != item["id"]:
            raise BrokerError("foreign replacement detected for an immutable planned name")
        if item["id"] in known_ids:
            continue
        value = cli.run([*GET_COMMANDS[item["kind"]], item["id"]])
        metadata = value.get("metadata", {})
        if (
            metadata.get("name") != item["name"]
            or metadata.get("parent_id") != lease["request"]["project_id"]
            or (metadata.get("labels", {}) or {}).get("lease") != lease["lease_id"]
        ):
            raise BrokerError("interrupted-create recovery found a foreign resource identity")
        resource = add_resource(lease, item["kind"], item["name"], value)
        resource["created_at"] = metadata.get("created_at") or resource["created_at"]
        add_event(
            lease,
            "INTERRUPTED_CREATE_RECONCILED",
            "PASS",
            f"{item['kind']}:{item['id']} recovered by exact plan name and ownership labels",
        )
        known_ids.add(item["id"])
        ledger_by_name[item["name"]] = resource


def add_event(lease: dict[str, Any], event_type: str, status: str, details: str) -> None:
    lease["events"].append(
        {"at": iso(utc_now()), "type": event_type, "status": status, "details": details}
    )


def add_resource(
    lease: dict[str, Any], kind: str, name: str, response: dict[str, Any]
) -> dict[str, Any]:
    resource = {
        "kind": kind,
        "id": metadata_id(response, kind),
        "name": name,
        "project_id": lease["request"]["project_id"],
        "region": lease["request"]["region"],
        "created_at": iso(utc_now()),
        "deleted_at": None,
        "delete_verified_at": None,
    }
    lease["resources"].append(resource)
    add_event(lease, "RESOURCE_CREATED", "PASS", f"{kind}:{resource['id']}")
    return resource


def add_managed_resource(
    lease: dict[str, Any], kind: str, response: dict[str, Any], managed_by_resource_id: str
) -> dict[str, Any]:
    resource_id = metadata_id(response, kind)
    for existing in lease["resources"]:
        if existing["id"] == resource_id:
            return existing
    metadata = response.get("metadata", {})
    resource = {
        "kind": kind,
        "id": resource_id,
        "name": metadata.get("name") or f"provider-managed-{kind}",
        "project_id": lease["request"]["project_id"],
        "region": lease["request"]["region"],
        "created_at": metadata.get("created_at") or iso(utc_now()),
        "deleted_at": None,
        "delete_verified_at": None,
        "deletion_mode": "PROVIDER_CASCADE",
        "managed_by_resource_id": managed_by_resource_id,
    }
    lease["resources"].append(resource)
    add_event(
        lease,
        "MANAGED_RESOURCE_RECONCILED",
        "PASS",
        f"{kind}:{resource_id} managed_by:{managed_by_resource_id}",
    )
    return resource


def add_external_reference(
    lease: dict[str, Any], kind: str, response: dict[str, Any], association_owner_id: str
) -> None:
    metadata = response.get("metadata", {})
    resource_id = metadata_id(response, kind)
    lease["resources"] = [item for item in lease["resources"] if item["id"] != resource_id]
    if any(item["id"] == resource_id for item in lease.get("external_references", [])):
        return
    lease.setdefault("external_references", []).append(
        {
            "kind": kind,
            "id": resource_id,
            "name": metadata.get("name") or f"external-{kind}",
            "project_id": lease["request"]["project_id"],
            "region": lease["request"]["region"],
            "created_at": metadata.get("created_at"),
            "association_owner_id": association_owner_id,
            "desired_final_state": "PRESENT_UNCHANGED",
            "cleanup_verified_at": None,
            "cleanup_evidence": None,
        }
    )
    add_event(
        lease,
        "EXTERNAL_REFERENCE_RECONCILED",
        "WARN",
        f"{kind}:{resource_id} predated lease; only lease association may be removed",
    )


def reconcile_managed_children(lease: dict[str, Any], cli: NebiusCLI) -> None:
    live = {item["kind"]: item for item in lease["resources"] if not item["deleted_at"]}
    instance = live.get("instance")
    network = live.get("network")
    subnet = live.get("subnet")
    security_group = live.get("security_group")
    if instance:
        instance_value = cli.run(["compute", "instance", "get", instance["id"]])
        for interface in instance_value.get("status", {}).get("network_interfaces", []):
            for address_kind in ("ip_address", "public_ip_address"):
                allocation_id = interface.get(address_kind, {}).get("allocation_id")
                if allocation_id:
                    allocation = cli.run(["vpc", "allocation", "get", allocation_id])
                    add_managed_resource(lease, "allocation", allocation, instance["id"])
    if network:
        network_value = cli.run(["vpc", "network", "get", network["id"]])
        for family in ("ipv4_private_pools", "ipv4_public_pools"):
            for pool_ref in network_value.get("spec", {}).get(family, {}).get("pools", []):
                pool = cli.run(["vpc", "pool", "get", pool_ref["id"]])
                pool_created = pool.get("metadata", {}).get("created_at")
                if not pool_created or parse_utc(pool_created) < parse_utc(
                    lease["created_at"]
                ):
                    add_external_reference(lease, "pool", pool, network["id"])
                else:
                    add_managed_resource(lease, "pool", pool, network["id"])
        route_table_id = network_value.get("status", {}).get("default_route_table_id")
        if route_table_id:
            route_table = cli.run(["vpc", "route-table", "get", route_table_id])
            add_managed_resource(lease, "route_table", route_table, network["id"])
    if subnet:
        subnet_value = cli.run(["vpc", "subnet", "get", subnet["id"]])
        for family in ("ipv4_private_pools", "ipv4_public_pools"):
            for pool_ref in subnet_value.get("spec", {}).get(family, {}).get("pools", []):
                pool = cli.run(["vpc", "pool", "get", pool_ref["id"]])
                pool_created = pool.get("metadata", {}).get("created_at")
                if not pool_created or parse_utc(pool_created) < parse_utc(lease["created_at"]):
                    add_external_reference(lease, "pool", pool, subnet["id"])
                else:
                    add_managed_resource(lease, "pool", pool, subnet["id"])
    if security_group:
        rules = cli.run(
            ["vpc", "security-rule", "list", "--parent-id", security_group["id"], "--all"]
        )
        for rule in rules.get("items", []):
            labels = rule.get("metadata", {}).get("labels", {}) or {}
            if labels.get("lease") == lease["lease_id"]:
                add_managed_resource(lease, "security_rule", rule, security_group["id"])


def _security_rule_proof(rule: dict[str, Any]) -> dict[str, Any]:
    metadata = rule.get("metadata", {})
    spec = rule.get("spec", {})
    ingress = spec.get("ingress")
    egress = spec.get("egress")
    if ingress:
        direction = "ingress"
        cidrs = ingress.get("source_cidrs", [])
        ports = ingress.get("destination_ports", [])
    elif egress:
        direction = "egress"
        cidrs = egress.get("destination_cidrs", [])
        ports = egress.get("destination_ports", [])
    else:
        direction = "unknown"
        cidrs = []
        ports = []
    return {
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "labels": metadata.get("labels", {}) or {},
        "access": str(spec.get("access", "")).lower(),
        "protocol": str(spec.get("protocol", "")).lower(),
        "type": str(spec.get("type", "")).lower(),
        "priority": spec.get("priority"),
        "direction": direction,
        "ports": [int(value) for value in ports],
        "cidr_sha256": [hashlib.sha256(str(value).encode()).hexdigest() for value in cidrs],
        "unrestricted_destination": direction == "egress" and cidrs == ["0.0.0.0/0"],
    }


def capture_isolation_proof(lease: dict[str, Any], cli: NebiusCLI) -> dict[str, Any]:
    live = {item["kind"]: item for item in lease["resources"] if not item["deleted_at"]}
    instance = cli.run(["compute", "instance", "get", live["instance"]["id"]])
    network = cli.run(["vpc", "network", "get", live["network"]["id"]])
    subnet = cli.run(["vpc", "subnet", "get", live["subnet"]["id"]])
    disk = cli.run(["compute", "disk", "get", live["disk"]["id"]])
    bucket = (
        cli.run(["storage", "bucket", "get", live["bucket"]["id"]])
        if "bucket" in live
        else None
    )
    rules = cli.run(
        ["vpc", "security-rule", "list", "--parent-id", live["security_group"]["id"], "--all"]
    )
    interfaces = instance.get("status", {}).get("network_interfaces", [])
    public_allocations = [
        interface.get("public_ip_address", {}).get("allocation_id")
        for interface in interfaces
        if interface.get("public_ip_address")
    ]
    return {
        "verified_at": iso(utc_now()),
        "project_id": lease["request"]["project_id"],
        "region": lease["request"]["region"],
        "instance": {
            "id": live["instance"]["id"],
            "state": instance_state(instance),
            "platform": instance.get("spec", {}).get("resources", {}).get("platform"),
            "preset": instance.get("spec", {}).get("resources", {}).get("preset"),
            "preemptible": instance.get("spec", {}).get("preemptible"),
            "service_account_id": instance.get("spec", {}).get("service_account_id"),
            "public_ip_allocation_ids": public_allocations,
            "local_disks": instance.get("spec", {}).get("local_disks"),
        },
        "network": {
            "id": live["network"]["id"],
            "private_pool_ids": [
                item["id"]
                for item in network.get("spec", {}).get("ipv4_private_pools", {}).get("pools", [])
            ],
            "public_pool_ids": [
                item["id"]
                for item in network.get("spec", {}).get("ipv4_public_pools", {}).get("pools", [])
            ],
            "external_reference_count": len(lease.get("external_references", [])),
        },
        "subnet": {
            "id": live["subnet"]["id"],
            "private_pool_ids": [
                item["id"]
                for item in subnet.get("spec", {}).get("ipv4_private_pools", {}).get("pools", [])
            ],
            "public_pool_ids": [
                item["id"]
                for item in subnet.get("spec", {}).get("ipv4_public_pools", {}).get("pools", [])
            ],
        },
        "security_group": {
            "id": live["security_group"]["id"],
            "rule_count": len(rules.get("items", [])),
            "rules": [_security_rule_proof(item) for item in rules.get("items", [])],
        },
        "boot_disk": {
            "id": live["disk"]["id"],
            "type": disk.get("spec", {}).get("type"),
            "size_bytes": disk.get("status", {}).get("size_bytes"),
            "source_image_id": disk.get("status", {}).get("source_image_id"),
        },
        "artifact_bucket": (
            {
                "id": live["bucket"]["id"],
                "state": bucket.get("status", {}).get("state"),
                "max_size_bytes": bucket.get("spec", {}).get("max_size_bytes"),
                "storage_class": bucket.get("spec", {}).get("default_storage_class"),
                "object_audit_logging": bucket.get("spec", {}).get("object_audit_logging"),
            }
            if bucket
            else None
        ),
    }


def validate_isolation_proof(lease: dict[str, Any], proof: dict[str, Any]) -> None:
    request = lease["request"]
    profile = lease["profile_snapshot"]
    instance = proof["instance"]
    network = proof["network"]
    subnet = proof["subnet"]
    security_group = proof["security_group"]
    disk = proof["boot_disk"]
    bucket = proof["artifact_bucket"]
    failures = []
    if instance["state"] != "RUNNING":
        failures.append("instance is not RUNNING")
    if instance["platform"] != profile["platform"] or instance["preset"] != profile["preset"]:
        failures.append("instance platform/preset differs from the frozen profile")
    if request["mode"] == "preemptible" and not instance["preemptible"]:
        failures.append("preemptible lease created a normal instance")
    if request["mode"] == "normal" and instance["preemptible"]:
        failures.append("normal lease created a preemptible instance")
    if instance["service_account_id"]:
        failures.append("instance has an attached service account")
    live_authorization = lease.get("live_authorization")
    if live_authorization:
        if len(instance["public_ip_allocation_ids"]) != 1:
            failures.append("authorized scout must have exactly one public IP allocation")
    elif instance["public_ip_allocation_ids"]:
        failures.append("instance has a public IP allocation")
    if not profile["local_nvme"]["request"] and instance["local_disks"]:
        failures.append("instance has an unrequested local disk")
    if network["public_pool_ids"]:
        failures.append("fresh network has a public-pool association")
    if network["external_reference_count"]:
        failures.append("fresh resources reference a pre-existing project resource")
    if not network["private_pool_ids"]:
        failures.append("fresh network has no private address pool")
    if live_authorization:
        if len(subnet["public_pool_ids"]) != 1:
            failures.append("authorized scout subnet must own exactly one public /32 pool")
        rules = security_group["rules"]
        expected_names = {f"{lease['prefix']}-ingress-8080"} | {
            f"{lease['prefix']}-egress-{index}" for index in range(1, 6)
        }
        if security_group["rule_count"] != 6 or {item["name"] for item in rules} != expected_names:
            failures.append("authorized security-rule identity/count differs")
        ingress = [item for item in rules if item["direction"] == "ingress"]
        egress = [item for item in rules if item["direction"] == "egress"]
        expected_source_hash = live_authorization["recorder_cidr_sha256"]
        if len(ingress) != 1 or not (
            ingress[0]["access"] == "allow"
            and ingress[0]["protocol"] == "tcp"
            and ingress[0]["type"] == "stateful"
            and ingress[0]["ports"] == [8080]
            and ingress[0]["cidr_sha256"] == [expected_source_hash]
        ):
            failures.append("authenticated recorder-only TCP/8080 ingress differs")
        expected_egress = {
            ("tcp", (443,)),
            ("tcp", (80,)),
            ("udp", (53,)),
            ("tcp", (53,)),
            ("udp", (123,)),
        }
        observed_egress = {
            (item["protocol"], tuple(item["ports"]))
            for item in egress
            if item["access"] == "allow"
            and item["type"] == "stateful"
            and item["unrestricted_destination"]
        }
        if len(egress) != 5 or observed_egress != expected_egress:
            failures.append("authorized least-port egress differs")
        if any(22 in item["ports"] or 8000 in item["ports"] for item in ingress):
            failures.append("SSH or direct inference-container ingress is exposed")
    else:
        if subnet["public_pool_ids"]:
            failures.append("air-gapped subnet has a public-pool association")
        if security_group["rule_count"] != 0:
            failures.append("deny-all security group has rules")
    if disk["type"] != "NETWORK_SSD":
        failures.append("boot disk is not Network SSD")
    expected_disk_size = int(profile["boot_disk_gib"]) * 1024**3
    if int(disk["size_bytes"] or 0) != expected_disk_size:
        failures.append("boot disk size differs from the frozen profile")
    if request["artifact_storage"]["enabled"]:
        expected_bucket_size = int(request["artifact_storage"]["max_size_gib"]) * 1024**3
        if not bucket:
            failures.append("artifact bucket is missing")
        elif (
            bucket["state"] != "ACTIVE"
            or bucket["storage_class"] != "STANDARD"
            or bucket["object_audit_logging"] != "ALL"
            or int(bucket["max_size_bytes"] or 0) != expected_bucket_size
        ):
            failures.append("artifact bucket differs from the frozen private profile")
    elif bucket is not None:
        failures.append("artifact bucket exists although storage was disabled")
    if failures:
        raise BrokerError("isolation proof failed: " + "; ".join(failures))


def resource_payload(name: str, project_id: str, labels: dict[str, str], spec: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {"name": name, "parent_id": project_id, "labels": labels}, "spec": spec}


def authorized_cloud_init(lease: dict[str, Any], context: dict[str, Any]) -> str:
    files = []
    for artifact in context["authorization"]["bootstrap_artifacts"]:
        source = (FASTSTART_ROOT / artifact["path"]).resolve()
        files.append(
            {
                "path": artifact["target"],
                "permissions": "0755" if artifact["target"].endswith(".sh") else "0644",
                "content": base64.b64encode(source.read_bytes()).decode(),
            }
        )
    files.append(
        {
            "path": "/run/catswitch/bearer-token",
            "permissions": "0600",
            "content": base64.b64encode(context["_bearer_token"].encode()).decode(),
        }
    )
    lines = ["#cloud-config", "write_files:"]
    for item in files:
        lines.extend(
            [
                f"  - path: {item['path']}",
                f"    permissions: '{item['permissions']}'",
                "    encoding: b64",
                f"    content: {item['content']}",
            ]
        )
    lines.extend(
        [
            "runcmd:",
            "  - [bash, /opt/catswitch/bootstrap_internal_qwen.sh]",
            (
                "final_message: 'catalog-switch Qwen bootstrap completed; "
                f"lease={lease['lease_id']}'"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def security_rule_payload(
    name: str,
    security_group_id: str,
    labels: dict[str, str],
    spec: dict[str, Any],
) -> dict[str, Any]:
    return {
        "metadata": {"name": name, "parent_id": security_group_id, "labels": labels},
        "spec": spec,
    }


def provision(
    lease_path: Path,
    registry_path: Path,
    cli: NebiusCLI,
    *,
    live_authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lease = load_json(lease_path)
    if lease.get("schema_version") != SCHEMA_VERSION:
        raise BrokerError("unsupported lease schema")
    if lease["state"] == "ACTIVE":
        return lease
    if lease["state"] != "PLANNED" or lease["resources"]:
        raise BrokerError("provision requires a clean PLANNED lease")
    if utc_now() >= parse_utc(lease["expires_at"]):
        raise BrokerError("cannot provision an expired lease")
    if live_authorization is not None:
        public_authorization = live_authorization.get("public", {})
        if (
            public_authorization.get("authorization_id") != QWEN_SCOUT_AUTHORIZATION_ID
            or public_authorization.get("state") != "PRE_CREATION_REVIEW"
            or public_authorization.get("independent_clearance", {}).get("decision") != "CLEARED"
            or "_recorder_cidr" not in live_authorization
            or "_bearer_token" not in live_authorization
        ):
            raise BrokerError("live bootstrap authorization has not passed independent review")
        lease["live_authorization"] = public_authorization
        add_event(
            lease,
            "LIVE_AUTHORIZATION",
            "PASS",
            f"{QWEN_SCOUT_AUTHORIZATION_ID}; recorder source and bearer retained as hashes only",
        )
    request = lease["request"]
    profile = lease["profile_snapshot"]
    lease["preflight"] = run_preflight(cli, request, profile)
    add_event(lease, "PREFLIGHT", "PASS", "auth, project, region, platform, preset, quotas checked")
    assert_no_collisions(cli, request["project_id"], lease["planned_resources"])
    add_event(lease, "COLLISION_SCAN", "PASS", "no exact planned names exist")
    lease["state"] = "CREATING"
    save_lease(lease_path, registry_path, lease)
    names = {item["kind"]: item["name"] for item in lease["planned_resources"]}
    labels = lease["labels"]
    project_id = request["project_id"]
    try:
        network_response = cli.run(
            ["vpc", "network", "create"],
            payload=resource_payload(
                names["network"],
                project_id,
                labels,
                {"ipv4_public_pools": {"pools": []}},
            ),
            timeout=180,
        )
        network = add_resource(lease, "network", names["network"], network_response)
        save_lease(lease_path, registry_path, lease)

        subnet_spec: dict[str, Any] = {
            "network_id": network["id"],
            "ipv4_private_pools": {"use_network_pools": True},
            "ipv4_public_pools": {"use_network_pools": False},
        }
        if live_authorization is not None:
            subnet_spec["ipv4_public_pools"] = {
                "use_network_pools": False,
                "pools": [{"cidrs": [{"cidr": "/32"}]}],
            }
        subnet_response = cli.run(
            ["vpc", "subnet", "create"],
            payload=resource_payload(
                names["subnet"],
                project_id,
                labels,
                subnet_spec,
            ),
            timeout=180,
        )
        subnet = add_resource(lease, "subnet", names["subnet"], subnet_response)
        save_lease(lease_path, registry_path, lease)
        reconcile_managed_children(lease, cli)
        save_lease(lease_path, registry_path, lease)

        sg_response = cli.run(
            ["vpc", "security-group", "create"],
            payload=resource_payload(
                names["security_group"], project_id, labels, {"network_id": network["id"]}
            ),
            timeout=180,
        )
        security_group = add_resource(
            lease, "security_group", names["security_group"], sg_response
        )
        save_lease(lease_path, registry_path, lease)

        if live_authorization is not None:
            ingress_name = f"{lease['prefix']}-ingress-8080"
            ingress_response = cli.run(
                ["vpc", "security-rule", "create"],
                payload=security_rule_payload(
                    ingress_name,
                    security_group["id"],
                    labels,
                    {
                        "access": "allow",
                        "protocol": "tcp",
                        "type": "stateful",
                        "priority": 100,
                        "ingress": {
                            "source_cidrs": [live_authorization["_recorder_cidr"]],
                            "destination_ports": [8080],
                        },
                    },
                ),
                timeout=180,
            )
            add_managed_resource(
                lease, "security_rule", ingress_response, security_group["id"]
            )
            save_lease(lease_path, registry_path, lease)
            for index, rule in enumerate(
                live_authorization["authorization"]["network"]["egress"], 1
            ):
                egress_name = f"{lease['prefix']}-egress-{index}"
                response = cli.run(
                    ["vpc", "security-rule", "create"],
                    payload=security_rule_payload(
                        egress_name,
                        security_group["id"],
                        labels,
                        {
                            "access": "allow",
                            "protocol": rule["protocol"].lower(),
                            "type": "stateful",
                            "priority": 100 + index,
                            "egress": {
                                "destination_cidrs": rule["destination_cidrs"],
                                "destination_ports": rule["ports"],
                            },
                        },
                    ),
                    timeout=180,
                )
                add_managed_resource(
                    lease, "security_rule", response, security_group["id"]
                )
                save_lease(lease_path, registry_path, lease)
            reconcile_managed_children(lease, cli)
            save_lease(lease_path, registry_path, lease)

        if request["artifact_storage"]["enabled"]:
            bucket_response = cli.run(
                ["storage", "bucket", "create"],
                payload=resource_payload(
                    names["bucket"],
                    project_id,
                    labels,
                    {
                        "default_storage_class": "STANDARD",
                        "force_storage_class": True,
                        "max_size_bytes": int(request["artifact_storage"]["max_size_gib"])
                        * 1024**3,
                        "object_audit_logging": "ALL",
                        "versioning_policy": "DISABLED",
                    },
                ),
                timeout=180,
            )
            add_resource(lease, "bucket", names["bucket"], bucket_response)
            save_lease(lease_path, registry_path, lease)

        disk_response = cli.run(
            ["compute", "disk", "create"],
            payload=resource_payload(
                names["disk"],
                project_id,
                labels,
                {
                    "block_size_bytes": 4096,
                    "forbid_deletion": False,
                    "size_bytes": int(profile["boot_disk_gib"]) * 1024**3,
                    "source_image_family": {"image_family": profile["image_family"]},
                    "type": "NETWORK_SSD",
                },
            ),
            timeout=600,
        )
        disk = add_resource(lease, "disk", names["disk"], disk_response)
        save_lease(lease_path, registry_path, lease)

        marker = request["health_proof"]["marker"]
        cloud_init = (
            authorized_cloud_init(lease, live_authorization)
            if live_authorization is not None
            else "\n".join(
                [
                    "#cloud-config",
                    "write_files:",
                    "  - path: /var/lib/catalog-switch-lease",
                    "    permissions: '0444'",
                    f"    content: '{lease['lease_id']}'",
                    "runcmd:",
                    f"  - [sh, -c, 'echo {marker} lease={lease['lease_id']} | tee /dev/console']",
                    f"final_message: '{marker} lease={lease['lease_id']}'",
                    "",
                ]
            )
        )
        instance_spec: dict[str, Any] = {
            "stopped": False,
            "cloud_init_user_data": cloud_init,
            "hostname": names["instance"][:63],
            "resources": {"platform": profile["platform"], "preset": profile["preset"]},
            "boot_disk": {"attach_mode": "READ_WRITE", "existing_disk": {"id": disk["id"]}},
            "network_interfaces": [
                {
                    "name": "eth0",
                    "subnet_id": subnet["id"],
                    "ip_address": {},
                    "security_groups": [{"id": security_group["id"]}],
                    **({"public_ip_address": {}} if live_authorization is not None else {}),
                }
            ],
            "recovery_policy": "FAIL" if request["mode"] == "preemptible" else "RECOVER",
            "reservation_policy": {"policy": "FORBID"},
        }
        if request["mode"] == "preemptible":
            instance_spec["preemptible"] = {"on_preemption": "STOP", "priority": 3}
        if profile["local_nvme"]["request"]:
            instance_spec["local_disks"] = {"passthrough_group": {"requested": True}}
        instance_response = cli.run(
            ["compute", "instance", "create"],
            payload=resource_payload(names["instance"], project_id, labels, instance_spec),
            timeout=900,
        )
        instance = add_resource(lease, "instance", names["instance"], instance_response)
        save_lease(lease_path, registry_path, lease)
        return verify_health_lease(lease_path, registry_path, cli, instance["id"])
    except Exception as exc:
        lease = load_json(lease_path)
        lease["state"] = "FAILED"
        add_event(lease, "PROVISION_FAILED", "FAIL", str(exc)[:1500])
        save_lease(lease_path, registry_path, lease)
        raise


def instance_state(instance: dict[str, Any]) -> str:
    status = instance.get("status", {})
    for key in ("state", "status", "power_state"):
        value = status.get(key)
        if value:
            return str(value).upper()
    return "UNKNOWN"


def prove_health(
    lease_path: Path, registry_path: Path, cli: NebiusCLI, instance_id: str
) -> None:
    lease = load_json(lease_path)
    deadline = time.monotonic() + int(lease["request"]["health_proof"]["timeout_seconds"])
    marker = lease["request"]["health_proof"]["marker"]
    expected_marker = f"{marker} lease={lease['lease_id']}"
    last_state = "UNKNOWN"
    last_logs = ""
    while time.monotonic() < deadline:
        instance = cli.run(["compute", "instance", "get", instance_id])
        last_state = instance_state(instance)
        try:
            last_logs = cli.run(
                [
                    "compute",
                    "instance",
                    "logs",
                    instance_id,
                    "--project-id",
                    lease["request"]["project_id"],
                    "--since",
                    "30m",
                    "--limit",
                    "500",
                ],
                json_output=False,
                timeout=45,
            )
        except BrokerError:
            last_logs = ""
        if last_state == "RUNNING" and expected_marker in last_logs:
            lease["health_proof"] = {
                "verified_at": iso(utc_now()),
                "instance_id": instance_id,
                "instance_state": last_state,
                "serial_log_marker": expected_marker,
                "serial_log_marker_observed": True,
            }
            add_event(lease, "HEALTH_PROOF", "PASS", "RUNNING plus serial-log marker")
            save_lease(lease_path, registry_path, lease)
            return
        time.sleep(10)
    raise BrokerError(
        "health proof timed out; "
        f"instance_state={last_state}, marker_observed={expected_marker in last_logs}"
    )


def verify_health_lease(
    lease_path: Path,
    registry_path: Path,
    cli: NebiusCLI,
    instance_id: str | None = None,
) -> dict[str, Any]:
    lease = load_json(lease_path)
    if lease["state"] == "ACTIVE" and lease.get("health_proof"):
        reconcile_managed_children(lease, cli)
        lease["isolation_proof"] = capture_isolation_proof(lease, cli)
        validate_isolation_proof(lease, lease["isolation_proof"])
        save_lease(lease_path, registry_path, lease)
        return lease
    if lease["state"] not in {"CREATING", "FAILED"}:
        raise BrokerError("health resume requires a CREATING or FAILED lease")
    live_instances = [
        item
        for item in lease.get("resources", [])
        if item["kind"] == "instance" and not item["deleted_at"]
    ]
    if instance_id is None:
        if len(live_instances) != 1:
            raise BrokerError("health resume requires exactly one live ledgered instance")
        instance_id = live_instances[0]["id"]
    elif instance_id not in {item["id"] for item in live_instances}:
        raise BrokerError("health instance ID is not a live resource in this lease")
    prove_health(lease_path, registry_path, cli, instance_id)
    lease = load_json(lease_path)
    reconcile_managed_children(lease, cli)
    lease["isolation_proof"] = capture_isolation_proof(lease, cli)
    validate_isolation_proof(lease, lease["isolation_proof"])
    lease["state"] = "ACTIVE"
    add_event(lease, "LEASE_ACTIVE", "PASS", "VM running and newest serial-log marker observed")
    save_lease(lease_path, registry_path, lease)
    return lease


def delete_args(kind: str, resource_id: str) -> list[str]:
    args = [*DELETE_COMMANDS[kind], resource_id]
    if kind == "bucket":
        args.extend(["--ttl", "0s"])
    return args


CLEANUP_PRIORITY = {
    "instance": 100,
    "allocation": 90,
    "disk": 80,
    "bucket": 70,
    "security_group": 60,
    "security_rule": 55,
    "subnet": 50,
    "network": 40,
    "route_table": 30,
    "pool": 30,
}


def wait_absent(cli: NebiusCLI, kind: str, resource_id: str, timeout_seconds: int = 180) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        value = cli.run(
            [*GET_COMMANDS[kind], resource_id], allow_not_found=True, timeout=30
        )
        if value is None:
            return True
        time.sleep(5)
    return False


def verify_direct_resource_identity(
    lease: dict[str, Any], resource: dict[str, Any], value: dict[str, Any]
) -> None:
    metadata = value.get("metadata", {})
    labels = metadata.get("labels", {}) or {}
    failures = []
    if metadata.get("id") != resource["id"]:
        failures.append("ID")
    if metadata.get("name") != resource["name"]:
        failures.append("name")
    if metadata.get("parent_id") != resource["project_id"]:
        failures.append("project parent")
    expected_labels = {
        "program": PROGRAM,
        "lease": lease["lease_id"],
        "task": lease["request"]["task_id"],
    }
    if any(labels.get(key) != expected for key, expected in expected_labels.items()):
        failures.append("ownership labels")
    if failures:
        raise BrokerError(
            "foreign replacement detected for exact resource; refusing delete: "
            + ", ".join(failures)
        )


def verify_external_references(lease: dict[str, Any], cli: NebiusCLI) -> list[str]:
    failures = []
    for reference in lease.get("external_references", []):
        try:
            value = cli.run([*GET_COMMANDS[reference["kind"]], reference["id"]])
            networks = value.get("status", {}).get("assignment", {}).get("networks", [])
            owner_id = reference["association_owner_id"]
            if owner_id in networks:
                raise BrokerError(f"lease association {owner_id} is still present")
            reference["cleanup_verified_at"] = iso(utc_now())
            reference["cleanup_evidence"] = (
                f"external resource remained present; lease association {owner_id} absent"
            )
            add_event(
                lease,
                "EXTERNAL_REFERENCE_RESTORED",
                "PASS",
                f"{reference['kind']}:{reference['id']} no longer references {owner_id}",
            )
        except Exception as exc:
            failures.append(f"external {reference['kind']}:{reference['id']}: {exc}")
    return failures


def cleanup(
    lease_path: Path,
    registry_path: Path,
    cli: NebiusCLI,
    *,
    execute: bool,
) -> dict[str, Any]:
    lease = load_json(lease_path)
    if lease.get("schema_version") != SCHEMA_VERSION:
        raise BrokerError("unsupported lease schema")
    if lease.get("state") != "RELEASED":
        reconcile_unledgered_direct_resources(lease, cli)
        reconcile_managed_children(lease, cli)
        save_lease(lease_path, registry_path, lease)
    pending = sorted(
        [resource for resource in lease["resources"] if not resource["deleted_at"]],
        key=lambda resource: CLEANUP_PRIORITY.get(resource["kind"], 0),
        reverse=True,
    )
    commands = [
        {
            "kind": resource["kind"],
            "id": resource["id"],
            "command": (
                f"VERIFY ABSENT after provider cascade from {resource['managed_by_resource_id']}"
                if resource.get("deletion_mode") == "PROVIDER_CASCADE"
                else " ".join(
                    [
                        NEBIUS,
                        *delete_args(resource["kind"], resource["id"]),
                        "--profile",
                        cli.profile,
                    ]
                )
            ),
        }
        for resource in pending
    ]
    if not execute:
        return {"mode": "DRY_RUN", "lease_id": lease["lease_id"], "delete_plan": commands}
    if lease["state"] == "RELEASED" and not pending:
        return lease
    lease["state"] = "CLEANING"
    add_event(lease, "CLEANUP_STARTED", "PASS", f"{len(pending)} exact IDs")
    save_lease(lease_path, registry_path, lease)
    failures = []
    for resource in pending:
        try:
            if resource.get("deletion_mode") != "PROVIDER_CASCADE":
                current = cli.run(
                    [*GET_COMMANDS[resource["kind"]], resource["id"]],
                    allow_not_found=True,
                    timeout=30,
                )
                if current is not None:
                    verify_direct_resource_identity(lease, resource, current)
                    cli.run(
                        delete_args(resource["kind"], resource["id"]),
                        json_output=False,
                        timeout=600,
                    )
            if not wait_absent(cli, resource["kind"], resource["id"], timeout_seconds=300):
                raise BrokerError("resource still present after delete")
            resource["deleted_at"] = iso(utc_now())
            resource["delete_verified_at"] = resource["deleted_at"]
            add_event(
                lease,
                "RESOURCE_DELETED",
                "PASS",
                f"{resource['kind']}:{resource['id']} NotFound verified",
            )
            save_lease(lease_path, registry_path, lease)
        except Exception as exc:
            failures.append(f"{resource['kind']}:{resource['id']}: {exc}")
            add_event(lease, "RESOURCE_DELETE_FAILED", "FAIL", failures[-1][:1500])
            save_lease(lease_path, registry_path, lease)
    failures.extend(verify_external_references(lease, cli))
    if failures:
        lease["state"] = "CLEANUP_FAILED"
        save_lease(lease_path, registry_path, lease)
        raise BrokerError("cleanup incomplete: " + "; ".join(failures))
    lease["state"] = "RELEASED"
    lease["released_at"] = iso(utc_now())
    add_event(lease, "LEASE_RELEASED", "PASS", "all exact resource IDs verified absent")
    save_lease(lease_path, registry_path, lease)
    return lease


def scan(registry_path: Path, cli: NebiusCLI | None, cloud: bool) -> dict[str, Any]:
    registry = load_json(registry_path)
    now = utc_now()
    leases = []
    known_ids: set[str] = set()
    for summary in registry.get("leases", []):
        lease_path = Path(summary["lease_file"])
        lease = load_json(lease_path)
        known_ids.update(resource["id"] for resource in lease.get("resources", []))
        expired = parse_utc(lease["expires_at"]) <= now and lease["state"] != "RELEASED"
        leases.append(
            {
                "lease_id": lease["lease_id"],
                "state": lease["state"],
                "expires_at": lease["expires_at"],
                "expired": expired,
                "cleanup_owner": lease["request"]["cleanup_owner"],
                "resource_ids": [
                    item["id"] for item in lease.get("resources", []) if not item["deleted_at"]
                ],
            }
        )
    cloud_resources: list[dict[str, Any]] = []
    cloud_scan_errors: list[dict[str, str]] = []
    if cloud:
        if cli is None:
            raise BrokerError("cloud scan requires a Nebius CLI profile")
        for project_id in AUTHORIZED_PROJECTS:
            resources, errors = scan_project_resources(cli, project_id)
            cloud_scan_errors.extend(errors)
            for resource in resources:
                resource["registered"] = resource.get("id") in known_ids
                resource["disposition"] = (
                    "LEDGER_MANAGED" if resource["registered"] else "MANUAL_REVIEW"
                )
                cloud_resources.append(resource)
    return {
        "schema_version": "catalog-switch-orphan-scan/v1",
        "scanned_at": iso(now),
        "leases": leases,
        "expired_lease_count": sum(item["expired"] for item in leases),
        "cloud_scan": cloud,
        "cloud_scan_complete": cloud and not cloud_scan_errors,
        "cloud_scan_errors": cloud_scan_errors,
        "cloud_resources": cloud_resources,
        "unregistered_cloud_resource_count": sum(
            not item["registered"] for item in cloud_resources
        ),
        "policy": "unregistered resources are reported for manual review and never auto-deleted",
    }


def supervisor_ledger(registry_path: Path) -> dict[str, Any]:
    registry = load_json(registry_path)
    exported_leases = []
    exported_resources = []
    for summary in registry.get("leases", []):
        lease_path = Path(summary["lease_file"])
        lease = load_json(lease_path)
        exported_leases.append(
            {
                "lease_id": lease["lease_id"],
                "canonical_lease": str(lease_path.resolve()),
                "state": lease["state"],
                "project": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "owner_task": lease["request"]["task_id"],
                "purpose": lease["request"]["purpose"],
                "created_at": lease["created_at"],
                "expires_at": lease["expires_at"],
                "ttl_hours": lease["request"]["ttl_hours"],
                "cleanup_owner": lease["request"]["cleanup_owner"],
                "estimated_cost_usd": lease["cost_estimate"]["expected_cost_usd"],
                "ttl_cost_ceiling_usd": lease["cost_estimate"]["ttl_cost_ceiling_usd"],
                "desired_final_state": "ABSENT",
            }
        )
        actual_names = set()
        for resource in lease.get("resources", []):
            actual_names.add(resource["name"])
            exported_resources.append(
                {
                    "lease_id": lease["lease_id"],
                    "project": lease["request"]["project_id"],
                    "region": lease["request"]["region"],
                    "resource_type": resource["kind"],
                    "resource_name": resource["name"],
                    "resource_id": resource.get("id"),
                    "owner_task": lease["request"]["task_id"],
                    "purpose": lease["request"]["purpose"],
                    "created_at": resource.get("created_at"),
                    "expires_at": lease["expires_at"],
                    "desired_final_state": "ABSENT",
                    "cleanup_owner": lease["request"]["cleanup_owner"],
                    "cleanup_state": (
                        "ABSENCE_VERIFIED"
                        if resource.get("delete_verified_at")
                        else "NOT_CREATED"
                        if not resource.get("id")
                        else "PENDING"
                    ),
                    "deleted_at": resource.get("deleted_at"),
                    "absence_verified_at": resource.get("delete_verified_at"),
                }
            )
        for planned in lease["planned_resources"]:
            if planned["name"] in actual_names:
                continue
            exported_resources.append(
                {
                    "lease_id": lease["lease_id"],
                    "project": lease["request"]["project_id"],
                    "region": lease["request"]["region"],
                    "resource_type": planned["kind"],
                    "resource_name": planned["name"],
                    "resource_id": None,
                    "owner_task": lease["request"]["task_id"],
                    "purpose": lease["request"]["purpose"],
                    "created_at": None,
                    "expires_at": lease["expires_at"],
                    "desired_final_state": "ABSENT",
                    "cleanup_owner": lease["request"]["cleanup_owner"],
                    "cleanup_state": "NOT_CREATED",
                    "deleted_at": None,
                    "absence_verified_at": None,
                }
            )
        for reference in lease.get("external_references", []):
            exported_resources.append(
                {
                    "lease_id": lease["lease_id"],
                    "project": reference["project_id"],
                    "region": reference["region"],
                    "resource_type": f"external_{reference['kind']}",
                    "resource_name": reference["name"],
                    "resource_id": reference["id"],
                    "owner_task": lease["request"]["task_id"],
                    "purpose": "Provider-selected external reference; no workload allocation permitted.",
                    "created_at": reference["created_at"],
                    "expires_at": lease["expires_at"],
                    "desired_final_state": "PRESENT_UNCHANGED",
                    "cleanup_owner": lease["request"]["cleanup_owner"],
                    "cleanup_state": (
                        "ASSOCIATION_REMOVAL_VERIFIED"
                        if reference.get("cleanup_verified_at")
                        else "ASSOCIATION_REMOVAL_PENDING"
                    ),
                    "deleted_at": None,
                    "absence_verified_at": reference.get("cleanup_verified_at"),
                    "cleanup_evidence": reference.get("cleanup_evidence"),
                }
            )
    return {
        "schema_version": "catalog-switch-supervisor-resource-ledger/v1",
        "updated_at": iso(utc_now()),
        "canonical_registry": str(registry_path.resolve()),
        "contains_secrets": False,
        "leases": exported_leases,
        "resources": exported_resources,
    }


def inventory(cli: NebiusCLI) -> dict[str, Any]:
    whoami = cli.run(["iam", "whoami"])
    identity_type = next(iter(whoami), "unknown")
    identity_info = whoami.get(identity_type, {}).get("info", {}).get("metadata", {})
    projects = []
    tenant_ids: set[str] = set()
    for project_id, expected_region in AUTHORIZED_PROJECTS.items():
        try:
            project = cli.run(["iam", "project", "get", project_id], timeout=45)
            tenant_ids.add(project.get("metadata", {}).get("parent_id", ""))
            platforms = cli.run(
                ["compute", "platform", "list", "--parent-id", project_id, "--all"], timeout=90
            )
            quotas = cli.run(
                ["quotas", "quota-allowance", "list", "--parent-id", project_id, "--all"],
                timeout=90,
            )
            projects.append(
                {
                    "project_id": project_id,
                    "name": project.get("metadata", {}).get("name"),
                    "expected_region": expected_region,
                    "observed_region": project_region(project),
                    "state": project.get("status", {}).get("container_state"),
                    "platforms": [
                        {
                            "name": item.get("metadata", {}).get("name"),
                            "presets": [
                                preset.get("name")
                                for preset in item.get("spec", {}).get("presets", [])
                            ],
                            "gpu_memory_gigabytes": item.get("spec", {}).get(
                                "gpu_memory_gigabytes"
                            ),
                        }
                        for item in platforms.get("items", [])
                    ],
                    "quota_usage": [
                        {
                            "name": item.get("metadata", {}).get("name"),
                            "usage": item.get("status", {}).get("usage"),
                            "unit": item.get("status", {}).get("unit"),
                            "usage_state": item.get("status", {}).get("usage_state"),
                            "allowance": item.get("spec", {}).get("allowance"),
                        }
                        for item in quotas.get("items", [])
                        if item.get("metadata", {}).get("name", "").startswith(
                            ("compute.", "vpc.", "storage.bucket")
                        )
                    ],
                    "status": "PASS",
                }
            )
        except AuthenticationError:
            raise
        except BrokerError as exc:
            projects.append(
                {
                    "project_id": project_id,
                    "expected_region": expected_region,
                    "status": "ERROR",
                    "error": str(exc)[:1200],
                }
            )
    capacity = []
    for tenant_id in sorted(value for value in tenant_ids if value):
        try:
            response = cli.run(
                ["capacity", "resource-advice", "list", "--parent-id", tenant_id, "--all"],
                timeout=90,
            )
            capacity.append(
                {
                    "tenant_id": tenant_id,
                    "status": "PASS",
                    "items": response.get("items", []),
                }
            )
        except AuthenticationError:
            raise
        except BrokerError as exc:
            capacity.append(
                {"tenant_id": tenant_id, "status": "ERROR", "error": str(exc)[:1200]}
            )
    return {
        "schema_version": "catalog-switch-authorized-inventory/v1",
        "observed_at": iso(utc_now()),
        "nebius_profile": cli.profile,
        "identity": {
            "type": identity_type,
            "id": identity_info.get("id"),
            "parent_id": identity_info.get("parent_id"),
            "name": identity_info.get("name"),
        },
        "secrets_recorded": False,
        "projects": projects,
        "capacity_advice": capacity,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, default=ROOT / "profiles.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "leases" / "registry.json")
    parser.add_argument("--nebius-profile", default="sandbox")
    sub = parser.add_subparsers(dest="command", required=True)

    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--request", required=True, type=Path)
    plan_parser.add_argument("--lease", required=True, type=Path)

    provision_parser = sub.add_parser("provision")
    provision_parser.add_argument("--lease", required=True, type=Path)
    provision_parser.add_argument("--execute", action="store_true", required=True)
    provision_parser.add_argument("--authorization", type=Path)
    provision_parser.add_argument("--independent-clearance", type=Path)
    provision_parser.add_argument("--bearer-token-file", type=Path)

    review_parser = sub.add_parser("review-authorization")
    review_parser.add_argument("--lease", required=True, type=Path)
    review_parser.add_argument("--authorization", required=True, type=Path)
    review_parser.add_argument("--bearer-token-file", required=True, type=Path)

    health_parser = sub.add_parser("verify-health")
    health_parser.add_argument("--lease", required=True, type=Path)
    health_parser.add_argument("--execute", action="store_true", required=True)

    cleanup_parser = sub.add_parser("cleanup")
    cleanup_parser.add_argument("--lease", required=True, type=Path)
    cleanup_parser.add_argument("--execute", action="store_true")

    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("--cloud", action="store_true")
    scan_parser.add_argument("--output", type=Path)

    inventory_parser = sub.add_parser("inventory")
    inventory_parser.add_argument("--output", required=True, type=Path)

    supervisor_parser = sub.add_parser("supervisor-ledger")
    supervisor_parser.add_argument(
        "--output", type=Path, default=DEFAULT_SUPERVISOR_LEDGER
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "plan":
            result = plan(args.request, args.lease, args.registry, args.profiles)
        elif args.command == "provision":
            if bool(args.authorization) != bool(args.bearer_token_file):
                raise BrokerError("authorization and bearer-token-file must be provided together")
            context = (
                validate_live_authorization(
                    args.authorization,
                    args.lease,
                    args.bearer_token_file,
                    require_cleared=True,
                    clearance_path=args.independent_clearance,
                )
                if args.authorization
                else None
            )
            result = provision(
                args.lease,
                args.registry,
                NebiusCLI(profile=args.nebius_profile),
                live_authorization=context,
            )
        elif args.command == "review-authorization":
            context = validate_live_authorization(
                args.authorization,
                args.lease,
                args.bearer_token_file,
            )
            result = {
                "status": "PASS",
                "gate": "PRE-CREATION REVIEW",
                "live_creation_authorized": False,
                "authorization": context["public"],
            }
        elif args.command == "verify-health":
            result = verify_health_lease(
                args.lease, args.registry, NebiusCLI(profile=args.nebius_profile)
            )
        elif args.command == "cleanup":
            result = cleanup(
                args.lease,
                args.registry,
                NebiusCLI(profile=args.nebius_profile),
                execute=args.execute,
            )
        elif args.command == "scan":
            cli = NebiusCLI(profile=args.nebius_profile) if args.cloud else None
            result = scan(args.registry, cli, args.cloud)
            if args.output:
                atomic_json(args.output, result)
        elif args.command == "inventory":
            result = inventory(NebiusCLI(profile=args.nebius_profile))
            atomic_json(args.output, result)
        elif args.command == "supervisor-ledger":
            result = supervisor_ledger(args.registry)
            atomic_json(args.output, result)
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except AuthenticationError as exc:
        print(f"AUTHORIZATION STOP: {exc}", file=sys.stderr)
        return 3
    except BrokerError as exc:
        print(f"BROKER ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
