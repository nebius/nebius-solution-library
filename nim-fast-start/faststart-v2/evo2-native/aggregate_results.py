#!/usr/bin/env python3
"""Aggregate exactly three passing, matched Evo2 native trials."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
PROFILE = json.loads((HERE / "profile.json").read_text(encoding="utf-8"))


class AggregateError(ValueError):
    pass


def finite_positive(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise AggregateError(f"{label} must be a finite positive number")
    return float(value)


def load_summary(path: Path, mode: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AggregateError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AggregateError(f"{path} is not a JSON object")
    exact = {
        "schema": "archvteams.nebius.ai/evo2-native-trial-summary/v1",
        "status": "PASS",
        "model": "Evo2-40B",
        "image": PROFILE["model"]["image"],
        "image_io_mode": mode,
        "checkpoint_id": PROFILE["artifacts"][mode]["checkpoint_id"],
        "semantic_request_count": 2,
    }
    for key, expected in exact.items():
        if value.get(key) != expected:
            raise AggregateError(f"{path}: {key} does not match the n=3 contract")
    semantic = value.get("semantic")
    if (
        not isinstance(semantic, dict)
        or semantic.get("status") != "PASS"
        or semantic.get("request_count") != 2
        or semantic.get("passed_case_count") != 2
        or semantic.get("failed_case_count") != 0
        or not isinstance(semantic.get("cases"), list)
        or len(semantic["cases"]) != 2
    ):
        raise AggregateError(f"{path}: semantic receipt is not exactly two passing calls")
    expected_sequences = PROFILE["semantic_profile"]["expected_sequences"]
    observed_sequences = [
        case.get("invariant", {}).get("output_sequence") for case in semantic["cases"]
    ]
    if observed_sequences != expected_sequences:
        raise AggregateError(f"{path}: semantic sequences differ from the pinned oracle")
    finite_positive(value.get("demand_to_two_semantic_seconds"), f"{path}: end-to-end")
    worker = value.get("worker_receipt")
    if not isinstance(worker, dict) or worker.get("status") != "succeeded":
        raise AggregateError(f"{path}: worker receipt did not succeed")
    finite_positive(worker.get("duration_ms"), f"{path}: worker duration")
    return value


def aggregate(paths: Sequence[Path], mode: str) -> dict[str, Any]:
    if len(paths) != 3:
        raise AggregateError("exactly three trial summaries are required")
    summaries = [load_summary(path, mode) for path in paths]
    run_ids = [item.get("run_id") for item in summaries]
    pod_uids = [item.get("pod_uid") for item in summaries]
    if len(set(run_ids)) != 3 or any(not isinstance(item, str) or not item for item in run_ids):
        raise AggregateError("the three run IDs must be unique and nonempty")
    if len(set(pod_uids)) != 3 or any(not isinstance(item, str) or not item for item in pod_uids):
        raise AggregateError("the three target Pod UIDs must be unique and nonempty")
    manifests = {item.get("artifact_manifest_sha256") for item in summaries}
    if len(manifests) != 1:
        raise AggregateError("the three runs did not use one immutable artifact manifest")
    e2e = [float(item["demand_to_two_semantic_seconds"]) for item in summaries]
    restore = [float(item["worker_receipt"]["duration_ms"]) / 1000 for item in summaries]
    semantic = [float(item["semantic"]["total_elapsed_seconds"]) for item in summaries]
    return {
        "schema": "archvteams.nebius.ai/evo2-native-n3/v1",
        "status": "PASS",
        "model": "Evo2-40B",
        "image": PROFILE["model"]["image"],
        "gpu_topology": "1x NVIDIA H200 SXM, full GPU, non-MIG",
        "image_io_mode": mode,
        "checkpoint_id": PROFILE["artifacts"][mode]["checkpoint_id"],
        "artifact_manifest_sha256": next(iter(manifests)),
        "trial_count": 3,
        "semantic_pass_count": 6,
        "run_ids": run_ids,
        "pod_uids": pod_uids,
        "demand_to_two_semantic_seconds": {
            "values": e2e,
            "median": statistics.median(e2e),
            "minimum": min(e2e),
            "maximum": max(e2e),
        },
        "worker_restore_seconds": {
            "values": restore,
            "median": statistics.median(restore),
            "minimum": min(restore),
            "maximum": max(restore),
        },
        "semantic_probe_seconds": {
            "values": semantic,
            "median": statistics.median(semantic),
            "minimum": min(semantic),
            "maximum": max(semantic),
        },
        "source_summaries": [str(path) for path in paths],
    }


def write_exclusive(path: Path, payload: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    if path.is_symlink() or os.path.lexists(path):
        raise AggregateError(f"refusing existing aggregate output: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent / path.name, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-io-mode", choices=("direct", "buffered"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("summaries", type=Path, nargs=3)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = aggregate(args.summaries, args.image_io_mode)
        payload = (
            json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode("ascii")
        write_exclusive(args.output, payload)
        sys.stdout.buffer.write(payload)
        return 0
    except (AggregateError, OSError) as exc:
        print(f"aggregate-evo2: refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
