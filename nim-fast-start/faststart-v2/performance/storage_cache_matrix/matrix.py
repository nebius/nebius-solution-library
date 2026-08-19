#!/usr/bin/env python3
"""Fail-closed storage/cache matrix receipts, validation, and aggregation.

The detailed receipt does not redefine the program's product metric.  Every
receipt is bound to an admitted ``performance.request_slo`` trace and ledger;
this module only adds the lower-level storage operations needed by the router
and simulator.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from performance.request_slo.harness import (
    HarnessError,
    canonical_json,
    canonical_sha256,
    load_ledger,
    load_trace,
    validate_ledger,
)


PLAN_SCHEMA = "archvteams.nebius.ai/storage-cache-matrix-plan/v1"
ATTEMPT_SCHEMA = "archvteams.nebius.ai/storage-cache-matrix-attempt/v1"
AGGREGATE_SCHEMA = "archvteams.nebius.ai/storage-cache-matrix-aggregate/v1"
ROUTER_SCHEMA = "archvteams.nebius.ai/router-locality-costs/v1"
SIMULATOR_SCHEMA_VERSION = "1.0.0"

T0_BOUNDARY = "external-client-request-accepted/v1"
TERMINAL_BOUNDARY = "first-complete-semantically-valid-response/v1"
ALLOWED_PROJECTS = {
    "project-e00z6b02t8ddk96c49": "eu-north1",
    "project-u00tds8vpr00jaxa76s22d": "us-central1",
    "project-i00xz31gpr00xp9jhp982v": "me-west1",
}
EVIDENCE_CLASSES = {
    "measured-live-product-slo",
    "synthetic-smoke-not-performance-evidence",
}
TIERS = ("local_nvme", "attached_block_pvc", "remote_artifact")
COHORTS = (
    "hot",
    "warm",
    "cold",
    "eviction_repopulation",
    "concurrent_fetch",
    "corruption",
    "boltz_external_tmp_hit",
    "boltz_external_tmp_clone_miss",
)
CACHE_STATES = ("hit", "miss", "evicted", "corrupt")
OUTCOMES = ("completed", "failed", "skipped")
TERMINAL_TYPES = ("response.validated", "attempt.failed")
FAILURE_CLASSES = (
    "backend",
    "capacity",
    "cancelled",
    "corruption",
    "infrastructure",
    "preempted",
    "timeout",
    "validation",
)
PERCENTILE_MINIMUMS = {"p50": 2, "p95": 20, "p99": 100}

# Every operation is present even when it is skipped.  A skipped observation is
# timestamped after T0 and explains which pre-existing investment made it a hit.
PHASES = (
    "catalog_selection",
    "queue",
    "drain",
    "gpu_release",
    "placement",
    "image_pull",
    "image_unpack",
    "artifact_fetch",
    "volume_attach",
    "volume_mount",
    "clone",
    "copy",
    "hash",
    "first_read",
    "restore",
    "conventional_load",
    "runtime_launch",
    "service_readiness",
    "inference",
    "semantic_validation",
)
PHASE_DEPENDENCIES = {
    "catalog_selection": (),
    "queue": ("catalog_selection",),
    "drain": ("queue",),
    "gpu_release": ("drain",),
    "placement": ("queue", "gpu_release"),
    "image_pull": ("placement",),
    "image_unpack": ("image_pull",),
    "artifact_fetch": ("placement",),
    "volume_attach": ("placement",),
    "volume_mount": ("volume_attach",),
    "clone": ("artifact_fetch", "volume_mount"),
    "copy": ("clone",),
    "hash": ("copy",),
    "first_read": ("hash",),
    "restore": ("image_unpack", "first_read", "volume_mount"),
    "conventional_load": ("image_unpack", "first_read", "volume_mount"),
    "runtime_launch": ("restore", "conventional_load"),
    "service_readiness": ("runtime_launch",),
    "inference": ("service_readiness",),
    "semantic_validation": ("inference",),
}

SHA256_RE = re.compile(r"[0-9a-f]{64}")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")
UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IMAGE_RE = re.compile(r"(?:[^\s]+@)?sha256:[0-9a-f]{64}")

PLAN_KEYS = {
    "schema",
    "plan_id",
    "task_id",
    "evidence_classification",
    "created_at_utc",
    "purpose",
    "code_revision",
    "metric_contract",
    "artifacts",
    "matrix",
    "environment_requirements",
    "cost_plan",
    "cleanup_plan",
    "boltz_external_tmp",
}
METRIC_KEYS = {"path", "sha256", "t0_boundary", "terminal_boundary"}
ARTIFACT_KEYS = {
    "model_id",
    "model_version",
    "artifact_id",
    "artifact_version",
    "sha256",
    "bytes",
    "payload_id",
    "publication_receipt_sha256",
    "published_before_t0",
    "strategy_default",
}
MATRIX_KEYS = {"cells", "one_variable_per_cohort", "shared_mutable_state"}
CELL_KEYS = {"cell_id", "model_id", "tier", "cohort", "minimum_attempts"}
ENV_REQ_KEYS = {
    "allowed_projects",
    "resource_prefix",
    "gpu_required",
    "prefer_preemptible",
    "local_nvme_requires_verified_entitlement",
}
COST_PLAN_KEYS = {
    "currency",
    "expected_duration_hours",
    "budget_usd",
    "price_source",
}
CLEANUP_PLAN_KEYS = {
    "owner",
    "ttl_hours",
    "exact_id_only",
    "dirty_generation_policy",
}
BOLTZ_PLAN_KEYS = {
    "enabled",
    "contract_path",
    "contract_sha256",
    "required_hit_cohort",
    "required_miss_cohort",
}

ATTEMPT_KEYS = {
    "schema",
    "plan_id",
    "plan_sha256",
    "attempt_id",
    "request_id",
    "cell_id",
    "evidence_classification",
    "artifact",
    "tier",
    "cohort",
    "cache",
    "concurrency",
    "environment",
    "ownership",
    "request",
    "request_slo_binding",
    "phases",
    "terminal",
    "accounting",
    "cleanup",
    "supporting_evidence",
}
ATTEMPT_ARTIFACT_KEYS = {
    "model_id",
    "model_version",
    "artifact_id",
    "artifact_version",
    "sha256",
    "bytes",
    "payload_id",
}
CACHE_KEYS = {
    "state",
    "generation_id",
    "artifact_version",
    "artifact_sha256",
    "age_seconds",
    "publication_investment_seconds",
    "node_cache_investment_seconds",
    "dirty_before_t0",
    "cow_first_write_expected",
    "shared_mutable_state",
}
CONCURRENCY_KEYS = {
    "group_id",
    "peer_attempt_ids",
    "mutable_namespace_id",
    "source_read_only",
}
ENVIRONMENT_KEYS = {
    "provider",
    "project_id",
    "region",
    "node_id",
    "gpu_type",
    "gpu_count",
    "preemptible",
    "image_digest",
    "storage_resource_id",
    "storage_medium",
    "filesystem",
    "mount_options",
    "local_nvme_entitlement_verified",
    "local_nvme_devices",
    "code_revision",
    "config_sha256",
}
OWNERSHIP_KEYS = {
    "owner_task_id",
    "resource_prefix",
    "dedicated",
    "resources",
}
RESOURCE_KEYS = {"kind", "id", "project_id", "region"}
REQUEST_KEYS = {
    "t0_boundary",
    "accepted_at_utc",
    "accepted_monotonic_ns",
    "input_id",
    "input_sha256",
    "input_bytes",
}
BINDING_KEYS = {
    "trace_path",
    "ledger_path",
    "trace_sha256",
    "ledger_sha256",
    "trace_id",
    "ledger_id",
    "request_id",
    "attempt_id",
}
PHASE_KEYS = {
    "name",
    "outcome",
    "started_at_utc",
    "finished_at_utc",
    "started_monotonic_ns",
    "finished_monotonic_ns",
    "bytes_read",
    "bytes_written",
    "bytes_network",
    "reason",
    "evidence_sha256",
}
TERMINAL_KEYS = {
    "type",
    "observed_at_utc",
    "observed_monotonic_ns",
    "boundary",
    "response_sha256",
    "response_bytes",
    "semantic_validator_id",
    "semantic_validator_sha256",
    "failure_class",
    "reason",
}
ACCOUNTING_KEYS = {
    "currency",
    "request_cost_usd",
    "publication_cost_usd",
    "node_cache_investment_cost_usd",
    "billed_seconds",
    "gpu_active_seconds",
    "gpu_idle_seconds",
    "bytes_read_total",
    "bytes_written_total",
    "bytes_network_total",
}
CLEANUP_KEYS = {
    "generation_id",
    "final_state",
    "dirty",
    "reusable",
    "verified_absent",
    "receipt_sha256",
    "resources_deleted",
    "resources_retained",
    "verified_at_utc",
}
EVIDENCE_KEYS = {"kind", "path", "sha256"}


class MatrixError(ValueError):
    """A plan, receipt, or evidence binding violates the frozen contract."""


def _expect_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MatrixError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise MatrixError(
            f"{label} keys differ; missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise MatrixError(f"{label} is not a canonical identifier")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise MatrixError(f"{label} is not a lowercase SHA-256")
    return value


def _utc(value: Any, label: str) -> str:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise MatrixError(f"{label} is not canonical UTC")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MatrixError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatrixError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise MatrixError(f"{label} must be finite and >= {minimum}")
    return result


def _bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise MatrixError(f"{label} must be boolean")
    return value


def _optional_identifier(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, label)


def _safe_evidence_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise MatrixError(f"{label} must be a nonempty relative path")
    root = root.resolve()
    unresolved = root / value
    if unresolved.is_symlink():
        raise MatrixError(f"{label} must resolve to a regular non-symlink file")
    candidate = unresolved.resolve()
    if candidate != root and root not in candidate.parents:
        raise MatrixError(f"{label} escapes the evidence root")
    if candidate.is_symlink() or not candidate.is_file():
        raise MatrixError(f"{label} must resolve to a regular non-symlink file")
    return candidate


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise MatrixError(f"{label} must be a regular non-symlink file")
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n"):
        raise MatrixError(f"{label} must end in exactly one newline")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MatrixError(f"{label} is not canonical JSON") from exc
    if not isinstance(value, dict) or raw.decode("utf-8") != canonical_json(value) + "\n":
        raise MatrixError(f"{label} is not canonical sorted compact JSON")
    return value


def load_plan(path: Path) -> dict[str, Any]:
    plan = _load_canonical_json(path, "matrix plan")
    return validate_plan(plan, path.parent)


def load_attempts(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise MatrixError("attempt ledger must be a regular non-symlink file")
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise MatrixError("attempt ledger must be nonempty and newline terminated")
    attempts: list[dict[str, Any]] = []
    for index, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line:
            raise MatrixError(f"attempt ledger line {index} is empty")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MatrixError(f"attempt ledger line {index} is invalid JSON") from exc
        if not isinstance(value, dict) or line != canonical_json(value):
            raise MatrixError(f"attempt ledger line {index} is not canonical JSON")
        attempts.append(value)
    return attempts


def write_canonical_json(path: Path, value: Any) -> None:
    if path.exists() and path.is_symlink():
        raise MatrixError("output cannot replace a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def write_attempts(path: Path, attempts: Sequence[dict[str, Any]]) -> None:
    if path.exists() and path.is_symlink():
        raise MatrixError("attempt output cannot replace a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(canonical_json(value) + "\n" for value in attempts),
        encoding="utf-8",
    )


def validate_plan(plan: Any, plan_root: Path) -> dict[str, Any]:
    plan = _expect_keys(plan, PLAN_KEYS, "plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise MatrixError("plan schema is unsupported")
    for key in ("plan_id", "task_id"):
        _identifier(plan[key], f"plan.{key}")
    if plan["task_id"] != "catalog-switch-storage-cache-matrix":
        raise MatrixError("plan task_id is not the task owner")
    if plan["evidence_classification"] not in EVIDENCE_CLASSES:
        raise MatrixError("plan evidence classification is not canonical")
    _utc(plan["created_at_utc"], "plan.created_at_utc")
    if not isinstance(plan["purpose"], str) or not plan["purpose"].strip():
        raise MatrixError("plan purpose must be nonempty")
    if not isinstance(plan["code_revision"], str) or COMMIT_RE.fullmatch(
        plan["code_revision"]
    ) is None:
        raise MatrixError("plan code_revision must be a full Git commit")

    metric = _expect_keys(plan["metric_contract"], METRIC_KEYS, "metric contract")
    metric_path = _safe_evidence_path(plan_root, metric["path"], "metric contract path")
    if _file_sha256(metric_path) != _sha256(metric["sha256"], "metric contract sha256"):
        raise MatrixError("metric contract file differs from its pinned SHA-256")
    if metric["t0_boundary"] != T0_BOUNDARY or metric["terminal_boundary"] != TERMINAL_BOUNDARY:
        raise MatrixError("plan weakens the reviewed request-SLO boundaries")

    if not isinstance(plan["artifacts"], list) or not plan["artifacts"]:
        raise MatrixError("plan requires at least one artifact")
    artifacts: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str, str, int]] = set()
    for index, raw in enumerate(plan["artifacts"]):
        artifact = _expect_keys(raw, ARTIFACT_KEYS, f"artifact {index}")
        for key in (
            "model_id",
            "model_version",
            "artifact_id",
            "artifact_version",
            "payload_id",
        ):
            _identifier(artifact[key], f"artifact {index}.{key}")
        _sha256(artifact["sha256"], f"artifact {index}.sha256")
        _sha256(
            artifact["publication_receipt_sha256"],
            f"artifact {index}.publication_receipt_sha256",
        )
        _integer(artifact["bytes"], f"artifact {index}.bytes", 1)
        if artifact["strategy_default"] not in {"snapshot", "conventional"}:
            raise MatrixError("artifact strategy_default is not snapshot or conventional")
        if artifact["published_before_t0"] is not True:
            raise MatrixError("one-time catalog publication must be explicitly pre-T0")
        if artifact["model_id"] in artifacts:
            raise MatrixError("plan repeats a model artifact")
        identity = (
            artifact["artifact_version"],
            artifact["sha256"],
            artifact["payload_id"],
            artifact["bytes"],
        )
        if identity in identities:
            raise MatrixError("distinct model rows reuse an ambiguous artifact identity")
        identities.add(identity)
        artifacts[artifact["model_id"]] = artifact

    matrix = _expect_keys(plan["matrix"], MATRIX_KEYS, "matrix")
    if matrix["one_variable_per_cohort"] is not True:
        raise MatrixError("matrix must freeze one variable per cohort")
    if matrix["shared_mutable_state"] is not False:
        raise MatrixError("matrix cannot permit shared mutable state")
    if not isinstance(matrix["cells"], list) or not matrix["cells"]:
        raise MatrixError("matrix cells must be nonempty")
    cell_ids: set[str] = set()
    cells: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(matrix["cells"]):
        cell = _expect_keys(raw, CELL_KEYS, f"matrix cell {index}")
        _identifier(cell["cell_id"], f"matrix cell {index}.cell_id")
        if cell["cell_id"] in cell_ids:
            raise MatrixError("matrix cell IDs are duplicated")
        cell_ids.add(cell["cell_id"])
        if cell["model_id"] not in artifacts:
            raise MatrixError("matrix cell references an unknown model")
        if cell["tier"] not in TIERS or cell["cohort"] not in COHORTS:
            raise MatrixError("matrix cell uses an unknown tier or cohort")
        _integer(cell["minimum_attempts"], "matrix cell minimum_attempts", 1)
        identity = (cell["model_id"], cell["tier"], cell["cohort"])
        if identity in cells:
            raise MatrixError("matrix repeats a model/tier/cohort cell")
        cells.add(identity)
    if {tier for _, tier, _ in cells} != set(TIERS):
        raise MatrixError("matrix must include local NVMe, attached block/PVC, and remote tiers")
    if {cohort for _, _, cohort in cells} != set(COHORTS):
        raise MatrixError("matrix does not include every required cache/adversary cohort")
    for model_id in artifacts:
        model_tiers = {tier for model, tier, _ in cells if model == model_id}
        if model_tiers != set(TIERS):
            raise MatrixError(
                f"model {model_id!r} is not byte-matched across all three storage tiers"
            )
    if plan["evidence_classification"] == "measured-live-product-slo" and any(
        cell["minimum_attempts"] < 20 for cell in matrix["cells"]
    ):
        raise MatrixError("measured-live matrix cells require at least 20 attempts for p95")

    environment = _expect_keys(
        plan["environment_requirements"], ENV_REQ_KEYS, "environment requirements"
    )
    if environment["allowed_projects"] != sorted(ALLOWED_PROJECTS):
        raise MatrixError("plan project allowlist differs from the epic")
    if not isinstance(environment["resource_prefix"], str) or not environment[
        "resource_prefix"
    ].startswith("mlsp-csw-"):
        raise MatrixError("plan resource prefix is not broker-owned")
    for key in (
        "gpu_required",
        "prefer_preemptible",
        "local_nvme_requires_verified_entitlement",
    ):
        _bool(environment[key], f"environment requirements.{key}")
    if environment["local_nvme_requires_verified_entitlement"] is not True:
        raise MatrixError("local-NVMe entitlement gate cannot be disabled")

    cost = _expect_keys(plan["cost_plan"], COST_PLAN_KEYS, "cost plan")
    if cost["currency"] != "USD":
        raise MatrixError("cost plan currency must be USD")
    _number(cost["expected_duration_hours"], "expected duration", 0.000001)
    _number(cost["budget_usd"], "budget", 0.000001)
    if not isinstance(cost["price_source"], str) or not cost["price_source"].strip():
        raise MatrixError("cost plan requires a price source")

    cleanup = _expect_keys(plan["cleanup_plan"], CLEANUP_PLAN_KEYS, "cleanup plan")
    _identifier(cleanup["owner"], "cleanup owner")
    _number(cleanup["ttl_hours"], "cleanup ttl_hours", 0.000001)
    if cleanup["exact_id_only"] is not True:
        raise MatrixError("cleanup must be exact-ID only")
    if cleanup["dirty_generation_policy"] != "delete-and-verify-absent":
        raise MatrixError("dirty cache generations must be deleted and proved absent")

    boltz = _expect_keys(plan["boltz_external_tmp"], BOLTZ_PLAN_KEYS, "Boltz plan")
    _bool(boltz["enabled"], "Boltz enabled")
    if boltz["enabled"]:
        contract = _safe_evidence_path(plan_root, boltz["contract_path"], "Boltz contract")
        if _file_sha256(contract) != _sha256(
            boltz["contract_sha256"], "Boltz contract sha256"
        ):
            raise MatrixError("Boltz external-/tmp contract digest differs")
        if boltz["required_hit_cohort"] != "boltz_external_tmp_hit":
            raise MatrixError("Boltz hit cohort is not canonical")
        if boltz["required_miss_cohort"] != "boltz_external_tmp_clone_miss":
            raise MatrixError("Boltz miss cohort is not canonical")
        boltz_cells = {
            (cell["model_id"], cell["cohort"]) for cell in matrix["cells"]
        }
        if (
            ("boltz2", "boltz_external_tmp_hit") not in boltz_cells
            or ("boltz2", "boltz_external_tmp_clone_miss") not in boltz_cells
        ):
            raise MatrixError("Boltz plan lacks exact boltz2 hit and clone/miss cells")
    return plan


def _validate_artifact(value: Any, planned: dict[str, Any], label: str) -> dict[str, Any]:
    artifact = _expect_keys(value, ATTEMPT_ARTIFACT_KEYS, label)
    for key in (
        "model_id",
        "model_version",
        "artifact_id",
        "artifact_version",
        "payload_id",
    ):
        _identifier(artifact[key], f"{label}.{key}")
    _sha256(artifact["sha256"], f"{label}.sha256")
    _integer(artifact["bytes"], f"{label}.bytes", 1)
    expected = {key: planned[key] for key in ATTEMPT_ARTIFACT_KEYS}
    if artifact != expected:
        raise MatrixError(f"{label} is not byte/version matched to the plan")
    return artifact


def _validate_cache(value: Any, artifact: dict[str, Any], label: str) -> dict[str, Any]:
    cache = _expect_keys(value, CACHE_KEYS, label)
    if cache["state"] not in CACHE_STATES:
        raise MatrixError(f"{label}.state is not canonical")
    _identifier(cache["generation_id"], f"{label}.generation_id")
    if cache["artifact_version"] != artifact["artifact_version"]:
        raise MatrixError(f"{label} version differs from the requested artifact")
    if cache["artifact_sha256"] != artifact["sha256"]:
        raise MatrixError(f"{label} digest differs from the requested artifact")
    if cache["state"] == "hit":
        _number(cache["age_seconds"], f"{label}.age_seconds")
    elif cache["age_seconds"] is not None:
        raise MatrixError(f"{label}.age_seconds must be null for a non-hit")
    _number(cache["publication_investment_seconds"], "publication investment")
    _number(cache["node_cache_investment_seconds"], "node-cache investment")
    _bool(cache["dirty_before_t0"], f"{label}.dirty_before_t0")
    _bool(cache["cow_first_write_expected"], f"{label}.cow_first_write_expected")
    if cache["shared_mutable_state"] is not False:
        raise MatrixError("attempt declares shared mutable cache state")
    return cache


def _validate_concurrency(value: Any, attempt_id: str, cohort: str) -> dict[str, Any]:
    concurrency = _expect_keys(value, CONCURRENCY_KEYS, "concurrency")
    group_id = _optional_identifier(concurrency["group_id"], "concurrency.group_id")
    _identifier(concurrency["mutable_namespace_id"], "mutable namespace")
    if not isinstance(concurrency["peer_attempt_ids"], list):
        raise MatrixError("peer_attempt_ids must be a list")
    peers = [_identifier(item, "peer attempt ID") for item in concurrency["peer_attempt_ids"]]
    if len(peers) != len(set(peers)) or attempt_id in peers:
        raise MatrixError("concurrent peer IDs are duplicated or self-referential")
    if concurrency["source_read_only"] is not True:
        raise MatrixError("concurrent cohorts require a read-only publication source")
    if cohort == "concurrent_fetch":
        if group_id is None or not peers:
            raise MatrixError("concurrent-fetch attempt lacks its group or peers")
    elif group_id is not None or peers:
        raise MatrixError("non-concurrent attempt declares concurrent peers")
    return concurrency


def _validate_environment(value: Any, evidence_class: str, tier: str) -> dict[str, Any]:
    environment = _expect_keys(value, ENVIRONMENT_KEYS, "environment")
    for key in ("provider", "project_id", "region", "storage_medium", "filesystem"):
        _identifier(environment[key], f"environment.{key}")
    for key in ("node_id", "gpu_type", "storage_resource_id"):
        _optional_identifier(environment[key], f"environment.{key}")
    _integer(environment["gpu_count"], "environment.gpu_count")
    _bool(environment["preemptible"], "environment.preemptible")
    _bool(
        environment["local_nvme_entitlement_verified"],
        "environment.local_nvme_entitlement_verified",
    )
    if not isinstance(environment["mount_options"], list) or not all(
        isinstance(item, str) and item for item in environment["mount_options"]
    ):
        raise MatrixError("environment.mount_options must contain strings")
    if not isinstance(environment["local_nvme_devices"], list) or not all(
        isinstance(item, str) and item.startswith("/dev/nvme")
        for item in environment["local_nvme_devices"]
    ):
        raise MatrixError("environment.local_nvme_devices is malformed")
    image = environment["image_digest"]
    if image is not None and (
        not isinstance(image, str) or IMAGE_RE.fullmatch(image) is None
    ):
        raise MatrixError("environment.image_digest is not digest pinned")
    if not isinstance(environment["code_revision"], str) or COMMIT_RE.fullmatch(
        environment["code_revision"]
    ) is None:
        raise MatrixError("environment.code_revision must be a full Git commit")
    _sha256(environment["config_sha256"], "environment.config_sha256")
    if evidence_class == "measured-live-product-slo":
        expected_region = ALLOWED_PROJECTS.get(environment["project_id"])
        if expected_region is None or environment["region"] != expected_region:
            raise MatrixError("measured attempt is outside the epic project/region allowlist")
        if environment["node_id"] is None:
            raise MatrixError("measured attempt lacks its task-owned node ID")
        allowed_media = {
            "local_nvme": {"local_nvme"},
            "attached_block_pvc": {"network_ssd", "block_pvc"},
            "remote_artifact": {"object_storage", "remote_http_artifact"},
        }
        if environment["storage_medium"] not in allowed_media[tier]:
            raise MatrixError("measured storage medium is inconsistent with its tier")
    if tier == "local_nvme":
        if environment["storage_medium"] != "local_nvme":
            raise MatrixError("local-NVMe tier is mislabeled by the environment")
        if evidence_class == "measured-live-product-slo" and (
            environment["local_nvme_entitlement_verified"] is not True
            or not environment["local_nvme_devices"]
        ):
            raise MatrixError("measured local-NVMe result lacks entitlement/device proof")
    return environment


def _validate_ownership(value: Any, environment: dict[str, Any], evidence_class: str) -> dict[str, Any]:
    ownership = _expect_keys(value, OWNERSHIP_KEYS, "ownership")
    if ownership["owner_task_id"] != "catalog-switch-storage-cache-matrix":
        raise MatrixError("attempt ownership has a different task owner")
    if not isinstance(ownership["resource_prefix"], str) or not ownership[
        "resource_prefix"
    ].startswith("mlsp-csw-"):
        raise MatrixError("attempt resource prefix is not broker-owned")
    if ownership["dedicated"] is not True:
        raise MatrixError("attempt resources are not explicitly dedicated")
    if not isinstance(ownership["resources"], list):
        raise MatrixError("ownership.resources must be a list")
    identities: set[tuple[str, str]] = set()
    for index, raw in enumerate(ownership["resources"]):
        resource = _expect_keys(raw, RESOURCE_KEYS, f"owned resource {index}")
        for key in RESOURCE_KEYS:
            _identifier(resource[key], f"owned resource {index}.{key}")
        if evidence_class == "measured-live-product-slo" and (
            resource["project_id"] != environment["project_id"]
            or resource["region"] != environment["region"]
        ):
            raise MatrixError("owned live resource is outside the attempt project/region")
        identity = (resource["kind"], resource["id"])
        if identity in identities:
            raise MatrixError("owned resource is duplicated")
        identities.add(identity)
    if evidence_class == "measured-live-product-slo" and not identities:
        raise MatrixError("measured attempt lacks exact task-owned resource IDs")
    return ownership


def _validate_request(value: Any) -> dict[str, Any]:
    request = _expect_keys(value, REQUEST_KEYS, "request")
    if request["t0_boundary"] != T0_BOUNDARY:
        raise MatrixError("attempt does not use the shared external T0")
    _utc(request["accepted_at_utc"], "request.accepted_at_utc")
    _integer(request["accepted_monotonic_ns"], "request.accepted_monotonic_ns", 1)
    _identifier(request["input_id"], "request.input_id")
    _sha256(request["input_sha256"], "request.input_sha256")
    _integer(request["input_bytes"], "request.input_bytes", 1)
    return request


def _validate_binding(value: Any, request_id: str, attempt_id: str) -> dict[str, Any]:
    binding = _expect_keys(value, BINDING_KEYS, "request-SLO binding")
    for key in ("trace_path", "ledger_path"):
        if not isinstance(binding[key], str) or not binding[key] or Path(binding[key]).is_absolute():
            raise MatrixError(f"request-SLO binding {key} must be relative")
    for key in ("trace_sha256", "ledger_sha256"):
        _sha256(binding[key], f"request-SLO binding {key}")
    for key in ("trace_id", "ledger_id", "request_id", "attempt_id"):
        _identifier(binding[key], f"request-SLO binding {key}")
    if binding["request_id"] != request_id or binding["attempt_id"] != attempt_id:
        raise MatrixError("request-SLO binding identity differs from the receipt")
    return binding


def _validate_phases(value: Any, t0: int, terminal_ns: int) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(PHASES):
        raise MatrixError("attempt must contain every detailed phase exactly once")
    phases: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(value):
        phase = _expect_keys(raw, PHASE_KEYS, f"phase {index}")
        if phase["name"] != PHASES[index]:
            raise MatrixError("detailed phases are missing, duplicated, or reordered")
        if phase["outcome"] not in OUTCOMES:
            raise MatrixError(f"phase {phase['name']} outcome is not canonical")
        finish = _integer(
            phase["finished_monotonic_ns"],
            f"phase {phase['name']} finished_monotonic_ns",
            1,
        )
        _utc(phase["finished_at_utc"], f"phase {phase['name']} finished_at_utc")
        if finish < t0 or finish > terminal_ns:
            raise MatrixError(f"phase {phase['name']} is outside T0-to-terminal")
        if phase["outcome"] == "skipped":
            if phase["started_monotonic_ns"] is not None or phase["started_at_utc"] is not None:
                raise MatrixError("skipped phase cannot have a start timestamp")
        else:
            start = _integer(
                phase["started_monotonic_ns"],
                f"phase {phase['name']} started_monotonic_ns",
                1,
            )
            _utc(phase["started_at_utc"], f"phase {phase['name']} started_at_utc")
            if start < t0 or finish <= start:
                raise MatrixError(f"phase {phase['name']} has a noncausal duration")
        for key in ("bytes_read", "bytes_written", "bytes_network"):
            _integer(phase[key], f"phase {phase['name']}.{key}")
        if not isinstance(phase["reason"], str) or not phase["reason"].strip():
            raise MatrixError(f"phase {phase['name']} reason must be nonempty")
        _sha256(phase["evidence_sha256"], f"phase {phase['name']} evidence_sha256")
        phases[phase["name"]] = phase
    for name, dependencies in PHASE_DEPENDENCIES.items():
        phase = phases[name]
        start_or_finish = (
            phase["started_monotonic_ns"]
            if phase["started_monotonic_ns"] is not None
            else phase["finished_monotonic_ns"]
        )
        for dependency in dependencies:
            if phases[dependency]["finished_monotonic_ns"] > start_or_finish:
                raise MatrixError(f"phase {name} precedes causal dependency {dependency}")
    return phases


def _validate_terminal(value: Any, t0: int) -> dict[str, Any]:
    terminal = _expect_keys(value, TERMINAL_KEYS, "terminal")
    if terminal["type"] not in TERMINAL_TYPES:
        raise MatrixError("terminal type is not canonical")
    _utc(terminal["observed_at_utc"], "terminal.observed_at_utc")
    observed = _integer(terminal["observed_monotonic_ns"], "terminal monotonic", 1)
    if observed <= t0:
        raise MatrixError("product terminal does not follow T0")
    if terminal["type"] == "response.validated":
        if terminal["boundary"] != TERMINAL_BOUNDARY:
            raise MatrixError("successful attempt weakens the product terminal boundary")
        _sha256(terminal["response_sha256"], "terminal.response_sha256")
        _integer(terminal["response_bytes"], "terminal.response_bytes", 1)
        _identifier(terminal["semantic_validator_id"], "semantic validator ID")
        _sha256(terminal["semantic_validator_sha256"], "semantic validator sha256")
        if terminal["failure_class"] is not None or terminal["reason"] != "semantic-pass":
            raise MatrixError("successful terminal contains failure state")
    else:
        if terminal["boundary"] is not None:
            raise MatrixError("failed attempt cannot claim a valid-response boundary")
        for key in (
            "response_sha256",
            "response_bytes",
            "semantic_validator_id",
            "semantic_validator_sha256",
        ):
            if terminal[key] is not None:
                raise MatrixError("failed terminal contains response validation state")
        if terminal["failure_class"] not in FAILURE_CLASSES:
            raise MatrixError("failed terminal has an unknown failure class")
        if not isinstance(terminal["reason"], str) or not terminal["reason"].strip():
            raise MatrixError("failed terminal reason must be nonempty")
    return terminal


def _validate_accounting(value: Any, phases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    accounting = _expect_keys(value, ACCOUNTING_KEYS, "accounting")
    if accounting["currency"] != "USD":
        raise MatrixError("attempt accounting currency must be USD")
    for key in (
        "request_cost_usd",
        "publication_cost_usd",
        "node_cache_investment_cost_usd",
        "billed_seconds",
        "gpu_active_seconds",
        "gpu_idle_seconds",
    ):
        _number(accounting[key], f"accounting.{key}")
    expected = {
        "bytes_read_total": sum(phase["bytes_read"] for phase in phases.values()),
        "bytes_written_total": sum(phase["bytes_written"] for phase in phases.values()),
        "bytes_network_total": sum(phase["bytes_network"] for phase in phases.values()),
    }
    for key, total in expected.items():
        if _integer(accounting[key], f"accounting.{key}") != total:
            raise MatrixError(f"accounting {key} omits or double-counts phase bytes")
    return accounting


def _validate_cleanup(value: Any, cache: dict[str, Any], cohort: str) -> dict[str, Any]:
    cleanup = _expect_keys(value, CLEANUP_KEYS, "cleanup")
    if cleanup["generation_id"] != cache["generation_id"]:
        raise MatrixError("cleanup generation differs from the cache generation")
    if cleanup["final_state"] not in {"ABSENT", "SEALED_RETAINED"}:
        raise MatrixError("cleanup final state is not canonical")
    for key in ("dirty", "reusable", "verified_absent"):
        _bool(cleanup[key], f"cleanup.{key}")
    _sha256(cleanup["receipt_sha256"], "cleanup.receipt_sha256")
    _utc(cleanup["verified_at_utc"], "cleanup.verified_at_utc")
    for key in ("resources_deleted", "resources_retained"):
        if not isinstance(cleanup[key], list) or len(cleanup[key]) != len(set(cleanup[key])):
            raise MatrixError(f"cleanup.{key} must be a unique list")
        for item in cleanup[key]:
            _identifier(item, f"cleanup.{key} identity")
    dirty = cache["dirty_before_t0"] or cache["state"] == "corrupt" or cohort == "corruption"
    if dirty and (
        cleanup["final_state"] != "ABSENT"
        or cleanup["verified_absent"] is not True
        or cleanup["reusable"] is not False
    ):
        raise MatrixError("dirty/corrupt generation was not deleted and proved absent")
    if cleanup["final_state"] == "ABSENT" and cleanup["verified_absent"] is not True:
        raise MatrixError("ABSENT cleanup state lacks an absence proof")
    if cleanup["final_state"] == "SEALED_RETAINED" and (
        cleanup["dirty"] or not cleanup["reusable"] or cleanup["verified_absent"]
    ):
        raise MatrixError("retained generation is not clean, sealed, and reusable")
    return cleanup


def _validate_supporting_evidence(value: Any, evidence_root: Path) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise MatrixError("attempt requires supporting evidence")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        item = _expect_keys(raw, EVIDENCE_KEYS, f"supporting evidence {index}")
        _identifier(item["kind"], f"supporting evidence {index}.kind")
        path = _safe_evidence_path(evidence_root, item["path"], f"supporting evidence {index}.path")
        if _file_sha256(path) != _sha256(item["sha256"], f"supporting evidence {index}.sha256"):
            raise MatrixError("supporting evidence digest differs")
        identity = (item["kind"], item["path"])
        if identity in seen:
            raise MatrixError("supporting evidence is duplicated")
        seen.add(identity)
    return value


def _validate_attempt_shape(
    value: Any,
    plan: dict[str, Any],
    plan_sha256: str,
    evidence_root: Path,
    cell_by_id: dict[str, dict[str, Any]],
    artifact_by_model: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    attempt = _expect_keys(value, ATTEMPT_KEYS, "attempt")
    if attempt["schema"] != ATTEMPT_SCHEMA:
        raise MatrixError("attempt schema is unsupported")
    if attempt["plan_id"] != plan["plan_id"] or attempt["plan_sha256"] != plan_sha256:
        raise MatrixError("attempt is not pinned to the exact plan")
    _identifier(attempt["attempt_id"], "attempt.attempt_id")
    _identifier(attempt["request_id"], "attempt.request_id")
    _identifier(attempt["cell_id"], "attempt.cell_id")
    if attempt["evidence_classification"] != plan["evidence_classification"]:
        raise MatrixError("attempt evidence classification differs from the plan")
    if attempt["tier"] not in TIERS or attempt["cohort"] not in COHORTS:
        raise MatrixError("attempt tier or cohort is unknown")
    cell = cell_by_id.get(attempt["cell_id"])
    if cell is None:
        raise MatrixError("attempt references an unknown matrix cell")
    if (cell["tier"], cell["cohort"]) != (attempt["tier"], attempt["cohort"]):
        raise MatrixError("attempt tier/cohort differs from its matrix cell")
    planned_artifact = artifact_by_model[cell["model_id"]]
    artifact = _validate_artifact(attempt["artifact"], planned_artifact, "attempt artifact")
    cache = _validate_cache(attempt["cache"], artifact, "cache")
    concurrency = _validate_concurrency(
        attempt["concurrency"], attempt["attempt_id"], attempt["cohort"]
    )
    environment = _validate_environment(
        attempt["environment"], attempt["evidence_classification"], attempt["tier"]
    )
    ownership = _validate_ownership(
        attempt["ownership"], environment, attempt["evidence_classification"]
    )
    if ownership["resource_prefix"] != plan["environment_requirements"]["resource_prefix"]:
        raise MatrixError("attempt resource prefix differs from the frozen plan")
    if environment["code_revision"] != plan["code_revision"]:
        raise MatrixError("attempt code revision differs from the frozen plan")
    if (
        attempt["evidence_classification"] == "measured-live-product-slo"
        and plan["environment_requirements"]["gpu_required"]
        and environment["gpu_count"] < 1
    ):
        raise MatrixError("measured model attempt lacks the required real GPU")
    request = _validate_request(attempt["request"])
    binding = _validate_binding(
        attempt["request_slo_binding"], attempt["request_id"], attempt["attempt_id"]
    )
    terminal = _validate_terminal(attempt["terminal"], request["accepted_monotonic_ns"])
    phases = _validate_phases(
        attempt["phases"],
        request["accepted_monotonic_ns"],
        terminal["observed_monotonic_ns"],
    )
    accounting = _validate_accounting(attempt["accounting"], phases)
    cleanup = _validate_cleanup(attempt["cleanup"], cache, attempt["cohort"])
    deleted = set(cleanup["resources_deleted"])
    retained = set(cleanup["resources_retained"])
    owned_ids = {resource["id"] for resource in ownership["resources"]}
    if deleted & retained or deleted | retained != owned_ids:
        raise MatrixError("cleanup resource disposition differs from exact ownership")
    _validate_supporting_evidence(attempt["supporting_evidence"], evidence_root)

    if terminal["type"] == "response.validated":
        if phases["inference"]["outcome"] != "completed" or phases[
            "semantic_validation"
        ]["outcome"] != "completed":
            raise MatrixError("valid response lacks completed inference and semantic validation")
    elif not any(phase["outcome"] == "failed" for phase in phases.values()):
        raise MatrixError("failed attempt does not expose a failed detailed phase")

    expected_cache_state = {
        "hot": "hit",
        "warm": "hit",
        "cold": "miss",
        "eviction_repopulation": "evicted",
        "concurrent_fetch": "miss",
        "corruption": "corrupt",
        "boltz_external_tmp_hit": "hit",
        "boltz_external_tmp_clone_miss": "miss",
    }[attempt["cohort"]]
    if cache["state"] != expected_cache_state:
        raise MatrixError("cache state is inconsistent with the frozen cohort")

    restore = phases["restore"]["outcome"] == "completed"
    conventional = phases["conventional_load"]["outcome"] == "completed"
    if terminal["type"] == "response.validated" and restore == conventional:
        raise MatrixError("success must execute exactly one restore or conventional-load path")
    if attempt["cohort"] == "boltz_external_tmp_hit":
        if artifact["model_id"] != "boltz2":
            raise MatrixError("Boltz external-/tmp cohort is bound to a different model")
        if cache["state"] != "hit" or phases["clone"]["outcome"] != "skipped":
            raise MatrixError("Boltz external-/tmp hit is not a verified clone-free hit")
    if attempt["cohort"] == "boltz_external_tmp_clone_miss":
        if artifact["model_id"] != "boltz2":
            raise MatrixError("Boltz external-/tmp cohort is bound to a different model")
        clone = phases["clone"]
        if cache["state"] != "miss" or clone["outcome"] != "completed":
            raise MatrixError("Boltz external-/tmp miss did not clone after T0")
        if clone["bytes_read"] <= 0 or clone["bytes_written"] <= 0:
            raise MatrixError("Boltz external-/tmp clone omits byte accounting")
        if clone["started_monotonic_ns"] < request["accepted_monotonic_ns"]:
            raise MatrixError("Boltz external-/tmp clone was moved before T0")
    return {
        "raw": attempt,
        "artifact": artifact,
        "cache": cache,
        "concurrency": concurrency,
        "environment": environment,
        "ownership": ownership,
        "request": request,
        "binding": binding,
        "phases": phases,
        "terminal": terminal,
        "accounting": accounting,
        "cleanup": cleanup,
    }


def _validate_request_slo_bindings(
    shaped: Sequence[dict[str, Any]], evidence_root: Path
) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in shaped:
        binding = item["binding"]
        groups[(binding["trace_path"], binding["ledger_path"])].append(item)
    for (trace_name, ledger_name), members in groups.items():
        trace_path = _safe_evidence_path(evidence_root, trace_name, "bound trace")
        ledger_path = _safe_evidence_path(evidence_root, ledger_name, "bound ledger")
        binding = members[0]["binding"]
        if _file_sha256(trace_path) != binding["trace_sha256"]:
            raise MatrixError("bound request-SLO trace digest differs")
        if _file_sha256(ledger_path) != binding["ledger_sha256"]:
            raise MatrixError("bound request-SLO ledger digest differs")
        try:
            trace = load_trace(trace_path)
            events = load_ledger(ledger_path)
            results = validate_ledger(events, trace)
        except HarnessError as exc:
            raise MatrixError(f"bound request-SLO evidence is invalid: {exc}") from exc
        if trace["trace_id"] != binding["trace_id"]:
            raise MatrixError("bound trace identity differs")
        ledger_ids = {event["ledger_id"] for event in events}
        if ledger_ids != {binding["ledger_id"]}:
            raise MatrixError("bound ledger identity differs")
        result_by_attempt = {result["attempt_id"]: result for result in results}
        request_by_attempt = {
            request["attempt_id"]: request for request in trace["requests"]
        }
        event_by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            event_by_attempt[event["attempt_id"]].append(event)
        for member in members:
            receipt = member["raw"]
            current = member["binding"]
            for key in ("trace_sha256", "ledger_sha256", "trace_id", "ledger_id"):
                if current[key] != binding[key]:
                    raise MatrixError("receipts disagree about a shared SLO evidence pair")
            result = result_by_attempt.get(receipt["attempt_id"])
            if result is None:
                raise MatrixError("receipt attempt is absent from its bound request-SLO ledger")
            if result["request_id"] != receipt["request_id"]:
                raise MatrixError("receipt request identity differs from request-SLO evidence")
            if result["model_id"] != member["artifact"]["model_id"] or result[
                "artifact_version"
            ] != member["artifact"]["artifact_version"]:
                raise MatrixError("receipt target identity differs from request-SLO evidence")
            trace_request = request_by_attempt[receipt["attempt_id"]]
            expected_target = {
                "model_id": member["artifact"]["model_id"],
                "model_version": member["artifact"]["model_version"],
                "artifact_id": member["artifact"]["artifact_id"],
                "artifact_version": member["artifact"]["artifact_version"],
                "artifact_sha256": member["artifact"]["sha256"],
            }
            if trace_request["target"] != expected_target:
                raise MatrixError("receipt artifact identity differs from its bound trace target")
            expected_input = {
                "input_id": member["request"]["input_id"],
                "payload_sha256": member["request"]["input_sha256"],
                "input_bytes": member["request"]["input_bytes"],
            }
            if any(
                trace_request["input"][key] != value
                for key, value in expected_input.items()
            ):
                raise MatrixError("receipt input identity differs from its bound trace")
            attempt_events = event_by_attempt[receipt["attempt_id"]]
            acceptance = attempt_events[0]
            terminal = next(
                event
                for event in attempt_events
                if event["event_type"] in {"response.validated", "attempt.failed"}
            )
            if (
                acceptance["observed_monotonic_ns"]
                != member["request"]["accepted_monotonic_ns"]
                or acceptance["observed_at_utc"] != member["request"]["accepted_at_utc"]
            ):
                raise MatrixError("receipt T0 does not equal the external recorder T0")
            if (
                terminal["observed_monotonic_ns"]
                != member["terminal"]["observed_monotonic_ns"]
                or terminal["observed_at_utc"] != member["terminal"]["observed_at_utc"]
            ):
                raise MatrixError("receipt terminal does not equal the external recorder terminal")
            success = member["terminal"]["type"] == "response.validated"
            if success != result["success"]:
                raise MatrixError("receipt success differs from request-SLO evidence")
            slo_resource_ids = {
                resource["id"]
                for resource in result["ownership"]["resources"]
            }
            receipt_resource_ids = {
                resource["id"] for resource in member["ownership"]["resources"]
            }
            if slo_resource_ids != receipt_resource_ids:
                raise MatrixError("receipt resource IDs differ from request-SLO ownership")


def _validate_concurrent_groups(shaped: Sequence[dict[str, Any]]) -> None:
    by_id = {item["raw"]["attempt_id"]: item for item in shaped}
    namespaces: dict[str, str] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in shaped:
        attempt_id = item["raw"]["attempt_id"]
        namespace = item["concurrency"]["mutable_namespace_id"]
        if namespace in namespaces:
            raise MatrixError(
                f"mutable namespace {namespace!r} is shared by attempts "
                f"{namespaces[namespace]!r} and {attempt_id!r}"
            )
        namespaces[namespace] = attempt_id
        group_id = item["concurrency"]["group_id"]
        if group_id is not None:
            groups[group_id].append(item)
    for group_id, members in groups.items():
        member_ids = {member["raw"]["attempt_id"] for member in members}
        if len(member_ids) < 2:
            raise MatrixError(f"concurrent group {group_id!r} has fewer than two attempts")
        models = {member["artifact"]["model_id"] for member in members}
        if len(models) < 2:
            raise MatrixError("concurrent cache-pressure group does not use distinct models")
        for member in members:
            peers = set(member["concurrency"]["peer_attempt_ids"])
            if peers != member_ids - {member["raw"]["attempt_id"]}:
                raise MatrixError("concurrent group peer identities are incomplete")
            for peer in peers:
                if peer not in by_id:
                    raise MatrixError("concurrent peer is missing from the attempt ledger")
        intervals = [
            (
                member["phases"]["artifact_fetch"]["started_monotonic_ns"],
                member["phases"]["artifact_fetch"]["finished_monotonic_ns"],
            )
            for member in members
        ]
        if any(start is None for start, _ in intervals):
            raise MatrixError("concurrent fetch group contains a skipped fetch")
        if max(start for start, _ in intervals) >= min(finish for _, finish in intervals):
            raise MatrixError("concurrent fetch evidence does not overlap in time")


def _validate_generation_lifecycle(shaped: Sequence[dict[str, Any]]) -> None:
    dirty_generations: set[str] = set()
    for item in sorted(shaped, key=lambda member: member["request"]["accepted_monotonic_ns"]):
        generation = item["cache"]["generation_id"]
        if generation in dirty_generations:
            raise MatrixError("a previously dirty/deleted generation was reused")
        cleanup = item["cleanup"]
        if cleanup["dirty"] or item["cache"]["state"] == "corrupt":
            dirty_generations.add(generation)


def validate_matrix(
    plan: dict[str, Any],
    attempts: Sequence[dict[str, Any]],
    evidence_root: Path,
) -> list[dict[str, Any]]:
    plan = validate_plan(plan, evidence_root)
    if not attempts:
        raise MatrixError("matrix attempt ledger is empty")
    plan_sha256 = canonical_sha256(plan)
    cells = {cell["cell_id"]: cell for cell in plan["matrix"]["cells"]}
    artifacts = {artifact["model_id"]: artifact for artifact in plan["artifacts"]}
    shaped = [
        _validate_attempt_shape(
            attempt, plan, plan_sha256, evidence_root, cells, artifacts
        )
        for attempt in attempts
    ]
    attempt_ids = [item["raw"]["attempt_id"] for item in shaped]
    request_ids = [item["raw"]["request_id"] for item in shaped]
    if len(attempt_ids) != len(set(attempt_ids)) or len(request_ids) != len(set(request_ids)):
        raise MatrixError("attempt or request identity is duplicated")
    counts = Counter(item["raw"]["cell_id"] for item in shaped)
    missing = {
        cell_id: cell["minimum_attempts"] - counts[cell_id]
        for cell_id, cell in cells.items()
        if counts[cell_id] < cell["minimum_attempts"]
    }
    if missing:
        raise MatrixError(f"matrix is incomplete; missing attempt counts={missing}")
    _validate_request_slo_bindings(shaped, evidence_root)
    _validate_concurrent_groups(shaped)
    _validate_generation_lifecycle(shaped)
    if plan["evidence_classification"] == "measured-live-product-slo":
        required_measured_operations = {
            "image_pull",
            "image_unpack",
            "artifact_fetch",
            "volume_attach",
            "volume_mount",
            "clone",
            "copy",
            "hash",
            "first_read",
            "restore",
            "conventional_load",
        }
        completed = {
            name
            for item in shaped
            for name, phase in item["phases"].items()
            if phase["outcome"] == "completed"
        }
        missing_operations = sorted(required_measured_operations - completed)
        if missing_operations:
            raise MatrixError(
                f"measured matrix omits required causal operations: {missing_operations}"
            )
        if not any(
            item["cache"]["cow_first_write_expected"]
            and item["phases"]["clone"]["outcome"] == "completed"
            and item["phases"]["first_read"]["outcome"] == "completed"
            for item in shaped
        ):
            raise MatrixError("measured matrix lacks a clone/COW first-read cohort")
    return shaped


def _distribution(values: Iterable[float]) -> dict[str, Any]:
    ordered = sorted(round(float(value), 9) for value in values)
    result: dict[str, Any] = {
        "sample_count": len(ordered),
        "samples": ordered,
        "estimator": "nearest-rank-on-per-attempt-raw-values/v1",
        "minimum_samples": dict(PERCENTILE_MINIMUMS),
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
    }
    for label, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        result[label] = (
            ordered[math.ceil(percentile * len(ordered)) - 1]
            if len(ordered) >= PERCENTILE_MINIMUMS[label]
            else None
        )
    return result


def _phase_seconds(phase: dict[str, Any]) -> float | None:
    if phase["started_monotonic_ns"] is None:
        return None
    return round(
        (phase["finished_monotonic_ns"] - phase["started_monotonic_ns"])
        / 1_000_000_000,
        9,
    )


def _attempt_result(item: dict[str, Any]) -> dict[str, Any]:
    raw = item["raw"]
    t0 = item["request"]["accepted_monotonic_ns"]
    terminal_ns = item["terminal"]["observed_monotonic_ns"]
    ready = item["phases"]["service_readiness"]["finished_monotonic_ns"]
    localization_starts = [
        phase["started_monotonic_ns"]
        for name, phase in item["phases"].items()
        if name
        in {
            "image_pull",
            "image_unpack",
            "artifact_fetch",
            "volume_attach",
            "volume_mount",
            "clone",
            "copy",
            "hash",
            "first_read",
        }
        and phase["started_monotonic_ns"] is not None
    ]
    localization_seconds = (
        round((ready - min(localization_starts)) / 1_000_000_000, 9)
        if localization_starts and ready >= min(localization_starts)
        else 0.0
    )
    return {
        "attempt_id": raw["attempt_id"],
        "request_id": raw["request_id"],
        "cell_id": raw["cell_id"],
        "model_id": item["artifact"]["model_id"],
        "tier": raw["tier"],
        "cohort": raw["cohort"],
        "cache_state": item["cache"]["state"],
        "cache_age_seconds": item["cache"]["age_seconds"],
        "success": item["terminal"]["type"] == "response.validated",
        "failure_class": item["terminal"]["failure_class"],
        "product_latency_seconds": round((terminal_ns - t0) / 1_000_000_000, 9),
        "request_to_service_ready_seconds": round((ready - t0) / 1_000_000_000, 9),
        "request_causal_localization_seconds": localization_seconds,
        "phases": {
            name: {
                "outcome": phase["outcome"],
                "duration_seconds": _phase_seconds(phase),
                "bytes_read": phase["bytes_read"],
                "bytes_written": phase["bytes_written"],
                "bytes_network": phase["bytes_network"],
            }
            for name, phase in item["phases"].items()
        },
        "accounting": item["accounting"],
        "cleanup": item["cleanup"],
        "environment": item["environment"],
    }


def _cell_aggregate(cell: dict[str, Any], members: Sequence[dict[str, Any]]) -> dict[str, Any]:
    results = [_attempt_result(member) for member in members]
    successes = [result for result in results if result["success"]]
    phase_aggregates: dict[str, Any] = {}
    for phase_name in PHASES:
        phases = [result["phases"][phase_name] for result in results]
        durations = [
            phase["duration_seconds"]
            for phase in phases
            if phase["duration_seconds"] is not None
        ]
        throughputs = []
        for phase in phases:
            duration = phase["duration_seconds"]
            total = phase["bytes_read"] + phase["bytes_written"] + phase["bytes_network"]
            if duration and total:
                throughputs.append(total / duration)
        phase_aggregates[phase_name] = {
            "outcomes": dict(sorted(Counter(phase["outcome"] for phase in phases).items())),
            "duration_seconds": _distribution(durations),
            "throughput_bytes_per_second": _distribution(throughputs),
            "bytes_read": sum(phase["bytes_read"] for phase in phases),
            "bytes_written": sum(phase["bytes_written"] for phase in phases),
            "bytes_network": sum(phase["bytes_network"] for phase in phases),
        }
    return {
        "cell": cell,
        "attempts": len(results),
        "valid_responses": len(successes),
        "failures": len(results) - len(successes),
        "failure_classes": dict(
            sorted(Counter(result["failure_class"] for result in results if not result["success"]).items())
        ),
        "cache_states": dict(sorted(Counter(result["cache_state"] for result in results).items())),
        "product_latency_seconds": _distribution(
            result["product_latency_seconds"] for result in successes
        ),
        "request_to_service_ready_seconds": _distribution(
            result["request_to_service_ready_seconds"] for result in successes
        ),
        "request_causal_localization_seconds": _distribution(
            result["request_causal_localization_seconds"] for result in successes
        ),
        "phase_operations": phase_aggregates,
        "bytes": {
            "read": sum(result["accounting"]["bytes_read_total"] for result in results),
            "written": sum(
                result["accounting"]["bytes_written_total"] for result in results
            ),
            "network": sum(
                result["accounting"]["bytes_network_total"] for result in results
            ),
        },
        "cost_usd": {
            "request": round(
                sum(result["accounting"]["request_cost_usd"] for result in results), 9
            ),
            "publication": round(
                sum(result["accounting"]["publication_cost_usd"] for result in results),
                9,
            ),
            "node_cache_investment": round(
                sum(
                    result["accounting"]["node_cache_investment_cost_usd"]
                    for result in results
                ),
                9,
            ),
        },
        "results": results,
    }


def _simulator_export(
    plan: dict[str, Any], shaped: Sequence[dict[str, Any]], evidence_source: str
) -> dict[str, Any]:
    models: dict[str, Any] = {}
    for artifact in plan["artifacts"]:
        model_id = artifact["model_id"]
        members = [
            item
            for item in shaped
            if item["artifact"]["model_id"] == model_id
            and item["terminal"]["type"] == "response.validated"
        ]
        hot = [item for item in members if item["raw"]["cohort"] == "hot"]
        cold = [item for item in members if item["raw"]["cohort"] != "hot"]
        if not hot or not cold:
            continue
        strategy = artifact["strategy_default"]
        strategy_cold = [
            item
            for item in cold
            if (
                "snapshot"
                if item["phases"]["restore"]["outcome"] == "completed"
                else "conventional"
            )
            == strategy
        ]
        if not strategy_cold:
            continue
        ready_seconds = [
            (
                item["phases"]["service_readiness"]["finished_monotonic_ns"]
                - item["request"]["accepted_monotonic_ns"]
            )
            / 1_000_000_000
            for item in strategy_cold
        ]
        call1 = [_phase_seconds(item["phases"]["inference"]) for item in strategy_cold]
        call2 = [_phase_seconds(item["phases"]["inference"]) for item in hot]
        first_reads = [
            _phase_seconds(item["phases"]["first_read"])
            for item in members
            if _phase_seconds(item["phases"]["first_read"]) is not None
        ]
        conventional_ready = sorted(
            (
                item["phases"]["service_readiness"]["finished_monotonic_ns"]
                - item["request"]["accepted_monotonic_ns"]
            )
            / 1_000_000_000
            for item in cold
            if item["phases"]["conventional_load"]["outcome"] == "completed"
        )
        model_override = {
            "source": evidence_source,
            "evidence_class": plan["evidence_classification"],
            "strategy_default": strategy,
            "ready_seconds": [round(value, 9) for value in ready_seconds],
            "call1_seconds": [round(float(value), 9) for value in call1 if value is not None],
            "call2_seconds": [round(float(value), 9) for value in call2 if value is not None],
            "artifact_bytes": artifact["bytes"],
            "artifact_digest": artifact["sha256"],
            "local_full_read_seconds": (
                round(sorted(first_reads)[len(first_reads) // 2], 9) if first_reads else None
            ),
        }
        if conventional_ready:
            model_override["conventional_ready_seconds"] = round(
                conventional_ready[math.ceil(0.5 * len(conventional_ready)) - 1], 9
            )
        models[model_id] = model_override
    remote_bandwidth = []
    for item in shaped:
        fetch = item["phases"]["artifact_fetch"]
        duration = _phase_seconds(fetch)
        if item["raw"]["tier"] == "remote_artifact" and duration and fetch["bytes_network"]:
            remote_bandwidth.append(fetch["bytes_network"] / duration)
    fleet: dict[str, Any] = {}
    if remote_bandwidth:
        ordered = sorted(remote_bandwidth)
        fleet["l2_fetch_bytes_per_s"] = {
            "value": round(ordered[math.ceil(0.5 * len(ordered)) - 1], 3),
            "source": evidence_source,
        }
    return {
        "schema_version": SIMULATOR_SCHEMA_VERSION,
        "kind": (
            "measured-overrides"
            if plan["evidence_classification"] == "measured-live-product-slo"
            else "synthetic-contract-overrides-not-admissible"
        ),
        "models": models,
        "fleet": fleet,
    }


def _router_export(
    cell_results: Sequence[dict[str, Any]],
    evidence_source: str,
    evidence_classification: str,
) -> dict[str, Any]:
    return {
        "schema": ROUTER_SCHEMA,
        "source": evidence_source,
        "evidence_classification": evidence_classification,
        "cost_semantics": (
            "raw per-attempt request-causal localization spans; phase percentile "
            "summation is forbidden"
        ),
        "cells": [
            {
                "cell_id": result["cell"]["cell_id"],
                "model_id": result["cell"]["model_id"],
                "tier": result["cell"]["tier"],
                "cohort": result["cell"]["cohort"],
                "attempts": result["attempts"],
                "failures": result["failures"],
                "localization_seconds_samples": result[
                    "request_causal_localization_seconds"
                ]["samples"],
                "product_latency_seconds_samples": result["product_latency_seconds"][
                    "samples"
                ],
                "bytes": result["bytes"],
                "request_cost_usd": result["cost_usd"]["request"],
            }
            for result in cell_results
        ],
    }


def _boltz_conclusion(plan: dict[str, Any], shaped: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not plan["boltz_external_tmp"]["enabled"]:
        return {"status": "not_requested"}
    hits = [
        item
        for item in shaped
        if item["raw"]["cohort"] == "boltz_external_tmp_hit"
        and item["terminal"]["type"] == "response.validated"
    ]
    misses = [
        item
        for item in shaped
        if item["raw"]["cohort"] == "boltz_external_tmp_clone_miss"
        and item["terminal"]["type"] == "response.validated"
    ]
    if not hits or not misses:
        return {
            "status": "insufficient_measured_attempts",
            "hit_valid_responses": len(hits),
            "clone_miss_valid_responses": len(misses),
            "projections_are_results": False,
        }
    if plan["evidence_classification"] != "measured-live-product-slo":
        return {
            "status": "synthetic_contract_coverage_not_measurement",
            "hit_valid_responses": len(hits),
            "clone_miss_valid_responses": len(misses),
            "contract_sha256": plan["boltz_external_tmp"]["contract_sha256"],
            "projections_are_results": False,
        }
    return {
        "status": "validated_external_t0_hit_and_clone_miss",
        "contract_sha256": plan["boltz_external_tmp"]["contract_sha256"],
        "hit_product_latency_seconds": _distribution(
            (
                item["terminal"]["observed_monotonic_ns"]
                - item["request"]["accepted_monotonic_ns"]
            )
            / 1_000_000_000
            for item in hits
        ),
        "clone_miss_product_latency_seconds": _distribution(
            (
                item["terminal"]["observed_monotonic_ns"]
                - item["request"]["accepted_monotonic_ns"]
            )
            / 1_000_000_000
            for item in misses
        ),
        "clone_bytes": sum(item["phases"]["clone"]["bytes_written"] for item in misses),
        "projections_are_results": False,
    }


def aggregate_matrix(
    plan: dict[str, Any],
    attempts: Sequence[dict[str, Any]],
    evidence_root: Path,
    *,
    evidence_source: str,
) -> dict[str, Any]:
    shaped = validate_matrix(plan, attempts, evidence_root)
    members_by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in shaped:
        members_by_cell[item["raw"]["cell_id"]].append(item)
    cells = [
        _cell_aggregate(cell, members_by_cell[cell["cell_id"]])
        for cell in plan["matrix"]["cells"]
    ]
    raw_results = [result for cell in cells for result in cell["results"]]
    successes = [result for result in raw_results if result["success"]]
    aggregate = {
        "schema": AGGREGATE_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_sha256": canonical_sha256(plan),
        "evidence_classification": plan["evidence_classification"],
        "boundary": {"t0": T0_BOUNDARY, "terminal": TERMINAL_BOUNDARY},
        "attempts": {
            "observed": len(raw_results),
            "valid_responses": len(successes),
            "failures": len(raw_results) - len(successes),
            "failure_classes": dict(
                sorted(
                    Counter(
                        result["failure_class"]
                        for result in raw_results
                        if not result["success"]
                    ).items()
                )
            ),
        },
        "product_latency_seconds": _distribution(
            result["product_latency_seconds"] for result in successes
        ),
        "cells": cells,
        "totals": {
            "bytes_read": sum(result["accounting"]["bytes_read_total"] for result in raw_results),
            "bytes_written": sum(
                result["accounting"]["bytes_written_total"] for result in raw_results
            ),
            "bytes_network": sum(
                result["accounting"]["bytes_network_total"] for result in raw_results
            ),
            "request_cost_usd": round(
                sum(result["accounting"]["request_cost_usd"] for result in raw_results),
                9,
            ),
            "publication_cost_usd": round(
                sum(
                    result["accounting"]["publication_cost_usd"]
                    for result in raw_results
                ),
                9,
            ),
            "node_cache_investment_cost_usd": round(
                sum(
                    result["accounting"]["node_cache_investment_cost_usd"]
                    for result in raw_results
                ),
                9,
            ),
            "gpu_active_seconds": round(
                sum(result["accounting"]["gpu_active_seconds"] for result in raw_results),
                9,
            ),
            "gpu_idle_seconds": round(
                sum(result["accounting"]["gpu_idle_seconds"] for result in raw_results),
                9,
            ),
        },
        "cleanup": {
            "absent_generations": sum(
                result["cleanup"]["final_state"] == "ABSENT" for result in raw_results
            ),
            "clean_sealed_generations": sum(
                result["cleanup"]["final_state"] == "SEALED_RETAINED"
                for result in raw_results
            ),
            "dirty_generation_reuse": 0,
        },
        "boltz_external_tmp": _boltz_conclusion(plan, shaped),
    }
    aggregate["simulator_overrides"] = _simulator_export(
        plan, shaped, evidence_source
    )
    aggregate["router_locality_costs"] = _router_export(
        cells, evidence_source, plan["evidence_classification"]
    )
    return aggregate
