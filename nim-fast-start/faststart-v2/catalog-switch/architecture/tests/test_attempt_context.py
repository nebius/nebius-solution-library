from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ARCH_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "attempt_context", ARCH_DIR / "attempt_context.py"
)
assert SPEC and SPEC.loader
CONTEXT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTEXT)


def ref(digest: str, name: str) -> dict:
    return {
        "kind": "immutable_ref",
        "uri": f"https://artifacts.invalid/{name}",
        "digest": digest,
        "bytes": 1,
        "media_type": "application/json",
    }


def make_bundle() -> dict:
    digest = "sha256:" + "a" * 64
    raw_digest = "a" * 64
    target = {
        "model_id": "model-1",
        "model_version": "v1",
        "artifact_id": "artifact-1",
        "artifact_version": "v1",
        "artifact_sha256": raw_digest,
    }
    request_input = {
        "workload_id": "workload-1",
        "input_id": "input-1",
        "payload_sha256": raw_digest,
        "input_bytes": 1,
    }
    precondition = {
        "current_node_occupant": None,
        "cache": {
            "image": "local_verified",
            "artifact": "node_local_hit",
            "checkpoint": "compatible_hit",
            "storage": "ready",
        },
        "capacity": "allocated",
        "queue_depth": 0,
    }
    trace_request = {
        "sequence": 0,
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "offered_at_offset_ms": 0,
        "scenario": "idle_local",
        "target": target,
        "input": request_input,
        "precondition": precondition,
    }
    trace = {
        "schema": CONTEXT.REQUEST_SLO.TRACE_SCHEMA,
        "trace_id": "trace-1",
        "distribution": "uniform",
        "seed": 1,
        "catalog_sha256": raw_digest,
        "request_count": 1,
        "scenario_labels": list(CONTEXT.REQUEST_SLO.SCENARIOS),
        "requests": [trace_request],
    }
    trace["trace_sha256"] = CONTEXT.REQUEST_SLO.canonical_sha256(
        CONTEXT.REQUEST_SLO._trace_payload(trace)
    )
    ledger_events = CONTEXT.REQUEST_SLO.synthetic_smoke_ledger(trace)
    accepted = ledger_events[0]
    accepted["data"]["environment"].update(
        {
            "backend": "catalog-router-unresolved",
            "provider": "catalog-ingress",
            "project_id": "project-e00z6b02t8ddk96c49",
            "region": "eu-north1",
        }
    )
    accepted["data"]["ownership"] = {
        "owner_task_id": "catalog-switch-integrated-architecture-adr",
        "resource_prefix": "mlsp-csw-context-test",
        "dedicated": True,
        "cleanup_required": True,
        "resources": [
            {
                "kind": "compute-instance",
                "id": "instance-1",
                "project_id": "project-e00z6b02t8ddk96c49",
                "region": "eu-north1",
            }
        ],
    }
    cleanup_event = next(
        event for event in ledger_events if event["event_type"] == "cleanup.finished"
    )
    cleanup_event["data"].update(
        {
            "required": True,
            "status": "complete",
            "resources_deleted": ["instance-1"],
            "resources_retained": [],
            "receipt_sha256": raw_digest,
            "reason": "synthetic exact cleanup receipt",
        }
    )
    terminal_event = next(
        event for event in ledger_events if event["event_type"] == "response.validated"
    )
    terminal_event["data"]["validator_sha256"] = raw_digest
    terminal_event["data"]["response_sha256"] = raw_digest
    accepted_hash = CONTEXT.canonical_digest(accepted)
    accept_response = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "requested_model_id": "model-1",
        "requested_model_version": "v1",
        "input_digest": digest,
        "accepted_input_ref": ref(digest, "input"),
        "accepted_event_hash": accepted_hash,
        "accepted_at_utc": "2026-08-19T15:00:00Z",
        "accepted_at_monotonic_ns": 1,
    }
    resolution = {
        "catalog_digest": digest,
        "model_id": "model-1",
        "model_version": "v1",
        "workload": "generation",
        "api_contract_digest": digest,
        "input_schema_digest": digest,
        "image_digest": digest,
        "artifact": {"digest": digest, "bytes": 1, "publication_id": "pub-1"},
        "validator_digest": digest,
        "hardware_runtime": {
            "gpu_sku": "gpu-h100-sxm",
            "gpu_count": 1,
            "gpu_memory_gib_min": 80,
            "runtime": "oci",
            "driver_version": "580.1",
            "cuda_version": "13.0",
            "topology_digest": digest,
        },
        "storage": {
            "l1_eligible": True,
            "l2_publication_required": True,
            "writable_state": [],
            "external_mounts": [],
        },
        "snapshot_status": "eligible",
        "checkpoint": {
            "digest": digest,
            "bytes": 1,
            "binding_digest": digest,
            "encrypted": True,
            "signature": "signature",
            "signer_key_id": "key-1",
            "evidence_refs": ["evidence-1"],
        },
        "fallback_ladder": ["conventional", "fail"],
        "policy": {
            "tenant_eligible": True,
            "license_eligible": True,
            "required_secret_refs": [],
            "egress_policy_digest": digest,
            "eligible_backends": ["node-vm"],
        },
    }
    lease_request = {
        "plan_digest": digest,
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "resource_prefix": "mlsp-csw-context-test",
        "ttl_seconds": 3600,
        "budget_usd": 1,
        "owner_task_id": "catalog-switch-integrated-architecture-adr",
        "dedicated": True,
        "cleanup_owner": "catalog-switch-integrated-architecture-adr",
    }
    lease_response = {
        "plan_digest": digest,
        "lease_id": "lease-1",
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "resource_prefix": "mlsp-csw-context-test",
        "owner_task_id": "catalog-switch-integrated-architecture-adr",
        "dedicated": True,
        "state": "ACTIVE",
        "exact_resource_ids": ["instance-1"],
        "cost_receipt_digests": [],
        "cleanup_receipt_digests": [],
    }
    lease = {"request": lease_request, "response": lease_response}
    context = {
        "schema_version": "catalog-switch-attempt-context/v1",
        "context_id": "context-1",
        "context_version": 1,
        "previous_context_commit_digest": None,
        "transition": None,
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "accepted_event_hash": accepted_hash,
        "accepted_environment_role": "target-neutral-ingress",
        "catalog_resolution_digest": CONTEXT.canonical_digest(resolution),
        "catalog_digest": digest,
        "policy_digest": digest,
        "placement_decision_digest": digest,
        "backend": "node-vm",
        "provider": "nebius",
        "resource_binding": {
            "kind": "internal_broker",
            "plan_digest": digest,
            "lease_binding_digest": CONTEXT.canonical_digest(lease),
            "project_id": "project-e00z6b02t8ddk96c49",
            "region": "eu-north1",
            "resource_prefix": "mlsp-csw-context-test",
            "owner_task_id": "catalog-switch-integrated-architecture-adr",
            "dedicated": True,
            "exact_resource_ids": ["instance-1"],
        },
        "node_lease_id": "lease-1",
        "instance_id": "instance-1",
        "boot_id": "boot-1",
        "generation": 1,
        "model_id": "model-1",
        "model_version": "v1",
        "api_contract_digest": digest,
        "input_schema_digest": digest,
        "image_digest": digest,
        "artifact_digest": digest,
        "launch_strategy": "conventional",
        "checkpoint_binding_digest": None,
        "validator_digest": digest,
        "input_digest": digest,
        "created_at_utc": "2026-08-19T15:00:01Z",
        "created_at_monotonic_ns": 2,
    }
    context_digest = CONTEXT.canonical_digest(context)
    placement = {
        "request": {
            "request_id": "request-1",
            "attempt_id": "attempt-1",
            "catalog_resolution": resolution,
            "deadline_utc": "2026-08-19T16:00:00Z",
            "queue_snapshot_digest": digest,
            "cache_snapshot_digest": digest,
            "capacity_snapshot_digest": digest,
            "policy_digest": digest,
        },
        "response": {
            "attempt_context": context,
            "attempt_context_digest": context_digest,
            "estimated_switch_cost_ms": 1,
            "decision_evidence_digest": digest,
        },
    }
    context["placement_decision_digest"] = CONTEXT.placement_decision_digest(
        placement["request"], placement["response"]
    )
    context_digest = CONTEXT.canonical_digest(context)
    placement["response"]["attempt_context_digest"] = context_digest
    context_commit_request = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "idempotency_key": "context-key-1",
        "attempt_context": context,
        "attempt_context_digest": context_digest,
    }
    context_commit_digest = CONTEXT.canonical_digest(context_commit_request)
    context_commit = {
        "request": context_commit_request,
        "response": {
            "request_id": "request-1",
            "attempt_id": "attempt-1",
            "context_version": 1,
            "attempt_context_digest": context_digest,
            "context_commit_digest": context_commit_digest,
            "committed_at_utc": "2026-08-19T15:00:02Z",
            "replayed": False,
        },
    }
    common = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "attempt_context_commit_digest": context_commit_digest,
        "node_lease_id": "lease-1",
        "generation": 1,
        "runtime_identity": "runtime-1",
    }
    dispatch_request = {
        **common,
        "idempotency_key": "dispatch-key-1",
        "accepted_input_ref": ref(digest, "input"),
        "input_digest": digest,
        "catalog_resolution_digest": CONTEXT.canonical_digest(resolution),
        "deadline_utc": "2026-08-19T16:00:00Z",
    }
    dispatch_response = {
        **common,
        "raw_output_ref": ref(digest, "raw-output"),
        "raw_output_digest": digest,
        "inference_receipt_digest": digest,
        "completed_at_utc": "2026-08-19T15:00:03Z",
    }
    validation_request = {
        **common,
        "inference_receipt_digest": digest,
        "model_id": "model-1",
        "model_version": "v1",
        "input_digest": digest,
        "raw_output_ref": ref(digest, "raw-output"),
        "raw_output_digest": digest,
        "validator_digest": digest,
    }
    validation_response = {
        **common,
        "inference_receipt_digest": digest,
        "valid": True,
        "semantic_receipt_digest": digest,
        "validated_output_ref": ref(digest, "validated-output"),
        "validated_output_digest": digest,
    }
    response_commit_request = {
        **common,
        "inference_receipt_digest": digest,
        "idempotency_key": "response-key-1",
        "accepted_event_hash": accepted_hash,
        "semantic_receipt_digest": digest,
        "validated_output_ref": ref(digest, "validated-output"),
        "validated_output_digest": digest,
    }
    response_commit_digest = CONTEXT.canonical_digest(response_commit_request)
    response_commit_response = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "attempt_context_commit_digest": context_commit_digest,
        "status": "success",
        "output": ref(digest, "validated-output"),
        "output_digest": digest,
        "semantic_receipt_digest": digest,
        "response_commit_digest": response_commit_digest,
        "committed_at_utc": "2026-08-19T15:00:04Z",
        "committed_at_monotonic_ns": terminal_event["observed_monotonic_ns"] - 1,
        "recorder_id": terminal_event["recorder"]["recorder_id"],
        "clock_id": terminal_event["recorder"]["clock_id"],
        "boot_id": terminal_event["recorder"]["boot_id"],
        "replayed": False,
    }
    attempt_commit_request = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "accepted_event_hash": accepted_hash,
        "terminal_event_digest": CONTEXT.canonical_digest(terminal_event),
        "terminal_outcome": "success",
        "attempt_context_commit_digest": context_commit_digest,
        "failure": None,
        "response_commit_digest": response_commit_digest,
        "trace_digest": CONTEXT.canonical_digest(trace_request),
        "ledger_digest": CONTEXT.canonical_digest(ledger_events),
        "accounting_digest": CONTEXT.canonical_digest(
            next(event for event in ledger_events if event["event_type"] == "accounting.recorded")
        ),
        "resource_inventory_digest": CONTEXT.canonical_digest(
            accepted["data"]["ownership"]
        ),
        "cleanup_final_state": "absent",
        "cleanup_receipt_digest": CONTEXT.canonical_digest(
            next(event for event in ledger_events if event["event_type"] == "cleanup.finished")
        ),
    }
    attempt_commit_response = {
        "commit_digest": CONTEXT.canonical_digest(attempt_commit_request),
        "validation_status": "valid",
        "aggregate_eligible": True,
    }
    return {
        "schema": "catalog-switch-attempt-context-binding/v1",
        "trace_request": trace_request,
        "ledger_events": ledger_events,
        "accept_response": accept_response,
        "lease": lease,
        "placement": placement,
        "context_commits": [context_commit],
        "exchanges": [
            {"operation": "DispatchInference", "request": dispatch_request, "response": dispatch_response},
            {"operation": "ValidateResponse", "request": validation_request, "response": validation_response},
            {"operation": "CommitResponse", "request": response_commit_request, "response": response_commit_response},
            {"operation": "CommitAttempt", "request": attempt_commit_request, "response": attempt_commit_response},
        ],
    }


