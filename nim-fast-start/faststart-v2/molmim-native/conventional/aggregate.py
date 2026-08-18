#!/usr/bin/env python3
"""Aggregate exactly three strict MolMIM conventional-cached trials."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


class AggregateError(ValueError):
    pass


def _positive_timing(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AggregateError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise AggregateError(f"{label} must be positive and finite")
    return result


def aggregate(values: list[dict[str, Any]]) -> dict[str, Any]:
    if len(values) != 3:
        raise AggregateError("exactly three conventional-cached trials are required")
    run_ids: list[str] = []
    demand: list[float] = []
    ready: list[float] = []
    call_1: list[float] = []
    call_2: list[float] = []
    for value in values:
        if (
            value.get("schema")
            != "archvteams.nebius.ai/molmim-conventional-cached-evidence/v1"
            or value.get("status") != "PASS"
            or value.get("mode") != "conventional-cached"
            or value.get("request_count") != 2
            or value.get("semantic_pass_count") != 2
        ):
            raise AggregateError("input is not a strict conventional-cached PASS")
        run_id = value.get("run_id")
        timings = value.get("timings_seconds")
        if not isinstance(run_id, str) or not isinstance(timings, dict):
            raise AggregateError("trial identity or timings are malformed")
        run_ids.append(run_id)
        demand.append(
            _positive_timing(
                timings.get("demand_to_two_semantic_responses"),
                "demand-to-two-semantic timing",
            )
        )
        ready.append(
            _positive_timing(timings.get("demand_to_http_ready"), "HTTP-ready timing")
        )
        call_1.append(_positive_timing(timings.get("call_1"), "first-call timing"))
        call_2.append(_positive_timing(timings.get("call_2"), "second-call timing"))
    if len(set(run_ids)) != 3:
        raise AggregateError("trial run IDs must be unique")
    return {
        "schema": "archvteams.nebius.ai/molmim-conventional-cached-n3/v1",
        "status": "PASS",
        "mode": "conventional-cached",
        "trial_count": 3,
        "request_count": 6,
        "semantic_pass_count": 6,
        "run_ids": run_ids,
        "demand_to_two_semantic_seconds": demand,
        "demand_to_http_ready_seconds": ready,
        "call_1_seconds": call_1,
        "call_2_seconds": call_2,
        "statistics_seconds": {
            "demand_to_two_semantic_min": min(demand),
            "demand_to_two_semantic_median": statistics.median(demand),
            "demand_to_two_semantic_max": max(demand),
            "demand_to_two_semantic_mean": statistics.mean(demand),
            "demand_to_http_ready_median": statistics.median(ready),
            "call_1_median": statistics.median(call_1),
            "call_2_median": statistics.median(call_2),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, nargs=3)
    args = parser.parse_args(argv)
    try:
        values = [json.loads(path.read_text(encoding="utf-8")) for path in args.evidence]
        result = aggregate(values)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"conventional aggregate refused: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
