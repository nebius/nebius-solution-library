#!/usr/bin/env python3
"""Executable v2 storage receipt gate bound to one complete request-SLO ledger."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from performance.request_slo.harness import (
    HarnessError,
    canonical_json,
    canonical_sha256,
    load_ledger,
    load_trace,
    validate_ledger,
)
from performance.storage_cache_matrix.catalog_boundary_analysis.analysis import (
    ACCOUNTING_KEYS,
    ACTIVE_MODEL_KEYS,
    ATTEMPT_KEYS,
    ATTEMPT_SCHEMA,
    BINDING_KEYS,
    BOUND_RESOURCE_KEYS,
    CACHE_STATES,
    CLEANUP_EVIDENCE_KEYS,
    CLEANUP_KEYS,
    CLOCK_KEYS,
    CONCURRENCY_KEYS,
    DEMAND_LABELS,
    EVIDENCE_CLASSES,
    EVIDENCE_KEYS,
    EVIDENCE_SCHEMA,
    GENERATION_KEYS,
    INVESTMENT_KEYS,
    OPERATION_EVIDENCE_KEYS,
    OPERATION_KEYS,
    OPERATIONS,
    OUTCOMES,
    OWNERSHIP_BINDING_KEYS,
    OWNERSHIP_RECEIPT_KEYS,
    OWNERSHIP_SCHEMA,
    REQUEST_KEYS,
    START_KEYS,
    T0_BOUNDARY,
    TARGET_KEYS,
    TERMINAL_KEYS,
    TYPED_EVIDENCE_KEYS,
    AnalysisError,
    _expect_keys,
    _file_sha256,
    _identifier,
    _integer,
    _number,
    _safe_path,
    _sha256,
    validate_source_manifest,
)


RESOURCE_KINDS = {
    "broker_lease",
    "node",
    "pvc",
    "pv",
    "provider_volume",
    "node_seed",
    "object_store_object",
}
WRITABLE_KINDS = {"pvc", "pv", "provider_volume"}
LOCALIZATION_OPERATIONS = {"artifact_fetch", "clone", "materialization", "hash"}
SECONDS_PER_BILLING_MONTH = 30 * 24 * 60 * 60


def _canonical_json_file(root: Path, relative: str, digest: str, label: str) -> dict[str, Any]:
    path = _safe_path(root, relative, label)
    if _file_sha256(path) != _sha256(digest, f"{label} digest"):
        raise AnalysisError(f"{label} digest differs")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"{label} is not JSON") from exc
    if not isinstance(value, dict) or text != canonical_json(value) + "\n":
        raise AnalysisError(f"{label} is not canonical newline-terminated JSON")
    return value


def _validate_clock(value: Any, label: str) -> dict[str, Any]:
    clock = _expect_keys(value, CLOCK_KEYS, label)
    for key in ("recorder_id", "clock_id", "boot_id", "utc_sync_source"):
        _identifier(clock[key], f"{label}.{key}")
    _number(clock["max_error_ms"], f"{label}.max_error_ms")
    if clock["timestamp_source"] != "external-request-slo-recorder-monotonic/v1":
        raise AnalysisError(f"{label} is not sourced from the external recorder")
    return clock


def _recorder_from_clock(clock: dict[str, Any]) -> dict[str, Any]:
    return {key: clock[key] for key in clock if key != "timestamp_source"}


def _validate_target(value: Any) -> dict[str, Any]:
    target = _expect_keys(value, TARGET_KEYS, "target")
    for key in ("model_id", "model_version", "artifact_id", "artifact_version"):
        _identifier(target[key], f"target.{key}")
    _sha256(target["artifact_sha256"], "target.artifact_sha256")
    _integer(target["artifact_bytes"], "target.artifact_bytes", 1)
    return target


def _validate_start(value: Any, target: dict[str, Any]) -> dict[str, Any]:
    start = _expect_keys(value, START_KEYS, "starting_state")
    flags = (
        start["target_materialized"],
        start["immutable_node_local_seed_present"],
        start["remote_artifact_required"],
    )
    if any(not isinstance(item, bool) for item in flags) or sum(flags) != 1:
        raise AnalysisError("starting-state sources are not mutually exclusive")
    expected = {
        (True, False, False): "materialized_generation",
        (False, True, False): "immutable_node_local_seed",
        (False, False, True): "immutable_remote_artifact",
    }[flags]
    if start["target_source"] != expected:
        raise AnalysisError("starting-state source label differs from its flags")
    active = start["active_model"]
    if active is not None:
        active = _expect_keys(active, ACTIVE_MODEL_KEYS, "starting_state.active_model")
        _identifier(active["model_id"], "active model id")
        _identifier(active["model_version"], "active model version")
        if active == {
            "model_id": target["model_id"],
            "model_version": target["model_version"],
        } and not start["target_materialized"]:
            raise AnalysisError("active target contradicts absent target materialization")
    return start


def _validate_request(value: Any) -> dict[str, Any]:
    request = _expect_keys(value, REQUEST_KEYS, "request")
    if request["t0_boundary"] != T0_BOUNDARY:
        raise AnalysisError("attempt does not use external acceptance as T0")
    if not isinstance(request["accepted_at_utc"], str):
        raise AnalysisError("request accepted UTC must be a string")
    _integer(request["accepted_monotonic_ns"], "request accepted monotonic", 1)
    _identifier(request["input_id"], "request input id")
    _sha256(request["input_sha256"], "request input digest")
    _integer(request["input_bytes"], "request input bytes", 1)
    return request


def _validate_binding(value: Any, attempt_id: str, request_id: str) -> dict[str, Any]:
    binding = _expect_keys(value, BINDING_KEYS, "request-SLO binding")
    if binding["attempt_id"] != attempt_id or binding["request_id"] != request_id:
        raise AnalysisError("request-SLO binding identity differs from receipt")
    for key in ("trace_sha256", "ledger_sha256"):
        _sha256(binding[key], f"request-SLO binding {key}")
    for key in ("trace_id", "ledger_id"):
        _identifier(binding[key], f"request-SLO binding {key}")
    return binding


def _validate_investment_shape(value: Any) -> dict[str, Any]:
    item = _expect_keys(value, INVESTMENT_KEYS, "pre-T0 investment")
    _integer(item["source_available_monotonic_ns"], "source available clock", 1)
    _number(item["source_age_seconds"], "source age")
    if item["residency_medium"] not in {"network_ssd", "object_storage"}:
        raise AnalysisError("residency medium is not canonical")
    _integer(item["residency_bytes"], "residency bytes", 1)
    _number(item["residency_rate_usd_per_gib_month"], "residency rate")
    _number(item["residency_cost_usd"], "residency cost")
    _integer(item["prehydration_bytes"], "prehydration bytes", 1)
    if item["prehydration_cost_usd"] is not None:
        raise AnalysisError("offline contract cannot invent prehydration cost")
    if item["prehydration_cost_status"] != "not-measured-no-live-receipt":
        raise AnalysisError("prehydration cost status overclaims evidence")
    if not isinstance(item["price_source_commit"], str):
        raise AnalysisError("price source commit must be a string")
    if item["included_in_request_totals"] is not False:
        raise AnalysisError("pre-T0 investment is included in request totals")
    return item


def _validate_operation_shape(value: Any, name: str) -> dict[str, Any]:
    operation = _expect_keys(value, OPERATION_KEYS, f"operation {name}")
    if operation["name"] != name or operation["outcome"] not in OUTCOMES:
        raise AnalysisError("operation identity or outcome is invalid")
    byte_keys = (
        "logical_bytes",
        "bytes_read",
        "bytes_written",
        "bytes_network",
        "bytes_deleted",
        "slo_bytes_moved",
    )
    for key in byte_keys:
        _integer(operation[key], f"operation {name}.{key}")
    if operation["logical_bytes"] < max(
        operation["bytes_read"],
        operation["bytes_written"],
        operation["bytes_network"],
        operation["bytes_deleted"],
        operation["slo_bytes_moved"],
    ):
        raise AnalysisError(f"operation {name} logical bytes undercount physical/SLO bytes")
    if not isinstance(operation["reason"], str) or not operation["reason"]:
        raise AnalysisError(f"operation {name} lacks a reason")
    start = operation["started_monotonic_ns"]
    finish = operation["finished_monotonic_ns"]
    evidence_ref = operation["evidence_ref"]
    if operation["outcome"] == "skipped":
        if start is not None or finish is not None or evidence_ref is not None or any(
            operation[key] for key in byte_keys
        ):
            raise AnalysisError(f"skipped operation {name} claims work or evidence")
    else:
        _integer(start, f"operation {name} start", 1)
        _integer(finish, f"operation {name} finish", 1)
        if finish <= start:
            raise AnalysisError(f"operation {name} duration is not positive")
        _identifier(evidence_ref, f"operation {name} evidence ref")
    return operation


def _validate_operations(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(OPERATIONS):
        raise AnalysisError("operations must contain every canonical operation")
    by_name: dict[str, dict[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, dict) or raw.get("name") not in OPERATIONS:
            raise AnalysisError("operation name is unknown")
        name = raw["name"]
        if name in by_name:
            raise AnalysisError("operation name is duplicated")
        by_name[name] = _validate_operation_shape(raw, name)
    return by_name


def _validate_accounting(value: Any, operations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    accounting = _expect_keys(value, ACCOUNTING_KEYS, "accounting")
    totals = {
        "bytes_read_total": sum(item["bytes_read"] for item in operations.values()),
        "bytes_written_total": sum(item["bytes_written"] for item in operations.values()),
        "bytes_network_total": sum(item["bytes_network"] for item in operations.values()),
        "bytes_deleted_total": sum(item["bytes_deleted"] for item in operations.values()),
        "operation_slo_bytes_moved_total": sum(
            item["slo_bytes_moved"] for item in operations.values()
        ),
    }
    for key, expected in totals.items():
        if _integer(accounting[key], f"accounting.{key}") != expected:
            raise AnalysisError("operation byte accounting omits or double-counts work")
    physical = sum(totals[key] for key in totals if key != "operation_slo_bytes_moved_total")
    if accounting["physical_bytes_total"] != physical:
        raise AnalysisError("physical byte total differs from read/write/network/deleted counters")
    if accounting["request_slo_bytes_moved_total"] != totals[
        "operation_slo_bytes_moved_total"
    ]:
        raise AnalysisError("physical operations are not reconciled to request-SLO bytes")
    _number(accounting["request_slo_cost_usd"], "request-SLO cost")
    return accounting


def _validate_concurrency(value: Any, attempt_id: str) -> dict[str, Any]:
    concurrency = _expect_keys(value, CONCURRENCY_KEYS, "concurrency")
    if concurrency["group_id"] is not None:
        _identifier(concurrency["group_id"], "concurrency group")
    peers = concurrency["peer_attempt_ids"]
    if not isinstance(peers, list) or len(peers) != len(set(peers)):
        raise AnalysisError("concurrency peers must be unique")
    for peer in peers:
        _identifier(peer, "concurrency peer")
        if peer == attempt_id:
            raise AnalysisError("attempt lists itself as a peer")
    _identifier(concurrency["mutable_namespace_id"], "mutable namespace")
    if concurrency["source_read_only"] is not True:
        raise AnalysisError("concurrent source is not immutable/read-only")
    if (concurrency["group_id"] is None) != (not peers):
        raise AnalysisError("concurrency group and peers are inconsistent")
    return concurrency


def _validate_terminal(value: Any) -> dict[str, Any]:
    terminal = _expect_keys(value, TERMINAL_KEYS, "terminal")
    if not isinstance(terminal["success"], bool):
        raise AnalysisError("terminal success must be boolean")
    if terminal["success"]:
        if terminal["failure_class"] is not None:
            raise AnalysisError("successful terminal has a failure class")
    else:
        _identifier(terminal["failure_class"], "terminal failure class")
    _integer(terminal["observed_monotonic_ns"], "terminal clock", 1)
    return terminal


def _validate_cleanup_shape(value: Any) -> dict[str, Any]:
    cleanup = _expect_keys(value, CLEANUP_KEYS, "cleanup")
    for key in ("generation_id", "generation_uid", "writable_resource_uid"):
        _identifier(cleanup[key], f"cleanup.{key}")
    if cleanup["final_state"] not in {"ABSENT", "SEALED_RETAINED"}:
        raise AnalysisError("cleanup final state is invalid")
    for key in ("dirty", "reusable", "verified_absent"):
        if not isinstance(cleanup[key], bool):
            raise AnalysisError(f"cleanup.{key} must be boolean")
    _identifier(cleanup["evidence_ref"], "cleanup evidence ref")
    if cleanup["dirty"] and (
        cleanup["final_state"] != "ABSENT"
        or not cleanup["verified_absent"]
        or cleanup["reusable"]
    ):
        raise AnalysisError("dirty generation was not deleted and proved absent")
    if cleanup["final_state"] == "ABSENT" and not cleanup["verified_absent"]:
        raise AnalysisError("ABSENT generation lacks absence proof")
    if cleanup["final_state"] == "SEALED_RETAINED" and (
        cleanup["dirty"] or not cleanup["reusable"] or cleanup["verified_absent"]
    ):
        raise AnalysisError("retained generation is not sealed and reusable")
    return cleanup


def _validate_ownership_receipt(
    value: Any,
    attempt: dict[str, Any],
    clock: dict[str, Any],
) -> dict[str, Any]:
    receipt = _expect_keys(value, OWNERSHIP_RECEIPT_KEYS, "ownership receipt")
    if receipt["schema"] != OWNERSHIP_SCHEMA:
        raise AnalysisError("ownership receipt schema is unsupported")
    if receipt["receipt_id"] != attempt["ownership_binding"]["receipt_id"]:
        raise AnalysisError("ownership receipt identity differs from binding")
    if receipt["attempt_id"] != attempt["attempt_id"]:
        raise AnalysisError("ownership receipt attempt differs")
    _identifier(receipt["owner_task_id"], "ownership receipt owner")
    if _validate_clock(receipt["clock_binding"], "ownership receipt clock") != clock:
        raise AnalysisError("ownership receipt clock differs from external recorder")
    if receipt["selected_node_id"] is not None:
        _identifier(receipt["selected_node_id"], "ownership selected node")
    if _validate_target(receipt["target"]) != attempt["target"]:
        raise AnalysisError("ownership receipt target differs from attempt")
    _integer(receipt["source_available_monotonic_ns"], "source available clock", 1)
    _identifier(receipt["source_resource_uid"], "source resource UID")

    resources = receipt["resources"]
    if not isinstance(resources, list) or len(resources) != len(RESOURCE_KINDS):
        raise AnalysisError("ownership receipt resource inventory is incomplete")
    by_kind: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    uids: set[str] = set()
    for index, raw in enumerate(resources):
        resource = _expect_keys(raw, BOUND_RESOURCE_KEYS, f"ownership resource {index}")
        kind = resource["kind"]
        if kind not in RESOURCE_KINDS or kind in by_kind:
            raise AnalysisError("ownership resource kind is unknown or duplicated")
        for key in ("id", "uid", "project_id", "region", "role"):
            _identifier(resource[key], f"ownership resource {index}.{key}")
        if resource["id"] in ids or resource["uid"] in uids:
            raise AnalysisError("ownership resource ID/UID is duplicated")
        ids.add(resource["id"])
        uids.add(resource["uid"])
        if resource["artifact_version"] is None:
            if resource["artifact_sha256"] is not None or resource["artifact_bytes"] is not None:
                raise AnalysisError("non-artifact resource has partial artifact identity")
        else:
            _identifier(resource["artifact_version"], "resource artifact version")
            _sha256(resource["artifact_sha256"], "resource artifact digest")
            _integer(resource["artifact_bytes"], "resource artifact bytes", 1)
        by_kind[kind] = resource
    if set(by_kind) != RESOURCE_KINDS:
        raise AnalysisError("ownership receipt omits required resource kinds")
    if receipt["selected_node_id"] != by_kind["node"]["id"]:
        raise AnalysisError("selected node is not the owned node identity")
    source = next(
        (resource for resource in resources if resource["uid"] == receipt["source_resource_uid"]),
        None,
    )
    if source is None or source["role"] != "immutable_source":
        raise AnalysisError("source resource UID is absent or mutable")
    target = attempt["target"]
    if (
        source["artifact_version"] != target["artifact_version"]
        or source["artifact_sha256"] != target["artifact_sha256"]
        or source["artifact_bytes"] != target["artifact_bytes"]
    ):
        raise AnalysisError("artifact size/version/digest is not anchored to source resource")
    expected_source_kind = (
        "object_store_object"
        if attempt["starting_state"]["remote_artifact_required"]
        else "node_seed"
    )
    if source["kind"] != expected_source_kind:
        raise AnalysisError("starting-state source differs from owned source resource")

    generation = _expect_keys(receipt["generation"], GENERATION_KEYS, "generation")
    for key in GENERATION_KEYS:
        _identifier(generation[key], f"generation.{key}")
    if generation["parent_source_uid"] != source["uid"]:
        raise AnalysisError("generation parent does not match immutable source UID")
    if generation["writable_resource_uid"] != by_kind["provider_volume"]["uid"]:
        raise AnalysisError("generation writable UID differs from provider volume UID")
    if generation["mutable_namespace_id"] != attempt["concurrency"]["mutable_namespace_id"]:
        raise AnalysisError("generation namespace differs from attempt namespace")
    if generation["generation_id"] != attempt["cleanup"]["generation_id"] or generation[
        "generation_uid"
    ] != attempt["cleanup"]["generation_uid"]:
        raise AnalysisError("cleanup generation identity differs from ownership receipt")
    if generation["writable_resource_uid"] != attempt["cleanup"]["writable_resource_uid"]:
        raise AnalysisError("cleanup writable UID differs from ownership receipt")
    if receipt["pre_t0_investment"] != attempt["pre_t0_investment"]:
        raise AnalysisError("pre-T0 investment differs from ownership receipt")
    return {"raw": receipt, "resources": resources, "by_kind": by_kind, "generation": generation}


def _validate_investment_derivation(
    attempt: dict[str, Any],
    ownership: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    investment = attempt["pre_t0_investment"]
    t0 = attempt["request"]["accepted_monotonic_ns"]
    source_clock = ownership["raw"]["source_available_monotonic_ns"]
    if source_clock >= t0:
        raise AnalysisError("pre-T0 source was not available before external T0")
    age = round((t0 - source_clock) / 1_000_000_000, 9)
    target_bytes = attempt["target"]["artifact_bytes"]
    medium = (
        "object_storage"
        if attempt["starting_state"]["remote_artifact_required"]
        else "network_ssd"
    )
    rate_key = (
        "object_storage_usd_per_gib_month"
        if medium == "object_storage"
        else "network_ssd_usd_per_gib_month"
    )
    rate = float(manifest["cost_source"][rate_key])
    cost = round(target_bytes / (1024**3) * rate * age / SECONDS_PER_BILLING_MONTH, 12)
    expected = {
        "source_available_monotonic_ns": source_clock,
        "source_age_seconds": age,
        "residency_medium": medium,
        "residency_bytes": target_bytes,
        "residency_rate_usd_per_gib_month": rate,
        "residency_cost_usd": cost,
        "prehydration_bytes": target_bytes,
        "prehydration_cost_usd": None,
        "prehydration_cost_status": "not-measured-no-live-receipt",
        "price_source_commit": manifest["cost_source"]["commit"],
        "included_in_request_totals": False,
    }
    if investment != expected:
        raise AnalysisError("source age or pre-T0 investment is not deterministically derived")


def _validate_typed_evidence(
    attempt: dict[str, Any],
    evidence_root: Path,
    clock: dict[str, Any],
    ownership: dict[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    entries = attempt["supporting_evidence"]
    if not isinstance(entries, list) or not entries:
        raise AnalysisError("supporting evidence is empty")
    by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    paths: set[str] = set()
    digests: set[str] = set()
    for index, raw in enumerate(entries):
        entry = _expect_keys(raw, EVIDENCE_KEYS, f"supporting evidence {index}")
        if entry["kind"] not in {"ownership", "operation", "cleanup"}:
            raise AnalysisError("supporting evidence kind is not typed")
        _identifier(entry["receipt_id"], "supporting evidence receipt ID")
        if entry["receipt_id"] in by_id or entry["path"] in paths or entry["sha256"] in digests:
            raise AnalysisError("supporting evidence receipt/path/digest is reused")
        document = _canonical_json_file(
            evidence_root, entry["path"], entry["sha256"], "supporting evidence"
        )
        by_id[entry["receipt_id"]] = (entry, document)
        paths.add(entry["path"])
        digests.add(entry["sha256"])

    ownership_ref = attempt["ownership_binding"]
    pair = by_id.get(ownership_ref["receipt_id"])
    if pair is None or pair[0]["kind"] != "ownership":
        raise AnalysisError("ownership binding lacks typed ownership evidence")
    if pair[0]["path"] != ownership_ref["path"] or pair[0]["sha256"] != ownership_ref[
        "sha256"
    ]:
        raise AnalysisError("ownership binding path/digest differs from evidence entry")
    if pair[1] != ownership["raw"]:
        raise AnalysisError("validated ownership receipt differs from evidence document")

    referenced: set[str] = {ownership_ref["receipt_id"]}
    permitted_uids = {item["uid"] for item in ownership["resources"]} | {
        ownership["generation"]["generation_uid"],
        ownership["generation"]["writable_resource_uid"],
    }
    for name, operation in attempt["_operations"].items():
        ref = operation["evidence_ref"]
        if operation["outcome"] == "skipped":
            continue
        if ref in referenced:
            raise AnalysisError("one evidence receipt backs multiple operations/cleanup")
        pair = by_id.get(ref)
        if pair is None or pair[0]["kind"] != "operation":
            raise AnalysisError(f"operation {name} lacks typed evidence")
        document = _expect_keys(pair[1], TYPED_EVIDENCE_KEYS, "operation evidence")
        if document["schema"] != EVIDENCE_SCHEMA or document["kind"] != "operation":
            raise AnalysisError("operation evidence schema/kind is invalid")
        if document["receipt_id"] != ref or document["attempt_id"] != attempt["attempt_id"]:
            raise AnalysisError("operation evidence identity differs")
        if _validate_clock(document["clock_binding"], "operation evidence clock") != clock:
            raise AnalysisError("operation evidence uses another clock")
        if document["operation"] != {
            key: operation[key] for key in OPERATION_EVIDENCE_KEYS
        } or document["cleanup"] is not None:
            raise AnalysisError("operation evidence content differs from receipt")
        resource_uids = document["resource_uids"]
        if not isinstance(resource_uids, list) or not resource_uids:
            raise AnalysisError("operation evidence lacks resource UIDs")
        if len(resource_uids) != len(set(resource_uids)) or not set(resource_uids) <= permitted_uids:
            raise AnalysisError("operation evidence resource UID is duplicated or unowned")
        referenced.add(ref)

    cleanup = attempt["cleanup"]
    ref = cleanup["evidence_ref"]
    if ref in referenced:
        raise AnalysisError("one evidence receipt backs multiple operations/cleanup")
    pair = by_id.get(ref)
    if pair is None or pair[0]["kind"] != "cleanup":
        raise AnalysisError("cleanup lacks typed evidence")
    document = _expect_keys(pair[1], TYPED_EVIDENCE_KEYS, "cleanup evidence")
    if document["schema"] != EVIDENCE_SCHEMA or document["kind"] != "cleanup":
        raise AnalysisError("cleanup evidence schema/kind is invalid")
    if document["receipt_id"] != ref or document["attempt_id"] != attempt["attempt_id"]:
        raise AnalysisError("cleanup evidence identity differs")
    if _validate_clock(document["clock_binding"], "cleanup evidence clock") != clock:
        raise AnalysisError("cleanup evidence uses another clock")
    if document["operation"] is not None or document["cleanup"] != {
        key: cleanup[key] for key in CLEANUP_EVIDENCE_KEYS
    }:
        raise AnalysisError("cleanup evidence content differs from receipt")
    resource_uids = document["resource_uids"]
    required_cleanup_uids = {
        ownership["generation"]["generation_uid"],
        ownership["generation"]["writable_resource_uid"],
        *(
            resource["uid"]
            for resource in ownership["resources"]
            if resource["kind"] in WRITABLE_KINDS
        ),
    }
    if cleanup["dirty"] and set(resource_uids) != required_cleanup_uids:
        raise AnalysisError("dirty cleanup absence proof omits exact writable UIDs")
    if not cleanup["dirty"] and not set(resource_uids) <= permitted_uids:
        raise AnalysisError("cleanup evidence references an unowned UID")
    referenced.add(ref)
    if referenced != set(by_id):
        raise AnalysisError("supporting evidence contains unreferenced receipts")
    return set(by_id), paths, digests


def _executed(operation: dict[str, Any]) -> bool:
    return operation["outcome"] != "skipped"


def _require_after(
    operations: dict[str, dict[str, Any]], current: str, dependencies: Iterable[str]
) -> None:
    operation = operations[current]
    if not _executed(operation):
        return
    for dependency in dependencies:
        predecessor = operations[dependency]
        if predecessor["outcome"] != "completed":
            raise AnalysisError(f"operation {current} executes without completed {dependency}")
        if operation["started_monotonic_ns"] < predecessor["finished_monotonic_ns"]:
            raise AnalysisError(f"operation order is inverted: {current} before {dependency}")


def _validate_operation_order(attempt: dict[str, Any]) -> None:
    operations = attempt["_operations"]
    _require_after(operations, "queue", ("catalog_selection",))
    if attempt["cache_state"] == "D_active_a_to_b_reclaim":
        _require_after(operations, "drain", ("queue",))
        _require_after(operations, "gpu_release", ("drain",))
        _require_after(operations, "eviction", ("gpu_release",))
        _require_after(operations, "placement", ("eviction",))
    else:
        _require_after(operations, "placement", ("queue",))
    if attempt["starting_state"]["remote_artifact_required"]:
        _require_after(operations, "artifact_fetch", ("placement",))
        _require_after(operations, "materialization", ("artifact_fetch",))
    elif attempt["starting_state"]["immutable_node_local_seed_present"]:
        _require_after(operations, "clone", ("placement",))
        _require_after(operations, "materialization", ("clone",))
    if attempt["cache_state"] == "A_materialized_hit":
        _require_after(operations, "first_read", ("queue",))
    else:
        _require_after(operations, "hash", ("materialization",))
        _require_after(operations, "first_read", ("hash",))


def _require_completed(operations: dict[str, dict[str, Any]], names: Iterable[str], label: str) -> None:
    missing = [name for name in names if operations[name]["outcome"] != "completed"]
    if missing:
        raise AnalysisError(f"{label} omits completed operations: {missing}")


def _validate_state_contract(attempt: dict[str, Any]) -> None:
    state = attempt["cache_state"]
    label = attempt["demand_label"]
    start = attempt["starting_state"]
    operations = attempt["_operations"]
    target_bytes = attempt["target"]["artifact_bytes"]
    expected_labels = {
        "A_materialized_hit": "cache_hit",
        "B_node_seed_post_t0_materialization": "unknown_model_cold_start",
        "C_remote_miss_post_t0": "unknown_model_cold_start",
        "D_active_a_to_b_reclaim": "active_a_to_b_switch",
    }
    if label != expected_labels[state]:
        raise AnalysisError("demand label differs from cache state")
    if label == "unknown_model_cold_start" and start["target_materialized"]:
        raise AnalysisError("prepared clone cannot be labeled unknown-model cold start")
    if state == "A_materialized_hit":
        if not start["target_materialized"]:
            raise AnalysisError("state A lacks materialized target")
        if start["active_model"] not in (
            None,
            {
                "model_id": attempt["target"]["model_id"],
                "model_version": attempt["target"]["model_version"],
            },
        ):
            raise AnalysisError("state A hides another active model")
    elif state == "B_node_seed_post_t0_materialization":
        if not start["immutable_node_local_seed_present"] or start["active_model"] is not None:
            raise AnalysisError("state B starting state is invalid")
    elif state == "C_remote_miss_post_t0":
        if not start["remote_artifact_required"] or start["active_model"] is not None:
            raise AnalysisError("state C starting state is invalid")
    else:
        active = start["active_model"]
        if active is None or active["model_id"] == attempt["target"]["model_id"]:
            raise AnalysisError("state D lacks a distinct active model")

    if not attempt["terminal"]["success"]:
        failed = [name for name, operation in operations.items() if operation["outcome"] == "failed"]
        if len(failed) != 1:
            raise AnalysisError("failed SLO attempt does not retain exactly one failed storage operation")
        return
    if any(operation["outcome"] == "failed" for operation in operations.values()):
        raise AnalysisError("successful SLO attempt contains failed storage operation")
    if state == "D_active_a_to_b_reclaim":
        _require_completed(operations, ("drain", "gpu_release", "eviction"), "state D")
        if operations["eviction"]["bytes_deleted"] != target_bytes:
            raise AnalysisError("state D does not account exact reclaimed generation bytes")
    if state == "A_materialized_hit":
        if any(
            operations[name]["outcome"] != "skipped"
            for name in ("placement", "artifact_fetch", "clone", "materialization", "hash")
        ):
            raise AnalysisError("state A performs request-time preparation")
        _require_completed(operations, ("catalog_selection", "queue", "first_read"), "state A")
        if attempt["accounting"]["request_slo_bytes_moved_total"] != 0:
            raise AnalysisError("state A claims request localization bytes")
        if any(operation["slo_bytes_moved"] for operation in operations.values()):
            raise AnalysisError("state A assigns physical reads to request localization")
        return
    _require_completed(
        operations,
        ("catalog_selection", "queue", "placement", "materialization", "hash", "first_read"),
        state,
    )
    if start["remote_artifact_required"]:
        _require_completed(operations, ("artifact_fetch",), state)
        if (
            operations["artifact_fetch"]["bytes_network"] != target_bytes
            or operations["artifact_fetch"]["slo_bytes_moved"] != target_bytes
        ):
            raise AnalysisError("remote state does not exactly reconcile fetched/SLO bytes")
        slo_source = "artifact_fetch"
    else:
        _require_completed(operations, ("clone",), state)
        if (
            operations["clone"]["bytes_read"] != target_bytes
            or operations["clone"]["bytes_written"] != target_bytes
            or operations["clone"]["slo_bytes_moved"] != target_bytes
        ):
            raise AnalysisError("node-seed state does not exactly reconcile clone/SLO bytes")
        slo_source = "clone"
    if (
        operations["materialization"]["bytes_written"] != target_bytes
        or operations["hash"]["bytes_read"] != target_bytes
        or operations["first_read"]["bytes_read"] != target_bytes
        or attempt["accounting"]["request_slo_bytes_moved_total"] != target_bytes
    ):
        raise AnalysisError("successful localization does not account exact target bytes")
    if any(
        operation["slo_bytes_moved"]
        for name, operation in operations.items()
        if name != slo_source
    ):
        raise AnalysisError("request-SLO bytes are assigned outside the exact source operation")


def _validate_attempt_shape(
    value: Any, manifest: dict[str, Any], evidence_root: Path
) -> dict[str, Any]:
    attempt = _expect_keys(value, ATTEMPT_KEYS, "attempt")
    if attempt["schema"] != ATTEMPT_SCHEMA:
        raise AnalysisError("attempt schema is unsupported")
    if attempt["source_manifest_sha256"] != canonical_sha256(manifest):
        raise AnalysisError("attempt is not pinned to exact source manifest")
    if attempt["evidence_classification"] not in EVIDENCE_CLASSES:
        raise AnalysisError("attempt evidence classification is unknown")
    if attempt["evidence_classification"] == "measured-live-product-slo":
        raise AnalysisError("measured receipt is forbidden while execution gate is closed")
    _identifier(attempt["attempt_id"], "attempt ID")
    _identifier(attempt["request_id"], "request ID")
    if attempt["cache_state"] not in CACHE_STATES or attempt["demand_label"] not in DEMAND_LABELS:
        raise AnalysisError("cache state or demand label is unknown")
    attempt["target"] = _validate_target(attempt["target"])
    attempt["starting_state"] = _validate_start(attempt["starting_state"], attempt["target"])
    attempt["request"] = _validate_request(attempt["request"])
    attempt["clock_binding"] = _validate_clock(attempt["clock_binding"], "attempt clock")
    attempt["request_slo_binding"] = _validate_binding(
        attempt["request_slo_binding"], attempt["attempt_id"], attempt["request_id"]
    )
    ownership_binding = _expect_keys(
        attempt["ownership_binding"], OWNERSHIP_BINDING_KEYS, "ownership binding"
    )
    _identifier(ownership_binding["receipt_id"], "ownership receipt ID")
    ownership_document = _canonical_json_file(
        evidence_root,
        ownership_binding["path"],
        ownership_binding["sha256"],
        "ownership receipt",
    )
    attempt["pre_t0_investment"] = _validate_investment_shape(
        attempt["pre_t0_investment"]
    )
    attempt["_operations"] = _validate_operations(attempt["operations"])
    attempt["accounting"] = _validate_accounting(attempt["accounting"], attempt["_operations"])
    attempt["concurrency"] = _validate_concurrency(attempt["concurrency"], attempt["attempt_id"])
    attempt["terminal"] = _validate_terminal(attempt["terminal"])
    attempt["cleanup"] = _validate_cleanup_shape(attempt["cleanup"])
    ownership = _validate_ownership_receipt(
        ownership_document, attempt, attempt["clock_binding"]
    )
    _validate_investment_derivation(attempt, ownership, manifest)
    receipt_ids, paths, digests = _validate_typed_evidence(
        attempt, evidence_root, attempt["clock_binding"], ownership
    )
    _validate_operation_order(attempt)
    _validate_state_contract(attempt)
    return {
        "raw": attempt,
        "target": attempt["target"],
        "starting_state": attempt["starting_state"],
        "request": attempt["request"],
        "clock": attempt["clock_binding"],
        "binding": attempt["request_slo_binding"],
        "ownership": ownership,
        "operations": attempt["_operations"],
        "accounting": attempt["accounting"],
        "concurrency": attempt["concurrency"],
        "terminal": attempt["terminal"],
        "cleanup": attempt["cleanup"],
        "evidence_receipt_ids": receipt_ids,
        "evidence_paths": paths,
        "evidence_digests": digests,
    }


def _load_shared_slo(shaped: Sequence[dict[str, Any]], evidence_root: Path):
    identities = {
        (
            item["binding"]["trace_path"],
            item["binding"]["ledger_path"],
            item["binding"]["trace_sha256"],
            item["binding"]["ledger_sha256"],
            item["binding"]["trace_id"],
            item["binding"]["ledger_id"],
        )
        for item in shaped
    }
    if len(identities) != 1:
        raise AnalysisError("storage receipts do not bind one exact SLO trace/ledger")
    trace_name, ledger_name, trace_sha, ledger_sha, trace_id, ledger_id = identities.pop()
    trace_path = _safe_path(evidence_root, trace_name, "bound trace")
    ledger_path = _safe_path(evidence_root, ledger_name, "bound ledger")
    if _file_sha256(trace_path) != trace_sha or _file_sha256(ledger_path) != ledger_sha:
        raise AnalysisError("bound request-SLO trace/ledger digest differs")
    try:
        trace = load_trace(trace_path)
        events = load_ledger(ledger_path)
        results = validate_ledger(events, trace)
    except HarnessError as exc:
        raise AnalysisError(f"bound request-SLO evidence is invalid: {exc}") from exc
    if trace["trace_id"] != trace_id or {event["ledger_id"] for event in events} != {ledger_id}:
        raise AnalysisError("bound request-SLO identity differs")
    recorder_payloads = {canonical_json(event["recorder"]) for event in events}
    if len(recorder_payloads) != 1:
        raise AnalysisError("request-SLO ledger uses mixed clocks")
    recorder = events[0]["recorder"]
    expected_attempts = {request["attempt_id"] for request in trace["requests"]}
    observed_attempts = {item["raw"]["attempt_id"] for item in shaped}
    if len(shaped) != trace["request_count"] or observed_attempts != expected_attempts:
        raise AnalysisError("storage receipts do not cover every SLO attempt/failure")
    return trace, events, results, recorder


def _validate_slo_joins(
    shaped: Sequence[dict[str, Any]],
    trace: dict[str, Any],
    events: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
    recorder: dict[str, Any],
) -> None:
    request_by_attempt = {item["attempt_id"]: item for item in trace["requests"]}
    result_by_attempt = {item["attempt_id"]: item for item in results}
    events_by_attempt: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_attempt[event["attempt_id"]].append(event)
    for item in shaped:
        attempt = item["raw"]
        attempt_id = attempt["attempt_id"]
        request = request_by_attempt[attempt_id]
        result = result_by_attempt[attempt_id]
        attempt_events = events_by_attempt[attempt_id]
        accepted = attempt_events[0]
        terminal_event = next(
            event
            for event in attempt_events
            if event["event_type"] in {"response.validated", "attempt.failed"}
        )
        if _recorder_from_clock(item["clock"]) != recorder:
            raise AnalysisError("storage clock identity differs from external recorder")
        if attempt["request_id"] != request["request_id"] or result["request_id"] != request[
            "request_id"
        ]:
            raise AnalysisError("request identity differs from SLO trace/ledger")
        if request["target"] != {
            key: attempt["target"][key]
            for key in (
                "model_id",
                "model_version",
                "artifact_id",
                "artifact_version",
                "artifact_sha256",
            )
        }:
            raise AnalysisError("target identity differs from SLO trace")
        if any(
            request["input"][key] != expected
            for key, expected in {
                "input_id": attempt["request"]["input_id"],
                "payload_sha256": attempt["request"]["input_sha256"],
                "input_bytes": attempt["request"]["input_bytes"],
            }.items()
        ):
            raise AnalysisError("input identity differs from SLO trace")
        if (
            accepted["observed_monotonic_ns"] != attempt["request"]["accepted_monotonic_ns"]
            or accepted["observed_at_utc"] != attempt["request"]["accepted_at_utc"]
        ):
            raise AnalysisError("storage receipt T0 differs from external recorder")
        if result["current_node_occupant"] != attempt["starting_state"]["active_model"]:
            raise AnalysisError("active model differs from SLO precondition")
        artifact_cache = request["precondition"]["cache"]["artifact"]
        allowed_cache = {
            "A_materialized_hit": {"memory_hit"},
            "B_node_seed_post_t0_materialization": {
                "node_local_hit",
                "attached_storage_hit",
            },
            "C_remote_miss_post_t0": {"remote_miss", "unavailable"},
            "D_active_a_to_b_reclaim": {
                "node_local_hit",
                "attached_storage_hit",
                "remote_miss",
            },
        }[attempt["cache_state"]]
        if artifact_cache not in allowed_cache:
            raise AnalysisError("cache state differs from SLO cache precondition")
        if accepted["data"]["environment"]["node_id"] != item["ownership"]["raw"][
            "selected_node_id"
        ]:
            raise AnalysisError("selected node is not joined to SLO environment")
        expected_success = terminal_event["event_type"] == "response.validated"
        failure_class = None if expected_success else terminal_event["data"]["failure_class"]
        if item["terminal"] != {
            "success": expected_success,
            "failure_class": failure_class,
            "observed_monotonic_ns": terminal_event["observed_monotonic_ns"],
        }:
            raise AnalysisError("storage terminal omits or changes SLO success/failure")
        if result["accounting"]["bytes_moved_total"] != item["accounting"][
            "request_slo_bytes_moved_total"
        ]:
            raise AnalysisError("storage physical/SLO byte reconciliation differs from ledger")
        if result["accounting"]["cost_usd"] != item["accounting"]["request_slo_cost_usd"]:
            raise AnalysisError("storage request cost differs from SLO ledger")
        slo_ownership = result["ownership"]
        ownership = item["ownership"]["raw"]
        if slo_ownership["owner_task_id"] != ownership["owner_task_id"]:
            raise AnalysisError("storage owner differs from SLO ownership")
        slo_resources = {
            (resource["kind"], resource["id"], resource["project_id"], resource["region"])
            for resource in slo_ownership["resources"]
        }
        receipt_resources = {
            (resource["kind"], resource["id"], resource["project_id"], resource["region"])
            for resource in ownership["resources"]
        }
        if slo_resources != receipt_resources:
            raise AnalysisError("PVC/PV/volume/object/node ownership is not joined to SLO")
        t0 = item["request"]["accepted_monotonic_ns"]
        terminal_ns = item["terminal"]["observed_monotonic_ns"]
        for operation in item["operations"].values():
            if _executed(operation) and (
                operation["started_monotonic_ns"] < t0
                or operation["finished_monotonic_ns"] > terminal_ns
            ):
                raise AnalysisError("storage operation lies outside external T0/terminal")
        deleted = set(result["cleanup"]["resources_deleted"])
        writable_ids = {
            resource["id"]
            for resource in ownership["resources"]
            if resource["kind"] in WRITABLE_KINDS
        }
        if item["cleanup"]["dirty"] and not writable_ids <= deleted:
            raise AnalysisError("SLO cleanup omits dirty PVC/PV/provider volume IDs")


def _has_true_overlap(members: Sequence[dict[str, Any]]) -> bool:
    intervals_by_member: list[list[tuple[int, int]]] = []
    for member in members:
        intervals = [
            (operation["started_monotonic_ns"], operation["finished_monotonic_ns"])
            for name, operation in member["operations"].items()
            if name in LOCALIZATION_OPERATIONS and _executed(operation)
        ]
        if not intervals:
            return False
        intervals_by_member.append(intervals)
    candidates = sorted({start for intervals in intervals_by_member for start, _ in intervals})
    return any(
        all(any(start <= point < finish for start, finish in intervals) for intervals in intervals_by_member)
        for point in candidates
    )


def _validate_cross_attempt_invariants(shaped: Sequence[dict[str, Any]]) -> None:
    attempt_ids = [item["raw"]["attempt_id"] for item in shaped]
    request_ids = [item["raw"]["request_id"] for item in shaped]
    namespaces = [item["concurrency"]["mutable_namespace_id"] for item in shaped]
    if len(attempt_ids) != len(set(attempt_ids)) or len(request_ids) != len(set(request_ids)):
        raise AnalysisError("attempt or request identity is duplicated")
    if len(namespaces) != len(set(namespaces)):
        raise AnalysisError("mutable namespace is shared")
    if {item["raw"]["cache_state"] for item in shaped} != set(CACHE_STATES):
        raise AnalysisError("ledger omits one or more mutually exclusive cache states")
    for attribute, label in (
        ("evidence_receipt_ids", "evidence receipt ID"),
        ("evidence_paths", "evidence path"),
        ("evidence_digests", "evidence digest"),
    ):
        values = [value for item in shaped for value in item[attribute]]
        if len(values) != len(set(values)):
            raise AnalysisError(f"{label} is reused across attempts")

    by_id = {item["raw"]["attempt_id"]: item for item in shaped}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in shaped:
        if item["concurrency"]["group_id"] is not None:
            groups[item["concurrency"]["group_id"]].append(item)
    for group_id, members in groups.items():
        ids = {item["raw"]["attempt_id"] for item in members}
        if len(ids) < 2 or len({item["target"]["model_id"] for item in members}) < 2:
            raise AnalysisError(f"concurrent group {group_id} lacks distinct models")
        for item in members:
            if set(item["concurrency"]["peer_attempt_ids"]) != ids - {
                item["raw"]["attempt_id"]
            } or any(peer not in by_id for peer in item["concurrency"]["peer_attempt_ids"]):
                raise AnalysisError("concurrent peer declarations are incomplete")
        if not _has_true_overlap(members):
            raise AnalysisError("concurrent group has no true same-clock localization overlap")

    dirty_uids: set[str] = set()
    for item in sorted(shaped, key=lambda member: member["request"]["accepted_monotonic_ns"]):
        ownership_uids = {resource["uid"] for resource in item["ownership"]["resources"]}
        generation_uids = {
            item["ownership"]["generation"]["generation_uid"],
            item["ownership"]["generation"]["writable_resource_uid"],
        }
        if dirty_uids & (ownership_uids | generation_uids):
            raise AnalysisError("dirty physical UID was renamed and reused")
        if item["cleanup"]["dirty"]:
            dirty_uids |= generation_uids
            dirty_uids |= {
                resource["uid"]
                for resource in item["ownership"]["resources"]
                if resource["kind"] in WRITABLE_KINDS
            }


def validate_attempts_v2(
    manifest: dict[str, Any], attempts: Sequence[dict[str, Any]], evidence_root: Path
) -> list[dict[str, Any]]:
    manifest = validate_source_manifest(manifest)
    if not attempts:
        raise AnalysisError("attempt ledger is empty")
    shaped = [
        _validate_attempt_shape(dict(attempt), manifest, evidence_root)
        for attempt in attempts
    ]
    trace, events, results, recorder = _load_shared_slo(shaped, evidence_root)
    _validate_slo_joins(shaped, trace, events, results, recorder)
    _validate_cross_attempt_invariants(shaped)
    return shaped