def refresh_latest_context(bundle: dict) -> None:
    """Recompute the canonical receipts after a deliberate context mutation."""
    commits = bundle["context_commits"]
    for index, commit in enumerate(commits):
        context = commit["request"]["attempt_context"]
        if index == 0:
            bundle["placement"]["response"]["attempt_context_digest"] = (
                CONTEXT.canonical_digest(context)
            )
        context_digest = CONTEXT.canonical_digest(context)
        commit["request"]["attempt_context_digest"] = context_digest
        commit_digest = CONTEXT.canonical_digest(commit["request"])
        commit["response"]["attempt_context_digest"] = context_digest
        commit["response"]["context_commit_digest"] = commit_digest
        if index + 1 < len(commits):
            commits[index + 1]["request"]["attempt_context"][
                "previous_context_commit_digest"
            ] = commit_digest
    latest_digest = commits[-1]["response"]["context_commit_digest"]
    resolution_digest = bundle["placement"]["response"]["attempt_context"][
        "catalog_resolution_digest"
    ]
    for exchange in bundle["exchanges"]:
        exchange["request"]["attempt_context_commit_digest"] = latest_digest
        if exchange["operation"] == "DispatchInference":
            exchange["request"]["catalog_resolution_digest"] = resolution_digest
        if "attempt_context_commit_digest" in exchange["response"]:
            exchange["response"]["attempt_context_commit_digest"] = latest_digest
    response_exchange = next(
        item for item in bundle["exchanges"] if item["operation"] == "CommitResponse"
    )
    response_digest = CONTEXT.canonical_digest(response_exchange["request"])
    response_exchange["response"]["response_commit_digest"] = response_digest
    attempt_exchange = next(
        item for item in bundle["exchanges"] if item["operation"] == "CommitAttempt"
    )
    attempt_exchange["request"]["response_commit_digest"] = response_digest
    attempt_exchange["response"]["commit_digest"] = CONTEXT.canonical_digest(
        attempt_exchange["request"]
    )


