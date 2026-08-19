#!/usr/bin/env python3
"""Executable exact-one-change contract for Kubernetes support-object trials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from performance.request_slo.harness import canonical_sha256, file_sha256

from .contract import BaselineError, _expect_keys, load_plan


COMPARISON_SCHEMA = "archvteams.nebius.ai/k8s-one-variable-comparison/v1"


def matched_projection(plan: dict[str, Any]) -> dict[str, Any]:
    """Return every field that must remain fixed across the support-object pair."""

    # The two runs deliberately share one broker lease/node/cache/credential
    # state.  Only the experiment label and the explicit support-object switch
    # may differ; even Kubernetes UIDs, lease hashes, deadlines, and prices are
    # part of the matched projection.
    projection = {
        key: value
        for key, value in plan.items()
        if key not in {"experiment_id", "variant", "precreated_support", "_resolved"}
    }
    return json.loads(json.dumps(projection, sort_keys=True))


def validate_pair_values(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> str:
    """Return the matched projection hash or reject more than one changed variable."""

    if baseline["variant"] != "per_run_service" or baseline["precreated_support"] != []:
        raise BaselineError("comparison baseline must use the current per-run Service path")
    if (
        candidate["variant"] != "precreated_service"
        or candidate["precreated_support"] != ["service"]
    ):
        raise BaselineError("comparison candidate must change only to one precreated Service")
    baseline_projection = matched_projection(baseline)
    candidate_projection = matched_projection(candidate)
    if baseline_projection != candidate_projection:
        raise BaselineError(
            "paired Kubernetes plans differ outside variant/precreated_support"
        )
    return canonical_sha256(baseline_projection)


def load_comparison(path: Path) -> dict[str, Any]:
    """Validate a source-bound pair artifact and both admitted plan files."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load comparison contract: {type(exc).__name__}") from exc
    value = _expect_keys(
        value,
        {
            "schema", "comparison_id", "status", "allowed_change",
            "baseline_plan_path", "baseline_plan_sha256", "candidate_plan_path",
            "candidate_plan_sha256", "matched_projection_sha256",
        },
        "comparison contract",
    )
    if (
        value["schema"] != COMPARISON_SCHEMA
        or value["status"] != "SEALED"
        or value["allowed_change"] != {
            "variant": ["per_run_service", "precreated_service"],
            "precreated_support": [[], ["service"]],
        }
    ):
        raise BaselineError("comparison contract is not the sealed one-variable design")
    paths = []
    for role in ("baseline", "candidate"):
        plan_path = Path(value[f"{role}_plan_path"])
        if not plan_path.is_absolute():
            plan_path = (path.parent / plan_path).resolve()
        if plan_path.is_symlink() or not plan_path.is_file():
            raise BaselineError(f"comparison {role} plan is unsafe or absent")
        if file_sha256(plan_path) != value[f"{role}_plan_sha256"]:
            raise BaselineError(f"comparison {role} plan differs from its digest")
        paths.append(plan_path)
    baseline = load_plan(paths[0])
    candidate = load_plan(paths[1])
    matched = validate_pair_values(baseline, candidate)
    if matched != value["matched_projection_sha256"]:
        raise BaselineError("comparison matched projection differs from its seal")
    return {
        **value,
        "_resolved_plan_paths": [str(item) for item in paths],
        "_attestation": {
            "schema": "archvteams.nebius.ai/k8s-one-variable-comparison-attestation/v1",
            "comparison_contract_sha256": file_sha256(path),
            "comparison_id": value["comparison_id"],
            "matched_projection_sha256": matched,
            "baseline_plan_sha256": value["baseline_plan_sha256"],
            "baseline_config_sha256": canonical_sha256(
                json.loads(paths[0].read_text(encoding="utf-8"))
            ),
            "baseline_experiment_id": baseline["experiment_id"],
            "baseline_variant": baseline["variant"],
            "candidate_plan_sha256": value["candidate_plan_sha256"],
            "candidate_config_sha256": canonical_sha256(
                json.loads(paths[1].read_text(encoding="utf-8"))
            ),
            "candidate_experiment_id": candidate["experiment_id"],
            "candidate_variant": candidate["variant"],
        },
    }
