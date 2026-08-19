#!/usr/bin/env python3
"""Fail-closed configuration contract for the Kubernetes switch baseline."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    IMAGE_DIGEST_RE,
    SCENARIOS,
    canonical_json,
    file_sha256,
    load_trace,
)


BASELINE_PLAN_SCHEMA = "archvteams.nebius.ai/catalog-switch-k8s-baseline-plan/v1"
AUTHORIZED_PROJECTS = {
    "project-e00z6b02t8ddk96c49": "eu-north1",
    "project-u00tds8vpr00jaxa76s22d": "us-central1",
    "project-i00xz31gpr00xp9jhp982v": "me-west1",
}
VARIANTS = {
    "per_run_service": frozenset(),
    "precreated_service": frozenset({"service"}),
}
STRATEGIES = {"conventional", "snapshot", "none"}
DNS_LABEL = re.compile(r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}")
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")


class BaselineError(ValueError):
    """A benchmark plan cannot be safely admitted."""


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BaselineError(f"{label} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise BaselineError(f"{label} keys differ; missing={missing}, extra={extra}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a canonical identifier")
    return value


def _dns_label(value: Any, label: str) -> str:
    if not isinstance(value, str) or DNS_LABEL.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a Kubernetes DNS label")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise BaselineError(f"{label} is not a lowercase SHA-256")
    return value


def _regular_file(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise BaselineError(f"{label} must be absolute")
    if path.is_symlink() or not path.is_file():
        raise BaselineError(f"{label} must be an existing regular non-symlink file")
    return path


def _load_json(path: Path, label: str) -> Any:
    _regular_file(path, label)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load {label}: {type(exc).__name__}") from exc


def _resolve(plan_path: Path, value: Any, label: str, *, live: bool) -> Path:
    if not isinstance(value, str) or not value:
        raise BaselineError(f"{label} must be a nonempty path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (plan_path.parent / candidate).resolve()
    if live:
        _regular_file(candidate, label)
    elif candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
        raise BaselineError(f"{label} cannot be a symlink or non-file")
    return candidate


def _validate_lease(
    plan: dict[str, Any], plan_path: Path, *, require_live: bool
) -> tuple[dict[str, Any] | None, Path]:
    lease_ref = _expect_keys(
        plan["resource_lease"],
        {"path", "lease_id", "prefix", "admitted_states"},
        "resource_lease",
    )
    _identifier(lease_ref["lease_id"], "resource_lease.lease_id")
    prefix = _identifier(lease_ref["prefix"], "resource_lease.prefix")
    if not prefix.startswith("mlsp-csw-"):
        raise BaselineError("resource lease prefix is outside the frozen broker namespace")
    expected_states = (
        ["PLANNED", "ACTIVE"]
        if plan["campaign_arm"] == "A_prepared_node"
        else ["PLANNED", "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"]
    )
    if lease_ref["admitted_states"] != expected_states:
        raise BaselineError(
            "resource lease states differ from the frozen campaign-arm transition"
        )
    lease_path = _resolve(
        plan_path, lease_ref["path"], "resource_lease.path", live=require_live
    )
    if not lease_path.exists():
        return None, lease_path
    lease = _load_json(lease_path, "resource lease")
    if lease.get("schema_version") != "catalog-switch-kubernetes-resource-lease/v2":
        raise BaselineError(
            "Kubernetes execution requires the versioned cluster/node-group broker contract"
        )
    expected = {
        "lease_id": lease_ref["lease_id"],
        "prefix": lease_ref["prefix"],
        "task_id": plan["task_id"],
        "project_id": plan["project_id"],
        "region": plan["region"],
        "campaign_arm": plan["campaign_arm"],
    }
    actual = {
        "lease_id": lease.get("lease_id"),
        "prefix": lease.get("prefix"),
        "task_id": lease.get("request", {}).get("task_id"),
        "project_id": lease.get("request", {}).get("project_id"),
        "region": lease.get("request", {}).get("region"),
        "campaign_arm": lease.get("request", {}).get("campaign_arm"),
    }
    if actual != expected:
        raise BaselineError(
            f"resource lease identity differs from plan; expected={expected}, actual={actual}"
        )
    if lease.get("state") not in lease_ref["admitted_states"]:
        raise BaselineError("resource lease state differs from the admitted plan")
    if require_live and plan["campaign_arm"] == "A_prepared_node":
        if lease.get("state") != "ACTIVE":
            raise BaselineError("prepared-node live execution requires an ACTIVE broker lease")
        if not lease.get("isolation_proof"):
            raise BaselineError("prepared-node live execution requires the broker isolation proof")
        if (
            not lease.get("cluster_id")
            or len(lease.get("node_group_ids", [])) != 1
            or len(lease.get("node_ids", [])) != 1
        ):
            raise BaselineError("prepared-node live lease lacks exact cluster/node identities")
    if require_live and plan["campaign_arm"] == "B_new_preemptible_node":
        if lease.get("state") != "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP":
            raise BaselineError(
                "new-node arm must enter T0 with target-neutral support and no GPU node group"
            )
        if not lease.get("cluster_id") or lease.get("node_group_ids") or lease.get("node_ids"):
            raise BaselineError(
                "new-node arm support lease must contain a fresh cluster and zero GPU nodes"
            )
        if not lease.get("isolation_proof"):
            raise BaselineError("new-node arm requires a fresh support-cluster isolation proof")
    return lease, lease_path


def _validate_model(
    value: Any, index: int, plan_path: Path, *, require_live: bool
) -> dict[str, Any]:
    model = _expect_keys(
        value,
        {
            "model_id",
            "model_version",
            "artifact_id",
            "artifact_version",
            "artifact_sha256",
            "image_digest",
            "target_templates",
            "validator_id",
            "validator_path",
            "endpoint_path",
            "ready_path",
            "request_file",
            "request_sha256",
            "container_name",
            "artifact_bytes",
            "image_bytes",
        },
        f"models[{index}]",
    )
    for key in ("model_id", "model_version", "artifact_id", "artifact_version", "validator_id"):
        _identifier(model[key], f"models[{index}].{key}")
    _digest(model["artifact_sha256"], f"models[{index}].artifact_sha256")
    if not isinstance(model["image_digest"], str) or IMAGE_DIGEST_RE.fullmatch(
        model["image_digest"]
    ) is None:
        raise BaselineError(f"models[{index}].image_digest is not digest-pinned")
    _dns_label(model["container_name"], f"models[{index}].container_name")
    for key in ("endpoint_path", "ready_path"):
        if (
            not isinstance(model[key], str)
            or not model[key].startswith("/")
            or "?" in model[key]
            or "#" in model[key]
        ):
            raise BaselineError(f"models[{index}].{key} must be an absolute HTTP path")
    for key in ("artifact_bytes", "image_bytes"):
        if not isinstance(model[key], int) or model[key] < 0:
            raise BaselineError(f"models[{index}].{key} must be nonnegative")
    templates = _expect_keys(
        model["target_templates"], {"conventional", "snapshot"}, f"models[{index}].target_templates"
    )
    paths = {
        "conventional_template": _resolve(
            plan_path,
            templates["conventional"],
            f"models[{index}].target_templates.conventional",
            live=True,
        ),
        "snapshot_template": _resolve(
            plan_path,
            templates["snapshot"],
            f"models[{index}].target_templates.snapshot",
            live=True,
        ),
        "validator_path": _resolve(
            plan_path, model["validator_path"], f"models[{index}].validator_path", live=True
        ),
        "request_file": _resolve(
            plan_path, model["request_file"], f"models[{index}].request_file", live=True
        ),
    }
    actual_request = file_sha256(paths["request_file"])
    if actual_request != _digest(model["request_sha256"], f"models[{index}].request_sha256"):
        raise BaselineError(f"models[{index}] request digest differs from the pinned file")
    model["_paths"] = {key: str(path) for key, path in paths.items()}
    model["validator_sha256"] = file_sha256(paths["validator_path"])
    return model


def validate_plan(
    value: Any, plan_path: Path, *, require_live: bool = False
) -> dict[str, Any]:
    """Validate a plan and return a normalized copy with resolved private paths."""

    plan = _expect_keys(
        value,
        {
            "schema",
            "experiment_id",
            "task_id",
            "project_id",
            "region",
            "backend",
            "backend_version",
            "code_revision",
            "campaign_arm",
            "boundary_policy",
            "semantic_calls_per_attempt",
            "product_terminal_call",
            "variant",
            "precreated_support",
            "scenario_strategies",
            "promoted_scenarios",
            "minimum_repetitions",
            "trace_path",
            "trace_sha256",
            "models",
            "kubernetes",
            "resource_lease",
            "cost",
            "cleanup",
        },
        "plan",
    )
    if plan["schema"] != BASELINE_PLAN_SCHEMA:
        raise BaselineError("plan schema is not supported")
    for key in ("experiment_id", "task_id", "backend", "backend_version"):
        _identifier(plan[key], f"plan.{key}")
    if plan["task_id"] != "catalog-switch-k8s-baseline":
        raise BaselineError("plan task_id does not own this benchmark")
    if plan["project_id"] not in AUTHORIZED_PROJECTS:
        raise BaselineError("project is outside the epic allowlist")
    if plan["region"] != AUTHORIZED_PROJECTS[plan["project_id"]]:
        raise BaselineError("project and region do not match the epic allowlist")
    if not isinstance(plan["code_revision"], str) or COMMIT.fullmatch(
        plan["code_revision"]
    ) is None:
        raise BaselineError("code_revision must be an exact Git commit")
    if plan["campaign_arm"] not in {"A_prepared_node", "B_new_preemptible_node"}:
        raise BaselineError("campaign_arm must be A_prepared_node or B_new_preemptible_node")
    boundary_policy = _expect_keys(
        plan["boundary_policy"],
        {"node_creation", "artifact_localization", "model_specific_work"},
        "boundary_policy",
    )
    expected_boundary = (
        {
            "node_creation": "before_cohort_t0",
            "artifact_localization": "declared_cache_precondition_or_after_t0",
            "model_specific_work": "declared_occupant_precondition_or_after_t0",
        }
        if plan["campaign_arm"] == "A_prepared_node"
        else {
            "node_creation": "after_t0",
            "artifact_localization": "after_t0",
            "model_specific_work": "after_t0",
        }
    )
    if boundary_policy != expected_boundary:
        raise BaselineError("campaign arm violates its frozen T0 boundary policy")
    if plan["semantic_calls_per_attempt"] != 2 or plan["product_terminal_call"] != 1:
        raise BaselineError(
            "campaign must preserve two-call qualification and the call-1 product terminal"
        )
    variant = plan["variant"]
    if variant not in VARIANTS:
        raise BaselineError("unknown support-object variant")
    support = plan["precreated_support"]
    if not isinstance(support, list) or len(support) != len(set(support)):
        raise BaselineError("precreated_support must contain unique values")
    if frozenset(support) != VARIANTS[variant]:
        raise BaselineError("variant differs from baseline by more than its admitted object")

    strategies = _expect_keys(
        plan["scenario_strategies"], set(SCENARIOS), "scenario_strategies"
    )
    if any(item not in STRATEGIES for item in strategies.values()):
        raise BaselineError("scenario strategy is not conventional, snapshot, or none")
    if strategies["capacity_miss"] != "none":
        raise BaselineError("capacity_miss must not launch a runtime")
    if strategies["checkpoint_fallback"] != "conventional":
        raise BaselineError("checkpoint_fallback must use the honest conventional path")
    if "snapshot" not in strategies.values() or "conventional" not in strategies.values():
        raise BaselineError("plan must cover both conventional and snapshot startup")
    promoted = plan["promoted_scenarios"]
    if (
        not isinstance(promoted, list)
        or not promoted
        or len(promoted) != len(set(promoted))
        or any(item not in SCENARIOS for item in promoted)
    ):
        raise BaselineError("promoted_scenarios is invalid")
    if not isinstance(plan["minimum_repetitions"], int) or plan["minimum_repetitions"] < 30:
        raise BaselineError("promoted cohorts require at least 30 repetitions")

    trace_path = _resolve(plan_path, plan["trace_path"], "trace_path", live=True)
    trace = load_trace(trace_path)
    if file_sha256(trace_path) != _digest(plan["trace_sha256"], "trace_sha256"):
        raise BaselineError("trace digest differs from the pinned file")
    counts = {scenario: 0 for scenario in SCENARIOS}
    for request in trace["requests"]:
        counts[request["scenario"]] += 1
    short = {
        scenario: counts[scenario]
        for scenario in promoted
        if counts[scenario] < plan["minimum_repetitions"]
    }
    if short:
        raise BaselineError(f"promoted trace cohorts are undersized: {short}")

    if not isinstance(plan["models"], list) or len(plan["models"]) < 2:
        raise BaselineError("plan requires at least two matched models")
    models = [
        _validate_model(item, index, plan_path, require_live=require_live)
        for index, item in enumerate(plan["models"])
    ]
    model_keys = {(item["model_id"], item["model_version"]) for item in models}
    if len(model_keys) != len(models):
        raise BaselineError("model identities are duplicated")
    trace_keys = {
        (item["target"]["model_id"], item["target"]["model_version"])
        for item in trace["requests"]
    }
    if not trace_keys <= model_keys:
        raise BaselineError("trace selects a model absent from the plan")

    kube = _expect_keys(
        plan["kubernetes"],
        {
            "kubeconfig",
            "context",
            "expected_server",
            "namespace",
            "node_name",
            "gpu_type",
            "gpu_count",
            "sentinel_pod",
            "ready_timeout_seconds",
            "drain_timeout_seconds",
        },
        "kubernetes",
    )
    for key in ("context", "node_name", "gpu_type"):
        _identifier(kube[key], f"kubernetes.{key}")
    for key in ("namespace", "sentinel_pod"):
        _dns_label(kube[key], f"kubernetes.{key}")
    if not isinstance(kube["expected_server"], str) or not kube["expected_server"].startswith(
        "https://"
    ):
        raise BaselineError("kubernetes.expected_server must be HTTPS")
    if kube["gpu_type"] != "H100" or kube["gpu_count"] != 1:
        raise BaselineError("this baseline is pinned to one real H100")
    for key in ("ready_timeout_seconds", "drain_timeout_seconds"):
        if not isinstance(kube[key], int) or kube[key] <= 0:
            raise BaselineError(f"kubernetes.{key} must be positive")
    if kube["drain_timeout_seconds"] > 30:
        raise BaselineError("drain timeout exceeds security control CTL-13")
    kubeconfig = _resolve(
        plan_path,
        kube["kubeconfig"],
        "kubernetes.kubeconfig",
        live=require_live and plan["campaign_arm"] == "A_prepared_node",
    )

    cost = _expect_keys(
        plan["cost"],
        {
            "lease_hour_usd",
            "transfer_usd_per_gib",
            "pre_t0_setup_cost_usd",
            "expected_duration_hours",
            "hard_cap_usd",
            "price_snapshot_utc",
            "source",
        },
        "cost",
    )
    for key in (
        "lease_hour_usd",
        "expected_duration_hours",
        "hard_cap_usd",
    ):
        if isinstance(cost[key], bool) or not isinstance(cost[key], (int, float)) or cost[key] <= 0:
            raise BaselineError(f"cost.{key} must be positive")
    for key in ("transfer_usd_per_gib", "pre_t0_setup_cost_usd"):
        if isinstance(cost[key], bool) or not isinstance(cost[key], (int, float)) or cost[key] < 0:
            raise BaselineError(f"cost.{key} must be nonnegative")
    if (
        cost["lease_hour_usd"] * cost["expected_duration_hours"]
        + cost["pre_t0_setup_cost_usd"]
        > cost["hard_cap_usd"]
    ):
        raise BaselineError("expected lease and setup cost exceeds the hard cap")
    if not isinstance(cost["price_snapshot_utc"], str) or not cost[
        "price_snapshot_utc"
    ].endswith("Z"):
        raise BaselineError("cost.price_snapshot_utc must be UTC")
    if not isinstance(cost["source"], str) or len(cost["source"].strip()) < 10:
        raise BaselineError("cost.source is too vague")
    cleanup = _expect_keys(
        plan["cleanup"], {"owner", "deadline_utc", "plan"}, "cleanup"
    )
    _identifier(cleanup["owner"], "cleanup.owner")
    if not isinstance(cleanup["deadline_utc"], str) or not cleanup["deadline_utc"].endswith("Z"):
        raise BaselineError("cleanup.deadline_utc must be UTC")
    if not isinstance(cleanup["plan"], str) or len(cleanup["plan"].strip()) < 20:
        raise BaselineError("cleanup.plan is too vague")

    lease, lease_path = _validate_lease(plan, plan_path, require_live=require_live)
    normalized = json.loads(canonical_json(plan))
    normalized["_resolved"] = {
        "plan_path": str(plan_path.resolve()),
        "trace_path": str(trace_path),
        "kubeconfig": str(kubeconfig),
        "lease_path": str(lease_path),
        "lease_loaded": lease is not None,
        "config_sha256": hashlib.sha256(canonical_json(plan).encode()).hexdigest(),
    }
    normalized["models"] = models
    return normalized


def load_plan(path: Path, *, require_live: bool = False) -> dict[str, Any]:
    """Load and validate one canonical plan file."""

    _regular_file(path, "plan")
    raw = path.read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BaselineError("plan is invalid JSON") from exc
    if raw != canonical_json(value) + "\n":
        raise BaselineError("plan must be canonical JSON with one terminal newline")
    return validate_plan(value, path, require_live=require_live)


def safe_output_path(path: Path) -> Path:
    """Require a new output below an existing non-symlink directory."""

    if not path.is_absolute():
        raise BaselineError("output path must be absolute")
    if os.path.lexists(path):
        raise BaselineError("output path already exists")
    parent = path.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise BaselineError("output parent must be a real directory")
    return parent / path.name
