#!/usr/bin/env python3
"""Fail-closed aggregation for PROVISIONAL Modal pilot adapter cohorts.

Outputs are adapter-test summaries only, never promotable backend
comparisons: the shared external-client ledger owned by
``catalog-switch-request-slo-harness`` supersedes this module, and cohorts
must be re-aggregated through it before any cross-backend claim.

Sample-size gates are local hard floors, not warnings:
- p50 requires n >= 5 valid responses,
- p95 requires n >= 20,
- p99 requires n >= 100,
- a promoted cold/switch claim requires n >= 30 valid responses.
Percentiles use the conservative nearest-rank-ceiling method (never
interpolated below an observed sample). Failures are always reported
alongside, never dropped.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .event_schema import EventValidationError, validate_event

MIN_N = {"p50": 5, "p95": 20, "p99": 100}
PROMOTION_MIN_N = 30


class AggregationError(ValueError):
    """A cohort violates an aggregation gate."""


def conservative_percentile(samples: Sequence[float], percentile: float) -> float:
    """Nearest-rank (ceiling) percentile: an actually observed upper sample."""
    if not samples:
        raise AggregationError("cannot take a percentile of zero samples")
    if not 0.0 < percentile <= 100.0:
        raise AggregationError("percentile must be in (0, 100]")
    ordered = sorted(float(s) for s in samples)
    rank = math.ceil(percentile / 100.0 * len(ordered))
    return ordered[max(rank, 1) - 1]


def aggregate_cohort(
    events: Sequence[Mapping[str, Any]],
    *,
    promoted: bool = False,
) -> dict[str, Any]:
    """Aggregate one (pilot, mode) cohort of validated request events."""
    if not events:
        raise AggregationError("cohort has no events")

    checked = [validate_event(e) for e in events]
    keys = {(e["pilot"], e["mode"]) for e in checked}
    if len(keys) != 1:
        raise AggregationError(f"cohort mixes (pilot, mode) pairs: {sorted(keys)}")
    (pilot, mode), = keys

    valid = [e for e in checked if e["outcome"] == "valid_response"]
    failures = [e for e in checked if e["outcome"] != "valid_response"]
    latencies = [
        float(e["t_first_valid_response_monotonic_s"]) - float(e["t0_monotonic_s"])
        for e in valid
    ]

    if promoted and mode in ("cold", "switch") and len(valid) < PROMOTION_MIN_N:
        raise AggregationError(
            f"promoted {mode} cohort needs >= {PROMOTION_MIN_N} valid responses, "
            f"got {len(valid)}"
        )

    percentiles: dict[str, float | None] = {}
    for name, minimum in MIN_N.items():
        if len(latencies) >= minimum:
            percentiles[name] = conservative_percentile(latencies, float(name[1:]))
        else:
            percentiles[name] = None

    return {
        "pilot": pilot,
        "mode": mode,
        "n_total": len(checked),
        "n_valid": len(valid),
        "n_failures": len(failures),
        "failure_reasons": sorted(
            {str(e.get("failure_reason", "unspecified")) for e in failures}
        ),
        "attempts_total": int(sum(int(e["attempts"]) for e in checked)),
        "gpu_allocated_set": sorted({e["gpu_allocated"] for e in checked}),
        "cache_states": sorted({e["cache_state"] for e in checked}),
        "latency_s": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            **percentiles,
        },
        "gates": {
            "promotion_min_n": PROMOTION_MIN_N,
            "percentile_min_n": dict(MIN_N),
            "promoted": promoted,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import json

    from .event_schema import load_events

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_jsonl", help="validated request-event JSONL file")
    parser.add_argument("--promoted", action="store_true")
    args = parser.parse_args(argv)
    try:
        events = load_events(args.events_jsonl)
        summary = aggregate_cohort(events, promoted=args.promoted)
    except (EventValidationError, AggregationError) as exc:
        print(f"FAIL-CLOSED: {exc}")
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