def make_fallback_bundle() -> dict:
    bundle = make_bundle()
    digest = "sha256:" + "a" * 64
    resolution = bundle["placement"]["request"]["catalog_resolution"]
    resolution["fallback_ladder"] = ["snapshot", "conventional", "fail"]
    first = bundle["context_commits"][0]
    initial = first["request"]["attempt_context"]
    initial["launch_strategy"] = "snapshot"
    initial["checkpoint_binding_digest"] = digest
    initial["catalog_resolution_digest"] = CONTEXT.canonical_digest(resolution)
    initial["placement_decision_digest"] = CONTEXT.placement_decision_digest(
        bundle["placement"]["request"], bundle["placement"]["response"]
    )
    refresh_latest_context(bundle)

    first_digest = first["response"]["context_commit_digest"]
    fallback = copy.deepcopy(initial)
    fallback.update(
        {
            "context_version": 2,
            "previous_context_commit_digest": first_digest,
            "transition": {
                "from_strategy": "snapshot",
                "to_strategy": "conventional",
                "checkpoint_failure_receipt_digest": digest,
                "scrub_receipt_digest": digest,
            },
            "launch_strategy": "conventional",
            "checkpoint_binding_digest": None,
            "created_at_utc": "2026-08-19T15:00:02Z",
            "created_at_monotonic_ns": 3,
        }
    )
    fallback_digest = CONTEXT.canonical_digest(fallback)
    fallback_request = {
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "idempotency_key": "context-key-2",
        "attempt_context": fallback,
        "attempt_context_digest": fallback_digest,
    }
    bundle["context_commits"].append(
        {
            "request": fallback_request,
            "response": {
                "request_id": "request-1",
                "attempt_id": "attempt-1",
                "context_version": 2,
                "attempt_context_digest": fallback_digest,
                "context_commit_digest": CONTEXT.canonical_digest(fallback_request),
                "committed_at_utc": "2026-08-19T15:00:03Z",
                "replayed": False,
            },
        }
    )
    refresh_latest_context(bundle)
    return bundle


