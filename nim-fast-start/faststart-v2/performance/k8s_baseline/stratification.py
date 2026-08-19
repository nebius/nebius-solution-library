#!/usr/bin/env python3
"""Promotion-safe per-cohort aggregation for Kubernetes switch evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    PERCENTILE_ESTIMATOR,
    PERCENTILE_MIN_SAMPLES,
    canonical_json,
    canonical_sha256,
)

from .contract import BaselineError


def _distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(round(float(value), 9) for value in values)
    result: dict[str, Any] = {
        "sample_count": len(ordered),
        "estimator": PERCENTILE_ESTIMATOR,
        "minimum_samples": dict(PERCENTILE_MIN_SAMPLES),
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
    }
    for label, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        result[label] = (
            ordered[math.ceil(percentile * len(ordered)) - 1]
            if len(ordered) >= PERCENTILE_MIN_SAMPLES[label]
            else None
        )
    return result


def _cohort(
    request: dict[str, Any], plan: dict[str, Any] | None, qualification: dict[str, Any] | None
) -> dict[str, Any]:
    target = request["target"]
    model = None
    if plan is not None:
        model = next(
            item
            for item in plan["models"]
            if (item["model_id"], item["model_version"])
            == (target["model_id"], target["model_version"])
        )
    return {
        "model_id": target["model_id"],
        "model_version": target["model_version"],
        "arm": plan["campaign_arm"] if plan else "synthetic",
        "scenario": request["scenario"],
        "strategy": plan["scenario_strategies"][request["scenario"]] if plan else "synthetic",
        "variant": plan["variant"] if plan else "synthetic",
        "cache": request["precondition"]["cache"],
        "gpu_profile": model["gpu_profile"] if model else "synthetic",
    }


def stratify_aggregate(
    raw: dict[str, Any],
    trace: dict[str, Any],
    *,
    plan: dict[str, Any] | None,
    qualification: dict[str, Any] | None,
    classification: str,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Remove mixed headline percentiles and emit complete, promotion-safe strata."""

    requests = {item["attempt_id"]: item for item in trace["requests"]}
    attempts = raw.get("attempts")
    if not isinstance(attempts, dict) or not isinstance(attempts.get("results"), list):
        raise BaselineError("raw aggregate lacks canonical per-attempt results")
    results = attempts["results"]
    results_by_id: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            raise BaselineError("raw aggregate contains a non-object attempt result")
        attempt_id = item.get("attempt_id")
        if (
            not isinstance(attempt_id, str)
            or attempt_id not in requests
            or attempt_id in results_by_id
        ):
            raise BaselineError("raw aggregate has foreign or duplicate attempt identity")
        if not isinstance(item.get("success"), bool):
            raise BaselineError("raw aggregate attempt success must be boolean")
        terminal_seconds = item.get("terminal_seconds")
        if (
            not isinstance(terminal_seconds, (int, float))
            or isinstance(terminal_seconds, bool)
            or not math.isfinite(float(terminal_seconds))
            or float(terminal_seconds) <= 0
        ):
            raise BaselineError("raw aggregate attempt lacks a valid product terminal")
        if item["success"] and item.get("failure_class") is not None:
            raise BaselineError("successful raw attempt has a failure classification")
        if not item["success"] and (
            not isinstance(item.get("failure_class"), str) or not item["failure_class"]
        ):
            raise BaselineError("failed raw attempt lacks a failure classification")
        results_by_id[attempt_id] = item
    if set(requests) != set(results_by_id):
        raise BaselineError("raw aggregate does not retain every offered attempt")
    successful_count = sum(item["success"] for item in results)
    if (
        attempts.get("offered") != len(requests)
        or attempts.get("observed") != len(results)
        or attempts.get("valid_responses") != successful_count
        or attempts.get("failures") != len(results) - successful_count
    ):
        raise BaselineError("raw aggregate attempt counters differ from retained results")
    qualification_rows = (qualification or {}).get("attempts")
    if not isinstance(qualification_rows, list):
        raise BaselineError("two-call qualification evidence lacks per-attempt rows")
    qualified: dict[str, dict[str, Any]] = {}
    expected_qualification_keys = {
        "attempt_id", "qualified", "t0_to_call2_validation_seconds", "failure_reason"
    }
    for row in qualification_rows:
        if not isinstance(row, dict) or set(row) != expected_qualification_keys:
            raise BaselineError("two-call qualification row has a noncanonical shape")
        attempt_id = row["attempt_id"]
        if (
            not isinstance(attempt_id, str)
            or attempt_id not in requests
            or attempt_id in qualified
        ):
            raise BaselineError("two-call qualification has foreign or duplicate attempt identity")
        if not isinstance(row["qualified"], bool):
            raise BaselineError("two-call qualification status must be boolean")
        if row["qualified"]:
            if (
                not results_by_id[attempt_id]["success"]
                or not isinstance(row["t0_to_call2_validation_seconds"], (int, float))
                or isinstance(row["t0_to_call2_validation_seconds"], bool)
                or not math.isfinite(float(row["t0_to_call2_validation_seconds"]))
                or float(row["t0_to_call2_validation_seconds"]) <= 0
                or row["failure_reason"] is not None
            ):
                raise BaselineError(
                    "qualified second semantic call lacks a successful first semantic terminal"
                )
        elif (
            row["t0_to_call2_validation_seconds"] is not None
            or not isinstance(row["failure_reason"], str)
            or not row["failure_reason"]
        ):
            raise BaselineError("failed second semantic call lacks an explicit retained reason")
        qualified[attempt_id] = row
    if set(qualified) != set(requests):
        raise BaselineError("two-call qualification does not retain every offered attempt")
    cleanup_receipts: dict[str, str | None] = {}
    for event in events or []:
        if event.get("event_type") == "cleanup.finished":
            attempt_id = event.get("attempt_id")
            if attempt_id in cleanup_receipts:
                raise BaselineError("cleanup evidence is duplicated for an offered attempt")
            cleanup_receipts[attempt_id] = event.get("data", {}).get("receipt_sha256")
    if plan is not None and set(cleanup_receipts) != set(requests):
        raise BaselineError("promotion evidence lacks exact per-attempt cleanup receipts")
    cleanup_proofs: dict[str, dict[str, Any]] = {}
    for proof_row in (qualification or {}).get("cleanup_receipts", []):
        if not isinstance(proof_row, dict) or set(proof_row) != {"attempt_id", "receipt", "receipt_sha256"}:
            raise BaselineError("backend cleanup receipt proof has a noncanonical shape")
        attempt_id = proof_row["attempt_id"]
        if attempt_id not in requests or attempt_id in cleanup_proofs:
            raise BaselineError("backend cleanup receipt has foreign or duplicate identity")
        if (
            not isinstance(proof_row["receipt"], dict)
            or canonical_sha256(proof_row["receipt"]) != proof_row["receipt_sha256"]
        ):
            raise BaselineError("backend cleanup receipt body differs from its digest")
        if cleanup_receipts.get(attempt_id) != proof_row["receipt_sha256"]:
            raise BaselineError("backend cleanup receipt digest differs from the canonical ledger")
        cleanup_proofs[attempt_id] = proof_row
    if plan is not None and set(cleanup_proofs) != set(requests):
        raise BaselineError("promotion evidence lacks replayable backend cleanup receipts")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: dict[str, dict[str, Any]] = {}
    for item in results:
        cohort = _cohort(requests[item["attempt_id"]], plan, qualification)
        key = hashlib.sha256(canonical_json(cohort).encode()).hexdigest()
        identities[key] = cohort
        groups[key].append(item)
    strata = []
    for key in sorted(groups):
        items = groups[key]
        successes = [item for item in items if item["success"]]
        call2 = [
            qualified[item["attempt_id"]]["t0_to_call2_validation_seconds"]
            for item in items
            if item["attempt_id"] in qualified
            and qualified[item["attempt_id"]].get("qualified") is True
            and qualified[item["attempt_id"]].get("t0_to_call2_validation_seconds") is not None
        ]
        call2_failures = [
            qualified[item["attempt_id"]]["failure_reason"]
            for item in items
            if not qualified[item["attempt_id"]]["qualified"]
        ]
        strata.append(
            {
                "cohort_sha256": key,
                "cohort": identities[key],
                "attempts": {
                    "offered": len(items),
                    "valid_responses": len(successes),
                    "failures": len(items) - len(successes),
                    "failure_classes": {
                        name: sum(item.get("failure_class") == name for item in items)
                        for name in sorted(
                            {item["failure_class"] for item in items if item.get("failure_class")}
                        )
                    },
                    "results": items,
                },
                "request_to_first_semantic_validation_seconds": _distribution(
                    [item["terminal_seconds"] for item in successes]
                ),
                "request_to_second_semantic_validation_seconds": _distribution(call2),
                "two_semantic_qualification": {
                    "offered": len(items),
                    "qualified": len(call2),
                    "failed_or_incomplete": len(items) - len(call2),
                    "failure_reasons": call2_failures,
                },
                "integrity": {
                    "cleanup_admitted": sum(
                        item.get("cleanup_status") in {"complete", "retained"}
                        and item["attempt_id"] in cleanup_proofs
                        for item in items
                    ),
                    "cleanup_failed_or_unreceipted": sum(
                        item.get("cleanup_status") not in {"complete", "retained"}
                        or item["attempt_id"] not in cleanup_proofs
                        for item in items
                    ),
                    "accounting_failure_sentinel_count": sum(
                        float(item.get("cost_usd", 0)) >= 1_000_000_000.0 for item in items
                    ),
                },
            }
        )
    return {
        "schema": "archvteams.nebius.ai/catalog-switch-k8s-stratified-aggregate/v2",
        "evidence_classification": classification,
        "trace_id": raw["trace_id"],
        "trace_sha256": raw["trace_sha256"],
        "ledger_sha256": raw["ledger_sha256"],
        "boundary": raw["boundary"],
        "two_call_qualification_sha256": canonical_sha256(qualification),
        "raw_global_bookkeeping": {
            "offered": raw["attempts"]["offered"],
            "observed": raw["attempts"]["observed"],
            "valid_responses": raw["attempts"]["valid_responses"],
            "failures": raw["attempts"]["failures"],
            "failure_rate": raw["attempts"]["failure_rate"],
            "failure_classes": raw["attempts"]["failure_classes"],
            "cost_usd_total": sum(float(item["cost_usd"]) for item in results),
            "bytes_moved_total": sum(int(item["bytes_moved_total"]) for item in results),
            "gpu_active_seconds_total": round(sum(float(item["gpu_active_seconds"]) for item in results), 9),
            "gpu_idle_seconds_total": round(sum(float(item["gpu_idle_seconds"]) for item in results), 9),
        },
        "promotion": {
            "mixed_cohort_count": len(strata),
            "mixed_headline_percentile": None,
            "mixed_promotion_allowed": False,
            "rule": "promotion is evaluated only within one exact NIM/arm/scenario/strategy/variant/cache/GPU-profile stratum",
            "minimum_offered_and_qualified": (
                plan["minimum_repetitions"] if plan is not None else None
            ),
        },
        "strata": strata,
    }


