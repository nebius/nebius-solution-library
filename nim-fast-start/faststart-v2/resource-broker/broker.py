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
LIVE_AUTH_SCHEMA_VERSION = "catalog-switch-internal-live-authorization/v3"
LIVE_CLEARANCE_SCHEMA_VERSION = "catalog-switch-independent-precreation-clearance/v2"
QWEN_SCOUT_AUTHORIZATION_ID = "internal-qwen3-h100-scout-v3-20260819"
QWEN_SCOUT_LEASE_ID = "catswitch-qwen3-h100-scout-v3-20260819"
QWEN_SCOUT_TASK_ID = "catalog-switch-cerebrium-qwen3-glm52-benchmark"
QWEN_SCOUT_ARM_ID = "internal-qwen3-new-target-matched"
QWEN_SCOUT_MODEL = "Qwen/Qwen3-8B"
QWEN_SCOUT_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
QWEN_SCOUT_IMAGE_DIGEST = (
    "sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d"
)
QWEN_SCOUT_REQUIRED_REVIEWER = "catalog-switch-independent-precreation-reviewer-v2"
QWEN_SCOUT_BRANCH = "agent/catalog-switch-cerebrium-qwen3-glm52-benchmark"
RECORDER_IP_ENDPOINT = "https://api.ipify.org"
STRICT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
LIVE_AUTH_TOP_KEYS = {
    "artifacts",
    "authorization_id",
    "authorized_by",
    "cleanup",
    "expires_at",
    "frozen",
    "issued_at",
    "network",
    "observed_gpu",
    "qualification",
    "required_reviewer",
    "schema",
    "scope",
    "state",
}


class BrokerError(RuntimeError):
    """Expected fail-closed broker error."""


class AuthenticationError(BrokerError):
    """Authentication/authorization stop condition."""


_LIVE_CONTEXT_SEAL = object()