def make_failure_bundle(
    code: str,
    phase: str,
    failure_class: str,
    *,
    context: bool,
    fallback: bool = False,
) -> dict:
    source = make_fallback_bundle() if fallback else make_bundle()
    events = source["ledger_events"]
    accepted = copy.deepcopy(events[0])
    phase_order = list(CONTEXT.REQUEST_SLO.PHASES)
    failure_index = phase_order.index(phase)
    rebuilt = [accepted]
    moved = 0
    for index, phase_name in enumerate(phase_order):
        started = next(
            (
                copy.deepcopy(event)
                for event in events
                if event["event_type"] == "phase.started"
                and event["data"]["phase"] == phase_name
            ),
            None,
        )
        finished = copy.deepcopy(
            next(
                event
                for event in events
                if event["event_type"] == "phase.finished"
                and event["data"]["phase"] == phase_name
            )
        )
        if index < failure_index:
            if started is not None:
                rebuilt.append(started)
            rebuilt.append(finished)
            moved += finished["data"]["bytes_moved"]
        elif index == failure_index:
            if started is None:
                started = copy.deepcopy(finished)
                started["event_type"] = "phase.started"
                started["data"] = {"phase": phase_name, "occurrence": 0}
                started["observed_monotonic_ns"] -= 1
            rebuilt.append(started)
            finished["data"].update(
                {"outcome": "failed", "reason": code, "bytes_moved": 0}
            )
            rebuilt.append(finished)
        else:
            finished["data"].update(
                {"outcome": "skipped", "reason": "prior failure", "bytes_moved": 0}
            )
            rebuilt.append(finished)
    terminal_template = copy.deepcopy(
        next(event for event in events if event["event_type"] == "response.validated")
    )
    terminal_template["event_type"] = "attempt.failed"
    terminal_template["data"] = {
        "failure_class": failure_class,
        "reason": code,
        "retryable": code in {"capacity_miss", "runtime_failed"},
    }
    rebuilt.append(terminal_template)
    accounting = copy.deepcopy(
        next(event for event in events if event["event_type"] == "accounting.recorded")
    )
    accounting["data"]["bytes_moved_total"] = moved
    rebuilt.append(accounting)
    rebuilt.append(
        copy.deepcopy(next(event for event in events if event["event_type"] == "cleanup.finished"))
    )
    for sequence, event in enumerate(rebuilt):
        event["ledger_sequence"] = sequence
        event["attempt_sequence"] = sequence
        event["event_id"] = f"attempt-1:{sequence:06d}"

    operation = {
        "resolution_denied": "ResolveCatalog",
        "capacity_miss": "PlaceAttempt",
        "deadline_exceeded": "DispatchInference",
        "command_rejected": "ApplyNodeCommand",
        "runtime_failed": "DispatchInference",
        "semantic_invalid": "ValidateResponse",
        "cancelled": "DispatchInference",
        "integrity_failure": "ApplyNodeCommand",
    }[code]
    failure = {
        "error_schema_version": "catalog-switch-error/v1",
        "correlation_id": "correlation-1",
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "operation": operation,
        "stage": "post_accept",
        "idempotency_key": "failure-key-1",
        "terminal": True,
        "error": {
            "code": code,
            "message": code,
            "retryable": code in {"capacity_miss", "runtime_failed"},
            "details_digest": "sha256:" + "a" * 64,
        },
    }
    attempt = next(
        item for item in source["exchanges"] if item["operation"] == "CommitAttempt"
    )
    latest_context = (
        source["context_commits"][-1]["response"]["context_commit_digest"]
        if context
        else None
    )
    request = copy.deepcopy(attempt["request"])
    request.update(
        {
            "terminal_event_digest": CONTEXT.canonical_digest(terminal_template),
            "terminal_outcome": "failure",
            "attempt_context_commit_digest": latest_context,
            "failure": failure,
            "response_commit_digest": None,
            "trace_digest": CONTEXT.canonical_digest(source["trace_request"]),
            "ledger_digest": CONTEXT.canonical_digest(rebuilt),
            "accounting_digest": CONTEXT.canonical_digest(accounting),
            "resource_inventory_digest": CONTEXT.canonical_digest(
                accepted["data"]["ownership"]
            ),
            "cleanup_receipt_digest": CONTEXT.canonical_digest(rebuilt[-1]),
        }
    )
    response = copy.deepcopy(attempt["response"])
    response["commit_digest"] = CONTEXT.canonical_digest(request)
    return {
        "schema": "catalog-switch-attempt-failure-binding/v1",
        "trace_request": source["trace_request"],
        "ledger_events": rebuilt,
        "accept_response": source["accept_response"],
        "lease": source["lease"] if context else None,
        "placement": source["placement"] if context else None,
        "context_commits": source["context_commits"] if context else [],
        "failure": failure,
        "terminal_commit": {
            "request": request,
            "response": response,
        },
    }


