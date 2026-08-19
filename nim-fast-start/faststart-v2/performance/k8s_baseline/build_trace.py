#!/usr/bin/env python3
"""Build a state-coherent, single-scenario promoted Kubernetes cohort trace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    CATALOG_SCHEMA,
    SCENARIOS,
    TRACE_SCHEMA,
    canonical_sha256,
    validate_trace,
    write_canonical_json,
)


def precondition(scenario: str, target: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    target_occupant = {
        "model_id": target["model_id"],
        "model_version": target["model_version"],
    }
    other_occupant = {
        "model_id": other["model_id"],
        "model_version": other["model_version"],
    }
    values = {
        "same_model_hot": {
            "current_node_occupant": target_occupant,
            "cache": {
                "image": "local_verified",
                "artifact": "memory_hit",
                "checkpoint": "not_applicable",
                "storage": "ready",
            },
            "capacity": "allocated",
            "queue_depth": 0,
        },
        "idle_local": {
            "current_node_occupant": None,
            "cache": {
                "image": "local_verified",
                "artifact": "node_local_hit",
                "checkpoint": "compatible_hit",
                "storage": "ready",
            },
            "capacity": "allocated",
            "queue_depth": 0,
        },
        "a_to_b_local": {
            "current_node_occupant": other_occupant,
            "cache": {
                "image": "local_verified",
                "artifact": "attached_storage_hit",
                "checkpoint": "compatible_hit",
                "storage": "ready",
            },
            "capacity": "allocated",
            "queue_depth": 1,
        },
        "a_to_b_remote": {
            "current_node_occupant": other_occupant,
            "cache": {
                "image": "remote_required",
                "artifact": "remote_miss",
                "checkpoint": "missing",
                "storage": "localization_required",
            },
            "capacity": "queued",
            "queue_depth": 2,
        },
        "checkpoint_fallback": {
            "current_node_occupant": other_occupant,
            "cache": {
                "image": "local_verified",
                "artifact": "attached_storage_hit",
                "checkpoint": "stale_version",
                "storage": "ready",
            },
            "capacity": "allocated",
            "queue_depth": 0,
        },
        "capacity_miss": {
            "current_node_occupant": None,
            "cache": {
                "image": "unavailable",
                "artifact": "unavailable",
                "checkpoint": "missing",
                "storage": "unavailable",
            },
            "capacity": "unavailable",
            "queue_depth": 3,
        },
    }
    return values[scenario]


def build_trace(
    catalog: dict[str, Any],
    *,
    scenario: str,
    request_count: int,
    interval_ms: int,
    trace_id: str,
    seed: int,
) -> dict[str, Any]:
    if set(catalog) != {"schema", "models"} or catalog["schema"] != CATALOG_SCHEMA:
        raise ValueError("catalog does not use the shared v1 contract")
    models = catalog["models"]
    if not isinstance(models, list) or len(models) != 2:
        raise ValueError("matched Kubernetes cohorts require exactly two models")
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    if request_count < 30:
        raise ValueError("promoted scenario trace requires at least 30 requests")
    if interval_ms < 100:
        raise ValueError("offered interval must leave at least the v1 100 ms recorder ceiling")
    requests = []
    for index in range(request_count):
        if scenario in {"a_to_b_local", "a_to_b_remote", "checkpoint_fallback"}:
            target = models[index % 2]
            other = models[(index + 1) % 2]
        else:
            target, other = models
        request_id = f"{trace_id}-request-{index + 1:06d}"
        requests.append(
            {
                "sequence": index,
                "request_id": request_id,
                "attempt_id": f"{trace_id}-attempt-{index + 1:06d}",
                "offered_at_offset_ms": index * interval_ms,
                "scenario": scenario,
                "target": {
                    key: target[key]
                    for key in (
                        "model_id",
                        "model_version",
                        "artifact_id",
                        "artifact_version",
                        "artifact_sha256",
                    )
                },
                "input": dict(target["input"]),
                "precondition": precondition(scenario, target, other),
            }
        )
    trace = {
        "schema": TRACE_SCHEMA,
        "trace_id": trace_id,
        "distribution": "adversarial",
        "seed": seed,
        "catalog_sha256": canonical_sha256(catalog),
        "request_count": request_count,
        "scenario_labels": list(SCENARIOS),
        "requests": requests,
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return validate_trace(trace)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    parser.add_argument("--requests", required=True, type=int)
    parser.add_argument("--interval-ms", required=True, type=int)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        trace = build_trace(
            catalog,
            scenario=args.scenario,
            request_count=args.requests,
            interval_ms=args.interval_ms,
            trace_id=args.trace_id,
            seed=args.seed,
        )
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("output must be new")
        write_canonical_json(args.output, trace)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": "PASS", "trace_sha256": trace["trace_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