class LiveAuthorizationContext:
    """Non-serializable result of the full authorization/clearance validation."""

    __slots__ = ("_value",)

    def __init__(self, value: dict[str, Any], seal: object) -> None:
        if seal is not _LIVE_CONTEXT_SEAL:
            raise BrokerError("live authorization context cannot be constructed directly")
        self._value = value

    def __getitem__(self, key: str) -> Any:
        return self._value[key]

    def __contains__(self, key: object) -> bool:
        return key in self._value

    def get(self, key: str, default: Any = None) -> Any:
        return self._value.get(key, default)

    def __repr__(self) -> str:
        return "LiveAuthorizationContext(<redacted>)"


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
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def strict_parse_utc(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or not STRICT_UTC_RE.fullmatch(value):
        raise BrokerError(f"{field} must be canonical UTC seconds (YYYY-MM-DDTHH:MM:SSZ)")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as exc:
        raise BrokerError(f"{field} is not a valid UTC timestamp") from exc
    if iso(parsed) != value:
        raise BrokerError(f"{field} is not canonical UTC")
    return parsed


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
    """Observe the recorder address without logging or persisting the literal value."""
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
        raise BrokerError("runtime bearer-token file must have mode 0600 or stricter")
    value = path.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BrokerError("runtime bearer token must be a 32-byte lowercase hex value")
    return value


def _git_state() -> tuple[str, str, bool]:
    def run_git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(FASTSTART_ROOT), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise BrokerError("cannot resolve the exact candidate Git state")
        return result.stdout.strip()

    commit = run_git("rev-parse", "HEAD")
    branch = run_git("branch", "--show-current")
    clean = run_git("status", "--porcelain") == ""
    return commit, branch, clean


def _validate_clearance(
    clearance: dict[str, Any],
    authorization: dict[str, Any],
    authorization_sha256: str,
    *,
    current_commit: str,
    current_branch: str,
    worktree_clean: bool,
    now: dt.datetime,
) -> dict[str, Any]:
    expected_keys = {
        "authorization_id",
        "authorization_sha256",
        "clearance_id",
        "decision",
        "expires_at",
        "reviewed_at",
        "reviewed_commit",
        "reviewer",
        "schema",
    }
    if set(clearance) != expected_keys:
        raise BrokerError("independent clearance fields differ from v2")
    if clearance.get("schema") != LIVE_CLEARANCE_SCHEMA_VERSION:
        raise BrokerError("unsupported independent clearance schema")
    if clearance.get("authorization_id") != authorization["authorization_id"]:
        raise BrokerError("clearance authorization ID differs")
    if clearance.get("authorization_sha256") != authorization_sha256:
        raise BrokerError("clearance authorization digest differs")
    if clearance.get("decision") != "CLEARED":
        raise BrokerError("independent clearance decision is not CLEARED")
    if clearance.get("reviewer") != authorization["required_reviewer"]:
        raise BrokerError("clearance reviewer is not the exactly required reviewer")
    reviewed_commit = str(clearance.get("reviewed_commit", ""))
    if (
        not COMMIT_RE.fullmatch(reviewed_commit)
        or reviewed_commit == "0" * 40
        or reviewed_commit != current_commit
    ):
        raise BrokerError("clearance is not bound to the exact current candidate commit")
    if current_branch != authorization["scope"]["branch"]:
        raise BrokerError("live execution branch differs from the reviewed branch")
    if not worktree_clean:
        raise BrokerError("live execution requires the exact clean reviewed worktree")
    issued_at = strict_parse_utc(authorization["issued_at"], "authorization.issued_at")
    authorization_expires = strict_parse_utc(
        authorization["expires_at"], "authorization.expires_at"
    )
    reviewed_at = strict_parse_utc(clearance.get("reviewed_at"), "clearance.reviewed_at")
    clearance_expires = strict_parse_utc(
        clearance.get("expires_at"), "clearance.expires_at"
    )
    if not issued_at <= reviewed_at <= now + dt.timedelta(minutes=5):
        raise BrokerError("clearance review time is outside the authorization/current-time window")
    if not now < clearance_expires <= authorization_expires:
        raise BrokerError("clearance expiry is stale or exceeds authorization expiry")
    if clearance_expires - reviewed_at > dt.timedelta(hours=1):
        raise BrokerError("clearance live window exceeds one hour")
    return {
        "schema": clearance["schema"],
        "clearance_id": clearance["clearance_id"],
        "decision": clearance["decision"],
        "reviewer": clearance["reviewer"],
        "reviewed_at": clearance["reviewed_at"],
        "reviewed_commit": clearance["reviewed_commit"],
        "expires_at": clearance["expires_at"],
        "authorization_sha256": clearance["authorization_sha256"],
    }


def validate_live_authorization(
    authorization_path: Path,
    clearance_path: Path,
    lease_path: Path,
    bearer_token_path: Path,
    *,
    observed_recorder_cidr: str | None = None,
    current_commit: str | None = None,
    current_branch: str | None = None,
    worktree_clean: bool | None = None,
    now: dt.datetime | None = None,
) -> LiveAuthorizationContext:
    """Validate the sole live-creation gate before any provider preflight or mutation."""
    authorization = load_json(authorization_path)
    if set(authorization) != LIVE_AUTH_TOP_KEYS:
        raise BrokerError("live authorization top-level fields differ from v3")
    if authorization.get("schema") != LIVE_AUTH_SCHEMA_VERSION:
        raise BrokerError("unsupported live authorization schema")
    if authorization.get("authorization_id") != QWEN_SCOUT_AUTHORIZATION_ID:
        raise BrokerError("authorization is not the exact Qwen v3 scout authorization")
    if authorization.get("state") != "PRE_CREATION_REVIEW":
        raise BrokerError("versioned authorization must remain PRE_CREATION_REVIEW")
    if authorization.get("authorized_by") != "explicit-user-manager-intervention-20260819":
        raise BrokerError("authorization provenance differs")
    if authorization.get("required_reviewer") != QWEN_SCOUT_REQUIRED_REVIEWER:
        raise BrokerError("authorization reviewer requirement differs")
    if any(
        re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}/32", value)
        for value in _strings(authorization)
    ):
        raise BrokerError("publishable authorization embeds the recorder /32")

    lease = load_json(lease_path)
    if lease.get("schema_version") != SCHEMA_VERSION:
        raise BrokerError("authorization references an unsupported lease")
    if lease.get("state") != "PLANNED" or lease.get("resources"):
        raise BrokerError("authorization requires a clean PLANNED zero-resource lease")
    if sha256_json(lease.get("request")) != lease.get("request_sha256"):
        raise BrokerError("lease request body differs from its immutable digest")
    expected_prefix = (
        f"{PROGRAM_PREFIX}-{lease['request']['task_id'][:18].rstrip('-._')}-"
        f"{lease['request_sha256'][:8]}"
    )
    if lease.get("prefix") != expected_prefix:
        raise BrokerError("lease resource prefix differs from the immutable request")
    now = (now or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    authorization_expires = strict_parse_utc(
        authorization.get("expires_at"), "authorization.expires_at"
    )
    issued_at = strict_parse_utc(authorization.get("issued_at"), "authorization.issued_at")
    if not issued_at <= now < authorization_expires:
        raise BrokerError("live authorization is not currently valid")
    if authorization.get("expires_at") != lease.get("expires_at"):
        raise BrokerError("authorization expiry differs from the immutable lease")

    scope = authorization.get("scope")
    expected_scope = {
        "arm_id": QWEN_SCOUT_ARM_ID,
        "backend": "internal-nebius",
        "branch": QWEN_SCOUT_BRANCH,
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
        raise BrokerError("authorization is not the exact internal Qwen arm allowlist")
    request = lease["request"]
    for key in ("lease_id", "mode", "profile", "project_id", "region", "task_id"):
        if request.get(key) != scope[key]:
            raise BrokerError(f"authorization/lease scope differs: {key}")
    if request["experiment"]["model_id"] != f"{QWEN_SCOUT_MODEL}@{QWEN_SCOUT_REVISION}":
        raise BrokerError("authorization rejects this model identity")

    frozen = authorization.get("frozen")
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
        raise BrokerError("authorization frozen model/input/lease/cost pins differ")

    artifacts = authorization.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 5:
        raise BrokerError("authorization must pin the five executable/schema artifacts")
    allowed_artifacts = {
        "resource-broker/broker.py",
        "catalog-switch/cerebrium-comparator/comparator.py",
        "catalog-switch/cerebrium-comparator/live/bootstrap_internal_qwen_v3.sh",
        "catalog-switch/cerebrium-comparator/live/internal_scout_server_v3.py",
        "catalog-switch/cerebrium-comparator/schemas/live-authorization-v3.schema.json",
    }
    if {item.get("path") for item in artifacts if isinstance(item, dict)} != allowed_artifacts:
        raise BrokerError("authorization executable/schema artifact allowlist differs")
    for artifact in artifacts:
        if set(artifact) != {"path", "sha256"}:
            raise BrokerError("authorization artifact fields differ")
        source = (FASTSTART_ROOT / artifact["path"]).resolve()
        if FASTSTART_ROOT not in source.parents or source.is_symlink() or not source.is_file():
            raise BrokerError("authorization artifact escapes the task source tree")
        if file_sha256(source) != artifact["sha256"]:
            raise BrokerError(f"authorization artifact digest differs: {artifact['path']}")

    expected_qualification = {
        "cold_scout_runtime_groups": 3,
        "headline_request_ordinal": 1,
        "independent_recorder_oracle_validation": True,
        "requests_per_runtime": 2,
        "semantic_smoke_runtime_groups": 1,
        "server_oracle_verdict_required": True,
        "teardown_after_request_ordinal": 2,
    }
    if authorization.get("qualification") != expected_qualification:
        raise BrokerError("authorization does not require two validations per cold runtime")
    expected_gpu = {
        "count": 1,
        "marker": "CATSWITCH_GPU_PROOF_B64",
        "name_regex": "^NVIDIA H100(?: |$)",
        "source": "bootstrap-nvidia-smi-serial-proof",
    }
    if authorization.get("observed_gpu") != expected_gpu:
        raise BrokerError("authorization observed-GPU contract differs")
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
    expected_bootstrap_egress = [
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [443], "protocol": "TCP", "purpose": "TLS image/model localization"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [53], "protocol": "UDP", "purpose": "DNS resolution"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [53], "protocol": "TCP", "purpose": "DNS fallback"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [123], "protocol": "UDP", "purpose": "UTC clock synchronization"},
    ]
    if not isinstance(network, dict) or set(network) != {
        "bearer_token_sha256",
        "bootstrap_egress",
        "direct_container_ingress",
        "ingress",
        "lifecycle_transition",
        "public_ipv4_count",
        "recorder_cidr_published",
        "recorder_cidr_sha256",
        "runtime_egress",
        "secret_values_published",
        "ssh_ingress",
    }:
        raise BrokerError("authorization network fields differ")
    if (
        network["ingress"] != expected_ingress
        or network["bootstrap_egress"] != expected_bootstrap_egress
        or network["runtime_egress"] != []
        or network["lifecycle_transition"] != "controller-delete-bootstrap-egress-before-active"
        or network["public_ipv4_count"] != 1
        or network["recorder_cidr_published"] is not False
        or network["secret_values_published"] is not False
        or network["ssh_ingress"] is not False
        or network["direct_container_ingress"] is not False
    ):
        raise BrokerError("authorization network lifecycle is not the exact v3 boundary")
    if any(80 in item["ports"] for item in network["bootstrap_egress"]):
        raise BrokerError("unconditional TCP/80 is forbidden")
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
    if hashlib.sha256(bearer_token.encode()).hexdigest() != network["bearer_token_sha256"]:
        raise BrokerError("runtime bearer token differs from the pinned hash")

    if current_commit is None or current_branch is None or worktree_clean is None:
        current_commit, current_branch, worktree_clean = _git_state()
    clearance_public = _validate_clearance(
        load_json(clearance_path),
        authorization,
        file_sha256(authorization_path),
        current_commit=current_commit,
        current_branch=current_branch,
        worktree_clean=worktree_clean,
        now=now,
    )
    public = {
        "authorization_id": authorization["authorization_id"],
        "authorization_sha256": file_sha256(authorization_path),
        "clearance": clearance_public,
        "network": {
            "bearer_token_sha256": network["bearer_token_sha256"],
            "bootstrap_egress_rule_count": 4,
            "ingress_port": 8080,
            "recorder_cidr_sha256": network["recorder_cidr_sha256"],
            "runtime_egress_rule_count": 0,
            "secret_values_published": False,
        },
        "observed_gpu": authorization["observed_gpu"],
        "qualification": authorization["qualification"],
        "scope": authorization["scope"],
        "state": authorization["state"],
    }
    return LiveAuthorizationContext(
        {
            "authorization": authorization,
            "public": public,
            "_bearer_token": bearer_token,
            "_recorder_cidr": canonical_cidr,
        },
        _LIVE_CONTEXT_SEAL,
    )


def validate_live_resume(
    authorization_path: Path,
    clearance_path: Path,
    lease_path: Path,
    bearer_token_path: Path,
    *,
    observed_recorder_cidr: str | None = None,
    current_commit: str | None = None,
    current_branch: str | None = None,
    worktree_clean: bool | None = None,
    now: dt.datetime | None = None,
) -> LiveAuthorizationContext:
    """Revalidate current code/reviewer/secrets for a partially created live lease."""
    authorization = load_json(authorization_path)
    lease = load_json(lease_path)
    stored = lease.get("live_authorization")
    if not isinstance(stored, dict):
        raise BrokerError("live lease has no previously validated authorization")
    if authorization.get("schema") != LIVE_AUTH_SCHEMA_VERSION:
        raise BrokerError("unsupported live resume authorization schema")
    authorization_sha256 = file_sha256(authorization_path)
    if (
        stored.get("authorization_id") != authorization.get("authorization_id")
        or stored.get("authorization_sha256") != authorization_sha256
        or stored.get("scope", {}).get("lease_id") != lease.get("lease_id")
    ):
        raise BrokerError("resume authorization differs from the stored live lease gate")
    now = (now or utc_now()).astimezone(dt.timezone.utc).replace(microsecond=0)
    if current_commit is None or current_branch is None or worktree_clean is None:
        current_commit, current_branch, worktree_clean = _git_state()
    clearance = _validate_clearance(
        load_json(clearance_path),
        authorization,
        authorization_sha256,
        current_commit=current_commit,
        current_branch=current_branch,
        worktree_clean=worktree_clean,
        now=now,
    )
    if stored.get("clearance") != clearance:
        raise BrokerError("resume clearance differs from the originally stored clearance")
    cidr = observed_recorder_cidr or observe_recorder_cidr()
    try:
        canonical_cidr = str(ipaddress.IPv4Network(cidr, strict=True))
    except ValueError as exc:
        raise BrokerError("resume recorder address is not a canonical IPv4 CIDR") from exc
    if hashlib.sha256(canonical_cidr.encode()).hexdigest() != stored["network"]["recorder_cidr_sha256"]:
        raise BrokerError("recorder IP drift detected during live resume")
    bearer_token = _load_runtime_bearer(bearer_token_path)
    if hashlib.sha256(bearer_token.encode()).hexdigest() != stored["network"]["bearer_token_sha256"]:
        raise BrokerError("runtime bearer token differs during live resume")
    return LiveAuthorizationContext(
        {
            "authorization": authorization,
            "public": stored,
            "_bearer_token": bearer_token,
            "_recorder_cidr": canonical_cidr,
        },
        _LIVE_CONTEXT_SEAL,
    )


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
    "security_rule": ["vpc", "security-rule", "get"],
    "disk": ["compute", "disk", "get"],
    "instance": ["compute", "instance", "get"],
    "bucket": ["storage", "bucket", "get"],
    "allocation": ["vpc", "allocation", "get"],
    "pool": ["vpc", "pool", "get"],
    "route_table": ["vpc", "route-table", "get"],
}