def _validate_promotion_cohort(cohort: dict[str, Any], minimum: int) -> None:
    attempts = cohort.get("attempts", {})
    results = attempts.get("results")
    offered = attempts.get("offered")
    if (
        not isinstance(results, list)
        or not isinstance(offered, int)
        or isinstance(offered, bool)
        or len(results) != offered
    ):
        raise BaselineError("promotion requires exact retained raw attempt results")
    successes = [
        item
        for item in results
        if isinstance(item, dict) and item.get("success") is True
    ]
    attempt_ids = [item.get("attempt_id") for item in results if isinstance(item, dict)]
    if (
        any(
            not isinstance(item, dict)
            or not isinstance(item.get("success"), bool)
            or not isinstance(item.get("terminal_seconds"), (int, float))
            or isinstance(item.get("terminal_seconds"), bool)
            or not math.isfinite(float(item["terminal_seconds"]))
            or float(item["terminal_seconds"]) <= 0
            or (item["success"] and item.get("failure_class") is not None)
            or (
                not item["success"]
                and (not isinstance(item.get("failure_class"), str) or not item["failure_class"])
            )
            for item in results
        )
        or any(not isinstance(attempt_id, str) or not attempt_id for attempt_id in attempt_ids)
        or len(attempt_ids) != len(set(attempt_ids))
        or attempts.get("valid_responses") != len(successes)
        or attempts.get("failures") != offered - len(successes)
        or cohort.get("request_to_first_semantic_validation_seconds")
        != _distribution([item["terminal_seconds"] for item in successes])
    ):
        raise BaselineError(
            "promotion requires coherent first-semantic results, counters, and distribution"
        )
    qualification = cohort.get("two_semantic_qualification", {})
    if (
        offered < minimum
        or len(successes) < minimum
        or qualification.get("offered") != offered
        or qualification.get("qualified", 0) > len(successes)
        or qualification.get("qualified", 0) < minimum
    ):
        raise BaselineError(
            "promotion requires the frozen minimum first- and two-semantically-qualified attempts"
        )
    integrity = cohort.get("integrity", {})
    if (
        integrity.get("cleanup_admitted") != offered
        or integrity.get("cleanup_failed_or_unreceipted") != 0
        or integrity.get("accounting_failure_sentinel_count") != 0
    ):
        raise BaselineError("promotion requires complete receipted per-attempt cleanup and accounting")


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _is_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_provider_evidence(receipt: dict[str, Any], label: str) -> None:
    """Recompute one immutable provider evidence file instead of trusting a claim."""

    path_value = receipt.get("evidence_path")
    digest = receipt.get("evidence_sha256")
    if not isinstance(path_value, str) or not path_value or not _is_digest(digest):
        raise BaselineError(f"{label} lacks source-bound provider evidence")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise BaselineError(f"{label} provider evidence is unsafe or absent")
    try:
        source = path.read_bytes()
        value = json.loads(source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"{label} provider evidence cannot be read") from exc
    expected = {
        key: value for key, value in receipt.items()
        if key not in {"evidence_path", "evidence_sha256"}
    }
    if hashlib.sha256(source).hexdigest() != digest or value != expected:
        raise BaselineError(f"{label} provider evidence differs from its exact receipt")


