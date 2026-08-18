#!/usr/bin/env python3
"""Aggregate exactly three passing, matched RFdiffusion native trials."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence


HERE = Path(__file__).resolve().parent
PROFILE = json.loads((HERE / "profile.json").read_text(encoding="utf-8"))


class AggregateError(ValueError):
    pass


def sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def finite_positive(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise AggregateError(f"{label} must be a finite positive number")
    return float(value)


def statistics_block(values: list[float]) -> dict[str, Any]:
    return {
        "values": values,
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def load_summary(path: Path, mode: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AggregateError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AggregateError(f"{path} is not a JSON object")
    exact = {
        "schema": "archvteams.nebius.ai/rfdiffusion-native-trial-summary/v1",
        "status": "PASS",
        "model": "RFdiffusion",
        "image": PROFILE["model"]["image"],
        "gpu_topology": "1x NVIDIA H100, full GPU, non-MIG",
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
    seeds = [case.get("invariant", {}).get("random_seed") for case in semantic["cases"]]
    if seeds != PROFILE["semantic_profile"]["request_seeds"]:
        raise AggregateError(f"{path}: semantic seeds differ from the pinned oracle")
    request_digests = [case.get("request_sha256") for case in semantic["cases"]]
    if request_digests != PROFILE["semantic_profile"]["request_body_sha256"]:
        raise AggregateError(f"{path}: semantic request bodies differ from the pinned oracle")
    response_digests = [case.get("response_sha256") for case in semantic["cases"]]
    if not all(sha256_digest(item) for item in response_digests) or len(set(response_digests)) != 2:
        raise AggregateError(f"{path}: seeded semantic responses are not distinct")
    case_run_ids = [case.get("run_id") for case in semantic["cases"]]
    if len(set(case_run_ids)) != 2 or any(
        not isinstance(item, str) or not item for item in case_run_ids
    ):
        raise AggregateError(f"{path}: semantic case run IDs are not distinct")
    for case in semantic["cases"]:
        if case.get("status") != "PASS" or case.get("ok") is not True or case.get("http_status") != 200:
            raise AggregateError(f"{path}: semantic case did not strictly pass")
        invariant = case.get("invariant", {})
        if invariant.get("fixture_sha256") != PROFILE["semantic_profile"]["fixture_sha256"]:
            raise AggregateError(f"{path}: semantic fixture identity is invalid")
        backbone = invariant.get("backbone", {})
        residues = backbone.get("residue_count")
        if (
            isinstance(residues, bool)
            or not isinstance(residues, int)
            or not PROFILE["semantic_profile"]["residue_count_min"]
            <= residues
            <= PROFILE["semantic_profile"]["residue_count_max"]
            or backbone.get("complete_backbone_residue_count") != residues
            or backbone.get("ca_count") != residues
            or not isinstance(backbone.get("adjacent_ca_pair_count"), int)
            or backbone["adjacent_ca_pair_count"] < 15
        ):
            raise AggregateError(f"{path}: semantic backbone invariant is invalid")
    finite_positive(value.get("demand_to_two_semantic_seconds"), f"{path}: end-to-end")
    finite_positive(value.get("demand_to_http_ready_seconds"), f"{path}: HTTP ready")
    finite_positive(
        value.get("demand_to_kubernetes_ready_seconds"), f"{path}: Kubernetes Ready"
    )
    request_1 = finite_positive(
        value.get("semantic_request_1_seconds"), f"{path}: request 1"
    )
    request_2 = finite_positive(
        value.get("semantic_request_2_seconds"), f"{path}: request 2"
    )
    case_elapsed = [
        finite_positive(case.get("elapsed_seconds"), f"{path}: semantic case elapsed")
        for case in semantic["cases"]
    ]
    if [request_1, request_2] != case_elapsed:
        raise AggregateError(f"{path}: request timings differ from semantic evidence")
    timestamps = value.get("timing_evidence")
    if not isinstance(timestamps, dict) or any(
        not isinstance(timestamps.get(key), str) or not timestamps[key]
        for key in (
            "demand_at",
            "http_ready_at",
            "kubernetes_ready_at",
            "semantic_started_at",
            "semantic_finished_at",
        )
    ):
        raise AggregateError(f"{path}: timing evidence timestamps are incomplete")
    finite_positive(semantic.get("total_elapsed_seconds"), f"{path}: semantic duration")
    worker = value.get("worker_receipt")
    if not isinstance(worker, dict) or worker.get("status") != "succeeded":
        raise AggregateError(f"{path}: worker receipt did not succeed")
    finite_positive(worker.get("duration_ms"), f"{path}: worker duration")
    if value.get("semantic_response_sha256") != response_digests:
        raise AggregateError(f"{path}: summary response digests differ from semantic evidence")
    try:
        if str(uuid.UUID(str(value.get("pod_uid")))) != value.get("pod_uid"):
            raise ValueError
    except ValueError as exc:
        raise AggregateError(f"{path}: target Pod UID is invalid") from exc
    if not sha256_digest(value.get("pod_spec_sha256")):
        raise AggregateError(f"{path}: target PodSpec digest is invalid")
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
    if (
        len(manifests) != 1
        or not sha256_digest(next(iter(manifests)))
    ):
        raise AggregateError("the three runs did not use one immutable artifact manifest")
    e2e = [float(item["demand_to_two_semantic_seconds"]) for item in summaries]
    http_ready = [float(item["demand_to_http_ready_seconds"]) for item in summaries]
    kubernetes_ready = [
        float(item["demand_to_kubernetes_ready_seconds"]) for item in summaries
    ]
    request_1 = [float(item["semantic_request_1_seconds"]) for item in summaries]
    request_2 = [float(item["semantic_request_2_seconds"]) for item in summaries]
    restore = [float(item["worker_receipt"]["duration_ms"]) / 1000 for item in summaries]
    semantic = [float(item["semantic"]["total_elapsed_seconds"]) for item in summaries]
    return {
        "schema": "archvteams.nebius.ai/rfdiffusion-native-n3/v1",
        "status": "PASS",
        "model": "RFdiffusion",
        "image": PROFILE["model"]["image"],
        "gpu_topology": "1x NVIDIA H100, full GPU, non-MIG",
        "image_io_mode": mode,
        "checkpoint_id": PROFILE["artifacts"][mode]["checkpoint_id"],
        "artifact_manifest_sha256": next(iter(manifests)),
        "trial_count": 3,
        "semantic_pass_count": 6,
        "run_ids": run_ids,
        "pod_uids": pod_uids,
        "demand_to_http_ready_seconds": statistics_block(http_ready),
        "demand_to_kubernetes_ready_seconds": statistics_block(kubernetes_ready),
        "semantic_request_1_seconds": statistics_block(request_1),
        "semantic_request_2_seconds": statistics_block(request_2),
        "demand_to_two_semantic_seconds": statistics_block(e2e),
        "worker_restore_seconds": statistics_block(restore),
        "semantic_probe_seconds": statistics_block(semantic),
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
        print(f"aggregate-rfdiffusion: refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
