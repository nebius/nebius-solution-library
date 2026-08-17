#!/usr/bin/env python3
"""Summarize Dynamo Snapshot agent timing records for one checkpoint ID."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path


UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}


def seconds(value: str) -> float:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|us|µs|ns|s)", value)
    if not match:
        raise ValueError(f"unsupported Go duration: {value!r}")
    return float(match.group(1)) * UNITS[match.group(2)]


def percentile(values: list[float], quantile: int) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[quantile - 1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("checkpoint_id")
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for line in args.log.read_text().splitlines():
        if "Restore timing summary" not in line or args.checkpoint_id not in line:
            continue
        payload = json.loads(line.rsplit("\t", 1)[1])
        if payload.get("checkpoint_id") != args.checkpoint_id:
            continue
        restore = payload["restore"]
        phases = restore["phases"]
        rows.append(
            {
                "total": seconds(restore["duration"]),
                "criu": seconds(phases["criu_restore_duration"]),
                "cuda": seconds(phases["cuda_duration"]),
            }
        )

    if not rows:
        raise SystemExit(f"no restore timings for {args.checkpoint_id}")

    print(f"agent_restore_runs={len(rows)}")
    for key in ("total", "criu", "cuda"):
        values = [float(row[key]) for row in rows]
        print(f"agent_{key}_p50_seconds={statistics.median(values):.3f}")
        print(f"agent_{key}_p95_seconds={percentile(values, 95):.3f}")
        print(f"agent_{key}_min_seconds={min(values):.3f}")
        print(f"agent_{key}_max_seconds={max(values):.3f}")


if __name__ == "__main__":
    main()