def _validate_final_audit_extension(
    value: dict[str, Any], expected_lease: dict[str, Any], receipt_hashes: dict[str, str]
) -> None:
    """Require broker cleanup events to extend the admitted immutable audit head."""

    audit = value.get("audit_extension_receipt", {})
    expected_audit = expected_lease.get("audit_chain", {})
    if not isinstance(audit, dict):
        raise BaselineError("broker RELEASED receipt lacks a final audit extension")
    events_path_value = audit.get("events_path")
    if not isinstance(events_path_value, str):
        raise BaselineError("broker final audit event path is absent")
    events_path = Path(events_path_value)
    if not events_path.is_absolute() or events_path.is_symlink() or not events_path.is_file():
        raise BaselineError("broker final audit event file is unsafe or absent")
    try:
        source = events_path.read_bytes()
        events = json.loads(source)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError("broker final audit event file cannot be read") from exc
    expected_operations = [
        "lease.gpu_zero", "lease.credential_revoked", "lease.provider_children_absent",
        "lease.resources_absent", "lease.cost_finalized",
    ]
    if (
        audit.get("schema") != "archvteams.nebius.ai/broker-final-audit-extension/v1"
        or audit.get("lease_id") != expected_lease.get("lease_id")
        or audit.get("chain_id") != expected_audit.get("chain_id")
        or audit.get("previous_head_sha256") != expected_audit.get("head_sha256")
        or audit.get("first_sequence") != expected_audit.get("event_count")
        or audit.get("event_count") != len(expected_operations)
        or hashlib.sha256(source).hexdigest() != audit.get("events_sha256")
        or value.get("audit_extension_receipt_sha256") != _sha256(audit)
        or not isinstance(events, list)
        or len(events) != len(expected_operations)
    ):
        raise BaselineError("broker final audit extension is not bound to the admitted lease")
    previous = expected_audit.get("head_sha256")
    receipt_names = [
        "gpu_zero_receipt_sha256", "credential_revocation_receipt_sha256",
        "provider_children_receipt_sha256", "exact_absence_receipt_sha256",
        "actual_cost_receipt_sha256",
    ]
    for offset, (operation, receipt_name, event) in enumerate(
        zip(expected_operations, receipt_names, events, strict=True)
    ):
        expected_payload = {
            "operation": operation,
            "lease_id": expected_lease["lease_id"],
            "receipt_sha256": receipt_hashes[receipt_name],
        }
        if not isinstance(event, dict):
            raise BaselineError("broker final audit event is not an object")
        core = {
            "sequence": expected_audit["event_count"] + offset,
            "previous_sha256": previous,
            "payload": expected_payload,
        }
        event_sha = _sha256(core)
        if event != {**core, "event_sha256": event_sha}:
            raise BaselineError("broker final audit event chain or payload is forged")
        previous = event_sha
    if audit.get("head_sha256") != previous:
        raise BaselineError("broker final audit head differs from recomputed cleanup events")


