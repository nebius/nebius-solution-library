#!/usr/bin/env python3
"""Canonical request-to-first-valid-response ledger and trace contract.

The canonical event clock is the external recorder clock. Backend timestamps may
be retained in backend-owned evidence, but they cannot replace or shift T0 or
the terminal response timestamp in this ledger.
"""

from __future__ import annotations

import csv
import fcntl
import hashlib
import json
import math
import os
import random
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence


EVENT_SCHEMA = "archvteams.nebius.ai/catalog-switch-ledger-event/v1"
TRACE_SCHEMA = "archvteams.nebius.ai/catalog-switch-trace/v1"
CATALOG_SCHEMA = "archvteams.nebius.ai/catalog-switch-model-catalog/v1"
AGGREGATE_SCHEMA = "archvteams.nebius.ai/catalog-switch-aggregate/v1"
LEGACY_IMPORT_SCHEMA = "archvteams.nebius.ai/prepared-node-import/v1"
T0_BOUNDARY = "external-client-request-accepted/v1"
TERMINAL_BOUNDARY = "first-complete-semantically-valid-response/v1"
PERCENTILE_ESTIMATOR = "nearest-rank-on-per-attempt-raw-values/v1"
MAX_DECLARED_CLOCK_ERROR_MS = 100.0
MAX_ACCEPTANCE_SCHEDULE_ERROR_MS = 100.0

ID_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,191}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
UTC_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IMAGE_DIGEST_RE = re.compile(r"(?:[^\s]+@)?sha256:[0-9a-f]{64}")

SCENARIOS = (
    "same_model_hot",
    "idle_local",
    "a_to_b_local",
    "a_to_b_remote",
    "checkpoint_fallback",
    "capacity_miss",
)
PHASES = (
    "catalog_selection",
    "queue",
    "drain",
    "gpu_release",
    "placement",
    "image_readiness",
    "artifact_readiness",
    "storage_readiness",
    "cache_readiness",
    "runtime_launch",
    "service_readiness",
    "inference",
)
PHASE_DEPENDENCIES = {
    "catalog_selection": (),
    "queue": ("catalog_selection",),
    "drain": ("queue",),
    "gpu_release": ("drain",),
    "placement": ("queue", "gpu_release"),
    "image_readiness": ("placement",),
    "artifact_readiness": ("placement",),
    "storage_readiness": ("placement",),
    "cache_readiness": ("placement",),
    "runtime_launch": (
        "image_readiness",
        "artifact_readiness",
        "storage_readiness",
        "cache_readiness",
    ),
    "service_readiness": ("runtime_launch",),
    "inference": ("service_readiness",),
}
EVENT_TYPES = (
    "request.accepted",
    "phase.started",
    "phase.finished",
    "response.validated",
    "attempt.failed",
    "accounting.recorded",
    "cleanup.finished",
)
PHASE_OUTCOMES = ("completed", "failed", "skipped")
CACHE_STATES = {
    "image": ("local_verified", "remote_required", "unavailable", "not_applicable"),
    "artifact": (
        "memory_hit",
        "node_local_hit",
        "attached_storage_hit",
        "remote_miss",
        "unavailable",
        "not_applicable",
    ),
    "checkpoint": (
        "compatible_hit",
        "stale_version",
        "missing",
        "restore_failed",
        "not_applicable",
    ),
    "storage": ("ready", "localization_required", "unavailable", "not_applicable"),
}
CACHE_HITS = {
    "image": {"local_verified"},
    "artifact": {"memory_hit", "node_local_hit", "attached_storage_hit"},
    "checkpoint": {"compatible_hit"},
    "storage": {"ready"},
}
CAPACITY_STATES = ("allocated", "queued", "unavailable")
FAILURE_CLASSES = (
    "backend",
    "capacity",
    "cancelled",
    "infrastructure",
    "preempted",
    "timeout",
    "validation",
)
PERCENTILE_MIN_SAMPLES = {"p50": 2, "p95": 20, "p99": 100}

TRACE_TOP_KEYS = {
    "schema",
    "trace_id",
    "distribution",
    "seed",
    "catalog_sha256",
    "request_count",
    "scenario_labels",
    "requests",
    "trace_sha256",
}
TRACE_REQUEST_KEYS = {
    "sequence",
    "request_id",
    "attempt_id",
    "offered_at_offset_ms",
    "scenario",
    "target",
    "input",
    "precondition",
}
TARGET_KEYS = {
    "model_id",
    "model_version",
    "artifact_id",
    "artifact_version",
    "artifact_sha256",
}
INPUT_KEYS = {"workload_id", "input_id", "payload_sha256", "input_bytes"}
PRECONDITION_KEYS = {
    "current_node_occupant",
    "cache",
    "capacity",
    "queue_depth",
}
OCCUPANT_KEYS = {"model_id", "model_version"}
EVENT_KEYS = {
    "schema",
    "ledger_id",
    "ledger_sequence",
    "trace_id",
    "request_id",
    "attempt_id",
    "attempt_sequence",
    "event_id",
    "observed_at_utc",
    "observed_monotonic_ns",
    "recorder",
    "event_type",
    "data",
}
RECORDER_KEYS = {
    "recorder_id",
    "clock_id",
    "boot_id",
    "utc_sync_source",
    "max_error_ms",
}
ACCEPTED_KEYS = {
    "boundary",
    "trace_request_sha256",
    "scenario",
    "target",
    "input",
    "precondition",
    "environment",
    "ownership",
}
ENVIRONMENT_KEYS = {
    "backend",
    "backend_version",
    "provider",
    "project_id",
    "region",
    "node_id",
    "gpu_type",
    "gpu_count",
    "image_digest",
    "code_revision",
    "config_sha256",
    "experiment_id",
}
OWNERSHIP_KEYS = {
    "owner_task_id",
    "resource_prefix",
    "dedicated",
    "cleanup_required",
    "resources",
}
RESOURCE_KEYS = {"kind", "id", "project_id", "region"}
PHASE_STARTED_KEYS = {"phase", "occurrence"}
PHASE_FINISHED_KEYS = {"phase", "occurrence", "outcome", "reason", "bytes_moved"}
RESPONSE_KEYS = {
    "boundary",
    "validator_id",
    "validator_sha256",
    "response_sha256",
    "response_bytes",
    "complete_body",
    "semantically_valid",
    "model_id",
    "model_version",
}
FAILURE_KEYS = {"failure_class", "reason", "retryable"}
ACCOUNTING_KEYS = {
    "currency",
    "cost_usd",
    "gpu_active_seconds",
    "gpu_idle_seconds",
    "billed_seconds",
    "bytes_moved_total",
}
CLEANUP_KEYS = {
    "required",
    "status",
    "resources_deleted",
    "resources_retained",
    "receipt_sha256",
    "reason",
}