DELETE_COMMANDS = {
    "instance": ["compute", "instance", "delete"],
    "disk": ["compute", "disk", "delete"],
    "bucket": ["storage", "bucket", "delete"],
    "security_group": ["vpc", "security-group", "delete"],
    "security_rule": ["vpc", "security-rule", "delete"],
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


def add_event(lease: dict[str, Any], event_type: str, status: str, details: str) -> None:
    lease["events"].append(
        {"at": iso(utc_now()), "type": event_type, "status": status, "details": details}
    )


def add_resource(
    lease: dict[str, Any],
    kind: str,
    name: str,
    response: dict[str, Any],
    *,
    parent_id: str | None = None,
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
    if parent_id is not None:
        resource["parent_id"] = parent_id
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
                if not pool_created or parse_utc(pool_created) < parse_utc(
                    lease["created_at"]
                ):
                    add_external_reference(lease, "pool", pool, subnet["id"])
                else:
                    add_managed_resource(lease, "pool", pool, subnet["id"])


def _security_rule_proof(value: dict[str, Any]) -> dict[str, Any]:
    metadata = value.get("metadata", {})
    spec = value.get("spec", {})
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
        "access": spec.get("access"),
        "cidr_sha256": [hashlib.sha256(str(item).encode()).hexdigest() for item in cidrs],
        "direction": direction,
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "ports": ports,
        "protocol": spec.get("protocol"),
        "type": spec.get("type"),
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
    interfaces = instance.get("spec", {}).get("network_interfaces", [])
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
        ingress = [item for item in rules if item["direction"] == "ingress"]
        egress = [item for item in rules if item["direction"] == "egress"]
        expected_source_hash = live_authorization["network"]["recorder_cidr_sha256"]
        if len(ingress) != 1 or not (
            ingress[0]["access"] == "allow"
            and ingress[0]["protocol"] == "tcp"
            and ingress[0]["type"] == "stateful"
            and ingress[0]["ports"] == [8080]
            and ingress[0]["cidr_sha256"] == [expected_source_hash]
        ):
            failures.append("authenticated recorder-only TCP/8080 ingress differs")
        if egress or security_group["rule_count"] != 1:
            failures.append("runtime security group retains bootstrap or foreign egress")
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


def authorized_cloud_init(
    lease: dict[str, Any], context: LiveAuthorizationContext
) -> str:
    artifact_paths = {
        "catalog-switch/cerebrium-comparator/live/bootstrap_internal_qwen_v3.sh": (
            "/opt/catswitch/bootstrap_internal_qwen_v3.sh",
            "0755",
        ),
        "catalog-switch/cerebrium-comparator/live/internal_scout_server_v3.py": (
            "/opt/catswitch/internal_scout_server_v3.py",
            "0644",
        ),
    }
    lines = ["#cloud-config", "write_files:"]
    for relative, (target, mode) in artifact_paths.items():
        encoded = base64.b64encode((FASTSTART_ROOT / relative).read_bytes()).decode()
        lines.extend(
            [
                f"  - path: {target}",
                f"    permissions: '{mode}'",
                "    encoding: b64",
                f"    content: {encoded}",
            ]
        )
    token_encoded = base64.b64encode(context["_bearer_token"].encode()).decode()
    lines.extend(
        [
            "  - path: /run/catswitch/bearer-token",
            "    permissions: '0600'",
            "    encoding: b64",
            f"    content: {token_encoded}",
            "runcmd:",
            "  - [bash, /opt/catswitch/bootstrap_internal_qwen_v3.sh]",
            f"final_message: 'catalog-switch bootstrap finished; lease={lease['lease_id']}'",
            "",
        ]
    )
    return "\n".join(lines)


def provision(
    lease_path: Path,
    registry_path: Path,
    cli: NebiusCLI,
    *,
    live_authorization: LiveAuthorizationContext | None = None,
) -> dict[str, Any]:
    lease = load_json(lease_path)
    if lease.get("schema_version") != SCHEMA_VERSION:
        raise BrokerError("unsupported lease schema")
    if live_authorization is None:
        raise BrokerError("mandatory live authorization/clearance is absent")
    if not isinstance(live_authorization, LiveAuthorizationContext):
        raise BrokerError("live authorization context was not produced by the validator")
    public_authorization = live_authorization.get("public", {})
    private_keys_present = {
        key for key in ("_bearer_token", "_recorder_cidr") if key in live_authorization
    }
    if (
        public_authorization.get("authorization_id") != QWEN_SCOUT_AUTHORIZATION_ID
        or public_authorization.get("clearance", {}).get("decision") != "CLEARED"
        or public_authorization.get("clearance", {}).get("reviewed_commit") is None
        or private_keys_present != {"_bearer_token", "_recorder_cidr"}
    ):
        raise BrokerError("live authorization has not passed the exact independent gate")
    if lease["state"] == "ACTIVE":
        if lease.get("live_authorization") != public_authorization:
            raise BrokerError("active lease authorization differs from the current clearance")
        return lease
    if lease["state"] != "PLANNED" or lease["resources"]:
        raise BrokerError("provision requires a clean PLANNED lease")
    if utc_now() >= parse_utc(lease["expires_at"]):
        raise BrokerError("cannot provision an expired lease")
    if lease["lease_id"] != public_authorization.get("scope", {}).get("lease_id"):
        raise BrokerError("live authorization lease binding differs")
    lease["live_authorization"] = public_authorization
    add_event(
        lease,
        "LIVE_AUTHORIZATION",
        "PASS",
        f"{QWEN_SCOUT_AUTHORIZATION_ID}; secrets retained as hashes only",
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

        subnet_response = cli.run(
            ["vpc", "subnet", "create"],
            payload=resource_payload(
                names["subnet"],
                project_id,
                labels,
                {
                    "network_id": network["id"],
                    "ipv4_private_pools": {"use_network_pools": True},
                    "ipv4_public_pools": {
                        "use_network_pools": False,
                        "pools": [{"cidrs": [{"cidr": "/32"}]}],
                    },
                },
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
        add_resource(
            lease,
            "security_rule",
            ingress_name,
            ingress_response,
            parent_id=security_group["id"],
        )
        save_lease(lease_path, registry_path, lease)
        for index, rule in enumerate(
            live_authorization["authorization"]["network"]["bootstrap_egress"], 1
        ):
            egress_name = f"{lease['prefix']}-bootstrap-egress-{index}"
            egress_response = cli.run(
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
            add_resource(
                lease,
                "security_rule",
                egress_name,
                egress_response,
                parent_id=security_group["id"],
            )
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

        cloud_init = authorized_cloud_init(lease, live_authorization)
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
                    "public_ip_address": {},
                    "security_groups": [{"id": security_group["id"]}],
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
        reconcile_managed_children(lease, cli)
        save_lease(lease_path, registry_path, lease)
        return verify_health_lease(
            lease_path,
            registry_path,
            cli,
            instance["id"],
            live_authorization=live_authorization,
        )
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


def parse_observed_gpu_proof(logs: str) -> dict[str, Any]:
    matches = re.findall(r"(?:^|\n)CATSWITCH_GPU_PROOF_B64=([A-Za-z0-9_-]+)(?:\n|$)", logs)
    if not matches:
        raise BrokerError("bootstrap logs contain no observed GPU proof")
    try:
        padded = matches[-1] + "=" * (-len(matches[-1]) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("observed GPU proof is not canonical base64url JSON") from exc
    if not isinstance(value, dict) or set(value) != {"count", "names", "uuids"}:
        raise BrokerError("observed GPU proof fields differ")
    if value["count"] != 1 or not isinstance(value["names"], list) or len(value["names"]) != 1:
        raise BrokerError("observed GPU count is not exactly one")
    if not re.fullmatch(r"NVIDIA H100(?: |$).*", str(value["names"][0])):
        raise BrokerError("observed GPU is not an H100")
    if (
        not isinstance(value["uuids"], list)
        or len(value["uuids"]) != 1
        or not re.fullmatch(r"GPU-[A-Za-z0-9-]{8,}", str(value["uuids"][0]))
    ):
        raise BrokerError("observed GPU UUID proof differs")
    return {
        "count": 1,
        "name": value["names"][0],
        "uuid_sha256": hashlib.sha256(value["uuids"][0].encode()).hexdigest(),
    }


def verify_direct_resource_identity(
    lease: dict[str, Any], cli: NebiusCLI, resource: dict[str, Any]
) -> dict[str, Any] | None:
    value = cli.run(
        [*GET_COMMANDS[resource["kind"]], resource["id"]],
        allow_not_found=True,
        timeout=30,
    )
    if value is None:
        return None
    metadata = value.get("metadata", {})
    expected_parent = resource.get("parent_id", lease["request"]["project_id"])
    labels = metadata.get("labels", {}) or {}
    expected_labels = lease["labels"]
    failures = []
    if metadata.get("id") != resource["id"]:
        failures.append("ID")
    if metadata.get("name") != resource["name"]:
        failures.append("name")
    if metadata.get("parent_id") != expected_parent:
        failures.append("parent")
    for key in ("program", "lease", "task", "owner"):
        if labels.get(key) != expected_labels[key]:
            failures.append(f"label:{key}")
    if failures:
        raise BrokerError(
            f"foreign replacement detected for {resource['kind']}:{resource['id']} ({','.join(failures)}); refusing delete"
        )
    return value


def narrow_bootstrap_egress(
    lease_path: Path, registry_path: Path, cli: NebiusCLI
) -> None:
    lease = load_json(lease_path)
    prefix = f"{lease['prefix']}-bootstrap-egress-"
    bootstrap_rules = [
        item
        for item in lease["resources"]
        if item["kind"] == "security_rule"
        and item["name"].startswith(prefix)
        and not item["deleted_at"]
    ]
    if len(bootstrap_rules) > 4:
        raise BrokerError("ledger contains unexpected bootstrap egress rules")
    for resource in sorted(bootstrap_rules, key=lambda item: item["name"]):
        current = verify_direct_resource_identity(lease, cli, resource)
        if current is not None:
            cli.run(delete_args(resource["kind"], resource["id"]), json_output=False, timeout=180)
        if not wait_absent(cli, resource["kind"], resource["id"], timeout_seconds=180):
            raise BrokerError("bootstrap egress rule remains after lifecycle narrowing")
        resource["deleted_at"] = iso(utc_now())
        resource["delete_verified_at"] = resource["deleted_at"]
        add_event(
            lease,
            "BOOTSTRAP_EGRESS_REMOVED",
            "PASS",
            f"security_rule:{resource['id']} NotFound verified",
        )
        save_lease(lease_path, registry_path, lease)
    lease = load_json(lease_path)
    if any(
        item["kind"] == "security_rule"
        and item["name"].startswith(prefix)
        and not item["deleted_at"]
        for item in lease["resources"]
    ):
        raise BrokerError("post-bootstrap network narrowing is incomplete")
    add_event(
        lease,
        "RUNTIME_NETWORK_NARROWED",
        "PASS",
        "all bootstrap egress removed; authenticated recorder ingress only",
    )
    save_lease(lease_path, registry_path, lease)


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
            observed_gpu = parse_observed_gpu_proof(last_logs)
            lease["health_proof"] = {
                "verified_at": iso(utc_now()),
                "instance_id": instance_id,
                "instance_state": last_state,
                "serial_log_marker": expected_marker,
                "serial_log_marker_observed": True,
                "observed_gpu": observed_gpu,
            }
            add_event(
                lease,
                "HEALTH_PROOF",
                "PASS",
                "RUNNING, serial marker, and observed exactly-one-H100 proof",
            )
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
    *,
    live_authorization: LiveAuthorizationContext | None = None,
) -> dict[str, Any]:
    lease = load_json(lease_path)
    if live_authorization is None:
        raise BrokerError("health verification requires the current exact live clearance")
    if not isinstance(live_authorization, LiveAuthorizationContext):
        raise BrokerError("health authorization context was not produced by the validator")
    if lease.get("live_authorization") != live_authorization.get("public"):
        raise BrokerError("health verification authorization differs from the lease")
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
    narrow_bootstrap_egress(lease_path, registry_path, cli)
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
    "security_rule": 65,
    "security_group": 60,
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
                current = verify_direct_resource_identity(lease, cli, resource)
                if current is not None:
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
    provision_parser.add_argument("--authorization", required=True, type=Path)
    provision_parser.add_argument("--clearance", required=True, type=Path)
    provision_parser.add_argument("--bearer-token", required=True, type=Path)
    provision_parser.add_argument("--execute", action="store_true", required=True)

    health_parser = sub.add_parser("verify-health")
    health_parser.add_argument("--lease", required=True, type=Path)
    health_parser.add_argument("--authorization", required=True, type=Path)
    health_parser.add_argument("--clearance", required=True, type=Path)
    health_parser.add_argument("--bearer-token", required=True, type=Path)
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
            if load_json(args.lease).get("state") == "PLANNED":
                live_authorization = validate_live_authorization(
                    args.authorization,
                    args.clearance,
                    args.lease,
                    args.bearer_token,
                )
            else:
                live_authorization = validate_live_resume(
                    args.authorization,
                    args.clearance,
                    args.lease,
                    args.bearer_token,
                )
            result = provision(
                args.lease,
                args.registry,
                NebiusCLI(profile=args.nebius_profile),
                live_authorization=live_authorization,
            )
        elif args.command == "verify-health":
            live_authorization = validate_live_resume(
                args.authorization,
                args.clearance,
                args.lease,
                args.bearer_token,
            )
            result = verify_health_lease(
                args.lease,
                args.registry,
                NebiusCLI(profile=args.nebius_profile),
                live_authorization=live_authorization,
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