def validate_broker_release(
    final_cleanup: dict[str, Any] | None,
    *,
    expected_lease: dict[str, Any] | None = None,
    expected_aggregate: dict[str, Any] | None = None,
) -> None:
    """Require the typed actual-cost, absence, and GPU-zero broker release receipt."""

    value = final_cleanup or {}
    gpu_zero = value.get("gpu_zero_receipt", {})
    absence = value.get("exact_absence_receipt", {})
    provider_children = value.get("provider_children_receipt", {})
    credential_revocation = value.get("credential_revocation_receipt", {})
    actual_cost = value.get("actual_cost_receipt", {})
    lease_id = value.get("lease_id")
    expected_ids = (
        sorted(item["id"] for item in expected_lease.get("resources", []))
        if expected_lease is not None
        else absence.get("resource_ids")
    )
    expected_node_ids = (
        sorted(
            item["id"] for item in expected_lease.get("resources", [])
            if item.get("kind") == "node"
        )
        if expected_lease is not None
        else [gpu_zero.get("node_id")]
    )
    discovered_children = provider_children.get("discovered_child_ids")
    not_found_children = provider_children.get("not_found_child_ids")
    bookkeeping = (expected_aggregate or {}).get("raw_global_bookkeeping", {})
    minimum_billed = float(bookkeeping.get("gpu_active_seconds_total", 0)) + float(
        bookkeeping.get("gpu_idle_seconds_total", 0)
    )
    minimum_transfer = int(bookkeeping.get("bytes_moved_total", 0))
    expected_cost = (expected_lease or {}).get("cost_estimate", {})
    expected_credential = (expected_lease or {}).get("credential", {})
    hard_cap = expected_cost.get("hard_cap_usd")
    try:
        minimum_cost = (
            float(expected_cost["pre_t0_setup_cost_usd"])
            + float(expected_cost["lease_hour_usd"])
            * float(actual_cost["billed_seconds"]) / 3600
            + float(expected_cost["transfer_usd_per_gib"])
            * int(actual_cost["transfer_bytes"]) / (1024**3)
        )
    except (KeyError, TypeError, ValueError):
        minimum_cost = math.inf if expected_lease is not None else 0.0
    try:
        gpu_observed = datetime.fromisoformat(
            str(gpu_zero.get("observed_at_utc", "")).removesuffix("Z") + "+00:00"
        )
        absent_observed = datetime.fromisoformat(
            str(absence.get("observed_at_utc", "")).removesuffix("Z") + "+00:00"
        )
        provider_observed = datetime.fromisoformat(
            str(provider_children.get("observed_at_utc", "")).removesuffix("Z") + "+00:00"
        )
        revoked_at = datetime.fromisoformat(
            str(credential_revocation.get("revoked_at_utc", "")).removesuffix("Z")
            + "+00:00"
        )
        revoke_by = datetime.fromisoformat(
            str(expected_credential.get("revoke_by_utc", "")).removesuffix("Z")
            + "+00:00"
        ) if expected_lease is not None else datetime.max.replace(tzinfo=UTC)
    except ValueError:
        gpu_observed = absent_observed = provider_observed = revoked_at = revoke_by = (
            datetime.max.replace(tzinfo=UTC)
        )
    if (
        final_cleanup is None
        or value.get("schema") != "archvteams.nebius.ai/k8s-broker-final-cleanup/v2"
        or value.get("status") != "PASS"
        or value.get("lease_state") != "RELEASED"
        or value.get("lease_cleanup_required") is not False
        or value.get("final_resource_state") != "ABSENT"
        or not isinstance(lease_id, str)
        or (expected_lease is not None and lease_id != expected_lease.get("lease_id"))
        or absence.get("schema") != "archvteams.nebius.ai/exact-resource-absence/v1"
        or absence.get("lease_id") != lease_id
        or absence.get("status") != "ALL_NOT_FOUND"
        or absence.get("resource_ids") != expected_ids
        or not isinstance(absence.get("observed_at_utc"), str)
        or not _is_digest(absence.get("evidence_sha256"))
        or value.get("exact_absence_receipt_sha256") != _sha256(absence)
        or actual_cost.get("schema") != "archvteams.nebius.ai/broker-actual-cost/v1"
        or actual_cost.get("lease_id") != lease_id
        or actual_cost.get("status") != "FINAL"
        or actual_cost.get("currency") != "USD"
        or not isinstance(actual_cost.get("actual_cost_usd"), (int, float))
        or isinstance(actual_cost.get("actual_cost_usd"), bool)
        or float(actual_cost.get("actual_cost_usd", -1)) < 0
        or not isinstance(actual_cost.get("billed_seconds"), (int, float))
        or float(actual_cost.get("billed_seconds", -1)) < 0
        or not isinstance(actual_cost.get("transfer_bytes"), int)
        or actual_cost.get("transfer_bytes", -1) < 0
        or not _is_digest(actual_cost.get("evidence_sha256"))
        or value.get("actual_cost_receipt_sha256") != _sha256(actual_cost)
        or provider_children.get("schema")
        != "archvteams.nebius.ai/provider-child-absence/v1"
        or provider_children.get("lease_id") != lease_id
        or provider_children.get("status") != "ALL_NOT_FOUND"
        or provider_children.get("discovery_complete") is not True
        or not isinstance(discovered_children, list)
        or discovered_children != sorted(set(discovered_children))
        or not_found_children != discovered_children
        or provider_children.get("remaining_child_ids") != []
        or not _is_digest(provider_children.get("evidence_sha256"))
        or value.get("provider_children_receipt_sha256") != _sha256(provider_children)
        or credential_revocation.get("schema")
        != "archvteams.nebius.ai/credential-revocation/v1"
        or credential_revocation.get("lease_id") != lease_id
        or credential_revocation.get("status") != "REVOKED"
        or credential_revocation.get("secret_not_found") is not True
        or credential_revocation.get("external_token_status") != "REVOKED"
        or not isinstance(credential_revocation.get("revoked_at_utc"), str)
        or not _is_digest(credential_revocation.get("evidence_sha256"))
        or value.get("credential_revocation_receipt_sha256")
        != _sha256(credential_revocation)
        or (
            expected_lease is not None
            and any(
                credential_revocation.get(receipt_key) != expected_credential.get(expected_key)
                for receipt_key, expected_key in (
                    ("secret_uid", "secret_uid"),
                    ("scope_sha256", "scope_sha256"),
                    ("original_receipt_sha256", "receipt_sha256"),
                )
            )
        )
        or (
            expected_lease is not None
            and (
                provider_children.get("project_id") != expected_lease.get("project_id")
                or provider_children.get("region") != expected_lease.get("region")
            )
        )
        or not isinstance(gpu_zero, dict)
        or gpu_zero.get("schema") != "archvteams.nebius.ai/final-gpu-zero/v1"
        or gpu_zero.get("lease_id") != lease_id
        or gpu_zero.get("status") != "PASS"
        or gpu_zero.get("compute_process_count") != 0
        or gpu_zero.get("observed_memory_bytes") != gpu_zero.get("baseline_memory_bytes")
        or not isinstance(gpu_zero.get("node_id"), str)
        or expected_node_ids != [gpu_zero.get("node_id")]
        or not isinstance(gpu_zero.get("observed_at_utc"), str)
        or not _is_digest(gpu_zero.get("evidence_sha256"))
        or value.get("gpu_zero_receipt_sha256") != _sha256(gpu_zero)
        or gpu_observed >= absent_observed
        or provider_observed > absent_observed
        or revoked_at > absent_observed
        or (expected_lease is not None and revoked_at > revoke_by)
        or actual_cost.get("billed_seconds", -1) < minimum_billed
        or actual_cost.get("transfer_bytes", -1) < minimum_transfer
        or (
            expected_lease is not None
            and (
                actual_cost.get("request_sha256") != expected_lease.get("request_sha256")
                or actual_cost.get("rate_contract_sha256") != _sha256(expected_cost)
                or actual_cost.get("hard_cost_cap_usd") != hard_cap
                or not isinstance(hard_cap, (int, float))
                or float(actual_cost.get("actual_cost_usd", math.inf)) > float(hard_cap)
                or float(actual_cost.get("actual_cost_usd", -1)) + 0.01 < minimum_cost
            )
        )
    ):
        raise BaselineError(
            "promotion requires broker RELEASED and exact absence/cost/GPU-zero receipts"
        )
    for label, receipt in (
        ("exact resource absence", absence),
        ("actual cost", actual_cost),
        ("provider child absence", provider_children),
        ("credential revocation", credential_revocation),
        ("GPU zero", gpu_zero),
    ):
        _validate_provider_evidence(receipt, label)
    if expected_lease is not None:
        _validate_final_audit_extension(
            value,
            expected_lease,
            {
                name: value[name]
                for name in (
                    "gpu_zero_receipt_sha256", "credential_revocation_receipt_sha256",
                    "provider_children_receipt_sha256", "exact_absence_receipt_sha256",
                    "actual_cost_receipt_sha256",
                )
            },
        )


