"""Deterministic contract smoke fixture; never admitted as performance evidence."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    canonical_json,
    canonical_sha256,
    generate_trace,
    synthetic_smoke_ledger,
    write_canonical_json as write_request_slo_json,
    write_ledger,
)

from .matrix import (
    ATTEMPT_SCHEMA,
    PHASES,
    PLAN_SCHEMA,
    TERMINAL_BOUNDARY,
    T0_BOUNDARY,
    _file_sha256,
    write_attempts,
    write_canonical_json,
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_utc(base: str, delta_ns: int) -> str:
    parsed = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    return (parsed + timedelta(microseconds=delta_ns // 1000)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _catalog() -> dict[str, Any]:
    return {
        "schema": "archvteams.nebius.ai/catalog-switch-model-catalog/v1",
        "models": [
            {
                "model_id": "boltz2",
                "model_version": "2.2.1",
                "artifact_id": "boltz2-smoke-artifact",
                "artifact_version": "sha256-boltz2-smoke-v1",
                "artifact_sha256": _digest("boltz2-smoke-artifact-v1"),
                "input": {
                    "workload_id": "boltz2-semantic-smoke",
                    "input_id": "boltz2-smoke-input",
                    "payload_sha256": _digest("boltz2-smoke-input-v1"),
                    "input_bytes": 1024,
                },
            },
            {
                "model_id": "proteinmpnn",
                "model_version": "1.0.0",
                "artifact_id": "proteinmpnn-smoke-artifact",
                "artifact_version": "sha256-proteinmpnn-smoke-v1",
                "artifact_sha256": _digest("proteinmpnn-smoke-artifact-v1"),
                "input": {
                    "workload_id": "proteinmpnn-semantic-smoke",
                    "input_id": "proteinmpnn-smoke-input",
                    "payload_sha256": _digest("proteinmpnn-smoke-input-v1"),
                    "input_bytes": 512,
                },
            },
        ],
    }


def _cells(trace: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = (
        ("attached_block_pvc", "boltz_external_tmp_hit"),
        ("local_nvme", "hot"),
        ("remote_artifact", "corruption"),
        ("attached_block_pvc", "warm"),
        ("attached_block_pvc", "boltz_external_tmp_clone_miss"),
        ("remote_artifact", "cold"),
        ("remote_artifact", "concurrent_fetch"),
        ("remote_artifact", "concurrent_fetch"),
        ("local_nvme", "eviction_repopulation"),
        ("attached_block_pvc", "eviction_repopulation"),
    )
    result = []
    for index, (request, (tier, cohort)) in enumerate(
        zip(trace["requests"], mapping, strict=True)
    ):
        result.append(
            {
                "cell_id": f"synthetic-cell-{index:02d}",
                "model_id": request["target"]["model_id"],
                "tier": tier,
                "cohort": cohort,
                "minimum_attempts": 1,
            }
        )
    return result


def _artifacts() -> list[dict[str, Any]]:
    result = []
    sizes = {"boltz2": 8_388_608, "proteinmpnn": 4_194_304}
    payloads = {"boltz2": "boltz2-payload-v1", "proteinmpnn": "proteinmpnn-payload-v1"}
    for model in _catalog()["models"]:
        model_id = model["model_id"]
        result.append(
            {
                "model_id": model_id,
                "model_version": model["model_version"],
                "artifact_id": model["artifact_id"],
                "artifact_version": model["artifact_version"],
                "sha256": model["artifact_sha256"],
                "bytes": sizes[model_id],
                "payload_id": payloads[model_id],
                "publication_receipt_sha256": _digest(f"publication-{model_id}"),
                "published_before_t0": True,
                "strategy_default": "snapshot",
            }
        )
    return result


def _make_plan(output_dir: Path, trace: dict[str, Any]) -> dict[str, Any]:
    source_root = Path(__file__).resolve().parents[2]
    metric_source = source_root / "performance" / "request_slo" / "harness.py"
    boltz_source = source_root / "boltz2-native" / "external-tmp-contract.json"
    metric_copy = output_dir / "pinned-request-slo-harness.py"
    boltz_copy = output_dir / "pinned-boltz-external-tmp-contract.json"
    shutil.copyfile(metric_source, metric_copy)
    shutil.copyfile(boltz_source, boltz_copy)
    return {
        "schema": PLAN_SCHEMA,
        "plan_id": "storage-cache-matrix-synthetic-smoke",
        "task_id": "catalog-switch-storage-cache-matrix",
        "evidence_classification": "synthetic-smoke-not-performance-evidence",
        "created_at_utc": "2026-08-19T00:00:00.000000Z",
        "purpose": "Exercise every matrix contract branch without publishing performance evidence.",
        "code_revision": "0" * 40,
        "metric_contract": {
            "path": metric_copy.name,
            "sha256": _file_sha256(metric_copy),
            "t0_boundary": T0_BOUNDARY,
            "terminal_boundary": TERMINAL_BOUNDARY,
        },
        "artifacts": _artifacts(),
        "matrix": {
            "cells": _cells(trace),
            "one_variable_per_cohort": True,
            "shared_mutable_state": False,
        },
        "environment_requirements": {
            "allowed_projects": sorted(
                (
                    "project-e00z6b02t8ddk96c49",
                    "project-u00tds8vpr00jaxa76s22d",
                    "project-i00xz31gpr00xp9jhp982v",
                )
            ),
            "resource_prefix": "mlsp-csw-storage-cache-smoke",
            "gpu_required": True,
            "prefer_preemptible": True,
            "local_nvme_requires_verified_entitlement": True,
        },
        "cost_plan": {
            "currency": "USD",
            "expected_duration_hours": 0.01,
            "budget_usd": 0.01,
            "price_source": "synthetic fixture; no cloud resources or spend",
        },
        "cleanup_plan": {
            "owner": "catalog-switch-storage-cache-matrix",
            "ttl_hours": 1,
            "exact_id_only": True,
            "dirty_generation_policy": "delete-and-verify-absent",
        },
        "boltz_external_tmp": {
            "enabled": True,
            "contract_path": boltz_copy.name,
            "contract_sha256": _file_sha256(boltz_copy),
            "required_hit_cohort": "boltz_external_tmp_hit",
            "required_miss_cohort": "boltz_external_tmp_clone_miss",
        },
    }


def _phase_receipts(
    *,
    t0_ns: int,
    t0_utc: str,
    terminal_ns: int,
    success: bool,
    tier: str,
    cohort: str,
    artifact_bytes: int,
) -> list[dict[str, Any]]:
    available = terminal_ns - t0_ns
    step = max(1_000, available // (len(PHASES) + 2))
    phase_receipts: list[dict[str, Any]] = []
    failed_phase = "placement" if not success else None
    for index, name in enumerate(PHASES):
        finish_offset = (index + 1) * step
        outcome = "completed"
        if failed_phase is not None:
            if name == failed_phase:
                outcome = "failed"
            elif PHASES.index(name) > PHASES.index(failed_phase):
                outcome = "skipped"
        elif name in {"image_pull", "image_unpack"} and cohort not in {
            "cold",
            "eviction_repopulation",
        }:
            outcome = "skipped"
        elif name in {"volume_attach", "volume_mount"} and not (
            tier == "attached_block_pvc"
            and cohort in {"boltz_external_tmp_clone_miss", "eviction_repopulation"}
        ):
            outcome = "skipped"
        elif name == "copy" and cohort != "eviction_repopulation":
            outcome = "skipped"
        elif name == "artifact_fetch" and tier != "remote_artifact":
            outcome = "skipped"
        elif name == "clone" and cohort != "boltz_external_tmp_clone_miss":
            outcome = "skipped"
        elif name == "restore" and cohort == "eviction_repopulation":
            outcome = "skipped"
        elif name == "conventional_load" and cohort != "eviction_repopulation":
            outcome = "skipped"
        started_offset = finish_offset - max(1, step // 2)
        bytes_read = 0
        bytes_written = 0
        bytes_network = 0
        if outcome == "completed" and name == "artifact_fetch":
            bytes_read = artifact_bytes
            bytes_written = artifact_bytes
            bytes_network = artifact_bytes
        elif outcome == "completed" and name == "clone":
            bytes_read = artifact_bytes
            bytes_written = artifact_bytes
        elif outcome == "completed" and name == "copy":
            bytes_read = artifact_bytes
            bytes_written = artifact_bytes
        elif outcome == "completed" and name in {"hash", "first_read"}:
            bytes_read = artifact_bytes
        receipt = {
            "name": name,
            "outcome": outcome,
            "started_at_utc": (
                None if outcome == "skipped" else _format_utc(t0_utc, started_offset)
            ),
            "finished_at_utc": _format_utc(t0_utc, finish_offset),
            "started_monotonic_ns": (
                None if outcome == "skipped" else t0_ns + started_offset
            ),
            "finished_monotonic_ns": t0_ns + finish_offset,
            "bytes_read": bytes_read,
            "bytes_written": bytes_written,
            "bytes_network": bytes_network,
            "reason": "deterministic synthetic contract smoke",
            "evidence_sha256": _digest(
                f"{t0_ns}:{name}:{outcome}:{bytes_read}:{bytes_written}:{bytes_network}"
            ),
        }
        phase_receipts.append(receipt)
    return phase_receipts


def _make_attempts(
    *,
    output_dir: Path,
    plan: dict[str, Any],
    trace: dict[str, Any],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    artifact_by_model = {artifact["model_id"]: artifact for artifact in plan["artifacts"]}
    cell_by_index = plan["matrix"]["cells"]
    events_by_attempt: dict[str, list[dict[str, Any]]] = {}
    for request in trace["requests"]:
        events_by_attempt[request["attempt_id"]] = [
            event for event in events if event["attempt_id"] == request["attempt_id"]
        ]
    trace_path = output_dir / "request-slo-trace.json"
    ledger_path = output_dir / "request-slo-ledger.jsonl"
    marker_path = output_dir / "synthetic-supporting-evidence.txt"
    marker_path.write_text(
        "Synthetic storage/cache matrix smoke. Not performance evidence.\n",
        encoding="utf-8",
    )
    plan_sha256 = canonical_sha256(plan)
    attempts = []
    concurrent_ids = {
        request["attempt_id"]
        for request, cell in zip(trace["requests"], cell_by_index, strict=True)
        if cell["cohort"] == "concurrent_fetch"
    }
    for index, (request, cell) in enumerate(
        zip(trace["requests"], cell_by_index, strict=True)
    ):
        model_id = request["target"]["model_id"]
        artifact = artifact_by_model[model_id]
        attempt_events = events_by_attempt[request["attempt_id"]]
        accepted = attempt_events[0]
        terminal_event = next(
            event
            for event in attempt_events
            if event["event_type"] in {"response.validated", "attempt.failed"}
        )
        success = terminal_event["event_type"] == "response.validated"
        cache_state = {
            "hot": "hit",
            "warm": "hit",
            "cold": "miss",
            "eviction_repopulation": "evicted",
            "concurrent_fetch": "miss",
            "corruption": "corrupt",
            "boltz_external_tmp_hit": "hit",
            "boltz_external_tmp_clone_miss": "miss",
        }[cell["cohort"]]
        phases = _phase_receipts(
            t0_ns=accepted["observed_monotonic_ns"],
            t0_utc=accepted["observed_at_utc"],
            terminal_ns=terminal_event["observed_monotonic_ns"],
            success=success,
            tier=cell["tier"],
            cohort=cell["cohort"],
            artifact_bytes=artifact["bytes"],
        )
        totals = {
            "bytes_read_total": sum(phase["bytes_read"] for phase in phases),
            "bytes_written_total": sum(phase["bytes_written"] for phase in phases),
            "bytes_network_total": sum(phase["bytes_network"] for phase in phases),
        }
        dirty = cache_state == "corrupt"
        if cell["cohort"] == "concurrent_fetch":
            peers = sorted(concurrent_ids - {request["attempt_id"]})
            group_id = "synthetic-concurrent-group"
        else:
            peers = []
            group_id = None
        response = terminal_event["data"] if success else None
        attempts.append(
            {
                "schema": ATTEMPT_SCHEMA,
                "plan_id": plan["plan_id"],
                "plan_sha256": plan_sha256,
                "attempt_id": request["attempt_id"],
                "request_id": request["request_id"],
                "cell_id": cell["cell_id"],
                "evidence_classification": plan["evidence_classification"],
                "artifact": {
                    key: artifact[key]
                    for key in (
                        "model_id",
                        "model_version",
                        "artifact_id",
                        "artifact_version",
                        "sha256",
                        "bytes",
                        "payload_id",
                    )
                },
                "tier": cell["tier"],
                "cohort": cell["cohort"],
                "cache": {
                    "state": cache_state,
                    "generation_id": f"synthetic-generation-{index:02d}",
                    "artifact_version": artifact["artifact_version"],
                    "artifact_sha256": artifact["sha256"],
                    "age_seconds": 60.0 if cache_state == "hit" else None,
                    "publication_investment_seconds": 1.0,
                    "node_cache_investment_seconds": 0.5 if cache_state == "hit" else 0.0,
                    "dirty_before_t0": dirty,
                    "cow_first_write_expected": cell["cohort"]
                    == "boltz_external_tmp_clone_miss",
                    "shared_mutable_state": False,
                },
                "concurrency": {
                    "group_id": group_id,
                    "peer_attempt_ids": peers,
                    "mutable_namespace_id": f"synthetic-namespace-{index:02d}",
                    "source_read_only": True,
                },
                "environment": {
                    "provider": "local",
                    "project_id": "local-contract-test",
                    "region": "local",
                    "node_id": None,
                    "gpu_type": None,
                    "gpu_count": 0,
                    "preemptible": False,
                    "image_digest": None,
                    "storage_resource_id": None,
                    "storage_medium": cell["tier"],
                    "filesystem": "syntheticfs",
                    "mount_options": ["synthetic"],
                    "local_nvme_entitlement_verified": False,
                    "local_nvme_devices": [],
                    "code_revision": "0" * 40,
                    "config_sha256": _digest(canonical_json(cell)),
                },
                "ownership": {
                    "owner_task_id": "catalog-switch-storage-cache-matrix",
                    "resource_prefix": "mlsp-csw-storage-cache-smoke",
                    "dedicated": True,
                    "resources": [],
                },
                "request": {
                    "t0_boundary": T0_BOUNDARY,
                    "accepted_at_utc": accepted["observed_at_utc"],
                    "accepted_monotonic_ns": accepted["observed_monotonic_ns"],
                    "input_id": request["input"]["input_id"],
                    "input_sha256": request["input"]["payload_sha256"],
                    "input_bytes": request["input"]["input_bytes"],
                },
                "request_slo_binding": {
                    "trace_path": trace_path.name,
                    "ledger_path": ledger_path.name,
                    "trace_sha256": _file_sha256(trace_path),
                    "ledger_sha256": _file_sha256(ledger_path),
                    "trace_id": trace["trace_id"],
                    "ledger_id": events[0]["ledger_id"],
                    "request_id": request["request_id"],
                    "attempt_id": request["attempt_id"],
                },
                "phases": phases,
                "terminal": {
                    "type": terminal_event["event_type"],
                    "observed_at_utc": terminal_event["observed_at_utc"],
                    "observed_monotonic_ns": terminal_event["observed_monotonic_ns"],
                    "boundary": TERMINAL_BOUNDARY if success else None,
                    "response_sha256": response["response_sha256"] if success else None,
                    "response_bytes": response["response_bytes"] if success else None,
                    "semantic_validator_id": response["validator_id"] if success else None,
                    "semantic_validator_sha256": (
                        response["validator_sha256"] if success else None
                    ),
                    "failure_class": None if success else terminal_event["data"]["failure_class"],
                    "reason": "semantic-pass" if success else terminal_event["data"]["reason"],
                },
                "accounting": {
                    "currency": "USD",
                    "request_cost_usd": 0.0,
                    "publication_cost_usd": 0.0,
                    "node_cache_investment_cost_usd": 0.0,
                    "billed_seconds": 0.0,
                    "gpu_active_seconds": 0.0,
                    "gpu_idle_seconds": 0.0,
                    **totals,
                },
                "cleanup": {
                    "generation_id": f"synthetic-generation-{index:02d}",
                    "final_state": "ABSENT" if dirty else "SEALED_RETAINED",
                    "dirty": dirty,
                    "reusable": not dirty,
                    "verified_absent": dirty,
                    "receipt_sha256": _digest(f"synthetic-cleanup-{index}"),
                    "resources_deleted": [],
                    "resources_retained": [],
                    "verified_at_utc": terminal_event["observed_at_utc"],
                },
                "supporting_evidence": [
                    {
                        "kind": "synthetic-marker",
                        "path": marker_path.name,
                        "sha256": _file_sha256(marker_path),
                    }
                ],
            }
        )
    concurrent = [attempt for attempt in attempts if attempt["cohort"] == "concurrent_fetch"]
    placement_finishes = []
    clone_boundaries = []
    for attempt in concurrent:
        phases_by_name = {phase["name"]: phase for phase in attempt["phases"]}
        placement_finishes.append(phases_by_name["placement"]["finished_monotonic_ns"])
        clone = phases_by_name["clone"]
        clone_boundaries.append(
            clone["started_monotonic_ns"]
            if clone["started_monotonic_ns"] is not None
            else clone["finished_monotonic_ns"]
        )
    common_start = max(placement_finishes) + 1_000
    common_finish = min(clone_boundaries) - 1_000
    if common_finish <= common_start:
        raise RuntimeError("synthetic concurrency fixture has no causal overlap window")
    for attempt in concurrent:
        fetch = next(phase for phase in attempt["phases"] if phase["name"] == "artifact_fetch")
        t0_ns = attempt["request"]["accepted_monotonic_ns"]
        t0_utc = attempt["request"]["accepted_at_utc"]
        fetch["started_monotonic_ns"] = common_start
        fetch["finished_monotonic_ns"] = common_finish
        fetch["started_at_utc"] = _format_utc(t0_utc, common_start - t0_ns)
        fetch["finished_at_utc"] = _format_utc(t0_utc, common_finish - t0_ns)
        fetch["evidence_sha256"] = _digest(
            f"synthetic-concurrent:{common_start}:{common_finish}:{attempt['attempt_id']}"
        )
    return attempts


def build_smoke(output_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trace = generate_trace(
        _catalog(),
        distribution="adversarial",
        seed=2407,
        request_count=10,
        trace_id="storage-cache-matrix-synthetic-trace",
        interval_ms=1000,
    )
    events = synthetic_smoke_ledger(trace)
    write_request_slo_json(output_dir / "request-slo-trace.json", trace)
    write_ledger(output_dir / "request-slo-ledger.jsonl", events)
    plan = _make_plan(output_dir, trace)
    write_canonical_json(output_dir / "plan.json", plan)
    attempts = _make_attempts(output_dir=output_dir, plan=plan, trace=trace, events=events)
    write_attempts(output_dir / "attempts.jsonl", attempts)
    return plan, attempts