class HarnessError(ValueError):
    """Input cannot be admitted to the shared product-SLO contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise HarnessError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _json_loads(value: str, label: str) -> Any:
    try:
        return json.loads(value, object_pairs_hook=_reject_duplicate_keys)
    except HarnessError:
        raise
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{label} is invalid JSON") from exc


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise HarnessError("value is not canonicalizable JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"input must be a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise HarnessError(f"cannot hash input: {type(exc).__name__}") from exc
    return digest.hexdigest()


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value) if isinstance(value, dict) else expected)
        extra = sorted(set(value) - expected if isinstance(value, dict) else ())
        raise HarnessError(f"{label} keys differ; missing={missing}, extra={extra}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise HarnessError(f"{label} is not a canonical identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HarnessError(f"{label} is not a lowercase SHA-256 digest")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HarnessError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str, minimum: float = 0.0) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < minimum
    ):
        raise HarnessError(f"{label} must be a finite number >= {minimum}")
    return float(value)


def _utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        raise HarnessError(f"{label} must be canonical UTC with six fractional digits")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise HarnessError(f"{label} is not a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        raise HarnessError(f"{label} is not normalized UTC")
    return parsed


def _string_or_none(value: Any, label: str, *, digest: bool = False) -> None:
    if value is None:
        return
    if digest:
        _digest(value, label)
    elif not isinstance(value, str) or not value:
        raise HarnessError(f"{label} must be null or a nonempty string")


def _validate_target(value: Any, label: str) -> dict[str, Any]:
    target = _expect_keys(value, TARGET_KEYS, label)
    for key in TARGET_KEYS - {"artifact_sha256"}:
        _identifier(target[key], f"{label}.{key}")
    _digest(target["artifact_sha256"], f"{label}.artifact_sha256")
    return target


def _validate_input(value: Any, label: str) -> dict[str, Any]:
    request_input = _expect_keys(value, INPUT_KEYS, label)
    for key in ("workload_id", "input_id"):
        _identifier(request_input[key], f"{label}.{key}")
    _digest(request_input["payload_sha256"], f"{label}.payload_sha256")
    _integer(request_input["input_bytes"], f"{label}.input_bytes", 1)
    return request_input


def _validate_precondition(value: Any, label: str) -> dict[str, Any]:
    precondition = _expect_keys(value, PRECONDITION_KEYS, label)
    occupant = precondition["current_node_occupant"]
    if occupant is not None:
        occupant = _expect_keys(occupant, OCCUPANT_KEYS, f"{label}.occupant")
        _identifier(occupant["model_id"], f"{label}.occupant.model_id")
        _identifier(occupant["model_version"], f"{label}.occupant.model_version")
    cache = _expect_keys(precondition["cache"], set(CACHE_STATES), f"{label}.cache")
    for tier, allowed in CACHE_STATES.items():
        if cache[tier] not in allowed:
            raise HarnessError(f"{label}.cache.{tier} has a noncanonical state")
    if precondition["capacity"] not in CAPACITY_STATES:
        raise HarnessError(f"{label}.capacity has a noncanonical state")
    _integer(precondition["queue_depth"], f"{label}.queue_depth")
    return precondition


def _validate_scenario(
    scenario: str, target: dict[str, Any], precondition: dict[str, Any], label: str
) -> None:
    if scenario not in SCENARIOS:
        raise HarnessError(f"{label} has an unknown scenario")
    occupant = precondition["current_node_occupant"]
    cache = precondition["cache"]
    same_occupant = occupant is not None and (
        occupant["model_id"], occupant["model_version"]
    ) == (target["model_id"], target["model_version"])
    if scenario == "same_model_hot" and not same_occupant:
        raise HarnessError(f"{label} same_model_hot occupant is not the target")
    if scenario == "same_model_hot" and (
        cache["image"] != "local_verified" or cache["artifact"] != "memory_hit"
    ):
        raise HarnessError(f"{label} same_model_hot does not have a verified hot state")
    if scenario == "idle_local" and occupant is not None:
        raise HarnessError(f"{label} idle_local must have no node occupant")
    if scenario == "idle_local" and (
        cache["image"] != "local_verified"
        or cache["artifact"] not in CACHE_HITS["artifact"]
    ):
        raise HarnessError(f"{label} idle_local does not have local artifacts")
    if scenario in {"a_to_b_local", "a_to_b_remote"} and (
        occupant is None or same_occupant
    ):
        raise HarnessError(f"{label} A-to-B scenario lacks a distinct occupant")
    if scenario == "a_to_b_local" and cache["artifact"] not in CACHE_HITS["artifact"]:
        raise HarnessError(f"{label} A-to-B local artifact is not local")
    if scenario == "a_to_b_local" and cache["image"] != "local_verified":
        raise HarnessError(f"{label} A-to-B local image is not verified local")
    if scenario == "a_to_b_remote" and cache["artifact"] != "remote_miss":
        raise HarnessError(f"{label} A-to-B remote artifact is not a remote miss")
    if scenario == "checkpoint_fallback" and cache["checkpoint"] not in {
        "stale_version",
        "missing",
        "restore_failed",
    }:
        raise HarnessError(f"{label} checkpoint fallback lacks a miss/failure")
    if scenario == "capacity_miss" and precondition["capacity"] != "unavailable":
        raise HarnessError(f"{label} capacity miss is not unavailable")
    if scenario != "capacity_miss" and precondition["capacity"] == "unavailable":
        raise HarnessError(f"{label} non-capacity scenario cannot be unavailable")


def _trace_payload(trace: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in trace.items() if key != "trace_sha256"}


def validate_trace(trace: Any) -> dict[str, Any]:
    trace = _expect_keys(trace, TRACE_TOP_KEYS, "trace")
    if trace["schema"] != TRACE_SCHEMA:
        raise HarnessError("trace has the wrong schema")
    _identifier(trace["trace_id"], "trace.trace_id")
    if trace["distribution"] not in {"uniform", "skewed", "adversarial"}:
        raise HarnessError("trace distribution is not supported")
    _integer(trace["seed"], "trace.seed")
    _digest(trace["catalog_sha256"], "trace.catalog_sha256")
    request_count = _integer(trace["request_count"], "trace.request_count", 1)
    if trace["scenario_labels"] != list(SCENARIOS):
        raise HarnessError("trace scenario label contract differs from v1")
    if not isinstance(trace["requests"], list) or len(trace["requests"]) != request_count:
        raise HarnessError("trace request_count does not match requests")
    previous_offset = -1
    identities: set[str] = set()
    attempts: set[str] = set()
    for index, value in enumerate(trace["requests"]):
        request = _expect_keys(value, TRACE_REQUEST_KEYS, f"trace request {index}")
        if request["sequence"] != index:
            raise HarnessError(f"trace request {index} sequence is not contiguous")
        request_id = _identifier(request["request_id"], f"trace request {index}.request_id")
        attempt_id = _identifier(request["attempt_id"], f"trace request {index}.attempt_id")
        if request_id in identities or attempt_id in attempts:
            raise HarnessError("trace contains duplicate request/attempt identity")
        identities.add(request_id)
        attempts.add(attempt_id)
        offset = _integer(
            request["offered_at_offset_ms"],
            f"trace request {index}.offered_at_offset_ms",
        )
        if offset < previous_offset:
            raise HarnessError("trace offered offsets are not monotonic")
        previous_offset = offset
        target = _validate_target(request["target"], f"trace request {index}.target")
        _validate_input(request["input"], f"trace request {index}.input")
        precondition = _validate_precondition(
            request["precondition"], f"trace request {index}.precondition"
        )
        _validate_scenario(request["scenario"], target, precondition, f"trace request {index}")
    expected = canonical_sha256(_trace_payload(trace))
    if trace["trace_sha256"] != expected:
        raise HarnessError("trace checksum does not match its canonical payload")
    return trace


def load_trace(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise HarnessError("trace must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot read trace: {type(exc).__name__}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError("trace is not UTF-8") from exc
    value = _json_loads(text, "trace")
    if text != canonical_json(value) + "\n":
        raise HarnessError("trace is not canonical JSON with one terminal newline")
    return validate_trace(value)


def write_canonical_json(path: Path, value: Any) -> None:
    if path.exists() and path.is_symlink():
        raise HarnessError("output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _catalog_models(catalog: Any) -> tuple[list[dict[str, Any]], str]:
    catalog = _expect_keys(catalog, {"schema", "models"}, "catalog")
    if catalog["schema"] != CATALOG_SCHEMA:
        raise HarnessError("catalog has the wrong schema")
    if not isinstance(catalog["models"], list) or len(catalog["models"]) < 2:
        raise HarnessError("catalog requires at least two models")
    models: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    expected = TARGET_KEYS | {"input"}
    for index, raw in enumerate(catalog["models"]):
        model = _expect_keys(raw, expected, f"catalog model {index}")
        target = _validate_target(
            {key: model[key] for key in TARGET_KEYS}, f"catalog model {index}"
        )
        request_input = _validate_input(model["input"], f"catalog model {index}.input")
        identity = (target["model_id"], target["model_version"])
        if identity in identities:
            raise HarnessError("catalog model identity is duplicated")
        identities.add(identity)
        models.append({**target, "input": request_input})
    return models, canonical_sha256(catalog)


def _scenario_precondition(
    scenario: str, target: dict[str, Any], other: dict[str, Any]
) -> dict[str, Any]:
    occupant = {
        "model_id": target["model_id"],
        "model_version": target["model_version"],
    }
    other_occupant = {
        "model_id": other["model_id"],
        "model_version": other["model_version"],
    }
    states: dict[str, dict[str, Any]] = {
        "same_model_hot": {
            "current_node_occupant": occupant,
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
    return states[scenario]


def generate_trace(
    catalog: Any,
    *,
    distribution: str,
    seed: int,
    request_count: int,
    trace_id: str,
    interval_ms: int = 1000,
) -> dict[str, Any]:
    models, catalog_digest = _catalog_models(catalog)
    if distribution not in {"uniform", "skewed", "adversarial"}:
        raise HarnessError("distribution must be uniform, skewed, or adversarial")
    _integer(seed, "seed")
    _integer(request_count, "request_count", 1)
    _integer(interval_ms, "interval_ms")
    _identifier(trace_id, "trace_id")
    rng = random.Random(seed)
    requests: list[dict[str, Any]] = []
    weights = [1.0 / ((index + 1) ** 1.2) for index in range(len(models))]
    if distribution == "adversarial":
        scenario_order = (
            "same_model_hot",
            "a_to_b_remote",
            "capacity_miss",
            "checkpoint_fallback",
            "a_to_b_local",
            "idle_local",
        )
    else:
        scenario_order = SCENARIOS
    for index in range(request_count):
        if distribution == "uniform":
            model_index = rng.randrange(len(models))
        elif distribution == "skewed":
            model_index = rng.choices(range(len(models)), weights=weights, k=1)[0]
        else:
            model_index = index % len(models) if index % 2 == 0 else len(models) - 1
        target_model = models[model_index]
        other_model = models[(model_index + 1) % len(models)]
        scenario = scenario_order[index % len(scenario_order)]
        target = {key: target_model[key] for key in TARGET_KEYS}
        requests.append(
            {
                "sequence": index,
                "request_id": f"{trace_id}-request-{index + 1:06d}",
                "attempt_id": f"{trace_id}-attempt-{index + 1:06d}",
                "offered_at_offset_ms": index * interval_ms,
                "scenario": scenario,
                "target": target,
                "input": dict(target_model["input"]),
                "precondition": _scenario_precondition(
                    scenario, target_model, other_model
                ),
            }
        )
    trace: dict[str, Any] = {
        "schema": TRACE_SCHEMA,
        "trace_id": trace_id,
        "distribution": distribution,
        "seed": seed,
        "catalog_sha256": catalog_digest,
        "request_count": request_count,
        "scenario_labels": list(SCENARIOS),
        "requests": requests,
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return validate_trace(trace)


def _validate_recorder(value: Any) -> dict[str, Any]:
    recorder = _expect_keys(value, RECORDER_KEYS, "event.recorder")
    for key in ("recorder_id", "clock_id", "boot_id", "utc_sync_source"):
        _identifier(recorder[key], f"event.recorder.{key}")
    error = _number(recorder["max_error_ms"], "event.recorder.max_error_ms")
    if error > MAX_DECLARED_CLOCK_ERROR_MS:
        raise HarnessError("recorder clock error exceeds the v1 admission limit")
    return recorder


def _validate_environment(value: Any) -> dict[str, Any]:
    environment = _expect_keys(value, ENVIRONMENT_KEYS, "acceptance.environment")
    for key in (
        "backend",
        "backend_version",
        "provider",
        "project_id",
        "region",
        "experiment_id",
    ):
        _identifier(environment[key], f"acceptance.environment.{key}")
    _string_or_none(environment["node_id"], "acceptance.environment.node_id")
    _string_or_none(environment["gpu_type"], "acceptance.environment.gpu_type")
    _integer(environment["gpu_count"], "acceptance.environment.gpu_count")
    image_digest = environment["image_digest"]
    if image_digest is not None and (
        not isinstance(image_digest, str)
        or IMAGE_DIGEST_RE.fullmatch(image_digest) is None
    ):
        raise HarnessError(
            "acceptance.environment.image_digest must be null or digest-pinned"
        )
    if not isinstance(environment["code_revision"], str) or COMMIT_RE.fullmatch(
        environment["code_revision"]
    ) is None:
        raise HarnessError("acceptance.environment.code_revision must be a Git commit")
    _digest(environment["config_sha256"], "acceptance.environment.config_sha256")
    return environment


def _validate_ownership(value: Any) -> dict[str, Any]:
    ownership = _expect_keys(value, OWNERSHIP_KEYS, "acceptance.ownership")
    _identifier(ownership["owner_task_id"], "acceptance.ownership.owner_task_id")
    _identifier(ownership["resource_prefix"], "acceptance.ownership.resource_prefix")
    if ownership["dedicated"] is not True:
        raise HarnessError("resources must be explicitly task-dedicated")
    if not isinstance(ownership["cleanup_required"], bool):
        raise HarnessError("acceptance.ownership.cleanup_required must be boolean")
    if not isinstance(ownership["resources"], list):
        raise HarnessError("acceptance.ownership.resources must be a list")
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(ownership["resources"]):
        resource = _expect_keys(raw, RESOURCE_KEYS, f"ownership resource {index}")
        for key in RESOURCE_KEYS:
            _identifier(resource[key], f"ownership resource {index}.{key}")
        identity = (resource["kind"], resource["id"])
        if identity in seen:
            raise HarnessError("ownership resource is duplicated")
        seen.add(identity)
    return ownership


def _validate_event_shape(value: Any, line_number: int) -> tuple[dict[str, Any], datetime]:
    event = _expect_keys(value, EVENT_KEYS, f"ledger line {line_number}")
    if event["schema"] != EVENT_SCHEMA:
        raise HarnessError(f"ledger line {line_number} has the wrong schema")
    for key in ("ledger_id", "trace_id", "request_id", "attempt_id"):
        _identifier(event[key], f"ledger line {line_number}.{key}")
    ledger_sequence = _integer(
        event["ledger_sequence"], f"ledger line {line_number}.ledger_sequence"
    )
    attempt_sequence = _integer(
        event["attempt_sequence"], f"ledger line {line_number}.attempt_sequence"
    )
    expected_event_id = f"{event['attempt_id']}:{attempt_sequence:06d}"
    if event["event_id"] != expected_event_id:
        raise HarnessError(f"ledger line {line_number} event_id is not derived identity")
    if ledger_sequence != line_number - 1:
        raise HarnessError("ledger_sequence is not contiguous file order")
    timestamp = _utc(event["observed_at_utc"], f"ledger line {line_number}.observed_at_utc")
    _integer(
        event["observed_monotonic_ns"],
        f"ledger line {line_number}.observed_monotonic_ns",
        1,
    )
    _validate_recorder(event["recorder"])
    if event["event_type"] not in EVENT_TYPES:
        raise HarnessError(f"ledger line {line_number} has an unknown event type")
    if not isinstance(event["data"], dict):
        raise HarnessError(f"ledger line {line_number}.data must be an object")
    return event, timestamp


def load_ledger(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise HarnessError("ledger must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot read ledger: {type(exc).__name__}") from exc
    if not raw or not raw.endswith(b"\n"):
        raise HarnessError("ledger must be nonempty and end with exactly one line newline")
    try:
        lines = raw.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise HarnessError("ledger is not UTF-8") from exc
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.endswith("\n") or line == "\n":
            raise HarnessError(f"ledger line {line_number} is empty or unterminated")
        text = line[:-1]
        value = _json_loads(text, f"ledger line {line_number}")
        if text != canonical_json(value):
            raise HarnessError(f"ledger line {line_number} is not canonical JSON")
        if not isinstance(value, dict):
            raise HarnessError(f"ledger line {line_number} is not an object")
        events.append(value)
    return events


def write_ledger(path: Path, events: Sequence[dict[str, Any]]) -> None:
    if path.exists() and path.is_symlink():
        raise HarnessError("ledger output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(canonical_json(event) + "\n" for event in events),
        encoding="utf-8",
    )


def _validate_acceptance_data(
    data: Any, trace_request: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = _expect_keys(data, ACCEPTED_KEYS, "request.accepted data")
    if accepted["boundary"] != T0_BOUNDARY:
        raise HarnessError("request.accepted does not use the external-client T0")
    expected_request_digest = canonical_sha256(trace_request)
    if accepted["trace_request_sha256"] != expected_request_digest:
        raise HarnessError("request.accepted trace request checksum differs")
    if accepted["scenario"] != trace_request["scenario"]:
        raise HarnessError("request.accepted scenario differs from the trace")
    for key, validator in (
        ("target", _validate_target),
        ("input", _validate_input),
        ("precondition", _validate_precondition),
    ):
        validator(accepted[key], f"request.accepted.{key}")
        if accepted[key] != trace_request[key]:
            raise HarnessError(f"request.accepted {key} differs from the trace")
    _validate_scenario(
        accepted["scenario"],
        accepted["target"],
        accepted["precondition"],
        "request.accepted",
    )
    environment = _validate_environment(accepted["environment"])
    ownership = _validate_ownership(accepted["ownership"])
    return environment, ownership


def _validate_phase_data(data: Any, event_type: str) -> tuple[str, int, str | None, int]:
    if event_type == "phase.started":
        phase_data = _expect_keys(data, PHASE_STARTED_KEYS, event_type)
        outcome = None
        moved = 0
    else:
        phase_data = _expect_keys(data, PHASE_FINISHED_KEYS, event_type)
        outcome = phase_data["outcome"]
        if outcome not in PHASE_OUTCOMES:
            raise HarnessError("phase.finished outcome is not canonical")
        if not isinstance(phase_data["reason"], str) or not phase_data["reason"]:
            raise HarnessError("phase.finished reason must be nonempty")
        moved = _integer(phase_data["bytes_moved"], "phase.finished.bytes_moved")
    phase = phase_data["phase"]
    if phase not in PHASES:
        raise HarnessError("phase event has an unknown phase")
    occurrence = _integer(phase_data["occurrence"], "phase occurrence")
    if phase != "inference" and occurrence != 0:
        raise HarnessError("only inference may have retry occurrences")
    return phase, occurrence, outcome, moved


def _validate_response_data(data: Any, target: dict[str, Any]) -> None:
    response = _expect_keys(data, RESPONSE_KEYS, "response.validated data")
    if response["boundary"] != TERMINAL_BOUNDARY:
        raise HarnessError("response terminal does not use the product boundary")
    for key in ("validator_id", "model_id", "model_version"):
        _identifier(response[key], f"response.validated.{key}")
    _digest(response["validator_sha256"], "response.validated.validator_sha256")
    _digest(response["response_sha256"], "response.validated.response_sha256")
    _integer(response["response_bytes"], "response.validated.response_bytes", 1)
    if response["complete_body"] is not True or response["semantically_valid"] is not True:
        raise HarnessError("response terminal is not complete and semantically valid")
    if (response["model_id"], response["model_version"]) != (
        target["model_id"],
        target["model_version"],
    ):
        raise HarnessError("response model identity is stale or mixed")


def _validate_accounting(data: Any, moved: int) -> dict[str, Any]:
    accounting = _expect_keys(data, ACCOUNTING_KEYS, "accounting.recorded data")
    if accounting["currency"] != "USD":
        raise HarnessError("accounting currency must be USD")
    for key in (
        "cost_usd",
        "gpu_active_seconds",
        "gpu_idle_seconds",
        "billed_seconds",
    ):
        _number(accounting[key], f"accounting.{key}")
    if accounting["bytes_moved_total"] != moved:
        raise HarnessError("accounting bytes omit or double-count phase bytes")
    return accounting


def _validate_cleanup(data: Any, ownership: dict[str, Any]) -> dict[str, Any]:
    cleanup = _expect_keys(data, CLEANUP_KEYS, "cleanup.finished data")
    cleanup_required = ownership["cleanup_required"]
    if cleanup["required"] is not cleanup_required:
        raise HarnessError("cleanup requirement differs from resource ownership")
    if cleanup["status"] not in {"not_required", "complete", "retained", "failed"}:
        raise HarnessError("cleanup status is not canonical")
    if cleanup_required and cleanup["status"] == "not_required":
        raise HarnessError("required cleanup cannot be marked not_required")
    if not cleanup_required and cleanup["status"] != "not_required":
        raise HarnessError("non-required cleanup must be marked not_required")
    for key in ("resources_deleted", "resources_retained"):
        if (
            not isinstance(cleanup[key], list)
            or any(not isinstance(item, str) or not item for item in cleanup[key])
            or len(cleanup[key]) != len(set(cleanup[key]))
        ):
            raise HarnessError(f"cleanup.{key} must contain unique resource IDs")
    deleted = set(cleanup["resources_deleted"])
    retained = set(cleanup["resources_retained"])
    if deleted & retained:
        raise HarnessError("cleanup resource cannot be both deleted and retained")
    owned = {resource["id"] for resource in ownership["resources"]}
    if deleted | retained != owned:
        raise HarnessError("cleanup final state omits or invents owned resources")
    if cleanup["status"] == "complete" and retained:
        raise HarnessError("complete cleanup cannot retain owned resources")
    if cleanup["status"] == "retained" and not retained:
        raise HarnessError("retained cleanup status lacks retained resources")
    _string_or_none(cleanup["receipt_sha256"], "cleanup.receipt_sha256", digest=True)
    if not isinstance(cleanup["reason"], str) or not cleanup["reason"]:
        raise HarnessError("cleanup.reason must be nonempty")
    return cleanup


def _phase_dependencies_finished(
    phase: str,
    finished: dict[tuple[str, int], tuple[str, dict[str, Any]]],
) -> bool:
    return all((dependency, 0) in finished for dependency in PHASE_DEPENDENCIES[phase])


def _validate_attempt(
    events: list[dict[str, Any]], trace_request: dict[str, Any]
) -> dict[str, Any]:
    if not events or events[0]["event_type"] != "request.accepted":
        raise HarnessError("request-specific setup was moved before external-client T0")
    if events[0]["attempt_sequence"] != 0:
        raise HarnessError("attempt sequence does not begin at request acceptance")
    for index, event in enumerate(events):
        if event["attempt_sequence"] != index:
            raise HarnessError("attempt event sequence is not contiguous")
        if (
            event["request_id"] != trace_request["request_id"]
            or event["attempt_id"] != trace_request["attempt_id"]
        ):
            raise HarnessError("attempt contains mixed request identity")
    accepted = events[0]
    if accepted["request_id"] != trace_request["request_id"] or accepted[
        "attempt_id"
    ] != trace_request["attempt_id"]:
        raise HarnessError("ledger request/attempt identity differs from trace")
    environment, ownership = _validate_acceptance_data(accepted["data"], trace_request)
    started: dict[tuple[str, int], dict[str, Any]] = {}
    finished: dict[tuple[str, int], tuple[str, dict[str, Any]]] = {}
    inference_occurrences: list[int] = []
    terminal: dict[str, Any] | None = None
    accounting: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None
    moved = 0
    phase_samples: list[dict[str, Any]] = []
    phase_records: list[dict[str, str]] = []
    for event in events[1:]:
        event_type = event["event_type"]
        if cleanup is not None:
            raise HarnessError("events cannot follow cleanup.finished")
        if event_type == "request.accepted":
            raise HarnessError("attempt contains more than one external acceptance")
        if event_type in {"phase.started", "phase.finished"}:
            if terminal is not None:
                raise HarnessError("request execution phase was recorded after product terminal")
            phase, occurrence, outcome, phase_moved = _validate_phase_data(
                event["data"], event_type
            )
            key = (phase, occurrence)
            if event_type == "phase.started":
                if key in started or key in finished:
                    raise HarnessError("phase occurrence was started more than once")
                if not _phase_dependencies_finished(phase, finished):
                    raise HarnessError(f"phase {phase} started before causal prerequisites")
                if any(
                    finished[(dependency, 0)][0] == "failed"
                    for dependency in PHASE_DEPENDENCIES[phase]
                ):
                    raise HarnessError(f"phase {phase} started after prerequisite failure")
                if phase == "inference" and occurrence > 0:
                    prior = finished.get(("inference", occurrence - 1))
                    if prior is None or prior[0] != "failed":
                        raise HarnessError("inference retry does not follow a failed occurrence")
                started[key] = event
            else:
                if key in finished:
                    raise HarnessError("phase occurrence was finished more than once")
                if not _phase_dependencies_finished(phase, finished):
                    raise HarnessError(f"phase {phase} finished before causal prerequisites")
                if outcome == "skipped":
                    if key in started:
                        raise HarnessError("skipped phase cannot have a start event")
                    duration = None
                else:
                    start = started.get(key)
                    if start is None:
                        raise HarnessError("completed/failed phase lacks a start event")
                    duration = (
                        event["observed_monotonic_ns"]
                        - start["observed_monotonic_ns"]
                    ) / 1_000_000_000
                    if duration <= 0:
                        raise HarnessError("phase duration is not positive")
                    phase_samples.append(
                        {
                            "phase": phase,
                            "occurrence": occurrence,
                            "outcome": outcome,
                            "seconds": duration,
                        }
                    )
                moved += phase_moved
                finished[key] = (str(outcome), event)
                phase_records.append({"phase": phase, "outcome": str(outcome)})
                if phase == "inference":
                    inference_occurrences.append(occurrence)
        elif event_type == "response.validated":
            if terminal is not None:
                raise HarnessError("attempt contains multiple product terminals")
            if accounting is not None:
                raise HarnessError("response terminal follows accounting")
            _validate_response_data(event["data"], accepted["data"]["target"])
            terminal = event
        elif event_type == "attempt.failed":
            if terminal is not None:
                raise HarnessError("attempt contains multiple product terminals")
            failure = _expect_keys(event["data"], FAILURE_KEYS, "attempt.failed data")
            if failure["failure_class"] not in FAILURE_CLASSES:
                raise HarnessError("attempt failure class is not canonical")
            if not isinstance(failure["reason"], str) or not failure["reason"]:
                raise HarnessError("attempt failure reason must be nonempty")
            if not isinstance(failure["retryable"], bool):
                raise HarnessError("attempt retryable flag must be boolean")
            terminal = event
        elif event_type == "accounting.recorded":
            if terminal is None:
                raise HarnessError("accounting precedes the product terminal")
            if accounting is not None:
                raise HarnessError("attempt contains multiple accounting records")
            accounting = _validate_accounting(event["data"], moved)
        elif event_type == "cleanup.finished":
            if accounting is None:
                raise HarnessError("cleanup precedes accounting")
            if cleanup is not None:
                raise HarnessError("attempt contains multiple cleanup records")
            cleanup = _validate_cleanup(event["data"], ownership)
    for phase in PHASES:
        occurrences = sorted(key[1] for key in finished if key[0] == phase)
        if phase == "inference":
            if not occurrences or occurrences != list(range(len(occurrences))):
                raise HarnessError("inference occurrences are missing or noncontiguous")
            if any(key[0] == "inference" and key not in finished for key in started):
                raise HarnessError("inference start lacks a finish")
        elif occurrences != [0]:
            raise HarnessError(f"phase {phase} is omitted from the causal ledger")
    if set(started) - set(finished):
        raise HarnessError("one or more phase starts lack finishes")
    if terminal is None:
        raise HarnessError("attempt lacks a product terminal")
    if accounting is None or cleanup is None:
        raise HarnessError("attempt lacks accounting or cleanup evidence")
    successful = terminal["event_type"] == "response.validated"
    final_inference = finished[("inference", max(inference_occurrences))][0]
    failed_phases = [key for key, value in finished.items() if value[0] == "failed"]
    if successful:
        if final_inference != "completed":
            raise HarnessError("valid response does not follow completed inference")
        if any(phase != "inference" for phase, _ in failed_phases):
            raise HarnessError("valid response follows a failed non-inference phase")
    elif not failed_phases:
        raise HarnessError("failed attempt does not expose a failed phase")
    if trace_request["scenario"] == "capacity_miss":
        if successful or finished[("placement", 0)][0] != "failed":
            raise HarnessError("capacity-miss scenario must expose placement failure")
        if terminal["data"]["failure_class"] != "capacity":
            raise HarnessError("capacity-miss terminal must be classified as capacity")
    duration = (
        terminal["observed_monotonic_ns"] - accepted["observed_monotonic_ns"]
    ) / 1_000_000_000
    if duration <= 0:
        raise HarnessError("product terminal does not follow T0")
    return {
        "request_id": accepted["request_id"],
        "attempt_id": accepted["attempt_id"],
        "t0_monotonic_ns": accepted["observed_monotonic_ns"],
        "scenario": trace_request["scenario"],
        "model_id": accepted["data"]["target"]["model_id"],
        "model_version": accepted["data"]["target"]["model_version"],
        "artifact_id": accepted["data"]["target"]["artifact_id"],
        "artifact_version": accepted["data"]["target"]["artifact_version"],
        "workload_id": accepted["data"]["input"]["workload_id"],
        "success": successful,
        "terminal_seconds": duration,
        "failure_class": None if successful else terminal["data"]["failure_class"],
        "cache": accepted["data"]["precondition"]["cache"],
        "current_node_occupant": accepted["data"]["precondition"][
            "current_node_occupant"
        ],
        "queue_depth": accepted["data"]["precondition"]["queue_depth"],
        "environment": environment,
        "ownership": ownership,
        "accounting": accounting,
        "cleanup": cleanup,
        "phase_samples": phase_samples,
        "phase_records": phase_records,
    }


def validate_ledger(
    events: Sequence[dict[str, Any]], trace: dict[str, Any]
) -> list[dict[str, Any]]:
    trace = validate_trace(trace)
    if not events:
        raise HarnessError("ledger is empty")
    shaped: list[tuple[dict[str, Any], datetime]] = [
        _validate_event_shape(event, index)
        for index, event in enumerate(events, 1)
    ]
    ledger_ids = {event["ledger_id"] for event, _ in shaped}
    trace_ids = {event["trace_id"] for event, _ in shaped}
    recorder_payloads = {canonical_json(event["recorder"]) for event, _ in shaped}
    if len(ledger_ids) != 1 or trace_ids != {trace["trace_id"]}:
        raise HarnessError("ledger or trace identity is mixed")
    if len(recorder_payloads) != 1:
        raise HarnessError("backend-specific/mixed recorder clocks are forbidden")
    first_event, first_utc = shaped[0]
    first_mono = first_event["observed_monotonic_ns"]
    previous_mono = 0
    previous_utc: datetime | None = None
    declared_error_ms = float(first_event["recorder"]["max_error_ms"])
    drift_limit_seconds = max(0.001, declared_error_ms * 2 / 1000)
    for event, timestamp in shaped:
        monotonic = event["observed_monotonic_ns"]
        if monotonic <= previous_mono:
            raise HarnessError("ledger monotonic clock is not strictly increasing")
        if previous_utc is not None and timestamp < previous_utc:
            raise HarnessError("ledger UTC clock moves backwards")
        utc_delta = (timestamp - first_utc).total_seconds()
        mono_delta = (monotonic - first_mono) / 1_000_000_000
        if abs(utc_delta - mono_delta) > drift_limit_seconds:
            raise HarnessError("UTC/monotonic clock drift exceeds declared bounds")
        previous_mono = monotonic
        previous_utc = timestamp
    by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event, _ in shaped:
        by_attempt[event["attempt_id"]].append(event)
    expected_attempts = {request["attempt_id"] for request in trace["requests"]}
    if set(by_attempt) != expected_attempts:
        missing = sorted(expected_attempts - set(by_attempt))
        extra = sorted(set(by_attempt) - expected_attempts)
        raise HarnessError(
            f"ledger excludes or invents attempts; missing={missing}, extra={extra}"
        )
    results = []
    for request in trace["requests"]:
        results.append(_validate_attempt(by_attempt[request["attempt_id"]], request))
    first_observed = results[0]["t0_monotonic_ns"]
    first_offered = trace["requests"][0]["offered_at_offset_ms"]
    for result, request in zip(results, trace["requests"], strict=True):
        observed_delta_ms = (result["t0_monotonic_ns"] - first_observed) / 1_000_000
        offered_delta_ms = request["offered_at_offset_ms"] - first_offered
        schedule_error_ms = round(observed_delta_ms - offered_delta_ms, 6)
        if abs(schedule_error_ms) > MAX_ACCEPTANCE_SCHEDULE_ERROR_MS:
            raise HarnessError("external acceptance schedule differs from the pinned trace")
        result["acceptance_schedule_error_ms"] = schedule_error_ms
    return results


def _distribution(values: Iterable[float]) -> dict[str, Any]:
    ordered = sorted(round(float(value), 9) for value in values)
    result: dict[str, Any] = {
        "sample_count": len(ordered),
        "estimator": PERCENTILE_ESTIMATOR,
        "minimum_samples": dict(PERCENTILE_MIN_SAMPLES),
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
    }
    for label, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        minimum = PERCENTILE_MIN_SAMPLES[label]
        result[label] = (
            ordered[math.ceil(percentile * len(ordered)) - 1]
            if len(ordered) >= minimum
            else None
        )
    return result


def aggregate_ledger(
    events: Sequence[dict[str, Any]], trace: dict[str, Any]
) -> dict[str, Any]:
    attempts = validate_ledger(events, trace)
    synthetic = all(
        event["recorder"]["recorder_id"] == "synthetic-contract-smoke"
        for event in events
    )
    successes = [attempt for attempt in attempts if attempt["success"]]
    failure_counts = Counter(
        attempt["failure_class"] for attempt in attempts if not attempt["success"]
    )
    phase_values: dict[str, list[float]] = defaultdict(list)
    phase_outcomes: dict[str, Counter[str]] = defaultdict(Counter)
    for attempt in attempts:
        for sample in attempt["phase_samples"]:
            phase_values[sample["phase"]].append(sample["seconds"])
        for record in attempt["phase_records"]:
            phase_outcomes[record["phase"]][record["outcome"]] += 1
    environment_groups: dict[str, dict[str, Any]] = {}
    ownership_groups: dict[str, dict[str, Any]] = {}
    for attempt in attempts:
        environment_digest = canonical_sha256(attempt["environment"])
        ownership_digest = canonical_sha256(attempt["ownership"])
        environment_group = environment_groups.setdefault(
            environment_digest,
            {
                "environment_sha256": environment_digest,
                "attempt_count": 0,
                "environment": attempt["environment"],
            },
        )
        environment_group["attempt_count"] += 1
        ownership_group = ownership_groups.setdefault(
            ownership_digest,
            {
                "ownership_sha256": ownership_digest,
                "attempt_count": 0,
                "ownership": attempt["ownership"],
            },
        )
        ownership_group["attempt_count"] += 1
    scenario_results: dict[str, Any] = {}
    for scenario in SCENARIOS:
        members = [attempt for attempt in attempts if attempt["scenario"] == scenario]
        valid = [attempt["terminal_seconds"] for attempt in members if attempt["success"]]
        scenario_results[scenario] = {
            "attempts": len(members),
            "valid_responses": len(valid),
            "failures": len(members) - len(valid),
            "product_latency_seconds": _distribution(valid),
        }
    cache_results: dict[str, Any] = {}
    for tier in CACHE_STATES:
        counts = Counter(attempt["cache"][tier] for attempt in attempts)
        eligible = sum(counts.values()) - counts.get("not_applicable", 0)
        hits = sum(counts.get(label, 0) for label in CACHE_HITS[tier])
        cache_results[tier] = {
            "states": dict(sorted(counts.items())),
            "eligible": eligible,
            "hits": hits,
            "hit_rate": round(hits / eligible, 9) if eligible else None,
        }
    total_cost = round(sum(item["accounting"]["cost_usd"] for item in attempts), 9)
    gpu_active = round(
        sum(item["accounting"]["gpu_active_seconds"] for item in attempts), 9
    )
    gpu_idle = round(
        sum(item["accounting"]["gpu_idle_seconds"] for item in attempts), 9
    )
    aggregate = {
        "schema": AGGREGATE_SCHEMA,
        "evidence_classification": (
            "synthetic-contract-smoke-not-performance-evidence"
            if synthetic
            else "external-request-product-slo"
        ),
        "trace_id": trace["trace_id"],
        "trace_sha256": trace["trace_sha256"],
        "ledger_sha256": hashlib.sha256(
            "".join(canonical_json(event) + "\n" for event in events).encode("utf-8")
        ).hexdigest(),
        "boundary": {"t0": T0_BOUNDARY, "terminal": TERMINAL_BOUNDARY},
        "attempts": {
            "offered": trace["request_count"],
            "observed": len(attempts),
            "valid_responses": len(successes),
            "failures": len(attempts) - len(successes),
            "failure_rate": round((len(attempts) - len(successes)) / len(attempts), 9),
            "failure_classes": dict(sorted(failure_counts.items())),
            "results": [
                {
                    key: attempt[key]
                    for key in (
                        "request_id",
                        "attempt_id",
                        "scenario",
                        "model_id",
                        "model_version",
                        "artifact_id",
                        "artifact_version",
                        "workload_id",
                        "success",
                        "terminal_seconds",
                        "failure_class",
                        "acceptance_schedule_error_ms",
                    )
                }
                | {
                    "current_node_occupant": attempt["current_node_occupant"],
                    "queue_depth": attempt["queue_depth"],
                    "cache": attempt["cache"],
                    "cost_usd": attempt["accounting"]["cost_usd"],
                    "bytes_moved_total": attempt["accounting"][
                        "bytes_moved_total"
                    ],
                    "gpu_active_seconds": attempt["accounting"][
                        "gpu_active_seconds"
                    ],
                    "gpu_idle_seconds": attempt["accounting"][
                        "gpu_idle_seconds"
                    ],
                    "cleanup_status": attempt["cleanup"]["status"],
                    "environment_sha256": canonical_sha256(attempt["environment"]),
                    "ownership_sha256": canonical_sha256(attempt["ownership"]),
                }
                for attempt in attempts
            ],
        },
        "environments": [environment_groups[key] for key in sorted(environment_groups)],
        "resource_ownership": [ownership_groups[key] for key in sorted(ownership_groups)],
        "product_latency_seconds": _distribution(
            attempt["terminal_seconds"] for attempt in successes
        ),
        "all_attempt_terminal_seconds": _distribution(
            attempt["terminal_seconds"] for attempt in attempts
        ),
        "trace_replay": {
            "maximum_allowed_acceptance_schedule_error_ms": (
                MAX_ACCEPTANCE_SCHEDULE_ERROR_MS
            ),
            "absolute_acceptance_schedule_error_ms": _distribution(
                abs(attempt["acceptance_schedule_error_ms"])
                for attempt in attempts
            ),
        },
        "scenarios": scenario_results,
        "cache": cache_results,
        "phases": {
            phase: {
                "operation_duration_seconds": _distribution(phase_values[phase]),
                "outcomes": dict(sorted(phase_outcomes[phase].items())),
                "additive_to_product_percentiles": False,
            }
            for phase in PHASES
        },
        "transfer": {
            "bytes_moved_total": sum(
                item["accounting"]["bytes_moved_total"] for item in attempts
            )
        },
        "gpu": {
            "active_seconds": gpu_active,
            "idle_seconds": gpu_idle,
            "active_fraction": (
                round(gpu_active / (gpu_active + gpu_idle), 9)
                if gpu_active + gpu_idle > 0
                else None
            ),
        },
        "cost": {
            "currency": "USD",
            "total": total_cost,
            "per_valid_response": (
                round(total_cost / len(successes), 9) if successes else None
            ),
        },
        "cleanup": dict(sorted(Counter(item["cleanup"]["status"] for item in attempts).items())),
        "aggregation_invariants": [
            "product latency is computed per attempt from external T0 to terminal "
            "before percentiles",
            "failed attempts remain in the denominator and never enter valid-response "
            "latency percentiles",
            "phase distributions are diagnostic and are never summed into a product percentile",
        ],
    }
    return aggregate


LEGACY_DEFAULTS = {
    "openfold2": {
        "model_version": (
            "sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4"
        ),
        "artifact_id": "openfold2-native-f7-v1",
        "artifact_version": (
            "sha256:78368af3e6f143d7dc681632c4150b29f6354717103638b56e776244d9631b04"
        ),
    },
    "boltz2": {
        "model_version": (
            "sha256:0788c95c8b5b6c1a73a62c656b298ecc353a8187dc22b794f496ae40672c4c98"
        ),
        "artifact_id": "boltz2-native-f7-v1",
        "artifact_version": (
            "sha256:6539b9f50a71c9f5fb6a3fbacd44f5d5ea41003539b6563682a38600d1492456"
        ),
    },
}


def import_legacy_cohort(path: Path, model: str) -> dict[str, Any]:
    """Read a published cohort without rewriting or promoting its boundary."""
    if model not in LEGACY_DEFAULTS:
        raise HarnessError("legacy model must be openfold2 or boltz2")
    source_digest = file_sha256(path)
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream, delimiter="\t"))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise HarnessError(f"cannot read legacy cohort: {type(exc).__name__}") from exc
    if not rows:
        raise HarnessError("legacy cohort is empty")
    required = {
        "record_type",
        "run_id",
        "demand_to_first_semantic_seconds",
        "demand_to_two_semantic_seconds",
        "cohort_outcome",
    }
    if not required.issubset(rows[0]):
        raise HarnessError("legacy cohort lacks fresh-cohort sample columns")
    samples: list[dict[str, Any]] = []
    excluded_summaries = 0
    for row_number, row in enumerate(rows, 2):
        if row["record_type"] == "summary":
            excluded_summaries += 1
            continue
        if row["record_type"] != "sample":
            raise HarnessError(f"legacy row {row_number} has an unknown record type")
        run_id = _identifier(row["run_id"], f"legacy row {row_number}.run_id")
        try:
            first = float(row["demand_to_first_semantic_seconds"])
            second = float(row["demand_to_two_semantic_seconds"])
        except (TypeError, ValueError) as exc:
            raise HarnessError(f"legacy row {row_number} timing is invalid") from exc
        _number(first, f"legacy row {row_number}.first", 0.000000001)
        _number(second, f"legacy row {row_number}.second", first)
        if row.get("runner_qualification") != "PASS" or row.get("cleanup") != "PASS":
            raise HarnessError(f"legacy row {row_number} is not qualified and cleaned")
        samples.append(
            {
                "run_id": run_id,
                "internal_stage_to_first_valid_response_seconds": round(first, 6),
                "internal_stage_to_two_valid_responses_seconds": round(second, 6),
                "published_outcome": row["cohort_outcome"],
            }
        )
    if not samples:
        raise HarnessError("legacy cohort contains no sample rows")
    defaults = LEGACY_DEFAULTS[model]
    return {
        "schema": LEGACY_IMPORT_SCHEMA,
        "evidence_classification": "prepared-node-internal-stage-only",
        "eligible_for_product_slo": False,
        "reason": (
            "source T0 precedes Kubernetes target creation on a prepared node; it is not "
            "external acceptance of a model_id plus input request"
        ),
        "source": {
            "path": str(path),
            "sha256": source_digest,
            "rows": len(rows),
            "sample_rows": len(samples),
            "excluded_published_summary_rows": excluded_summaries,
            "mutated": False,
        },
        "model": {
            "model_id": model,
            "model_version": defaults["model_version"],
            "artifact_id": defaults["artifact_id"],
            "artifact_version": defaults["artifact_version"],
        },
        "source_boundary": "prepared-node-pre-dispatch-to-semantic-response/v1",
        "product_boundary": None,
        "samples": samples,
    }


def _read_boot_id() -> str:
    path = Path("/proc/sys/kernel/random/boot_id")
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError as exc:
        raise HarnessError("cannot read the recorder boot identity") from exc


def append_event(
    path: Path,
    *,
    ledger_id: str,
    trace_id: str,
    request_id: str,
    attempt_id: str,
    recorder: dict[str, Any],
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Append one external-recorder observation under an exclusive file lock."""
    for value, label in (
        (ledger_id, "ledger_id"),
        (trace_id, "trace_id"),
        (request_id, "request_id"),
        (attempt_id, "attempt_id"),
    ):
        _identifier(value, label)
    _validate_recorder(recorder)
    if event_type not in EVENT_TYPES:
        raise HarnessError("event_type is not supported")
    if not isinstance(data, dict):
        raise HarnessError("event data must be an object")
    if path.exists() and path.is_symlink():
        raise HarnessError("ledger output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "r+", encoding="utf-8", closefd=False) as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            text = stream.read()
            existing: list[dict[str, Any]] = []
            if text:
                if not text.endswith("\n"):
                    raise HarnessError("existing ledger is not newline terminated")
                for line_number, line in enumerate(text.splitlines(), 1):
                    value = _json_loads(line, f"existing ledger line {line_number}")
                    if line != canonical_json(value) or not isinstance(value, dict):
                        raise HarnessError("existing ledger is not canonical")
                    existing.append(value)
                for index, value in enumerate(existing, 1):
                    _validate_event_shape(value, index)
                if any(value["ledger_id"] != ledger_id for value in existing):
                    raise HarnessError("append ledger_id differs from existing ledger")
                if any(value["trace_id"] != trace_id for value in existing):
                    raise HarnessError("append trace_id differs from existing ledger")
                if any(value["recorder"] != recorder for value in existing):
                    raise HarnessError("append recorder clock differs from existing ledger")
            attempt_sequence = sum(
                1 for value in existing if value["attempt_id"] == attempt_id
            )
            event = {
                "schema": EVENT_SCHEMA,
                "ledger_id": ledger_id,
                "ledger_sequence": len(existing),
                "trace_id": trace_id,
                "request_id": request_id,
                "attempt_id": attempt_id,
                "attempt_sequence": attempt_sequence,
                "event_id": f"{attempt_id}:{attempt_sequence:06d}",
                "observed_at_utc": datetime.now(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                ),
                "observed_monotonic_ns": time.monotonic_ns(),
                "recorder": dict(recorder),
                "event_type": event_type,
                "data": data,
            }
            stream.seek(0, os.SEEK_END)
            stream.write(canonical_json(event) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            return event
    finally:
        os.close(descriptor)


def default_recorder(recorder_id: str, *, max_error_ms: float) -> dict[str, Any]:
    _identifier(recorder_id, "recorder_id")
    return {
        "recorder_id": recorder_id,
        "clock_id": f"linux-boottime:{_read_boot_id()}",
        "boot_id": _read_boot_id(),
        "utc_sync_source": "host-chrony-or-timesyncd",
        "max_error_ms": max_error_ms,
    }


def synthetic_smoke_ledger(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Create contract-only fixture events; never valid as performance evidence."""
    trace = validate_trace(trace)
    events: list[dict[str, Any]] = []
    ledger_id = f"{trace['trace_id']}-synthetic-smoke"
    recorder = {
        "recorder_id": "synthetic-contract-smoke",
        "clock_id": "synthetic-clock",
        "boot_id": "synthetic-boot",
        "utc_sync_source": "deterministic-fixture",
        "max_error_ms": 0.0,
    }
    base_utc = datetime(2026, 1, 1, tzinfo=UTC)
    base_mono = 1_000_000_000_000
    elapsed_ns = 0
    attempt_sequences: Counter[str] = Counter()

    def add(
        request: dict[str, Any],
        event_type: str,
        data: dict[str, Any],
        *,
        advance_ns: int = 10_000_000,
    ) -> None:
        nonlocal elapsed_ns
        elapsed_ns += advance_ns
        attempt_sequence = attempt_sequences[request["attempt_id"]]
        attempt_sequences[request["attempt_id"]] += 1
        timestamp = base_utc + timedelta(microseconds=elapsed_ns // 1000)
        events.append(
            {
                "schema": EVENT_SCHEMA,
                "ledger_id": ledger_id,
                "ledger_sequence": len(events),
                "trace_id": trace["trace_id"],
                "request_id": request["request_id"],
                "attempt_id": request["attempt_id"],
                "attempt_sequence": attempt_sequence,
                "event_id": f"{request['attempt_id']}:{attempt_sequence:06d}",
                "observed_at_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "observed_monotonic_ns": base_mono + elapsed_ns,
                "recorder": dict(recorder),
                "event_type": event_type,
                "data": data,
            }
        )

    environment = {
        "backend": "synthetic-smoke",
        "backend_version": "v1",
        "provider": "local",
        "project_id": "local-contract-test",
        "region": "local",
        "node_id": None,
        "gpu_type": None,
        "gpu_count": 0,
        "image_digest": None,
        "code_revision": "0" * 40,
        "config_sha256": "0" * 64,
        "experiment_id": ledger_id,
    }
    ownership = {
        "owner_task_id": "catalog-switch-request-slo-harness",
        "resource_prefix": "synthetic-smoke",
        "dedicated": True,
        "cleanup_required": False,
        "resources": [],
    }
    for request in trace["requests"]:
        scheduled_ns = request["offered_at_offset_ms"] * 1_000_000
        elapsed_ns = max(elapsed_ns, scheduled_ns)
        add(
            request,
            "request.accepted",
            {
                "boundary": T0_BOUNDARY,
                "trace_request_sha256": canonical_sha256(request),
                "scenario": request["scenario"],
                "target": request["target"],
                "input": request["input"],
                "precondition": request["precondition"],
                "environment": environment,
                "ownership": ownership,
            },
            advance_ns=1_000,
        )
    for request in trace["requests"]:
        failed = request["scenario"] == "capacity_miss"
        moved = 0
        for phase in PHASES:
            if failed and PHASES.index(phase) > PHASES.index("placement"):
                outcome = "skipped"
            elif failed and phase == "placement":
                outcome = "failed"
            elif request["scenario"] == "same_model_hot" and phase in {
                "drain",
                "gpu_release",
                "placement",
                "image_readiness",
                "artifact_readiness",
                "storage_readiness",
                "runtime_launch",
            }:
                outcome = "skipped"
            elif phase in {"drain", "gpu_release"} and request["scenario"] == "idle_local":
                outcome = "skipped"
            else:
                outcome = "completed"
            if outcome != "skipped":
                add(request, "phase.started", {"phase": phase, "occurrence": 0})
            phase_bytes = 1024 if phase == "artifact_readiness" and outcome == "completed" else 0
            moved += phase_bytes
            add(
                request,
                "phase.finished",
                {
                    "phase": phase,
                    "occurrence": 0,
                    "outcome": outcome,
                    "reason": "synthetic contract smoke",
                    "bytes_moved": phase_bytes,
                },
            )
        if failed:
            add(
                request,
                "attempt.failed",
                {
                    "failure_class": "capacity",
                    "reason": "synthetic capacity miss",
                    "retryable": True,
                },
            )
        else:
            add(
                request,
                "response.validated",
                {
                    "boundary": TERMINAL_BOUNDARY,
                    "validator_id": "synthetic-semantic-validator-v1",
                    "validator_sha256": "1" * 64,
                    "response_sha256": hashlib.sha256(
                        request["request_id"].encode("utf-8")
                    ).hexdigest(),
                    "response_bytes": 128,
                    "complete_body": True,
                    "semantically_valid": True,
                    "model_id": request["target"]["model_id"],
                    "model_version": request["target"]["model_version"],
                },
            )
        add(
            request,
            "accounting.recorded",
            {
                "currency": "USD",
                "cost_usd": 0.0,
                "gpu_active_seconds": 0.0,
                "gpu_idle_seconds": 0.0,
                "billed_seconds": 0.0,
                "bytes_moved_total": moved,
            },
        )
        add(
            request,
            "cleanup.finished",
            {
                "required": False,
                "status": "not_required",
                "resources_deleted": [],
                "resources_retained": [],
                "receipt_sha256": None,
                "reason": "synthetic smoke creates no resources",
            },
        )
    return events
