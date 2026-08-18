#!/usr/bin/env python3
"""Build the shared warm-instance and runtime-health qualification receipt.

The collector is deliberately offline.  Runners capture the API objects and the
target-container ``nvidia-smi`` output; this program rejects incomplete or
contradictory evidence before a trial can be counted in a fresh cohort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


SCHEMA = "archvteams.nebius.ai/warm-instance-qualification/v1"
ACCEPTANCE_RESPONSE_PROXY = "client-observed-api-create-response-return/v1"
PRE_DISPATCH_BOUNDARY = "client-target-create-dispatch/v1"
HOST_XID_UNAVAILABLE_REASON = (
    "no task-scoped privileged node-log collector is present; target-container "
    "nvidia-smi cannot authoritatively prove absence of host-driver Xid records"
)
CLOCK_SAMPLE_SCHEMA = "archvteams.nebius.ai/node-clock-sample/v1"
MAX_CLOCK_SAMPLE_ROUND_TRIP_SECONDS = 1.0
MAX_CLOCK_ABSOLUTE_OFFSET_SECONDS = 1.0


class QualificationError(ValueError):
    """Captured qualification evidence is missing, malformed, or unsafe to count."""


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"{label} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read {label}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"{label} must be a JSON object")
    return value


def _read_timestamp(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"{label} must be a regular non-symlink file")
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise QualificationError(f"cannot read {label}: {type(exc).__name__}") from exc
    _timestamp(value, label)
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise QualificationError(f"{label} must be an RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise QualificationError(f"{label} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualificationError(f"{label} must include a UTC offset")
    return parsed.astimezone(UTC)


def _sha256(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise QualificationError(f"{label} must be a regular non-symlink file")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise QualificationError(f"cannot hash {label}: {type(exc).__name__}") from exc
    return digest.hexdigest()


def _container_health(
    pod: dict[str, Any], *, expected_name: str, expected_phase: str, label: str
) -> dict[str, Any]:
    status = pod.get("status")
    if not isinstance(status, dict):
        raise QualificationError(f"{label} has no status")
    if status.get("phase") != expected_phase:
        raise QualificationError(f"{label} phase is not {expected_phase}")
    if status.get("reason") == "Evicted" or "evicted" in str(
        status.get("message", "")
    ).lower():
        raise QualificationError(f"{label} was evicted")

    statuses: list[dict[str, Any]] = []
    for field in ("initContainerStatuses", "containerStatuses"):
        values = status.get(field, [])
        if not isinstance(values, list):
            raise QualificationError(f"{label} {field} is malformed")
        statuses.extend(value for value in values if isinstance(value, dict))
    matches = [item for item in statuses if item.get("name") == expected_name]
    if len(matches) != 1:
        raise QualificationError(
            f"{label} must have exactly one {expected_name} container status"
        )
    if not statuses:
        raise QualificationError(f"{label} has no container statuses")

    for item in statuses:
        name = item.get("name")
        restart_count = item.get("restartCount")
        if isinstance(restart_count, bool) or restart_count != 0:
            raise QualificationError(f"{label} container {name} restarted")
        for state_field in ("state", "lastState"):
            state = item.get(state_field, {})
            if not isinstance(state, dict):
                raise QualificationError(
                    f"{label} container {name} {state_field} is malformed"
                )
            terminated = state.get("terminated")
            if isinstance(terminated, dict) and (
                terminated.get("reason") == "OOMKilled"
                or terminated.get("exitCode") not in (None, 0)
            ):
                raise QualificationError(
                    f"{label} container {name} has an OOM/nonzero termination"
                )

    expected_state = matches[0].get("state")
    if not isinstance(expected_state, dict):
        raise QualificationError(f"{label} expected container state is malformed")
    if expected_phase == "Running":
        if not isinstance(expected_state.get("running"), dict):
            raise QualificationError(f"{label} target container is not running")
    else:
        terminated = expected_state.get("terminated")
        if (
            not isinstance(terminated, dict)
            or terminated.get("exitCode") != 0
            or terminated.get("reason") == "OOMKilled"
        ):
            raise QualificationError(f"{label} job container did not exit cleanly")
    return {
        "phase": expected_phase,
        "expected_container": expected_name,
        "container_count": len(statuses),
        "restart_count": 0,
        "oom_killed": False,
        "evicted": False,
        "nonzero_termination": False,
    }


def _event_receipt(
    events: dict[str, Any], *, target_uid: str, expected_image: str
) -> dict[str, Any]:
    if events.get("kind") not in {"EventList", "List"}:
        raise QualificationError("target Events capture is not an Event list")
    items = events.get("items")
    if not isinstance(items, list) or not items:
        raise QualificationError("target Events capture is empty")

    reason_counts: dict[str, int] = {}
    warning_count = 0
    pulling_count = 0
    cached_pull_count = 0
    for item in items:
        if not isinstance(item, dict):
            raise QualificationError("target Events contains a malformed item")
        if item.get("involvedObject", {}).get("uid") != target_uid:
            raise QualificationError("target Events contains an event for another UID")
        reason = str(item.get("reason", ""))
        event_type = str(item.get("type", ""))
        message = str(item.get("message", ""))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if event_type == "Warning":
            warning_count += 1
        if reason == "Pulling":
            pulling_count += 1
        if reason == "Pulled":
            if (
                "already present on machine" not in message.lower()
                or expected_image not in message
            ):
                raise QualificationError(
                    "target Pulled event does not prove the exact image was already present"
                )
            cached_pull_count += 1

    if warning_count:
        raise QualificationError("target emitted one or more Warning events")
    if pulling_count:
        raise QualificationError("target emitted a post-T0 Pulling event")
    if cached_pull_count < 1:
        raise QualificationError(
            "target has no Pulled event proving the exact image was already present"
        )
    return {
        "event_count": len(items),
        "reason_counts": dict(sorted(reason_counts.items())),
        "warning_event_count": 0,
        "pulling_event_count": 0,
        "exact_image_already_present_event_count": cached_pull_count,
    }


def _gpu_receipt(path: Path, stderr_path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise QualificationError("nvidia-smi XML must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise QualificationError(
            f"cannot read nvidia-smi XML: {type(exc).__name__}"
        ) from exc
    if not raw or len(raw) > 16 * 1024 * 1024:
        raise QualificationError("nvidia-smi XML size is outside the bounded receipt limit")
    if stderr_path.is_symlink() or not stderr_path.is_file():
        raise QualificationError("nvidia-smi stderr must be a regular non-symlink file")
    try:
        raw_stderr = stderr_path.read_bytes()
    except OSError as exc:
        raise QualificationError(
            f"cannot read nvidia-smi stderr: {type(exc).__name__}"
        ) from exc
    if len(raw_stderr) > 64 * 1024 or raw_stderr.strip():
        raise QualificationError("nvidia-smi emitted nonempty or unbounded stderr")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise QualificationError("nvidia-smi output is not valid XML") from exc
    if root.tag != "nvidia_smi_log":
        raise QualificationError("nvidia-smi XML has the wrong root element")
    attached_raw = root.findtext("attached_gpus")
    try:
        attached = int(str(attached_raw))
    except ValueError as exc:
        raise QualificationError("nvidia-smi XML has no valid attached GPU count") from exc
    gpus = root.findall("gpu")
    if attached < 1 or len(gpus) != attached:
        raise QualificationError("nvidia-smi did not expose the declared GPU set")
    identities: list[dict[str, str]] = []
    for gpu in gpus:
        uuid = (gpu.findtext("uuid") or "").strip()
        product_name = (gpu.findtext("product_name") or "").strip()
        if not uuid or not product_name or "H100" not in product_name:
            raise QualificationError("nvidia-smi GPU identity is incomplete")
        identities.append({"uuid": uuid, "product_name": product_name})
    if b"ERR!" in raw:
        raise QualificationError("nvidia-smi reported ERR! in the target container")
    return {
        "status": "PASS",
        "scope": "target-container",
        "command": ["nvidia-smi", "-q", "-x"],
        "attached_gpu_count": attached,
        "gpus": identities,
        "raw_xml_sha256": hashlib.sha256(raw).hexdigest(),
        "stderr_sha256": hashlib.sha256(raw_stderr).hexdigest(),
        "host_xid_check": {
            "status": "unavailable",
            "reason": HOST_XID_UNAVAILABLE_REASON,
        },
    }


def _clock_alignment(
    start: dict[str, Any],
    end: dict[str, Any],
    *,
    target_name: str,
    target_uid: str,
    target_node: str,
    target_container: str,
) -> dict[str, Any]:
    intervals: list[tuple[float, float]] = []
    samples: list[dict[str, Any]] = []
    for value, phase in ((start, "before-semantic"), (end, "after-semantic")):
        sampled_name = value.get("sampled_pod_name")
        sampled_uid = value.get("sampled_pod_uid")
        sampled_container = value.get("sampled_container")
        if (
            value.get("schema") != CLOCK_SAMPLE_SCHEMA
            or value.get("phase") != phase
            or value.get("target_node") != target_node
            or not isinstance(sampled_name, str)
            or not sampled_name
            or not isinstance(sampled_uid, str)
            or not sampled_uid
            or not isinstance(sampled_container, str)
            or (
                phase == "before-semantic"
                and sampled_container != ""
            )
            or (
                phase == "after-semantic"
                and (
                    sampled_name != target_name
                    or sampled_uid != target_uid
                    or sampled_container != target_container
                )
            )
        ):
            raise QualificationError(f"{phase} clock sample identity is inconsistent")
        controller_before = _timestamp(
            value.get("controller_before"), f"{phase} controller before"
        )
        node_observed = _timestamp(value.get("node_observed"), f"{phase} node clock")
        controller_after = _timestamp(
            value.get("controller_after"), f"{phase} controller after"
        )
        if controller_after < controller_before:
            raise QualificationError(f"{phase} controller clock moved backwards")
        round_trip = (controller_after - controller_before).total_seconds()
        lower = (node_observed - controller_after).total_seconds()
        upper = (node_observed - controller_before).total_seconds()
        absolute_bound = max(abs(lower), abs(upper))
        if (
            round_trip > MAX_CLOCK_SAMPLE_ROUND_TRIP_SECONDS
            or absolute_bound > MAX_CLOCK_ABSOLUTE_OFFSET_SECONDS
        ):
            raise QualificationError(
                f"{phase} controller-to-node clock uncertainty exceeds the bound"
            )
        intervals.append((lower, upper))
        samples.append(
            {
                "phase": phase,
                "controller_before": value["controller_before"],
                "node_observed": value["node_observed"],
                "controller_after": value["controller_after"],
                "round_trip_seconds": round(round_trip, 6),
                "node_minus_controller_lower_seconds": round(lower, 6),
                "node_minus_controller_upper_seconds": round(upper, 6),
                "absolute_offset_upper_bound_seconds": round(absolute_bound, 6),
            }
        )
    overall_lower = min(value[0] for value in intervals)
    overall_upper = max(value[1] for value in intervals)
    overall_absolute = max(abs(overall_lower), abs(overall_upper))
    return {
        "status": "PASS",
        "scope": "controller-to-target-node",
        "worker_and_probe_must_share_target_node": True,
        "absolute_offset_upper_bound_seconds": round(overall_absolute, 6),
        "node_minus_controller_lower_seconds": round(overall_lower, 6),
        "node_minus_controller_upper_seconds": round(overall_upper, 6),
        "maximum_allowed_absolute_offset_seconds": (
            MAX_CLOCK_ABSOLUTE_OFFSET_SECONDS
        ),
        "maximum_allowed_sample_round_trip_seconds": (
            MAX_CLOCK_SAMPLE_ROUND_TRIP_SECONDS
        ),
        "samples": samples,
    }


def build_receipt(
    *,
    model: str,
    run_id: str,
    namespace: str,
    target_name: str,
    target_container: str,
    expected_image: str,
    target_submit_at: str,
    target_create_response_at: str,
    target_create_response: dict[str, Any],
    target: dict[str, Any],
    target_events: dict[str, Any],
    worker_pod: dict[str, Any],
    worker_container: str,
    probe_pod: dict[str, Any],
    probe_container: str,
    gpu_health_xml: Path,
    gpu_health_stderr: Path,
    clock_sample_start: dict[str, Any],
    clock_sample_end: dict[str, Any],
    source_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    if model not in {"openfold2", "boltz2"}:
        raise QualificationError("model must be openfold2 or boltz2")
    if not run_id or not namespace or not target_name or not expected_image:
        raise QualificationError("run identity fields must be nonempty")

    submit = _timestamp(target_submit_at, "target submit")
    response = _timestamp(target_create_response_at, "target create response")
    api_rtt = (response - submit).total_seconds()
    if not math.isfinite(api_rtt) or api_rtt < 0:
        raise QualificationError("target create response precedes request dispatch")

    response_metadata = target_create_response.get("metadata")
    target_metadata = target.get("metadata")
    if not isinstance(response_metadata, dict) or not isinstance(target_metadata, dict):
        raise QualificationError("target/create-response metadata is missing")
    target_uid = response_metadata.get("uid")
    if (
        target_create_response.get("apiVersion") != "v1"
        or target_create_response.get("kind") != "Pod"
        or response_metadata.get("name") != target_name
        or response_metadata.get("namespace") != namespace
        or not isinstance(target_uid, str)
        or not target_uid
        or target.get("apiVersion") != "v1"
        or target.get("kind") != "Pod"
        or target_metadata.get("name") != target_name
        or target_metadata.get("namespace") != namespace
        or target_metadata.get("uid") != target_uid
        or target_metadata.get("creationTimestamp")
        != response_metadata.get("creationTimestamp")
    ):
        raise QualificationError("API create response does not identify the final target Pod")
    created = _timestamp(response_metadata.get("creationTimestamp"), "server creation")
    if (submit - created).total_seconds() >= 1 or created > response:
        raise QualificationError(
            "coarse server creation timestamp is outside the client request/response bracket"
        )

    annotations = target_metadata.get("annotations", {})
    pod_spec_sha256 = (
        annotations.get("archvteams.nebius.ai/target-pod-spec-sha256")
        if isinstance(annotations, dict)
        else None
    )
    if (
        not isinstance(pod_spec_sha256, str)
        or len(pod_spec_sha256) != 64
        or any(character not in "0123456789abcdef" for character in pod_spec_sha256)
    ):
        raise QualificationError("target PodSpec digest annotation is missing")

    event_receipt = _event_receipt(
        target_events, target_uid=target_uid, expected_image=expected_image
    )
    pod_health = {
        "target": _container_health(
            target,
            expected_name=target_container,
            expected_phase="Running",
            label="target Pod",
        ),
        "worker": _container_health(
            worker_pod,
            expected_name=worker_container,
            expected_phase="Succeeded",
            label="worker Pod",
        ),
        "probe": _container_health(
            probe_pod,
            expected_name=probe_container,
            expected_phase="Succeeded",
            label="probe Pod",
        ),
    }
    target_node = target.get("spec", {}).get("nodeName")
    if (
        not isinstance(target_node, str)
        or not target_node
        or worker_pod.get("spec", {}).get("nodeName") != target_node
        or probe_pod.get("spec", {}).get("nodeName") != target_node
    ):
        raise QualificationError(
            "target, worker, and semantic probe are not bound to one node clock"
        )
    clock_alignment = _clock_alignment(
        clock_sample_start,
        clock_sample_end,
        target_name=target_name,
        target_uid=target_uid,
        target_node=target_node,
        target_container=target_container,
    )
    gpu = _gpu_receipt(gpu_health_xml, gpu_health_stderr)

    source_hashes: dict[str, str] = {}
    for label, path in (source_paths or {}).items():
        source_hashes[label] = _sha256(path, label)
    source_hashes["target_nvidia_smi_xml"] = _sha256(
        gpu_health_xml, "target nvidia-smi XML"
    )
    source_hashes["target_nvidia_smi_stderr"] = _sha256(
        gpu_health_stderr, "target nvidia-smi stderr"
    )

    return {
        "schema": SCHEMA,
        "status": "PASS",
        "model": model,
        "run_id": run_id,
        "target": {
            "namespace": namespace,
            "name": target_name,
            "uid": target_uid,
            "pod_spec_sha256": pod_spec_sha256,
            "image": expected_image,
        },
        "timing_boundaries": {
            "primary": {
                "label": PRE_DISPATCH_BOUNDARY,
                "timestamp": target_submit_at,
                "conservative_relative_to_api_acceptance": True,
            },
            "acceptance_response_proxy": {
                "label": ACCEPTANCE_RESPONSE_PROXY,
                "timestamp": target_create_response_at,
                "is_exact_server_acceptance": False,
                "client_observed_api_round_trip_seconds": round(api_rtt, 6),
                "server_creation_timestamp": response_metadata["creationTimestamp"],
            },
        },
        "warm_instance": {
            "target_image_already_present_before_t0": True,
            "target_image_pull_or_download_after_t0": False,
            "target_events": event_receipt,
        },
        "pod_health": pod_health,
        "clock_alignment": clock_alignment,
        "gpu_health": gpu,
        "source_sha256": dict(sorted(source_hashes.items())),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("openfold2", "boltz2"), required=True)
    for name in (
        "run-id",
        "namespace",
        "target-name",
        "target-container",
        "expected-image",
        "worker-container",
        "probe-container",
    ):
        parser.add_argument(f"--{name}", required=True)
    for name in (
        "target-submit-at",
        "target-create-response-at",
        "target-create-response",
        "target-pod",
        "target-events",
        "worker-pod",
        "probe-pod",
        "gpu-health-xml",
        "gpu-health-stderr",
        "clock-sample-start",
        "clock-sample-end",
        "capture-agent-absence",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source_paths = {
        "target_create_response": args.target_create_response,
        "target_pod": args.target_pod,
        "target_events": args.target_events,
        "worker_pod": args.worker_pod,
        "probe_pod": args.probe_pod,
        "clock_sample_start": args.clock_sample_start,
        "clock_sample_end": args.clock_sample_end,
        "capture_agent_absence": args.capture_agent_absence,
    }
    try:
        receipt = build_receipt(
            model=args.model,
            run_id=args.run_id,
            namespace=args.namespace,
            target_name=args.target_name,
            target_container=args.target_container,
            expected_image=args.expected_image,
            target_submit_at=_read_timestamp(args.target_submit_at, "target submit"),
            target_create_response_at=_read_timestamp(
                args.target_create_response_at, "target create response"
            ),
            target_create_response=_load_json(
                args.target_create_response, "target create response"
            ),
            target=_load_json(args.target_pod, "target Pod"),
            target_events=_load_json(args.target_events, "target Events"),
            worker_pod=_load_json(args.worker_pod, "worker Pod"),
            worker_container=args.worker_container,
            probe_pod=_load_json(args.probe_pod, "probe Pod"),
            probe_container=args.probe_container,
            gpu_health_xml=args.gpu_health_xml,
            gpu_health_stderr=args.gpu_health_stderr,
            clock_sample_start=_load_json(
                args.clock_sample_start, "before-semantic clock sample"
            ),
            clock_sample_end=_load_json(
                args.clock_sample_end, "after-semantic clock sample"
            ),
            source_paths=source_paths,
        )
    except QualificationError as exc:
        print(f"qualification-receipt: refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
