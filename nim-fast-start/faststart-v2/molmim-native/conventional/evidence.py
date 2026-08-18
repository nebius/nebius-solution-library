#!/usr/bin/env python3
"""Build strict evidence for one MolMIM conventional-cached comparison trial."""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import render as lane_render
except ImportError:  # pragma: no cover - package import path
    from . import render as lane_render


IMAGE = (
    "nvcr.io/nim/nvidia/molmim@sha256:"
    "7700c5556935a93055bee5367d36acb6d3e55d22fd1ba28503f5447656fa63fa"
)
NODE = "computeinstance-e00hf93cfnsgaxygn3"
NAMESPACE = "nim-fast-start"
REQUEST_SHA256 = (
    "3a59acaf04e18fc5a7ed37b27ffdeee05f2542f23734d204bf487cc5f172a55e",
    "98ac4fccf35f4a9c3cbb3666b8d98218b24e7f2d5cff9cb174c76b2d242927da",
)


class EvidenceError(ValueError):
    """A recorded comparator object does not prove a strict cached trial."""


def _require_expected(actual: Any, expected: Any, label: str) -> None:
    """Require the rendered subtree while allowing Kubernetes-added fields."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise EvidenceError(f"{label} is not an object")
        for key, expected_value in expected.items():
            if key not in actual:
                raise EvidenceError(f"{label}.{key} is absent")
            _require_expected(actual[key], expected_value, f"{label}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise EvidenceError(f"{label} list does not match the rendered contract")
        for index, (actual_value, expected_value) in enumerate(
            zip(actual, expected, strict=True)
        ):
            _require_expected(actual_value, expected_value, f"{label}[{index}]")
        return
    if actual != expected:
        raise EvidenceError(f"{label} does not match the rendered contract")


def _load(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"{label} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot load {label}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must contain an object")
    return value


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError(f"{label} is not an RFC3339 UTC timestamp")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{label} is not an RFC3339 UTC timestamp") from exc
    if result.tzinfo != UTC:
        result = result.astimezone(UTC)
    return result


def _case(value: Any, index: int, run_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"semantic case {index} is malformed")
    expected_name = ("caffeine", "aspirin")[index - 1]
    expected_run_id = f"{run_id}-semantic-{'a' if index == 1 else 'b'}"
    if (
        value.get("index") != index
        or value.get("input_id") != expected_name
        or value.get("run_id") != expected_run_id
        or value.get("status") != "PASS"
        or value.get("ok") is not True
        or value.get("exit_code") != 0
        or value.get("request_sha256") != REQUEST_SHA256[index - 1]
    ):
        raise EvidenceError(f"semantic case {index} identity/status mismatch")
    elapsed = value.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed <= 0:
        raise EvidenceError(f"semantic case {index} elapsed time is invalid")
    response_bytes = value.get("response_bytes")
    response_hash = value.get("response_sha256")
    if (
        not isinstance(response_bytes, int)
        or isinstance(response_bytes, bool)
        or not 1 <= response_bytes <= 16 * 1024 * 1024
        or not isinstance(response_hash, str)
        or len(response_hash) != 64
        or any(character not in "0123456789abcdef" for character in response_hash)
    ):
        raise EvidenceError(f"semantic case {index} response receipt is invalid")
    invariant = value.get("invariant")
    if not isinstance(invariant, dict):
        raise EvidenceError(f"semantic case {index} invariant is absent")
    if (
        invariant.get("generated_count") != 1
        or not isinstance(invariant.get("smiles"), str)
        or not invariant["smiles"]
        or not isinstance(invariant.get("atom_count"), int)
        or isinstance(invariant.get("atom_count"), bool)
        or invariant["atom_count"] < 1
    ):
        raise EvidenceError(f"semantic case {index} did not prove one parsed molecule")
    score = invariant.get("score")
    reference = invariant.get("rdkit_qed")
    if any(
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not math.isfinite(number)
        for number in (score, reference)
    ) or not (
        0 <= float(score) <= 1 and 0 <= float(reference) <= 1
    ) or abs(float(score) - float(reference)) > 0.02:
        raise EvidenceError(f"semantic case {index} did not prove its RDKit QED score")
    return value


def build(
    run: dict[str, Any],
    target: dict[str, Any],
    probe_job: dict[str, Any],
    probe_pod: dict[str, Any],
    semantic: dict[str, Any],
    events: dict[str, Any],
) -> dict[str, Any]:
    if set(run) != {"schema", "run_id", "demand_at", "node", "image", "mode"}:
        raise EvidenceError("run receipt has the wrong fields")
    run_id = run.get("run_id")
    if run.get("schema") != "archvteams.nebius.ai/molmim-conventional-run/v1" or run.get("mode") != "conventional-cached":
        raise EvidenceError("run receipt schema/mode mismatch")
    if run.get("node") != NODE or run.get("image") != IMAGE or not isinstance(run_id, str):
        raise EvidenceError("run receipt execution identity mismatch")
    demand = _time(run.get("demand_at"), "demand_at")

    try:
        expected_target = lane_render.render_target(run_id, run["demand_at"])[0]
    except lane_render.RenderError as exc:
        raise EvidenceError(str(exc)) from exc
    _require_expected(target, expected_target, "target Pod")

    metadata = target.get("metadata", {})
    spec = target.get("spec", {})
    status = target.get("status", {})
    if not all(isinstance(value, dict) for value in (metadata, spec, status)):
        raise EvidenceError("target Pod is malformed")
    target_uid = metadata.get("uid")
    try:
        if str(uuid.UUID(str(target_uid))) != target_uid:
            raise ValueError
    except ValueError as exc:
        raise EvidenceError("target Pod UID is not canonical") from exc
    if (
        metadata.get("name") != f"molmim-cached-{run_id}"
        or metadata.get("namespace") != NAMESPACE
        or spec.get("nodeName") != NODE
    ):
        raise EvidenceError("target Pod name/namespace/node mismatch")
    labels = metadata.get("labels", {})
    if (
        not isinstance(labels, dict)
        or labels.get("app.kubernetes.io/component") != "conventional-cached-target"
        or labels.get("archvteams.nebius.ai/run-id") != run_id
    ):
        raise EvidenceError("target Pod labels do not bind this run")
    containers = spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise EvidenceError("target Pod container set mismatch")
    container = containers[0]
    if (
        container.get("name") != "molmim"
        or container.get("image") != IMAGE
        or container.get("imagePullPolicy") != "IfNotPresent"
        or container.get("command") != ["/opt/nvidia/nvidia_entrypoint.sh"]
        or container.get("args") != ["start_server"]
    ):
        raise EvidenceError("target Pod is not the exact conventional MolMIM process")
    env = container.get("env", [])
    if not any(
        isinstance(item, dict)
        and item.get("name") == "TORCHINDUCTOR_COMPILE_THREADS"
        and item.get("value") == "1"
        for item in env
    ):
        raise EvidenceError("target Pod did not use the single TorchInductor worker setting")
    statuses = status.get("containerStatuses")
    if not isinstance(statuses, list) or len(statuses) != 1:
        raise EvidenceError("target container status is absent")
    target_status = statuses[0]
    if target_status.get("imageID", "").removeprefix("docker-pullable://") != IMAGE:
        raise EvidenceError("target imageID is not the pinned MolMIM digest")
    try:
        container_started_raw = target_status["state"]["running"]["startedAt"]
    except (KeyError, TypeError) as exc:
        raise EvidenceError("target container did not remain running") from exc
    container_started = _time(container_started_raw, "target container startedAt")
    if container_started < demand:
        raise EvidenceError("target container started before demand")

    try:
        expected_probe_job = next(
            document
            for document in lane_render.render_probe(run_id, run["demand_at"], target_uid)
            if document.get("kind") == "Job"
        )
    except (lane_render.RenderError, StopIteration) as exc:
        raise EvidenceError(f"cannot reconstruct exact semantic probe Job: {exc}") from exc
    _require_expected(probe_job, expected_probe_job, "semantic probe Job")
    job_metadata = probe_job.get("metadata", {})
    job_uid = job_metadata.get("uid") if isinstance(job_metadata, dict) else None
    try:
        if str(uuid.UUID(str(job_uid))) != job_uid:
            raise ValueError
    except ValueError as exc:
        raise EvidenceError("semantic probe Job UID is not canonical") from exc
    if probe_job.get("status", {}).get("succeeded") != 1:
        raise EvidenceError("semantic probe Job did not succeed exactly once")
    job_annotations = job_metadata.get("annotations", {})
    if (
        not isinstance(job_annotations, dict)
        or job_annotations.get("archvteams.nebius.ai/target-pod-uid") != target_uid
        or job_annotations.get("archvteams.nebius.ai/demand-at") != run["demand_at"]
    ):
        raise EvidenceError("semantic probe Job is not UID/demand bound")
    probe_name = f"molmim-cached-probe-{run_id}"
    probe_metadata = probe_pod.get("metadata", {})
    probe_spec = probe_pod.get("spec", {})
    probe_status = probe_pod.get("status", {})
    if not all(
        isinstance(value, dict) for value in (probe_metadata, probe_spec, probe_status)
    ):
        raise EvidenceError("semantic probe Pod is malformed")
    owners = probe_metadata.get("ownerReferences")
    controllers = (
        [owner for owner in owners if isinstance(owner, dict) and owner.get("controller") is True]
        if isinstance(owners, list)
        else []
    )
    if (
        probe_pod.get("apiVersion") != "v1"
        or probe_pod.get("kind") != "Pod"
        or probe_metadata.get("namespace") != NAMESPACE
        or probe_metadata.get("generateName") != f"{probe_name}-"
        or not isinstance(probe_metadata.get("name"), str)
        or not probe_metadata["name"].startswith(f"{probe_name}-")
        or len(controllers) != 1
        or any(
            controllers[0].get(key) != value
            for key, value in {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "name": probe_name,
                "uid": job_uid,
            }.items()
        )
    ):
        raise EvidenceError("semantic probe Pod is not controlled by the exact probe Job")
    _require_expected(
        probe_metadata.get("labels"),
        expected_probe_job["spec"]["template"]["metadata"]["labels"],
        "semantic probe Pod labels",
    )
    _require_expected(
        probe_metadata.get("annotations"),
        expected_probe_job["spec"]["template"]["metadata"]["annotations"],
        "semantic probe Pod annotations",
    )
    _require_expected(
        probe_spec,
        expected_probe_job["spec"]["template"]["spec"],
        "semantic probe PodSpec",
    )
    init_statuses = probe_status.get("initContainerStatuses")
    if (
        not isinstance(init_statuses, list)
        or len(init_statuses) != 1
        or init_statuses[0].get("name") != "stage-validator"
        or init_statuses[0].get("imageID", "").removeprefix("docker-pullable://")
        != IMAGE
        or init_statuses[0].get("state", {}).get("terminated", {}).get("exitCode") != 0
    ):
        raise EvidenceError("semantic probe validator stage is not the pinned successful image")
    probe_statuses = probe_status.get("containerStatuses")
    if not isinstance(probe_statuses, list) or len(probe_statuses) != 1:
        raise EvidenceError("semantic probe Pod status is absent")
    probe_container_status = probe_statuses[0]
    terminated = probe_container_status.get("state", {}).get("terminated", {})
    if (
        probe_container_status.get("name") != "semantic-probe"
        or probe_container_status.get("imageID", "").removeprefix("docker-pullable://")
        != IMAGE
        or not isinstance(terminated, dict)
        or terminated.get("exitCode") != 0
    ):
        raise EvidenceError("semantic probe container did not exit successfully")

    service_name = f"molmim-cached-svc-{run_id}"
    if (
        semantic.get("schema_version") != 1
        or semantic.get("validator") != "molmim-faststart-semantic-v1"
        or semantic.get("base_url") != f"http://{service_name}:8000"
        or semantic.get("inference_path") != "/generate"
        or semantic.get("endpoint") != f"http://{service_name}:8000/generate"
        or semantic.get("proxy_policy") != "disabled"
        or semantic.get("redirect_policy") != "reject"
        or semantic.get("status") != "PASS"
        or semantic.get("ok") is not True
        or semantic.get("passed_case_count") != 2
        or semantic.get("failed_case_count") != 0
        or semantic.get("exit_code") != 0
    ):
        raise EvidenceError("semantic summary does not prove the exact two-call contract")
    total_elapsed = semantic.get("total_elapsed_seconds")
    if (
        isinstance(total_elapsed, bool)
        or not isinstance(total_elapsed, (int, float))
        or not math.isfinite(float(total_elapsed))
        or total_elapsed < 0
    ):
        raise EvidenceError("semantic summary total elapsed time is invalid")
    cases_raw = semantic.get("cases")
    if not isinstance(cases_raw, list) or len(cases_raw) != 2:
        raise EvidenceError("semantic summary must contain exactly two cases")
    cases = [_case(item, index, run_id) for index, item in enumerate(cases_raw, 1)]
    if cases[0]["response_sha256"] == cases[1]["response_sha256"]:
        raise EvidenceError("two distinct calls returned byte-identical responses")
    if cases[0]["invariant"]["smiles"] == cases[1]["invariant"]["smiles"]:
        raise EvidenceError("two distinct seeds returned the same molecule")
    started_at = _time(semantic.get("started_at"), "semantic started_at")
    ready_at = _time(semantic.get("ready_at"), "semantic ready_at")
    finished = _time(semantic.get("finished_at"), "semantic finished_at")
    if not (
        demand <= container_started <= ready_at <= finished
        and demand <= started_at <= ready_at
    ):
        raise EvidenceError("demand, container, readiness, and semantic times are not ordered")

    items = events.get("items")
    if not isinstance(items, list):
        raise EvidenceError("target EventList is malformed")
    cached_image_message = f'Container image "{IMAGE}" already present on machine'
    cached_events = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("involvedObject", {}).get("uid") == target_uid
        and item.get("involvedObject", {}).get("fieldPath")
        == "spec.containers{molmim}"
        and item.get("reason") == "Pulled"
        and item.get("message") == cached_image_message
    ]
    if len(cached_events) < 1:
        raise EvidenceError("target Events do not prove that the exact image was already cached")

    return {
        "schema": "archvteams.nebius.ai/molmim-conventional-cached-evidence/v1",
        "status": "PASS",
        "mode": "conventional-cached",
        "run_id": run_id,
        "request_count": 2,
        "semantic_pass_count": 2,
        "execution_identity": {
            "node": NODE,
            "image": IMAGE,
            "image_id": target_status["imageID"],
            "target_pod": metadata["name"],
            "target_uid": target_uid,
            "cache_pvc": "molmim-native-f7-cache",
            "torchinductor_compile_threads": 1,
            "image_already_present_event_count": len(cached_events),
        },
        "timings_seconds": {
            "demand_to_container_started": round((container_started - demand).total_seconds(), 6),
            "demand_to_http_ready": round((ready_at - demand).total_seconds(), 6),
            "call_1": float(cases[0]["elapsed_seconds"]),
            "call_2": float(cases[1]["elapsed_seconds"]),
            "demand_to_two_semantic_responses": round((finished - demand).total_seconds(), 6),
        },
        "semantic": semantic,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--probe-job", type=Path, required=True)
    parser.add_argument("--probe-pod", type=Path, required=True)
    parser.add_argument("--semantic-summary", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = build(
            _load(args.run, "run receipt"),
            _load(args.target, "target Pod"),
            _load(args.probe_job, "probe Job"),
            _load(args.probe_pod, "probe Pod"),
            _load(args.semantic_summary, "semantic summary"),
            _load(args.events, "target Events"),
        )
    except EvidenceError as exc:
        print(f"conventional evidence refused: {exc}", file=sys.stderr)
        return 2
    json.dump(value, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
