#!/usr/bin/env python3
"""Break a semantic restore clock into orchestration, agent, and response time."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import statistics
from pathlib import Path


def parse_timestamp(value: str) -> float:
    value = re.sub(r"\.(\d{6})\d*Z$", r".\1+00:00", value)
    value = value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else "")
    return dt.datetime.fromisoformat(value).timestamp()


def percentile95(values: list[float]) -> float:
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def summarize(name: str, values: list[float]) -> None:
    print(f"{name}_p50_seconds={statistics.median(values):.3f}")
    print(f"{name}_p95_seconds={percentile95(values):.3f}")
    print(f"{name}_min_seconds={min(values):.3f}")
    print(f"{name}_max_seconds={max(values):.3f}")


def log_events(path: Path, checkpoint_id: str) -> tuple[list[float], list[float]]:
    detections: list[float] = []
    completions: list[float] = []
    for line in path.read_text().splitlines():
        if checkpoint_id not in line:
            continue
        if "Restore target detected" not in line and "Restore timing summary" not in line:
            continue
        timestamp = parse_timestamp(line.split("\t", 1)[0])
        payload = json.loads(line[line.index("{") :])
        if payload.get("checkpoint_id") != checkpoint_id:
            continue
        if "Restore target detected" in line:
            detections.append(timestamp)
        else:
            completions.append(timestamp)
    return detections, completions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("agent_log", type=Path)
    parser.add_argument("checkpoint_id")
    args = parser.parse_args()

    with args.csv.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    detections, completions = log_events(args.agent_log, args.checkpoint_id)
    if not rows or len(rows) != len(detections) or len(rows) != len(completions):
        raise SystemExit(
            "row/event mismatch: "
            f"rows={len(rows)} detections={len(detections)} completions={len(completions)}"
        )

    submitted = [int(row["submitted_unix_ns"]) / 1e9 for row in rows]
    semantic = [int(row["semantic_unix_ns"]) / 1e9 for row in rows]
    summarize(
        "submission_to_agent_detection",
        [detections[i] - submitted[i] for i in range(len(rows))],
    )
    summarize(
        "agent_detection_to_restore_summary",
        [completions[i] - detections[i] for i in range(len(rows))],
    )
    summarize(
        "restore_summary_to_semantic",
        [semantic[i] - completions[i] for i in range(len(rows))],
    )
    summarize(
        "submission_to_semantic",
        [semantic[i] - submitted[i] for i in range(len(rows))],
    )

    if rows[0].get("wake_accepted_unix_ns"):
        wake = [int(row["wake_accepted_unix_ns"]) / 1e9 for row in rows]
        summarize(
            "submission_to_wake_accepted",
            [wake[i] - submitted[i] for i in range(len(rows))],
        )
        summarize(
            "wake_accepted_to_semantic",
            [semantic[i] - wake[i] for i in range(len(rows))],
        )


if __name__ == "__main__":
    main()
