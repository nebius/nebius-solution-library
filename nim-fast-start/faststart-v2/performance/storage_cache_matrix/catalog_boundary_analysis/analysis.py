#!/usr/bin/env python3
"""Fail-closed catalog-boundary storage receipts and offline capacity analysis."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
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


SOURCE_SCHEMA = "archvteams.nebius.ai/catalog-boundary-source-manifest/v2"
CONFIG_SCHEMA = "archvteams.nebius.ai/catalog-boundary-capacity-analysis/v2"
RESULT_SCHEMA = "archvteams.nebius.ai/catalog-boundary-capacity-result/v2"
ATTEMPT_SCHEMA = "archvteams.nebius.ai/catalog-boundary-storage-attempt/v2"
OWNERSHIP_SCHEMA = "archvteams.nebius.ai/catalog-boundary-storage-ownership/v2"
EVIDENCE_SCHEMA = "archvteams.nebius.ai/catalog-boundary-operation-evidence/v2"
T0_BOUNDARY = "external-client-request-accepted/v1"

CACHE_STATES = (
    "A_materialized_hit",
    "B_node_seed_post_t0_materialization",
    "C_remote_miss_post_t0",
    "D_active_a_to_b_reclaim",
)
DEMAND_LABELS = (
    "cache_hit",
    "unknown_model_cold_start",
    "active_a_to_b_switch",
)
EVIDENCE_CLASSES = (
    "measured-live-product-slo",
    "synthetic-contract-smoke-not-performance-evidence",
)
OPERATIONS = (
    "catalog_selection",
    "queue",
    "drain",
    "gpu_release",
    "eviction",
    "placement",
    "artifact_fetch",
    "clone",
    "materialization",
    "hash",
    "first_read",
)
OUTCOMES = ("completed", "failed", "skipped")

SOURCE_KEYS = {
    "schema",
    "created_at_utc",
    "evidence_classification",
    "request_slo",
    "catalog",
    "cost_source",
    "boltz_external_tmp",
    "execution_gate",
}
REQUEST_SLO_SOURCE_KEYS = {
    "integrated_commit",
    "reviewed_commit",
    "t0_boundary",
    "terminal_boundary",
    "files",
}
CATALOG_SOURCE_KEYS = {
    "commit",
    "path",
    "sha256",
    "catalog_version",
    "row_count",
    "canonical_model_count",
    "known_canonical_model_count",
    "known_canonical_bytes",
    "known_canonical_median_bytes",
    "known_canonical_p90_bytes",
    "row_storage_low_bytes",
    "row_storage_high_bytes",
    "row_storage_high_is_planning_ceiling",
}
COST_SOURCE_KEYS = {
    "commit",
    "path",
    "sha256",
    "profile",
    "price_observed_at",
    "network_ssd_usd_per_gib_month",
    "object_storage_usd_per_gib_month",
    "price_source",
}
BOLTZ_SOURCE_KEYS = {"commit", "files", "status_observation"}
OBSERVATION_KEYS = {
    "source_path",
    "text",
    "text_sha256",
    "bytes_per_attempt",
    "elapsed_seconds_range",
    "classification",
    "raw_attempt_receipts_present_in_this_package",
}
EXECUTION_GATE_KEYS = {
    "live_execution_permitted",
    "created_resource_ids",
    "required_before_execution",
    "local_nvme",
}

ATTEMPT_KEYS = {
    "schema",
    "source_manifest_sha256",
    "evidence_classification",
    "attempt_id",
    "request_id",
    "cache_state",
    "demand_label",
    "target",
    "starting_state",
    "request",
    "clock_binding",
    "request_slo_binding",
    "ownership_binding",
    "pre_t0_investment",
    "operations",
    "accounting",
    "concurrency",
    "terminal",
    "cleanup",
    "supporting_evidence",
}
TARGET_KEYS = {
    "model_id",
    "model_version",
    "artifact_id",
    "artifact_version",
    "artifact_sha256",
    "artifact_bytes",
}
START_KEYS = {
    "target_materialized",
    "immutable_node_local_seed_present",
    "remote_artifact_required",
    "target_source",
    "active_model",
}
ACTIVE_MODEL_KEYS = {"model_id", "model_version"}
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
OWNERSHIP_BINDING_KEYS = {"path", "sha256", "receipt_id"}
CLOCK_KEYS = {
    "recorder_id",
    "clock_id",
    "boot_id",
    "utc_sync_source",
    "max_error_ms",
    "timestamp_source",
}
INVESTMENT_KEYS = {
    "source_available_monotonic_ns",
    "source_age_seconds",
    "residency_medium",
    "residency_bytes",
    "residency_rate_usd_per_gib_month",
    "residency_cost_usd",
    "prehydration_bytes",
    "prehydration_cost_usd",
    "prehydration_cost_status",
    "price_source_commit",
    "included_in_request_totals",
}
OPERATION_KEYS = {
    "name",
    "outcome",
    "started_monotonic_ns",
    "finished_monotonic_ns",
    "logical_bytes",
    "bytes_read",
    "bytes_written",
    "bytes_network",
    "bytes_deleted",
    "slo_bytes_moved",
    "reason",
    "evidence_ref",
}
ACCOUNTING_KEYS = {
    "bytes_read_total",
    "bytes_written_total",
    "bytes_network_total",
    "bytes_deleted_total",
    "physical_bytes_total",
    "operation_slo_bytes_moved_total",
    "request_slo_bytes_moved_total",
    "request_slo_cost_usd",
}
CONCURRENCY_KEYS = {
    "group_id",
    "peer_attempt_ids",
    "mutable_namespace_id",
    "source_read_only",
}
CLEANUP_KEYS = {
    "generation_id",
    "generation_uid",
    "writable_resource_uid",
    "final_state",
    "dirty",
    "reusable",
    "verified_absent",
    "evidence_ref",
}
TERMINAL_KEYS = {"success", "failure_class", "observed_monotonic_ns"}
EVIDENCE_KEYS = {"kind", "path", "sha256", "receipt_id"}
OWNERSHIP_RECEIPT_KEYS = {
    "schema",
    "receipt_id",
    "attempt_id",
    "owner_task_id",
    "clock_binding",
    "selected_node_id",
    "target",
    "source_available_monotonic_ns",
    "source_resource_uid",
    "resources",
    "generation",
    "pre_t0_investment",
}
BOUND_RESOURCE_KEYS = {
    "kind",
    "id",
    "uid",
    "project_id",
    "region",
    "role",
    "artifact_version",
    "artifact_sha256",
    "artifact_bytes",
}
GENERATION_KEYS = {
    "generation_id",
    "generation_uid",
    "parent_source_uid",
    "writable_resource_uid",
    "mutable_namespace_id",
}
TYPED_EVIDENCE_KEYS = {
    "schema",
    "kind",
    "receipt_id",
    "attempt_id",
    "clock_binding",
    "operation",
    "cleanup",
    "resource_uids",
}
OPERATION_EVIDENCE_KEYS = OPERATION_KEYS - {"evidence_ref"}
CLEANUP_EVIDENCE_KEYS = CLEANUP_KEYS - {"evidence_ref"}
FILE_PIN_KEYS = {"path", "sha256"}

SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")


class AnalysisError(ValueError):
    """A source, projection, receipt, or evidence binding is invalid."""


def _expect_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AnalysisError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise AnalysisError(
            f"{label} keys differ; missing={sorted(keys - actual)}, "
            f"extra={sorted(actual - keys)}"
        )
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AnalysisError(f"{label} is not a canonical identifier")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise AnalysisError(f"{label} is not a SHA-256 digest")
    return value


def _commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise AnalysisError(f"{label} is not a full commit ID")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AnalysisError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise AnalysisError(f"{label} must be finite and >= {minimum}")
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_path(root: Path, relative: Any, label: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise AnalysisError(f"{label} must be a nonempty relative path")
    root = root.resolve()
    candidate = root / relative
    if candidate.is_symlink():
        raise AnalysisError(f"{label} must resolve to a regular non-symlink file")
    path = candidate.resolve()
    if root not in path.parents or not path.is_file():
        raise AnalysisError(f"{label} must resolve to a regular non-symlink file")
    return path


def load_canonical_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AnalysisError("JSON input must be a regular non-symlink file")
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisError("JSON input is invalid") from exc
    if not isinstance(value, dict):
        raise AnalysisError("JSON input must contain an object")
    return value


def load_attempts(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise AnalysisError("attempt ledger must be a regular non-symlink file")
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise AnalysisError("attempt ledger must be nonempty and newline terminated")
    attempts: list[dict[str, Any]] = []
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AnalysisError("attempt ledger is not UTF-8") from exc
    for line_number, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"attempt line {line_number} is invalid JSON") from exc
        if not isinstance(value, dict) or line != canonical_json(value):
            raise AnalysisError(f"attempt line {line_number} is not canonical JSON")
        attempts.append(value)
    return attempts


def _validate_file_pins(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AnalysisError(f"{label} must be a nonempty list")
    paths: set[str] = set()
    for index, raw in enumerate(value):
        item = _expect_keys(raw, FILE_PIN_KEYS, f"{label}[{index}]")
        if not isinstance(item["path"], str) or not item["path"]:
            raise AnalysisError(f"{label}[{index}].path is invalid")
        _sha256(item["sha256"], f"{label}[{index}].sha256")
        if item["path"] in paths:
            raise AnalysisError(f"{label} contains duplicate paths")
        paths.add(item["path"])
    return value


def validate_source_manifest(value: Any) -> dict[str, Any]:
    manifest = _expect_keys(value, SOURCE_KEYS, "source manifest")
    if manifest["schema"] != SOURCE_SCHEMA:
        raise AnalysisError("source manifest schema is unsupported")
    if manifest["evidence_classification"] != (
        "offline-source-pinned-analysis-not-performance-evidence"
    ):
        raise AnalysisError("source manifest overclaims performance evidence")

    request_slo = _expect_keys(
        manifest["request_slo"], REQUEST_SLO_SOURCE_KEYS, "request_slo source"
    )
    _commit(request_slo["integrated_commit"], "request_slo.integrated_commit")
    _commit(request_slo["reviewed_commit"], "request_slo.reviewed_commit")
    if request_slo["t0_boundary"] != T0_BOUNDARY:
        raise AnalysisError("request-SLO T0 boundary was changed")
    if request_slo["terminal_boundary"] != (
        "first-complete-semantically-valid-response/v1"
    ):
        raise AnalysisError("request-SLO terminal boundary was changed")
    _validate_file_pins(request_slo["files"], "request_slo.files")

    catalog = _expect_keys(manifest["catalog"], CATALOG_SOURCE_KEYS, "catalog source")
    _commit(catalog["commit"], "catalog.commit")
    _sha256(catalog["sha256"], "catalog.sha256")
    for key in (
        "row_count",
        "canonical_model_count",
        "known_canonical_model_count",
        "known_canonical_bytes",
        "known_canonical_median_bytes",
        "known_canonical_p90_bytes",
        "row_storage_low_bytes",
        "row_storage_high_bytes",
    ):
        _integer(catalog[key], f"catalog.{key}", 1)
    if catalog["known_canonical_model_count"] > catalog["canonical_model_count"]:
        raise AnalysisError("known catalog count exceeds canonical model count")
    if catalog["row_storage_high_is_planning_ceiling"] is not True:
        raise AnalysisError("catalog high estimate must stay labeled as a planning ceiling")

    cost_source = _expect_keys(
        manifest["cost_source"], COST_SOURCE_KEYS, "cost source"
    )
    _commit(cost_source["commit"], "cost_source.commit")
    _sha256(cost_source["sha256"], "cost_source.sha256")
    if (
        cost_source["profile"] != "h100-single"
        or cost_source["network_ssd_usd_per_gib_month"] != "0.071"
        or cost_source["object_storage_usd_per_gib_month"] != "0.0147"
    ):
        raise AnalysisError("cost source differs from the pinned storage profile")
    for key in ("path", "price_observed_at", "price_source"):
        if not isinstance(cost_source[key], str) or not cost_source[key]:
            raise AnalysisError(f"cost_source.{key} must be nonempty")

    boltz = _expect_keys(
        manifest["boltz_external_tmp"], BOLTZ_SOURCE_KEYS, "Boltz source"
    )
    _commit(boltz["commit"], "boltz_external_tmp.commit")
    _validate_file_pins(boltz["files"], "boltz_external_tmp.files")
    observation = _expect_keys(
        boltz["status_observation"], OBSERVATION_KEYS, "Boltz status observation"
    )
    _sha256(observation["text_sha256"], "Boltz observation digest")
    if _bytes_sha256(observation["text"].encode()) != observation["text_sha256"]:
        raise AnalysisError("Boltz observation text differs from its digest")
    if observation["bytes_per_attempt"] != 1_826_220_898:
        raise AnalysisError("Boltz prepared-clone byte observation changed")
    if observation["elapsed_seconds_range"] != [440, 442]:
        raise AnalysisError("Boltz prepared-clone elapsed range changed")
    if observation["classification"] != (
        "prepared-clone-evidence-not-unknown-model-demand-startup"
    ):
        raise AnalysisError("Boltz prepared clone is mislabeled")
    if observation["raw_attempt_receipts_present_in_this_package"] is not False:
        raise AnalysisError("package falsely claims raw Boltz attempt receipts")

    gate = _expect_keys(manifest["execution_gate"], EXECUTION_GATE_KEYS, "execution gate")
    if gate["live_execution_permitted"] is not False or gate["created_resource_ids"] != []:
        raise AnalysisError("offline package cannot permit execution or claim resources")
    if not isinstance(gate["required_before_execution"], list) or len(
        gate["required_before_execution"]
    ) < 3:
        raise AnalysisError("execution prerequisites are incomplete")
    if gate["local_nvme"] != {
        "status": "unavailable-entitlement-not-proven",
        "substitution_permitted": False,
    }:
        raise AnalysisError("local NVMe must remain unavailable and unsubstituted")
    return manifest


def _git_show(repo_root: Path, commit: str, path: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AnalysisError(f"cannot resolve pinned Git source {commit}:{path}") from exc


def _git_tree_id(repo_root: Path, commit: str, path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit}:{path}"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AnalysisError(f"cannot resolve pinned Git tree {commit}:{path}") from exc
    object_id = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", object_id):
        raise AnalysisError("pinned request-SLO tree identity is malformed")
    return object_id


def _nearest_rank(values: Sequence[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]


def _catalog_facts(raw: bytes) -> dict[str, Any]:
    try:
        catalog = json.loads(raw)
        rows = catalog["rows"]
        meta = catalog["meta"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnalysisError("pinned catalog is malformed") from exc
    canonical: dict[str, int] = {}
    for row in rows:
        key = row["canonical_key"]
        known = _integer(row["storage"]["local_bytes_known"], "catalog local bytes")
        canonical[key] = max(canonical.get(key, 0), known)
    positive = [value for value in canonical.values() if value > 0]
    storage = meta["storage_feasibility"]
    return {
        "catalog_version": meta["catalog_version"],
        "row_count": len(rows),
        "canonical_model_count": len(canonical),
        "known_canonical_model_count": len(positive),
        "known_canonical_bytes": sum(positive),
        "known_canonical_median_bytes": _nearest_rank(positive, 0.5),
        "known_canonical_p90_bytes": _nearest_rank(positive, 0.9),
        "row_storage_low_bytes": storage["estimated_total_bytes_low"],
        "row_storage_high_bytes": storage["estimated_total_bytes_high"],
    }


def verify_pinned_sources(
    manifest: dict[str, Any], repo_root: Path, task_deck_root: Path | None = None
) -> dict[str, Any]:
    manifest = validate_source_manifest(manifest)
    repo_root = repo_root.resolve()
    checked: list[dict[str, str]] = []
    request = manifest["request_slo"]
    request_slo_path = "nim-fast-start/faststart-v2/performance/request_slo"
    reviewed_tree = _git_tree_id(
        repo_root, request["reviewed_commit"], request_slo_path
    )
    integrated_tree = _git_tree_id(
        repo_root, request["integrated_commit"], request_slo_path
    )
    if reviewed_tree != integrated_tree:
        raise AnalysisError(
            "integrated request-SLO subtree differs from the exact reviewed subtree"
        )
    for pin in request["files"]:
        for lineage, commit in (
            ("reviewed", request["reviewed_commit"]),
            ("integrated", request["integrated_commit"]),
        ):
            content = _git_show(repo_root, commit, pin["path"])
            if _bytes_sha256(content) != pin["sha256"]:
                raise AnalysisError(
                    f"request-SLO {lineage} source drifted: {pin['path']}"
                )
            checked.append(
                {"kind": f"request_slo_{lineage}", "path": pin["path"]}
            )

    catalog_pin = manifest["catalog"]
    catalog_raw = _git_show(repo_root, catalog_pin["commit"], catalog_pin["path"])
    if _bytes_sha256(catalog_raw) != catalog_pin["sha256"]:
        raise AnalysisError("catalog source digest differs")
    facts = _catalog_facts(catalog_raw)
    for key, actual in facts.items():
        if catalog_pin[key] != actual:
            raise AnalysisError(f"catalog derived fact differs: {key}")
    checked.append({"kind": "catalog", "path": catalog_pin["path"]})

    cost_pin = manifest["cost_source"]
    cost_raw = _git_show(repo_root, cost_pin["commit"], cost_pin["path"])
    if _bytes_sha256(cost_raw) != cost_pin["sha256"]:
        raise AnalysisError("cost source digest differs")
    try:
        profile = json.loads(cost_raw)["profiles"][cost_pin["profile"]]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AnalysisError("pinned cost profile is malformed") from exc
    for key in (
        "price_observed_at",
        "network_ssd_usd_per_gib_month",
        "object_storage_usd_per_gib_month",
        "price_source",
    ):
        if profile[key] != cost_pin[key]:
            raise AnalysisError(f"pinned cost profile differs: {key}")
    checked.append({"kind": "cost_source", "path": cost_pin["path"]})

    boltz = manifest["boltz_external_tmp"]
    for pin in boltz["files"]:
        content = _git_show(repo_root, boltz["commit"], pin["path"])
        if _bytes_sha256(content) != pin["sha256"]:
            raise AnalysisError(f"Boltz source drifted: {pin['path']}")
        checked.append({"kind": "boltz_external_tmp", "path": pin["path"]})

    observation_status = "pinned-text-only"
    if task_deck_root is not None:
        observation = boltz["status_observation"]
        source = _safe_path(task_deck_root, observation["source_path"], "Task Deck source")
        if observation["text"] not in source.read_text(encoding="utf-8"):
            raise AnalysisError("pinned Boltz manager observation is absent from Task Deck")
        observation_status = "verified-in-task-deck"
    return {
        "schema": "archvteams.nebius.ai/catalog-boundary-source-verification/v2",
        "source_manifest_sha256": canonical_sha256(manifest),
        "verified_file_count": len(checked),
        "verified_files": checked,
        "reviewed_request_slo_tree": reviewed_tree,
        "integrated_request_slo_tree": integrated_tree,
        "request_slo_integration": "content-identical-reviewed-subtree",
        "boltz_status_observation": observation_status,
        "live_execution_permitted": False,
        "created_resource_ids": [],
    }


def _validate_config(value: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "schema",
        "evidence_classification",
        "catalog_size",
        "cache_sizes_gib",
        "top_k_values",
        "reuse_exponents",
        "state_mix_top_k_values",
        "active_switch_probabilities",
        "node_local_seed_fractions",
        "size_profiles",
        "known_catalog_lower_bound",
        "cost_semantics",
    }
    config = _expect_keys(value, keys, "analysis config")
    if config["schema"] != CONFIG_SCHEMA or config["evidence_classification"] != (
        "projection-from-pinned-sources-not-measurement"
    ):
        raise AnalysisError("analysis config schema or evidence classification is invalid")
    catalog_size = _integer(config["catalog_size"], "catalog_size", 1)
    if catalog_size != 200:
        raise AnalysisError("analysis must retain the 200-model planning catalog")
    for key in ("cache_sizes_gib", "top_k_values", "state_mix_top_k_values"):
        values = config[key]
        if not isinstance(values, list) or not values:
            raise AnalysisError(f"{key} must be a nonempty list")
        for item in values:
            _integer(item, key)
    if any(
        item > catalog_size
        for item in config["top_k_values"] + config["state_mix_top_k_values"]
    ):
        raise AnalysisError("top-K exceeds catalog size")
    for key in (
        "cache_sizes_gib",
        "top_k_values",
        "state_mix_top_k_values",
        "reuse_exponents",
        "active_switch_probabilities",
        "node_local_seed_fractions",
    ):
        if len(config[key]) != len(set(config[key])):
            raise AnalysisError(f"{key} contains duplicate sensitivity points")
    for key in (
        "reuse_exponents",
        "active_switch_probabilities",
        "node_local_seed_fractions",
    ):
        values = config[key]
        if not isinstance(values, list) or not values:
            raise AnalysisError(f"{key} must be a nonempty list")
        for item in values:
            number = _number(item, key)
            if key != "reuse_exponents" and number > 1:
                raise AnalysisError(f"{key} probabilities must not exceed one")
    profiles = config["size_profiles"]
    if not isinstance(profiles, list) or len(profiles) < 2:
        raise AnalysisError("at least two size profiles are required")
    seen: set[str] = set()
    for profile in profiles:
        _expect_keys(profile, {"id", "bytes_per_model", "source"}, "size profile")
        _identifier(profile["id"], "size profile id")
        _integer(profile["bytes_per_model"], "size profile bytes", 1)
        if profile["id"] in seen or not isinstance(profile["source"], str):
            raise AnalysisError("size profile identity/source is invalid")
        seen.add(profile["id"])
    expected_profiles = {
        "catalog-known-canonical-median": manifest["catalog"][
            "known_canonical_median_bytes"
        ],
        "catalog-known-canonical-p90": manifest["catalog"][
            "known_canonical_p90_bytes"
        ],
    }
    if {profile["id"]: profile["bytes_per_model"] for profile in profiles} != (
        expected_profiles
    ):
        raise AnalysisError("size profiles differ from pinned catalog statistics")
    lower = _expect_keys(
        config["known_catalog_lower_bound"],
        {"known_models", "unknown_or_added_models", "known_bytes"},
        "known catalog lower bound",
    )
    if lower != {
        "known_models": manifest["catalog"]["known_canonical_model_count"],
        "unknown_or_added_models": catalog_size
        - manifest["catalog"]["known_canonical_model_count"],
        "known_bytes": manifest["catalog"]["known_canonical_bytes"],
    }:
        raise AnalysisError("known catalog lower bound differs from pinned source")
    costs = _expect_keys(
        config["cost_semantics"],
        {
            "currency",
            "network_ssd_residency_usd_per_gib_month",
            "object_storage_publication_usd_per_gib_month",
            "price_observed_at",
            "price_source_commit",
            "prehydration_transfer_and_compute_cost_usd",
            "reason",
        },
        "cost semantics",
    )
    if (
        costs["currency"] != "USD"
        or costs["network_ssd_residency_usd_per_gib_month"]
        != float(manifest["cost_source"]["network_ssd_usd_per_gib_month"])
        or costs["object_storage_publication_usd_per_gib_month"]
        != float(manifest["cost_source"]["object_storage_usd_per_gib_month"])
        or costs["price_observed_at"]
        != manifest["cost_source"]["price_observed_at"]
        or costs["price_source_commit"] != manifest["cost_source"]["commit"]
        or costs["prehydration_transfer_and_compute_cost_usd"] is not None
    ):
        raise AnalysisError("analysis cost assumptions differ from the pinned source")
    return config


def _zipf_hit_rate(catalog_size: int, top_k: int, exponent: float) -> float:
    if top_k <= 0:
        return 0.0
    if top_k >= catalog_size:
        return 1.0
    weights = [rank ** (-exponent) for rank in range(1, catalog_size + 1)]
    return sum(weights[:top_k]) / sum(weights)


def _round_probability(value: float) -> float:
    return round(value, 12)


def analyze_capacity(
    manifest: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    manifest = validate_source_manifest(manifest)
    config = _validate_config(config, manifest)
    catalog_size = config["catalog_size"]
    gib = 1024**3
    network_ssd_rate = config["cost_semantics"][
        "network_ssd_residency_usd_per_gib_month"
    ]
    object_storage_rate = config["cost_semantics"][
        "object_storage_publication_usd_per_gib_month"
    ]

    capacity_rows: list[dict[str, Any]] = []
    full_catalog_rows: list[dict[str, Any]] = []
    for profile in config["size_profiles"]:
        size = profile["bytes_per_model"]
        full_bytes = size * catalog_size
        full_catalog_rows.append(
            {
                "size_profile": profile["id"],
                "bytes": full_bytes,
                "gib": round(full_bytes / gib, 6),
                "tib": round(full_bytes / (1024**4), 6),
                "models_imputed": config["known_catalog_lower_bound"][
                    "unknown_or_added_models"
                ],
                "network_ssd_residency_usd_per_month": round(
                    full_bytes / gib * network_ssd_rate, 6
                ),
                "object_storage_publication_usd_per_month": round(
                    full_bytes / gib * object_storage_rate, 6
                ),
                "prehydration_transfer_and_compute_cost_usd": None,
            }
        )
        for budget_gib in config["cache_sizes_gib"]:
            budget_bytes = budget_gib * gib
            fit = min(catalog_size, budget_bytes // size)
            capacity_rows.append(
                {
                    "size_profile": profile["id"],
                    "cache_gib": budget_gib,
                    "fit_models": fit,
                    "catalog_fraction": _round_probability(fit / catalog_size),
                    "resident_bytes_at_capacity": fit * size,
                    "full_catalog_fits": fit == catalog_size,
                    "network_ssd_residency_usd_per_month": round(
                        fit * size / gib * network_ssd_rate, 6
                    ),
                    "object_storage_publication_usd_per_month": round(
                        fit * size / gib * object_storage_rate, 6
                    ),
                    "prehydration_transfer_and_compute_cost_usd": None,
                }
            )

    reuse_rows: list[dict[str, Any]] = []
    for exponent in config["reuse_exponents"]:
        for top_k in config["top_k_values"]:
            reuse_rows.append(
                {
                    "reuse_exponent": exponent,
                    "top_k": top_k,
                    "cache_hit_probability": _round_probability(
                        _zipf_hit_rate(catalog_size, top_k, exponent)
                    ),
                }
            )

    state_rows: list[dict[str, Any]] = []
    median_profile = next(
        profile
        for profile in config["size_profiles"]
        if profile["id"] == "catalog-known-canonical-median"
    )
    for exponent in config["reuse_exponents"]:
        for top_k in config["state_mix_top_k_values"]:
            hit = _zipf_hit_rate(catalog_size, top_k, exponent)
            for switch_probability in config["active_switch_probabilities"]:
                for seed_fraction in config["node_local_seed_fractions"]:
                    miss = 1.0 - hit
                    state_d = miss * switch_probability
                    non_switch_miss = miss - state_d
                    state_b = non_switch_miss * seed_fraction
                    state_c = non_switch_miss - state_b
                    probabilities = {
                        "A_materialized_hit": _round_probability(hit),
                        "B_node_seed_post_t0_materialization": _round_probability(state_b),
                        "C_remote_miss_post_t0": _round_probability(state_c),
                        "D_active_a_to_b_reclaim": _round_probability(state_d),
                    }
                    if abs(sum(probabilities.values()) - 1.0) > 1e-9:
                        raise AnalysisError("state probability model does not conserve requests")
                    d_remote = state_d * (1.0 - seed_fraction)
                    d_seed = state_d * seed_fraction
                    size = median_profile["bytes_per_model"]
                    state_rows.append(
                        {
                            "reuse_exponent": exponent,
                            "top_k": top_k,
                            "active_switch_probability_given_miss": switch_probability,
                            "node_seed_fraction_given_localization": seed_fraction,
                            "state_probabilities": probabilities,
                            "expected_remote_source_bytes_per_request": round(
                                (state_c + d_remote) * size, 3
                            ),
                            "expected_node_seed_logical_bytes_per_request": round(
                                (state_b + d_seed) * size, 3
                            ),
                            "byte_projection_profile": median_profile["id"],
                        }
                    )

    return {
        "schema": RESULT_SCHEMA,
        "evidence_classification": "projection-from-pinned-sources-not-measurement",
        "source_manifest_sha256": canonical_sha256(manifest),
        "analysis_config_sha256": canonical_sha256(config),
        "catalog_summary": {
            "planning_models": catalog_size,
            "pinned_catalog_rows": manifest["catalog"]["row_count"],
            "pinned_canonical_models": manifest["catalog"]["canonical_model_count"],
            "known_canonical_models": manifest["catalog"][
                "known_canonical_model_count"
            ],
            "known_canonical_bytes_lower_bound": manifest["catalog"][
                "known_canonical_bytes"
            ],
            "unknown_or_added_models": config["known_catalog_lower_bound"][
                "unknown_or_added_models"
            ],
            "row_duplicate_high_ceiling_excluded_bytes": manifest["catalog"][
                "row_storage_high_bytes"
            ],
            "row_duplicate_high_ceiling_used_in_projection": False,
        },
        "full_catalog_capacity": full_catalog_rows,
        "cache_budget_sensitivity": capacity_rows,
        "top_k_reuse_sensitivity": reuse_rows,
        "request_state_sensitivity": state_rows,
        "simulator_input": {
            "kind": "projection-only-not-runtime-latency-distribution",
            "cache_hit_curves": reuse_rows,
            "state_mix_model": (
                "A=hit; D=(1-A)*active_switch_probability; "
                "B=(1-A-D)*node_seed_fraction; C=1-A-B-D"
            ),
            "latency_samples": [],
            "measured_bytes_samples": [],
        },
        "local_nvme": {
            "status": "unavailable-entitlement-not-proven",
            "substitution_permitted": False,
        },
        "boltz_external_tmp": {
            "classification": manifest["boltz_external_tmp"]["status_observation"][
                "classification"
            ],
            "bytes_per_attempt": manifest["boltz_external_tmp"]["status_observation"][
                "bytes_per_attempt"
            ],
            "elapsed_seconds_range": manifest["boltz_external_tmp"][
                "status_observation"
            ]["elapsed_seconds_range"],
            "external_t0_latency_distribution": None,
            "reason": "copy/hash completed before T0 and raw external-T0 receipts are absent",
        },
        "caveats": [
            "No live resource was created and no performance measurement is claimed.",
            "Homogeneous median/p90 capacity profiles impute 55 of 200 planning slots.",
            (
                "The 220-row high ceiling is excluded because duplicate rows cannot "
                "be scaled or labeled as canonical models."
            ),
            (
                "Storage residency cost uses pinned public PAYG assumptions; "
                "prehydration transfer/compute remains unquantified until measured."
            ),
            (
                "Latency distributions must come from raw external-T0 attempts; "
                "phase percentile summation is forbidden."
            ),
        ],
    }


def _validate_target(value: Any) -> dict[str, Any]:
    target = _expect_keys(value, TARGET_KEYS, "target")
    for key in ("model_id", "model_version", "artifact_id", "artifact_version"):
        _identifier(target[key], f"target.{key}")
    _sha256(target["artifact_sha256"], "target.artifact_sha256")
    _integer(target["artifact_bytes"], "target.artifact_bytes", 1)
    return target


def _validate_starting_state(value: Any, target: dict[str, Any]) -> dict[str, Any]:
    state = _expect_keys(value, START_KEYS, "starting_state")
    _identifier(state["selected_node_id"], "starting_state.selected_node_id")
    booleans = (
        state["target_materialized"],
        state["immutable_node_local_seed_present"],
        state["remote_artifact_required"],
    )
    if any(not isinstance(item, bool) for item in booleans) or sum(booleans) != 1:
        raise AnalysisError("starting-state target sources must be mutually exclusive")
    expected_source = {
        (True, False, False): "materialized_generation",
        (False, True, False): "immutable_node_local_seed",
        (False, False, True): "immutable_remote_artifact",
    }[booleans]
    if state["target_source"] != expected_source:
        raise AnalysisError("starting-state target source disagrees with its booleans")
    if (
        state["source_artifact_version"] != target["artifact_version"]
        or state["source_artifact_sha256"] != target["artifact_sha256"]
    ):
        raise AnalysisError("starting source version/digest differs from the request target")
    _number(state["source_age_seconds"], "starting_state.source_age_seconds")
    active = state["active_model"]
    if active is not None:
        active = _expect_keys(active, ACTIVE_MODEL_KEYS, "starting_state.active_model")
        _identifier(active["model_id"], "active model id")
        _identifier(active["model_version"], "active model version")
        if active == {
            "model_id": target["model_id"],
            "model_version": target["model_version"],
        } and not state["target_materialized"]:
            raise AnalysisError("active target contradicts an absent target materialization")
    return state


def _validate_request(value: Any) -> dict[str, Any]:
    request = _expect_keys(value, REQUEST_KEYS, "request")
    if request["t0_boundary"] != T0_BOUNDARY:
        raise AnalysisError("attempt does not use external request acceptance as T0")
    if not isinstance(request["accepted_at_utc"], str):
        raise AnalysisError("request.accepted_at_utc must be a string")
    _integer(request["accepted_monotonic_ns"], "request.accepted_monotonic_ns", 1)
    _identifier(request["input_id"], "request.input_id")
    _sha256(request["input_sha256"], "request.input_sha256")
    _integer(request["input_bytes"], "request.input_bytes", 1)
    return request


def _validate_investment(value: Any) -> dict[str, Any]:
    investment = _expect_keys(value, INVESTMENT_KEYS, "pre_t0_investment")
    byte_keys = (
        "publication_bytes",
        "node_seed_bytes",
        "node_seed_prehydration_bytes",
        "materialized_bytes",
        "materialized_prehydration_bytes",
    )
    second_keys = ("node_seed_residency_seconds", "materialized_residency_seconds")
    cost_keys = (
        "publication_cost_usd",
        "node_seed_prehydration_cost_usd",
        "node_seed_residency_cost_usd",
        "materialized_prehydration_cost_usd",
        "materialized_residency_cost_usd",
    )
    for key in byte_keys:
        _integer(investment[key], f"pre_t0_investment.{key}")
    for key in second_keys + cost_keys:
        _number(investment[key], f"pre_t0_investment.{key}")
    if not isinstance(investment["price_source"], str) or not investment["price_source"]:
        raise AnalysisError("pre-T0 investment requires an explicit price source")
    if investment["included_in_request_totals"] is not False:
        raise AnalysisError("pre-T0 investment must stay outside request totals")
    return investment


def _validate_operations(value: Any, t0: int) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(OPERATIONS):
        raise AnalysisError("operations must contain every canonical storage operation")
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(value):
        operation = _expect_keys(raw, OPERATION_KEYS, f"operation[{index}]")
        name = operation["name"]
        if name not in OPERATIONS or name in result:
            raise AnalysisError("operation name is unknown or duplicated")
        if operation["outcome"] not in OUTCOMES:
            raise AnalysisError("operation outcome is unknown")
        for key in (
            "logical_bytes",
            "bytes_read",
            "bytes_written",
            "bytes_network",
            "bytes_deleted",
        ):
            _integer(operation[key], f"operation {name}.{key}")
        if not isinstance(operation["reason"], str) or not operation["reason"]:
            raise AnalysisError(f"operation {name} requires a reason")
        _sha256(operation["evidence_sha256"], f"operation {name}.evidence_sha256")
        start = operation["started_monotonic_ns"]
        finish = operation["finished_monotonic_ns"]
        if operation["outcome"] == "skipped":
            if start is not None or finish is not None or any(
                operation[key]
                for key in (
                    "logical_bytes",
                    "bytes_read",
                    "bytes_written",
                    "bytes_network",
                    "bytes_deleted",
                )
            ):
                raise AnalysisError(f"skipped operation {name} has work or byte claims")
        else:
            _integer(start, f"operation {name}.start", 1)
            _integer(finish, f"operation {name}.finish", 1)
            if start < t0:
                raise AnalysisError(f"request operation {name} starts before external T0")
            if finish < start:
                raise AnalysisError(f"request operation {name} has negative duration")
        result[name] = operation
    if set(result) != set(OPERATIONS):
        raise AnalysisError("operations omit a canonical storage operation")
    return result


def _validate_accounting(value: Any, operations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    accounting = _expect_keys(value, ACCOUNTING_KEYS, "accounting")
    totals = {
        "bytes_read_total": sum(item["bytes_read"] for item in operations.values()),
        "bytes_written_total": sum(item["bytes_written"] for item in operations.values()),
        "bytes_network_total": sum(item["bytes_network"] for item in operations.values()),
        "bytes_deleted_total": sum(item["bytes_deleted"] for item in operations.values()),
    }
    for key, expected in totals.items():
        if _integer(accounting[key], f"accounting.{key}") != expected:
            raise AnalysisError("request physical-byte accounting omits or double-counts work")
    _integer(
        accounting["request_slo_bytes_moved_total"],
        "accounting.request_slo_bytes_moved_total",
    )
    _number(accounting["request_slo_cost_usd"], "accounting.request_slo_cost_usd")
    return accounting


def _validate_concurrency(value: Any, attempt_id: str) -> dict[str, Any]:
    concurrency = _expect_keys(value, CONCURRENCY_KEYS, "concurrency")
    if concurrency["group_id"] is not None:
        _identifier(concurrency["group_id"], "concurrency.group_id")
    if not isinstance(concurrency["peer_attempt_ids"], list) or len(
        concurrency["peer_attempt_ids"]
    ) != len(set(concurrency["peer_attempt_ids"])):
        raise AnalysisError("concurrency peers must be a unique list")
    for peer in concurrency["peer_attempt_ids"]:
        _identifier(peer, "concurrency peer")
        if peer == attempt_id:
            raise AnalysisError("attempt cannot list itself as a concurrency peer")
    _identifier(concurrency["mutable_namespace_id"], "mutable namespace")
    if concurrency["source_read_only"] is not True:
        raise AnalysisError("shared source must be immutable/read-only")
    if (concurrency["group_id"] is None) != (not concurrency["peer_attempt_ids"]):
        raise AnalysisError("concurrency group and peer list must be declared together")
    return concurrency


def _validate_cleanup(value: Any) -> dict[str, Any]:
    cleanup = _expect_keys(value, CLEANUP_KEYS, "cleanup")
    _identifier(cleanup["generation_id"], "cleanup.generation_id")
    if cleanup["final_state"] not in {"ABSENT", "SEALED_RETAINED"}:
        raise AnalysisError("cleanup final state is invalid")
    for key in ("dirty", "reusable", "verified_absent"):
        if not isinstance(cleanup[key], bool):
            raise AnalysisError(f"cleanup.{key} must be boolean")
    _sha256(cleanup["receipt_sha256"], "cleanup.receipt_sha256")
    if cleanup["dirty"] and (
        cleanup["final_state"] != "ABSENT"
        or not cleanup["verified_absent"]
        or cleanup["reusable"]
    ):
        raise AnalysisError("dirty generation was not deleted and proved absent")
    if cleanup["final_state"] == "ABSENT" and not cleanup["verified_absent"]:
        raise AnalysisError("ABSENT generation lacks an absence proof")
    if cleanup["final_state"] == "SEALED_RETAINED" and (
        cleanup["dirty"] or not cleanup["reusable"] or cleanup["verified_absent"]
    ):
        raise AnalysisError("retained generation is not sealed and reusable")
    return cleanup


def _validate_evidence(value: Any, evidence_root: Path) -> set[str]:
    if not isinstance(value, list) or not value:
        raise AnalysisError("supporting_evidence must be nonempty")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        item = _expect_keys(raw, EVIDENCE_KEYS, f"supporting_evidence[{index}]")
        _identifier(item["kind"], "supporting evidence kind")
        path = _safe_path(evidence_root, item["path"], "supporting evidence path")
        if _file_sha256(path) != _sha256(item["sha256"], "supporting evidence digest"):
            raise AnalysisError("supporting evidence digest differs")
        identity = (item["kind"], item["path"])
        if identity in seen:
            raise AnalysisError("supporting evidence is duplicated")
        seen.add(identity)
    return {item["sha256"] for item in value}


def _validate_binding(
    binding_value: Any,
    request: dict[str, Any],
    target: dict[str, Any],
    starting_state: dict[str, Any],
    accounting: dict[str, Any],
    attempt_id: str,
    request_id: str,
    evidence_root: Path,
) -> int:
    binding = _expect_keys(binding_value, BINDING_KEYS, "request_slo_binding")
    if binding["attempt_id"] != attempt_id or binding["request_id"] != request_id:
        raise AnalysisError("request-SLO binding identity differs from receipt")
    for key in ("trace_sha256", "ledger_sha256"):
        _sha256(binding[key], f"request_slo_binding.{key}")
    trace_path = _safe_path(evidence_root, binding["trace_path"], "bound trace")
    ledger_path = _safe_path(evidence_root, binding["ledger_path"], "bound ledger")
    if _file_sha256(trace_path) != binding["trace_sha256"]:
        raise AnalysisError("bound request-SLO trace digest differs")
    if _file_sha256(ledger_path) != binding["ledger_sha256"]:
        raise AnalysisError("bound request-SLO ledger digest differs")
    try:
        trace = load_trace(trace_path)
        events = load_ledger(ledger_path)
        results = validate_ledger(events, trace)
    except HarnessError as exc:
        raise AnalysisError(f"bound request-SLO evidence is invalid: {exc}") from exc
    if trace["trace_id"] != binding["trace_id"]:
        raise AnalysisError("bound request-SLO trace identity differs")
    if {event["ledger_id"] for event in events} != {binding["ledger_id"]}:
        raise AnalysisError("bound request-SLO ledger identity differs")
    result = next((item for item in results if item["attempt_id"] == attempt_id), None)
    if result is None or result["request_id"] != request_id:
        raise AnalysisError("receipt attempt is absent from bound request-SLO evidence")
    if (
        result["model_id"] != target["model_id"]
        or result["model_version"] != target["model_version"]
        or result["artifact_id"] != target["artifact_id"]
        or result["artifact_version"] != target["artifact_version"]
    ):
        raise AnalysisError("receipt target differs from bound request-SLO evidence")
    trace_request = next(item for item in trace["requests"] if item["attempt_id"] == attempt_id)
    if trace_request["target"] != {
        "model_id": target["model_id"],
        "model_version": target["model_version"],
        "artifact_id": target["artifact_id"],
        "artifact_version": target["artifact_version"],
        "artifact_sha256": target["artifact_sha256"],
    }:
        raise AnalysisError("receipt target digest differs from bound trace")
    if any(
        trace_request["input"][key] != expected
        for key, expected in {
            "input_id": request["input_id"],
            "payload_sha256": request["input_sha256"],
            "input_bytes": request["input_bytes"],
        }.items()
    ):
        raise AnalysisError("receipt input differs from bound trace")
    attempt_events = [event for event in events if event["attempt_id"] == attempt_id]
    accepted = attempt_events[0]
    terminal = next(
        event
        for event in attempt_events
        if event["event_type"] in {"response.validated", "attempt.failed"}
    )
    if (
        accepted["observed_monotonic_ns"] != request["accepted_monotonic_ns"]
        or accepted["observed_at_utc"] != request["accepted_at_utc"]
    ):
        raise AnalysisError("receipt T0 differs from external recorder T0")
    if result["current_node_occupant"] != starting_state["active_model"]:
        raise AnalysisError("starting active model differs from request-SLO precondition")
    if result["accounting"]["bytes_moved_total"] != accounting[
        "request_slo_bytes_moved_total"
    ]:
        raise AnalysisError("request-SLO byte total differs from receipt binding")
    if result["accounting"]["cost_usd"] != accounting["request_slo_cost_usd"]:
        raise AnalysisError("request-SLO cost differs from receipt binding")
    return terminal["observed_monotonic_ns"]


def _require_completed(
    operations: dict[str, dict[str, Any]], names: Iterable[str], label: str
) -> None:
    missing = [name for name in names if operations[name]["outcome"] != "completed"]
    if missing:
        raise AnalysisError(f"{label} omits completed operations: {missing}")


def _validate_state_contract(
    cache_state: str,
    demand_label: str,
    target: dict[str, Any],
    start: dict[str, Any],
    investment: dict[str, Any],
    operations: dict[str, dict[str, Any]],
) -> None:
    prepared = start["target_materialized"] or investment["materialized_bytes"] > 0
    if demand_label == "unknown_model_cold_start" and prepared:
        raise AnalysisError(
            "prepared clone cannot be labeled unknown-model cold start"
        )
    expected_labels = {
        "A_materialized_hit": "cache_hit",
        "B_node_seed_post_t0_materialization": "unknown_model_cold_start",
        "C_remote_miss_post_t0": "unknown_model_cold_start",
        "D_active_a_to_b_reclaim": "active_a_to_b_switch",
    }
    if demand_label != expected_labels[cache_state]:
        raise AnalysisError("demand label differs from mutually exclusive cache state")
    bytes_required = target["artifact_bytes"]
    prep_names = ("artifact_fetch", "clone", "materialization", "hash")

    if cache_state == "A_materialized_hit":
        if not start["target_materialized"]:
            raise AnalysisError("state A lacks a materialized target")
        if start["active_model"] not in (
            None,
            {"model_id": target["model_id"], "model_version": target["model_version"]},
        ):
            raise AnalysisError("state A cannot hide an active different model")
        if investment["materialized_bytes"] < bytes_required or investment[
            "materialized_prehydration_bytes"
        ] < bytes_required:
            raise AnalysisError("state A omits materialized residency/prehydration bytes")
        if investment["materialized_residency_seconds"] <= 0:
            raise AnalysisError("state A omits materialized residency duration")
        if any(operations[name]["outcome"] != "skipped" for name in prep_names):
            raise AnalysisError("state A performs request-time localization")
    elif cache_state == "B_node_seed_post_t0_materialization":
        if not start["immutable_node_local_seed_present"] or start["active_model"] is not None:
            raise AnalysisError("state B starting state is not a node-seed miss")
        if investment["node_seed_bytes"] < bytes_required or investment[
            "node_seed_prehydration_bytes"
        ] < bytes_required:
            raise AnalysisError("state B omits separately accounted node-seed investment")
        if not any(
            operations[name]["outcome"] == "completed"
            for name in ("clone", "materialization")
        ):
            raise AnalysisError("state B lacks post-T0 clone/materialization")
        _require_completed(operations, ("hash", "first_read"), "state B")
        if sum(
            operations[name]["bytes_written"] for name in ("clone", "materialization")
        ) < bytes_required or operations["hash"]["bytes_read"] < bytes_required:
            raise AnalysisError("state B omits full clone/materialization/hash bytes")
    elif cache_state == "C_remote_miss_post_t0":
        if not start["remote_artifact_required"] or start["active_model"] is not None:
            raise AnalysisError("state C starting state is not a remote miss")
        if investment["publication_bytes"] < bytes_required:
            raise AnalysisError("state C omits immutable publication investment")
        _require_completed(
            operations,
            ("artifact_fetch", "materialization", "hash", "first_read"),
            "state C",
        )
        if (
            operations["artifact_fetch"]["bytes_network"] < bytes_required
            or operations["materialization"]["bytes_written"] < bytes_required
            or operations["hash"]["bytes_read"] < bytes_required
        ):
            raise AnalysisError("state C omits full remote/materialization/hash bytes")
    else:
        active = start["active_model"]
        if active is None or active["model_id"] == target["model_id"]:
            raise AnalysisError("state D lacks a different active model")
        if start["target_materialized"]:
            raise AnalysisError("state D target must require post-T0 localization")
        _require_completed(
            operations, ("drain", "gpu_release", "eviction"), "state D"
        )
        if operations["eviction"]["bytes_deleted"] <= 0:
            raise AnalysisError("state D omits eviction/reclaim bytes")
        if start["immutable_node_local_seed_present"]:
            if investment["node_seed_bytes"] < bytes_required or investment[
                "node_seed_prehydration_bytes"
            ] < bytes_required:
                raise AnalysisError("state D node-seed source is not separately accounted")
            if not any(
                operations[name]["outcome"] == "completed"
                for name in ("clone", "materialization")
            ):
                raise AnalysisError("state D node-seed target is not materialized after T0")
            if sum(
                operations[name]["bytes_written"]
                for name in ("clone", "materialization")
            ) < bytes_required:
                raise AnalysisError("state D omits full target materialization bytes")
        else:
            if investment["publication_bytes"] < bytes_required:
                raise AnalysisError("state D remote publication is not separately accounted")
            _require_completed(
                operations, ("artifact_fetch", "materialization"), "state D"
            )
            if operations["artifact_fetch"]["bytes_network"] < bytes_required:
                raise AnalysisError("state D remote target omits fetched bytes")
            if operations["materialization"]["bytes_written"] < bytes_required:
                raise AnalysisError("state D remote target omits materialized bytes")
        _require_completed(operations, ("hash", "first_read"), "state D")
        if operations["hash"]["bytes_read"] < bytes_required:
            raise AnalysisError("state D omits full target validation bytes")


def _validate_attempt(
    value: Any,
    manifest_sha256: str,
    live_execution_permitted: bool,
    evidence_root: Path,
) -> dict[str, Any]:
    attempt = _expect_keys(value, ATTEMPT_KEYS, "attempt")
    if attempt["schema"] != ATTEMPT_SCHEMA:
        raise AnalysisError("attempt schema is unsupported")
    if attempt["source_manifest_sha256"] != manifest_sha256:
        raise AnalysisError("attempt is not pinned to the exact source manifest")
    if attempt["evidence_classification"] not in EVIDENCE_CLASSES:
        raise AnalysisError("attempt evidence classification is unknown")
    if (
        attempt["evidence_classification"] == "measured-live-product-slo"
        and not live_execution_permitted
    ):
        raise AnalysisError("measured receipt is forbidden while execution gate is closed")
    attempt_id = _identifier(attempt["attempt_id"], "attempt_id")
    request_id = _identifier(attempt["request_id"], "request_id")
    cache_state = attempt["cache_state"]
    demand_label = attempt["demand_label"]
    if cache_state not in CACHE_STATES or demand_label not in DEMAND_LABELS:
        raise AnalysisError("attempt cache state or demand label is unknown")
    target = _validate_target(attempt["target"])
    start = _validate_starting_state(attempt["starting_state"], target)
    request = _validate_request(attempt["request"])
    investment = _validate_investment(attempt["pre_t0_investment"])
    operations = _validate_operations(
        attempt["operations"], request["accepted_monotonic_ns"]
    )
    accounting = _validate_accounting(attempt["accounting"], operations)
    concurrency = _validate_concurrency(attempt["concurrency"], attempt_id)
    cleanup = _validate_cleanup(attempt["cleanup"])
    evidence_digests = _validate_evidence(attempt["supporting_evidence"], evidence_root)
    if any(
        operation["evidence_sha256"] not in evidence_digests
        for operation in operations.values()
    ) or cleanup["receipt_sha256"] not in evidence_digests:
        raise AnalysisError("operation or cleanup digest lacks pinned supporting evidence")
    _validate_state_contract(
        cache_state, demand_label, target, start, investment, operations
    )
    terminal_ns = _validate_binding(
        attempt["request_slo_binding"],
        request,
        target,
        start,
        accounting,
        attempt_id,
        request_id,
        evidence_root,
    )
    if any(
        operation["finished_monotonic_ns"] is not None
        and operation["finished_monotonic_ns"] > terminal_ns
        for operation in operations.values()
    ):
        raise AnalysisError("storage operation finishes after the product terminal")
    return {
        "raw": attempt,
        "target": target,
        "starting_state": start,
        "request": request,
        "operations": operations,
        "accounting": accounting,
        "concurrency": concurrency,
        "cleanup": cleanup,
    }


def _validate_attempts_rejected_v1(
    manifest: dict[str, Any], attempts: Sequence[dict[str, Any]], evidence_root: Path
) -> list[dict[str, Any]]:
    manifest = validate_source_manifest(manifest)
    if not attempts:
        raise AnalysisError("attempt ledger is empty")
    manifest_sha256 = canonical_sha256(manifest)
    shaped = [
        _validate_attempt(
            attempt,
            manifest_sha256,
            manifest["execution_gate"]["live_execution_permitted"],
            evidence_root,
        )
        for attempt in attempts
    ]
    attempt_ids = [item["raw"]["attempt_id"] for item in shaped]
    request_ids = [item["raw"]["request_id"] for item in shaped]
    namespaces = [item["concurrency"]["mutable_namespace_id"] for item in shaped]
    if len(attempt_ids) != len(set(attempt_ids)) or len(request_ids) != len(set(request_ids)):
        raise AnalysisError("attempt or request identity is duplicated")
    if len(namespaces) != len(set(namespaces)):
        raise AnalysisError("mutable namespace is shared across attempts")
    observed_states = {item["raw"]["cache_state"] for item in shaped}
    if observed_states != set(CACHE_STATES):
        raise AnalysisError(
            "attempt ledger must contain all four mutually exclusive cache states"
        )
    by_id = {item["raw"]["attempt_id"]: item for item in shaped}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in shaped:
        group = item["concurrency"]["group_id"]
        if group is not None:
            groups[group].append(item)
    for group_id, members in groups.items():
        ids = {item["raw"]["attempt_id"] for item in members}
        if len(ids) < 2 or len({item["target"]["model_id"] for item in members}) < 2:
            raise AnalysisError(f"concurrent group {group_id} lacks distinct models")
        for item in members:
            if set(item["concurrency"]["peer_attempt_ids"]) != ids - {
                item["raw"]["attempt_id"]
            }:
                raise AnalysisError("concurrent peer declarations are incomplete")
            if any(peer not in by_id for peer in item["concurrency"]["peer_attempt_ids"]):
                raise AnalysisError("concurrent peer is absent from ledger")
    dirty_generations: set[str] = set()
    for item in sorted(shaped, key=lambda member: member["request"]["accepted_monotonic_ns"]):
        generation = item["cleanup"]["generation_id"]
        if generation in dirty_generations:
            raise AnalysisError("a dirty/deleted generation was reused")
        if item["cleanup"]["dirty"]:
            dirty_generations.add(generation)
    return shaped


# The original v1 implementation is retained only for audit of rejected commit
# 75e3b1fa.  All public callers execute the v2 full-ledger gate below.
from performance.storage_cache_matrix.catalog_boundary_analysis.contract_v2 import (  # noqa: E402
    validate_attempts_v2 as validate_attempts,
)
