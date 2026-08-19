#!/usr/bin/env python3
"""PROVISIONAL adapter event schema for the Modal pilot.

This is NOT the program metric contract. The authoritative external-client
request/switch ledger is owned by ``catalog-switch-request-slo-harness``;
until that contract is published and reviewed, records produced here are
provisional adapter-test artifacts only and must be re-emitted through the
shared ledger before any cross-backend claim. No result aggregated from this
schema may be promoted as a backend comparison.

Within that limit the local rules stay fail-closed: T0 is client-side
external acceptance of a request carrying ``model_id`` plus input;
completion is the first complete semantically valid response; one record is
one request attempt window (platform-internal retries stay inside it via
``attempts``); a record that cannot be validated is rejected, never coerced.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA = (
    "ml-specialist.nebius.ai/catalog-switch-modal-pilot/provisional-adapter-event/v1"
)

MODES = frozenset(
    {"cold", "cpu_snapshot", "gpu_snapshot", "warm_bounded", "switch", "burst", "capacity"}
)
CACHE_STATES = frozenset(
    {"remote-miss", "volume-hit", "image-cached", "snapshot-restored", "warm", "unknown"}
)
OUTCOMES = frozenset({"valid_response", "invalid_response", "error", "timeout", "rejected"})

# Provenance label for interior phases Modal's managed layer does not expose.
UNOBSERVABLE = "unobservable(managed)"

_REQUIRED_STR = (
    "run_id",
    "pilot",
    "model_id",
    "mode",
    "cache_state",
    "outcome",
    "gpu_requested",
    "gpu_allocated",
    "region_requested",
    "image_ref",
    "t0_wall_utc",
)
_REQUIRED_NUM = (
    "t0_monotonic_s",
    "t_first_valid_response_monotonic_s",
    "attempts",
)


class EventValidationError(ValueError):
    """A request event violates the frozen schema."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EventValidationError(message)


def validate_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one request event; return a plain dict copy or raise."""
    _require(isinstance(event, Mapping), "event must be a mapping")
    _require(event.get("schema") == SCHEMA, f"schema must be {SCHEMA}")
    for key in _REQUIRED_STR:
        value = event.get(key)
        _require(isinstance(value, str) and value != "", f"{key} must be a non-empty string")
    for key in _REQUIRED_NUM:
        value = event.get(key)
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{key} must be a number",
        )
    _require(event["mode"] in MODES, f"mode must be one of {sorted(MODES)}")
    _require(
        event["cache_state"] in CACHE_STATES,
        f"cache_state must be one of {sorted(CACHE_STATES)}",
    )
    _require(event["outcome"] in OUTCOMES, f"outcome must be one of {sorted(OUTCOMES)}")
    _require(int(event["attempts"]) >= 1, "attempts must be >= 1")
    _require(
        "@sha256:" in event["image_ref"],
        "image_ref must pin a digest (artifact-version binding)",
    )

    latency = float(event["t_first_valid_response_monotonic_s"]) - float(event["t0_monotonic_s"])
    if event["outcome"] == "valid_response":
        _require(latency > 0.0, "valid_response requires completion after T0")
        _require(
            isinstance(event.get("semantic_validator"), str) and event["semantic_validator"],
            "valid_response requires the semantic_validator identity",
        )
    else:
        _require(
            isinstance(event.get("failure_reason"), str) and event["failure_reason"],
            "non-valid outcomes require failure_reason",
        )

    phases = event.get("phases", {})
    _require(isinstance(phases, Mapping), "phases must be a mapping")
    for name, phase in phases.items():
        _require(isinstance(phase, Mapping), f"phase {name} must be a mapping")
        _require(
            phase.get("provenance") in ("client", "container-log", UNOBSERVABLE),
            f"phase {name} needs provenance client|container-log|{UNOBSERVABLE}",
        )
        if phase["provenance"] != UNOBSERVABLE:
            offset = phase.get("offset_from_t0_s")
            _require(
                isinstance(offset, (int, float))
                and not isinstance(offset, bool)
                and float(offset) >= 0.0,
                f"phase {name} needs offset_from_t0_s >= 0 (never before T0)",
            )
    return dict(event)


def latency_seconds(event: Mapping[str, Any]) -> float:
    """T0-to-first-valid-response latency of a validated valid_response event."""
    checked = validate_event(event)
    _require(checked["outcome"] == "valid_response", "latency only defined for valid_response")
    return float(checked["t_first_valid_response_monotonic_s"]) - float(
        checked["t0_monotonic_s"]
    )


def load_events(path: str) -> list[dict[str, Any]]:
    """Load and validate a JSONL event file; any bad line fails the load."""
    events: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EventValidationError(f"line {line_number}: invalid JSON") from exc
            try:
                events.append(validate_event(raw))
            except EventValidationError as exc:
                raise EventValidationError(f"line {line_number}: {exc}") from exc
    return events