def validate_promotion_cohorts(
    aggregate: dict[str, Any],
    *,
    final_cleanup: dict[str, Any] | None = None,
    expected_lease: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run every content gate before a final receipt may claim promotion."""

    cohorts = aggregate.get("strata", [])
    if not isinstance(cohorts, list) or not cohorts:
        raise BaselineError("promotion aggregate has no exact cohorts")
    minimum = aggregate.get("promotion", {}).get("minimum_offered_and_qualified")
    if not isinstance(minimum, int) or minimum < 30:
        raise BaselineError("promotion aggregate lacks the frozen minimum repetition gate")
    for cohort in cohorts:
        _validate_promotion_cohort(cohort, minimum)
    validate_broker_release(
        final_cleanup, expected_lease=expected_lease, expected_aggregate=aggregate
    )
    return cohorts


def require_promotion_cohorts(
    aggregate: dict[str, Any],
    *,
    final_cleanup: dict[str, Any] | None = None,
    expected_lease: dict[str, Any] | None = None,
    seal_verified: bool = False,
) -> list[dict[str, Any]]:
    """Promote every exact stratum independently; never pool a mixed headline."""

    cohorts = validate_promotion_cohorts(
        aggregate, final_cleanup=final_cleanup, expected_lease=expected_lease
    )
    if not seal_verified:
        raise BaselineError("promotion requires a verified joint seal")
    return cohorts


def require_single_promotion_cohort(
    aggregate: dict[str, Any],
    *,
    final_cleanup: dict[str, Any] | None = None,
    expected_lease: dict[str, Any] | None = None,
    seal_verified: bool = False,
) -> dict[str, Any]:
    """Compatibility gate for callers intentionally freezing a one-stratum run."""

    if len(aggregate.get("strata", [])) != 1:
        raise BaselineError("single-cohort promotion received a mixed aggregate")
    cohort = require_promotion_cohorts(
        aggregate, final_cleanup=final_cleanup, expected_lease=expected_lease,
        seal_verified=seal_verified
    )[0]
    return cohort
