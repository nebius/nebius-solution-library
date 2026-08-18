#!/usr/bin/env python3
"""Build benchmark timings from semantic HTTP and Kubernetes evidence."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


class TimingEvidenceError(ValueError):
    """Raised when timing evidence is missing, malformed, or contradictory."""


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TimingEvidenceError(f"{label} timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimingEvidenceError(f"{label} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TimingEvidenceError(f"{label} timestamp must include a UTC offset")
    return parsed


def _elapsed(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise TimingEvidenceError(f"{label} must be a finite nonnegative number")
    return round(float(value), 6)


def _kubernetes_ready(target: dict[str, Any]) -> tuple[datetime, str]:
    conditions = target.get("status", {}).get("conditions")
    if not isinstance(conditions, list):
        raise TimingEvidenceError("target has no Kubernetes conditions")
    matches = [
        condition
        for condition in conditions
        if isinstance(condition, dict)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
    ]
    if len(matches) != 1:
        raise TimingEvidenceError(
            "target must have exactly one successful Kubernetes Ready condition"
        )
    raw = matches[0].get("lastTransitionTime")
    return _timestamp(raw, "Kubernetes Ready"), str(raw)


def _http_ready(semantic: dict[str, Any]) -> tuple[datetime, datetime, str]:
    ready = semantic.get("ready_wait")
    if ready is None:
        ready = semantic.get("ready")
    if isinstance(ready, dict):
        if ready.get("status") != "PASS":
            raise TimingEvidenceError(
                "semantic probe has no successful HTTP readiness receipt"
            )
        base_url = semantic.get("base_url")
        if (
            not isinstance(base_url, str)
            or ready.get("endpoint") != base_url.rstrip("/") + "/v1/health/ready"
        ):
            raise TimingEvidenceError(
                "HTTP readiness receipt is not bound to the semantic probe origin"
            )
        started = _timestamp(ready.get("started_at"), "HTTP readiness probe start")
        raw_finished = ready.get("finished_at")
        return started, _timestamp(raw_finished, "successful HTTP readiness"), str(
            raw_finished
        )

    raw_ready = semantic.get("ready_at")
    http_ready = _timestamp(raw_ready, "successful HTTP readiness")
    return (
        _timestamp(semantic.get("started_at"), "semantic probe start"),
        http_ready,
        str(raw_ready),
    )


def build_timing_evidence(
    run: dict[str, Any], semantic: dict[str, Any], target: dict[str, Any]
) -> dict[str, Any]:
    """Return the standardized warm-instance benchmark timing fields.

    Worker timing is deliberately absent: worker receipt and semantic probing are
    independent concurrent timelines and must not be ordered against one another.
    """

    if (
        semantic.get("status") != "PASS"
        or semantic.get("ok") is not True
        or semantic.get("request_count") != 2
        or semantic.get("passed_case_count") != 2
        or semantic.get("failed_case_count") != 0
    ):
        raise TimingEvidenceError("semantic summary is not a strict two-call PASS")
    cases = semantic.get("cases")
    if not isinstance(cases, list) or len(cases) != 2:
        raise TimingEvidenceError("semantic summary must contain exactly two cases")
    calls: list[float] = []
    for index, case in enumerate(cases, 1):
        if (
            not isinstance(case, dict)
            or case.get("status") != "PASS"
            or case.get("ok") is not True
        ):
            raise TimingEvidenceError(f"semantic request {index} did not pass")
        calls.append(_elapsed(case.get("elapsed_seconds"), f"semantic request {index}"))

    demand_raw = run.get("demand_at")
    semantic_started_raw = semantic.get("started_at")
    semantic_finished_raw = semantic.get("finished_at")
    demand = _timestamp(demand_raw, "demand")
    semantic_started = _timestamp(semantic_started_raw, "semantic probe start")
    semantic_finished = _timestamp(semantic_finished_raw, "second semantic completion")
    http_probe_started, http_ready, http_ready_raw = _http_ready(semantic)
    kubernetes_ready, kubernetes_ready_raw = _kubernetes_ready(target)

    if not (
        demand
        <= semantic_started
        <= http_probe_started
        <= http_ready
        <= semantic_finished
    ):
        raise TimingEvidenceError("semantic probe timestamps are not monotonically ordered")
    kubernetes_ready_seconds = (kubernetes_ready - demand).total_seconds()
    if kubernetes_ready_seconds < 0:
        if abs(kubernetes_ready_seconds) >= 1:
            raise TimingEvidenceError(
                "Kubernetes Ready precedes demand by at least one second"
            )
        # Kubernetes condition timestamps may be serialized to whole seconds.
        # Preserve the raw timestamp below, but normalize only this bounded
        # same-second precision inversion for the diagnostic duration.
        kubernetes_ready_seconds = 0.0

    return {
        "demand_to_http_ready_seconds": round(
            (http_ready - demand).total_seconds(), 6
        ),
        "demand_to_kubernetes_ready_seconds": round(kubernetes_ready_seconds, 6),
        "demand_to_two_semantic_seconds": round(
            (semantic_finished - demand).total_seconds(), 6
        ),
        "semantic_request_1_seconds": calls[0],
        "semantic_request_2_seconds": calls[1],
        "timing_evidence": {
            "demand_at": demand_raw,
            "http_ready_at": http_ready_raw,
            "kubernetes_ready_at": kubernetes_ready_raw,
            "semantic_started_at": semantic_started_raw,
            "semantic_finished_at": semantic_finished_raw,
        },
    }