def refresh_failure_context(bundle: dict) -> None:
    commits = bundle["context_commits"]
    for index, commit in enumerate(commits):
        context = commit["request"]["attempt_context"]
        if index == 0:
            bundle["placement"]["response"]["attempt_context_digest"] = (
                CONTEXT.canonical_digest(context)
            )
        context_digest = CONTEXT.canonical_digest(context)
        commit["request"]["attempt_context_digest"] = context_digest
        commit_digest = CONTEXT.canonical_digest(commit["request"])
        commit["response"]["attempt_context_digest"] = context_digest
        commit["response"]["context_commit_digest"] = commit_digest
        if index + 1 < len(commits):
            commits[index + 1]["request"]["attempt_context"][
                "previous_context_commit_digest"
            ] = commit_digest
    terminal = bundle["terminal_commit"]
    terminal["request"]["attempt_context_commit_digest"] = commits[-1]["response"][
        "context_commit_digest"
    ]
    terminal["response"]["commit_digest"] = CONTEXT.canonical_digest(
        terminal["request"]
    )


class AttemptContextTests(unittest.TestCase):
    def test_complete_chain_passes(self) -> None:
        CONTEXT.validate_binding(make_bundle())

    def test_backend_selection_cannot_be_hidden_at_t0(self) -> None:
        bundle = make_bundle()
        bundle["ledger_events"][0]["data"]["environment"]["backend"] = "node-vm"
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "target-neutral"):
            CONTEXT.validate_binding(bundle)

    def test_required_context_identity_cannot_be_omitted(self) -> None:
        bundle = make_bundle()
        del bundle["placement"]["response"]["attempt_context"]["generation"]
        with self.assertRaises(CONTEXT.ContextBindingError):
            CONTEXT.validate_binding(bundle)

    def test_stale_generation_cannot_reach_semantic_commit(self) -> None:
        bundle = make_bundle()
        validation = next(
            item for item in bundle["exchanges"] if item["operation"] == "ValidateResponse"
        )
        validation["request"]["generation"] = 2
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "validation input"):
            CONTEXT.validate_binding(bundle)

    def test_stale_context_cannot_reach_terminal_commit(self) -> None:
        bundle = make_bundle()
        terminal = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitAttempt"
        )
        terminal["request"]["attempt_context_commit_digest"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "stale attempt context"):
            CONTEXT.validate_binding(bundle)

    def test_full_request_slo_acceptance_contract_is_required(self) -> None:
        bundle = make_bundle()
        del bundle["ledger_events"][0]["data"]["trace_request_sha256"]
        with self.assertRaises(CONTEXT.REQUEST_SLO.HarnessError):
            CONTEXT.validate_binding(bundle)

    def test_accepted_input_reference_cannot_be_substituted(self) -> None:
        bundle = make_bundle()
        dispatch = next(
            item for item in bundle["exchanges"] if item["operation"] == "DispatchInference"
        )
        dispatch["request"]["accepted_input_ref"]["uri"] = (
            "https://artifacts.invalid/substituted"
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "input reference"):
            CONTEXT.validate_binding(bundle)

    def test_unvalidated_client_output_cannot_be_substituted(self) -> None:
        bundle = make_bundle()
        response = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitResponse"
        )
        response["response"]["output"]["uri"] = "https://artifacts.invalid/unvalidated"
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "validated output"):
            CONTEXT.validate_binding(bundle)

    def test_terminal_event_must_follow_response_commit(self) -> None:
        bundle = make_bundle()
        terminal = next(
            event for event in bundle["ledger_events"] if event["event_type"] == "response.validated"
        )
        response = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitResponse"
        )
        response["response"]["committed_at_monotonic_ns"] = terminal[
            "observed_monotonic_ns"
        ]
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "must follow"):
            CONTEXT.validate_binding(bundle)

    def test_terminal_event_must_use_response_recorder_clock(self) -> None:
        bundle = make_bundle()
        response = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitResponse"
        )
        response["response"]["clock_id"] = "other-clock"
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "external terminal clock"):
            CONTEXT.validate_binding(bundle)

    def test_terminal_event_digest_is_committed_only_after_delivery(self) -> None:
        bundle = make_bundle()
        terminal = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitAttempt"
        )
        terminal["request"]["terminal_event_digest"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "product terminal"):
            CONTEXT.validate_binding(bundle)

    def test_backend_must_be_catalog_policy_eligible(self) -> None:
        bundle = make_bundle()
        bundle["placement"]["request"]["catalog_resolution"]["policy"][
            "eligible_backends"
        ] = ["kubernetes"]
        context = bundle["placement"]["response"]["attempt_context"]
        context["catalog_resolution_digest"] = CONTEXT.canonical_digest(
            bundle["placement"]["request"]["catalog_resolution"]
        )
        refresh_latest_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "policy eligible"):
            CONTEXT.validate_binding(bundle)

    def test_placement_snapshots_and_decision_evidence_are_bound(self) -> None:
        for field in ("queue_snapshot_digest", "cache_snapshot_digest", "capacity_snapshot_digest"):
            with self.subTest(field=field):
                bundle = make_bundle()
                bundle["placement"]["request"][field] = "sha256:" + "b" * 64
                with self.assertRaisesRegex(CONTEXT.ContextBindingError, "placement decision"):
                    CONTEXT.validate_binding(bundle)
        bundle = make_bundle()
        bundle["placement"]["response"]["decision_evidence_digest"] = (
            "sha256:" + "b" * 64
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "placement decision"):
            CONTEXT.validate_binding(bundle)

    def test_internal_project_must_be_allowlisted(self) -> None:
        bundle = make_bundle()
        bundle["lease"]["request"]["project_id"] = "project-foreign"
        with self.assertRaises(CONTEXT.ContextBindingError):
            CONTEXT.validate_binding(bundle)

    def test_foreign_resource_substitution_is_rejected(self) -> None:
        bundle = make_bundle()
        bundle["lease"]["response"]["exact_resource_ids"] = ["foreign-instance"]
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "exact broker lease"):
            CONTEXT.validate_binding(bundle)

    def test_released_or_quarantined_lease_cannot_launch(self) -> None:
        for state in ("PLANNED", "RELEASED", "QUARANTINED"):
            with self.subTest(state=state):
                bundle = make_bundle()
                bundle["lease"]["response"]["state"] = state
                context = bundle["placement"]["response"]["attempt_context"]
                context["resource_binding"]["lease_binding_digest"] = (
                    CONTEXT.canonical_digest(bundle["lease"])
                )
                refresh_latest_context(bundle)
                with self.assertRaisesRegex(CONTEXT.ContextBindingError, "ACTIVE"):
                    CONTEXT.validate_binding(bundle)

    def test_runtime_instance_must_belong_to_exact_lease(self) -> None:
        bundle = make_bundle()
        bundle["placement"]["response"]["attempt_context"]["instance_id"] = (
            "foreign-instance"
        )
        refresh_latest_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "outside exact"):
            CONTEXT.validate_binding(bundle)

    def test_internal_cleanup_requires_a_real_receipt(self) -> None:
        bundle = make_bundle()
        cleanup = next(
            event for event in bundle["ledger_events"] if event["event_type"] == "cleanup.finished"
        )
        cleanup["data"]["receipt_sha256"] = None
        terminal = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitAttempt"
        )
        terminal["request"]["ledger_digest"] = CONTEXT.canonical_digest(
            bundle["ledger_events"]
        )
        terminal["request"]["cleanup_receipt_digest"] = CONTEXT.canonical_digest(cleanup)
        terminal["response"]["commit_digest"] = CONTEXT.canonical_digest(
            terminal["request"]
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "cleanup requires"):
            CONTEXT.validate_binding(bundle)

    def test_modal_cannot_hide_behind_cerebrium_backend(self) -> None:
        bundle = make_bundle()
        context = bundle["placement"]["response"]["attempt_context"]
        resolution = bundle["placement"]["request"]["catalog_resolution"]
        resolution["policy"]["eligible_backends"] = ["cerebrium"]
        context.update(
            {
                "backend": "cerebrium",
                "provider": "modal",
                "resource_binding": {
                    "kind": "external_provider",
                    "provider_project_id": "modal-project",
                    "region": "us-test1",
                    "task_scope_digest": "sha256:" + "a" * 64,
                    "provider_receipt_digest": "sha256:" + "a" * 64,
                    "cleanup_contract_digest": "sha256:" + "a" * 64,
                    "exact_resource_ids": ["modal-app"],
                },
                "catalog_resolution_digest": CONTEXT.canonical_digest(resolution),
                "node_lease_id": "modal-lease",
                "instance_id": None,
                "boot_id": None,
            }
        )
        bundle["lease"] = None
        refresh_latest_context(bundle)
        with self.assertRaises(CONTEXT.ContextBindingError):
            CONTEXT.validate_binding(bundle)

    def test_fallback_context_is_append_only(self) -> None:
        CONTEXT.validate_binding(make_fallback_bundle())

    def test_fallback_cannot_skip_prior_context(self) -> None:
        bundle = make_fallback_bundle()
        bundle["context_commits"] = [bundle["context_commits"][1]]
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "first context"):
            CONTEXT.validate_binding(bundle)

    def test_fallback_cannot_silently_relabel_snapshot(self) -> None:
        bundle = make_fallback_bundle()
        bundle["context_commits"][0]["request"]["attempt_context"][
            "launch_strategy"
        ] = "conventional"
        bundle["context_commits"][0]["request"]["attempt_context"][
            "checkpoint_binding_digest"
        ] = None
        refresh_latest_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "silently relabels"):
            CONTEXT.validate_binding(bundle)

    def test_snapshot_context_binds_catalog_checkpoint(self) -> None:
        bundle = make_fallback_bundle()
        first = bundle["context_commits"][0]["request"]["attempt_context"]
        first["checkpoint_binding_digest"] = "sha256:" + "b" * 64
        refresh_latest_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "checkpoint binding"):
            CONTEXT.validate_binding(bundle)

    def test_resolution_denial_commits_without_fake_placement(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("resolution_denied", "catalog_selection", "backend", context=False)
        )

    def test_capacity_miss_commits_without_fake_context(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("capacity_miss", "placement", "capacity", context=False)
        )

    def test_runtime_failure_commits_with_context_but_no_success_receipts(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("runtime_failed", "runtime_launch", "backend", context=True)
        )

    def test_semantic_invalid_commits_with_context_but_no_client_success(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("semantic_invalid", "inference", "validation", context=True)
        )

    def test_cancellation_remains_in_failure_denominator(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("cancelled", "inference", "cancelled", context=True)
        )

    def test_deadline_failure_remains_in_denominator(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle("deadline_exceeded", "inference", "timeout", context=True)
        )

    def test_command_rejection_remains_in_denominator(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle(
                "command_rejected", "runtime_launch", "infrastructure", context=True
            )
        )

    def test_integrity_failure_remains_in_denominator(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle(
                "integrity_failure", "artifact_readiness", "infrastructure", context=True
            )
        )

    def test_failure_cannot_substitute_foreign_lease_or_resources(self) -> None:
        bundle = make_failure_bundle(
            "runtime_failed", "runtime_launch", "backend", context=True
        )
        context = bundle["placement"]["response"]["attempt_context"]
        context["node_lease_id"] = "foreign-lease"
        context["resource_binding"]["exact_resource_ids"] = ["foreign-instance"]
        refresh_failure_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "broker lease"):
            CONTEXT.validate_binding(bundle)

    def test_failure_context_must_remain_backend_eligible(self) -> None:
        bundle = make_failure_bundle(
            "runtime_failed", "runtime_launch", "backend", context=True
        )
        resolution = bundle["placement"]["request"]["catalog_resolution"]
        resolution["policy"]["eligible_backends"] = ["kubernetes"]
        context = bundle["placement"]["response"]["attempt_context"]
        context["catalog_resolution_digest"] = CONTEXT.canonical_digest(resolution)
        refresh_failure_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "policy eligible"):
            CONTEXT.validate_binding(bundle)

    def test_failure_fallback_chain_is_append_only(self) -> None:
        CONTEXT.validate_binding(
            make_failure_bundle(
                "runtime_failed",
                "runtime_launch",
                "backend",
                context=True,
                fallback=True,
            )
        )

    def test_failure_fallback_cannot_change_immutable_identity(self) -> None:
        bundle = make_failure_bundle(
            "runtime_failed",
            "runtime_launch",
            "backend",
            context=True,
            fallback=True,
        )
        bundle["context_commits"][1]["request"]["attempt_context"]["model_id"] = (
            "other-model"
        )
        refresh_failure_context(bundle)
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "immutable identity"):
            CONTEXT.validate_binding(bundle)

    def test_failure_path_t0_must_remain_target_neutral(self) -> None:
        bundle = make_failure_bundle(
            "capacity_miss", "placement", "capacity", context=False
        )
        accepted = bundle["ledger_events"][0]
        accepted["data"]["environment"].update(
            {
                "backend": "node-vm",
                "provider": "nebius",
                "node_id": "node-1",
                "gpu_type": "gpu-h100-sxm",
                "gpu_count": 1,
                "image_digest": "sha256:" + "a" * 64,
            }
        )
        bundle["accept_response"]["accepted_event_hash"] = CONTEXT.canonical_digest(
            accepted
        )
        bundle["terminal_commit"]["request"]["accepted_event_hash"] = bundle[
            "accept_response"
        ]["accepted_event_hash"]
        bundle["terminal_commit"]["request"]["ledger_digest"] = CONTEXT.canonical_digest(
            bundle["ledger_events"]
        )
        bundle["terminal_commit"]["response"]["commit_digest"] = CONTEXT.canonical_digest(
            bundle["terminal_commit"]["request"]
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "target-neutral"):
            CONTEXT.validate_binding(bundle)

    def test_failure_details_must_match_typed_error(self) -> None:
        bundle = make_failure_bundle(
            "runtime_failed", "runtime_launch", "backend", context=True
        )
        terminal = next(
            event for event in bundle["ledger_events"] if event["event_type"] == "attempt.failed"
        )
        terminal["data"]["reason"] = "different reason"
        bundle["terminal_commit"]["request"]["terminal_event_digest"] = (
            CONTEXT.canonical_digest(terminal)
        )
        bundle["terminal_commit"]["request"]["ledger_digest"] = CONTEXT.canonical_digest(
            bundle["ledger_events"]
        )
        bundle["terminal_commit"]["response"]["commit_digest"] = CONTEXT.canonical_digest(
            bundle["terminal_commit"]["request"]
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "details differ"):
            CONTEXT.validate_binding(bundle)

    def test_terminal_commit_receipt_must_be_canonical_and_aggregate_eligible(self) -> None:
        bundle = make_bundle()
        terminal = next(
            item for item in bundle["exchanges"] if item["operation"] == "CommitAttempt"
        )
        terminal["response"].update(
            {
                "commit_digest": "sha256:" + "b" * 64,
                "validation_status": "invalid",
                "aggregate_eligible": False,
            }
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "canonical"):
            CONTEXT.validate_binding(bundle)

    def test_pre_context_failure_cannot_invent_successful_placement(self) -> None:
        bundle = make_failure_bundle(
            "capacity_miss", "placement", "capacity", context=False
        )
        bundle["placement"] = make_bundle()["placement"]
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "cannot invent"):
            CONTEXT.validate_binding(bundle)

    def test_failure_terminal_digest_cannot_be_substituted(self) -> None:
        bundle = make_failure_bundle(
            "runtime_failed", "runtime_launch", "backend", context=True
        )
        bundle["terminal_commit"]["request"]["terminal_event_digest"] = (
            "sha256:" + "b" * 64
        )
        with self.assertRaisesRegex(CONTEXT.ContextBindingError, "attempt.failed"):
            CONTEXT.validate_binding(bundle)


if __name__ == "__main__":
    unittest.main()
