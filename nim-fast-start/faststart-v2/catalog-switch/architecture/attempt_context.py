#!/usr/bin/env python3
"""Validate the immutable post-T0 attempt context and receipt chain."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import jsonschema


ARCHITECTURE_DIR = Path(__file__).resolve().parent
FASTSTART_ROOT = ARCHITECTURE_DIR.parents[1]
CONTROL_SCHEMA_PATH = ARCHITECTURE_DIR / "control-plane-api.schema.json"
EVENT_SCHEMA_PATH = FASTSTART_ROOT / "performance/request_slo/event.schema.json"
HARNESS_PATH = FASTSTART_ROOT / "performance/request_slo/harness.py"
HARNESS_SPEC = importlib.util.spec_from_file_location("request_slo_harness", HARNESS_PATH)
assert HARNESS_SPEC and HARNESS_SPEC.loader
REQUEST_SLO = importlib.util.module_from_spec(HARNESS_SPEC)
HARNESS_SPEC.loader.exec_module(REQUEST_SLO)
REQUIRED_EXCHANGES = {
    "DispatchInference",
    "ValidateResponse",
    "CommitResponse",
    "CommitAttempt",
}
FRAGMENTS = {
    "DispatchInference": ("DispatchInferenceRequest", "DispatchInferenceResponse"),
    "ValidateResponse": ("ValidateResponseRequest", "ValidateResponseResponse"),
    "CommitResponse": ("CommitResponseRequest", "CommitResponseResponse"),
    "CommitAttempt": ("CommitAttemptRequest", "CommitAttemptResponse"),
    "ApplyNodeCommand": ("ApplyNodeCommandRequest", "ApplyNodeCommandResponse"),
}
FAILURE_CODE_BINDINGS = {
    "resolution_denied": ("ResolveCatalog", "backend", False),
    "capacity_miss": ("PlaceAttempt", "capacity", False),
    "deadline_exceeded": ("DispatchInference", "timeout", True),
    "command_rejected": ("ApplyNodeCommand", "infrastructure", True),
    "runtime_failed": ("DispatchInference", "backend", True),
    "semantic_invalid": ("ValidateResponse", "validation", True),
    "cancelled": ("DispatchInference", "cancelled", True),
    "integrity_failure": ("ApplyNodeCommand", "infrastructure", True),
}


class ContextBindingError(ValueError):
    """The context or a downstream receipt is not bound to the accepted attempt."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def placement_decision_digest(
    request: dict[str, Any], response: dict[str, Any]
) -> str:
    """Bind causal placement inputs without hashing the context recursively."""
    return canonical_digest(
        {
            "request": request,
            "decision": {
                "estimated_switch_cost_ms": response["estimated_switch_cost_ms"],
                "decision_evidence_digest": response["decision_evidence_digest"],
            },
        }
    )


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContextBindingError(f"{path} must contain an object")
    return value


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContextBindingError(f"{label} must contain exactly {sorted(expected)}")
    return value


def _validate_fragment(
    instance: dict[str, Any],
    definition: str,
    control_schema: dict[str, Any],
) -> None:
    resolver = jsonschema.RefResolver.from_schema(control_schema)
    validator = jsonschema.Draft202012Validator(
        control_schema["$defs"][definition],
        resolver=resolver,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = list(validator.iter_errors(instance))
    if errors:
        raise ContextBindingError(f"{definition}: {errors[0].message}")


def _same_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: tuple[str, ...],
    label: str,
) -> None:
    mismatched = [field for field in fields if left.get(field) != right.get(field)]
    if mismatched:
        raise ContextBindingError(f"{label} identity mismatch: {mismatched}")


def _validate_terminal_evidence(
    request: dict[str, Any],
    response: dict[str, Any],
    trace_request: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    accounting = next(event for event in events if event["event_type"] == "accounting.recorded")
    cleanup = next(event for event in events if event["event_type"] == "cleanup.finished")
    accepted = events[0]
    expected = {
        "trace_digest": canonical_digest(trace_request),
        "ledger_digest": canonical_digest(events),
        "accounting_digest": canonical_digest(accounting),
        "resource_inventory_digest": canonical_digest(accepted["data"]["ownership"]),
        "cleanup_receipt_digest": canonical_digest(cleanup),
    }
    mismatched = [key for key, value in expected.items() if request.get(key) != value]
    if mismatched:
        raise ContextBindingError(f"terminal evidence digest mismatch: {mismatched}")
    cleanup_status = cleanup["data"]["status"]
    if accepted["data"]["ownership"]["cleanup_required"] and not cleanup["data"].get(
        "receipt_sha256"
    ):
        raise ContextBindingError("owned-resource cleanup requires a receipt")
    expected_final_state = {
        "not_required": "absent",
        "complete": "absent",
        "retained": "retained",
        "failed": "quarantined",
    }[cleanup_status]
    if request.get("cleanup_final_state") != expected_final_state:
        raise ContextBindingError("terminal cleanup final state differs from ledger")
    if response.get("commit_digest") != canonical_digest(request):
        raise ContextBindingError("terminal commit receipt is not canonical")
    if response.get("validation_status") != "valid" or response.get(
        "aggregate_eligible"
    ) is not True:
        raise ContextBindingError("terminal attempt must be valid and aggregate eligible")


def _validate_internal_lease_ownership(
    context: dict[str, Any],
    lease: dict[str, Any],
    ownership: dict[str, Any],
) -> None:
    request = lease["request"]
    response = lease["response"]
    if response["state"] != "ACTIVE":
        raise ContextBindingError("attempt context requires an ACTIVE broker lease")
    exact_ids = set(response["exact_resource_ids"])
    if context["instance_id"] not in exact_ids:
        raise ContextBindingError("attempt context instance is outside exact broker resources")
    if context["node_lease_id"] != response["lease_id"]:
        raise ContextBindingError("attempt context uses a foreign resource lease")
    owned_resources = ownership.get("resources", [])
    if {
        resource.get("id") for resource in owned_resources if isinstance(resource, dict)
    } != exact_ids:
        raise ContextBindingError("v1 ownership differs from exact broker resources")
    if (
        ownership.get("owner_task_id") != request["owner_task_id"]
        or ownership.get("resource_prefix") != request["resource_prefix"]
        or ownership.get("dedicated") is not True
        or ownership.get("cleanup_required") is not True
    ):
        raise ContextBindingError("v1 ownership differs from exact broker lease policy")
    if any(
        resource.get("project_id") != request["project_id"]
        or resource.get("region") != request["region"]
        for resource in owned_resources
    ):
        raise ContextBindingError("v1 ownership project/region differs from broker lease")


def validate_binding(bundle: dict[str, Any]) -> None:
    if bundle.get("schema") == "catalog-switch-attempt-failure-binding/v1":
        _validate_failure_binding(bundle)
        return
    bundle = _exact_keys(
        bundle,
        {
            "schema",
            "trace_request",
            "ledger_events",
            "accept_response",
            "lease",
            "placement",
            "context_commits",
            "exchanges",
        },
        "binding bundle",
    )
    if bundle["schema"] != "catalog-switch-attempt-context-binding/v1":
        raise ContextBindingError("unexpected binding schema")

    control_schema = _load(CONTROL_SCHEMA_PATH)
    event_schema = _load(EVENT_SCHEMA_PATH)
    ledger_events = bundle["ledger_events"]
    if not isinstance(ledger_events, list) or not ledger_events:
        raise ContextBindingError("ledger_events must be a nonempty array")
    for index, event in enumerate(ledger_events, 1):
        jsonschema.Draft202012Validator(event_schema).validate(event)
        REQUEST_SLO._validate_event_shape(event, index)
    accepted = ledger_events[0]
    if accepted["event_type"] != "request.accepted":
        raise ContextBindingError("accepted_event must be request.accepted")
    trace_request = bundle["trace_request"]
    attempt_summary = REQUEST_SLO._validate_attempt(ledger_events, trace_request)
    if accepted["request_id"] != trace_request.get("request_id") or accepted[
        "attempt_id"
    ] != trace_request.get("attempt_id"):
        raise ContextBindingError("accepted event differs from trace request identity")
    if not attempt_summary["success"]:
        raise ContextBindingError("success binding requires response.validated terminal")
    terminal_event = next(
        event for event in ledger_events if event["event_type"] == "response.validated"
    )
    terminal_event_digest = canonical_digest(terminal_event)
    accepted_data = accepted["data"]
    if accepted_data.get("boundary") != "external-client-request-accepted/v1":
        raise ContextBindingError("accepted_event uses the wrong boundary")
    environment = accepted_data.get("environment", {})
    unresolved = {
        "backend": "catalog-router-unresolved",
        "provider": "catalog-ingress",
        "node_id": None,
        "gpu_type": None,
        "gpu_count": 0,
        "image_digest": None,
    }
    if any(environment.get(key) != value for key, value in unresolved.items()):
        raise ContextBindingError(
            "request.accepted environment must remain target-neutral and unresolved"
        )

    accept_response = bundle["accept_response"]
    _validate_fragment(accept_response, "AcceptRequestResponse", control_schema)
    accepted_hash = canonical_digest(accepted)
    if accept_response["accepted_event_hash"] != accepted_hash:
        raise ContextBindingError("accepted response hash does not bind accepted_event")
    _same_fields(
        accepted,
        accept_response,
        ("request_id", "attempt_id"),
        "accept response",
    )
    target = accepted_data.get("target", {})
    if accept_response["requested_model_id"] != target.get("model_id"):
        raise ContextBindingError("accepted model differs from the metric ledger")
    input_sha = accepted_data.get("input", {}).get("payload_sha256")
    if accept_response["input_digest"] != f"sha256:{input_sha}":
        raise ContextBindingError("accepted input digest differs from the metric ledger")

    placement = _exact_keys(bundle["placement"], {"request", "response"}, "placement")
    _validate_fragment(placement["request"], "PlaceAttemptRequest", control_schema)
    _validate_fragment(placement["response"], "PlaceAttemptResponse", control_schema)
    resolution = placement["request"]["catalog_resolution"]
    context = placement["response"]["attempt_context"]
    context_digest = canonical_digest(context)
    if placement["response"]["attempt_context_digest"] != context_digest:
        raise ContextBindingError("placement context digest is not canonical")
    _same_fields(
        accepted,
        context,
        ("request_id", "attempt_id"),
        "attempt context",
    )
    if context["accepted_event_hash"] != accepted_hash:
        raise ContextBindingError("attempt context does not bind accepted_event")
    if context["input_digest"] != accept_response["input_digest"]:
        raise ContextBindingError("attempt context input differs from acceptance")
    if context["catalog_resolution_digest"] != canonical_digest(resolution):
        raise ContextBindingError("attempt context does not bind catalog resolution")
    _same_fields(
        resolution,
        context,
        ("catalog_digest", "model_id", "model_version", "api_contract_digest", "input_schema_digest", "image_digest", "validator_digest"),
        "catalog resolution",
    )
    if context["artifact_digest"] != resolution["artifact"]["digest"]:
        raise ContextBindingError("attempt context artifact differs from resolution")
    # The reviewed v1 measurement ledger pre-resolves artifact identity. This
    # equality is compatibility evidence for those benchmark cohorts only; the
    # production model-id+input ingress needs the explicitly blocked v2
    # acceptance contract described by BLK-ACCEPTANCE-CONTRACT.
    if context["artifact_digest"] != "sha256:" + target["artifact_sha256"]:
        raise ContextBindingError("resolved artifact differs from v1 benchmark target")
    if context["backend"] not in resolution["policy"]["eligible_backends"]:
        raise ContextBindingError("attempt context backend is not policy eligible")
    if context["launch_strategy"] == "snapshot":
        checkpoint = resolution["checkpoint"]
        if checkpoint is None or context["checkpoint_binding_digest"] != checkpoint[
            "binding_digest"
        ]:
            raise ContextBindingError("attempt context checkpoint binding differs")
    elif context["checkpoint_binding_digest"] is not None:
        raise ContextBindingError("conventional context cannot retain checkpoint binding")
    if context["policy_digest"] != placement["request"]["policy_digest"]:
        raise ContextBindingError("attempt context policy differs from placement")
    if context["placement_decision_digest"] != placement_decision_digest(
        placement["request"], placement["response"]
    ):
        raise ContextBindingError("attempt context does not bind causal placement decision")
    resource_binding = context["resource_binding"]
    if context["backend"] in {"kubernetes", "node-vm"}:
        lease = _exact_keys(bundle["lease"], {"request", "response"}, "resource lease")
        _validate_fragment(lease["request"], "LeaseResourcesRequest", control_schema)
        _validate_fragment(lease["response"], "LeaseResourcesResponse", control_schema)
        _same_fields(
            lease["request"],
            lease["response"],
            ("plan_digest", "project_id", "region", "resource_prefix", "owner_task_id", "dedicated"),
            "resource lease receipt",
        )
        lease_binding_digest = canonical_digest(lease)
        expected_binding = {
            "kind": "internal_broker",
            "plan_digest": lease["request"]["plan_digest"],
            "lease_binding_digest": lease_binding_digest,
            "project_id": lease["request"]["project_id"],
            "region": lease["request"]["region"],
            "resource_prefix": lease["request"]["resource_prefix"],
            "owner_task_id": lease["request"]["owner_task_id"],
            "dedicated": True,
            "exact_resource_ids": lease["response"]["exact_resource_ids"],
        }
        if resource_binding != expected_binding:
            raise ContextBindingError("attempt context differs from exact broker lease")
        if context["node_lease_id"] != lease["response"]["lease_id"]:
            raise ContextBindingError("attempt context uses a foreign resource lease")
        _validate_internal_lease_ownership(
            context, lease, accepted_data["ownership"]
        )
    elif bundle["lease"] is not None:
        raise ContextBindingError("external provider context cannot claim an internal lease")

    context_commits = bundle["context_commits"]
    if not isinstance(context_commits, list) or len(context_commits) not in {1, 2}:
        raise ContextBindingError("context_commits must contain one launch or one fallback chain")
    previous_context: dict[str, Any] | None = None
    previous_commit_digest: str | None = None
    initial_context = context
    for index, raw_commit in enumerate(context_commits):
        context_commit = _exact_keys(
            raw_commit, {"request", "response"}, f"context commit {index + 1}"
        )
        _validate_fragment(
            context_commit["request"], "CommitAttemptContextRequest", control_schema
        )
        _validate_fragment(
            context_commit["response"], "CommitAttemptContextResponse", control_schema
        )
        commit_request = context_commit["request"]
        commit_response = context_commit["response"]
        current_context = commit_request["attempt_context"]
        current_digest = canonical_digest(current_context)
        _same_fields(
            initial_context,
            current_context,
            ("request_id", "attempt_id"),
            "context commit",
        )
        if commit_request["attempt_context_digest"] != current_digest:
            raise ContextBindingError("context commit body digest is not canonical")
        if index == 0 and current_context != initial_context:
            raise ContextBindingError("first context commit differs from placement")
        if previous_context is not None:
            mutable = {
                "context_version",
                "previous_context_commit_digest",
                "transition",
                "launch_strategy",
                "checkpoint_binding_digest",
                "created_at_utc",
                "created_at_monotonic_ns",
            }
            if any(
                current_context[key] != previous_context[key]
                for key in set(previous_context) - mutable
            ):
                raise ContextBindingError("fallback context changed immutable identity")
            if current_context["context_version"] != previous_context["context_version"] + 1:
                raise ContextBindingError("fallback context version is not contiguous")
            if current_context["previous_context_commit_digest"] != previous_commit_digest:
                raise ContextBindingError("fallback context does not bind prior commit")
            if previous_context["launch_strategy"] != "snapshot" or current_context[
                "launch_strategy"
            ] != "conventional":
                raise ContextBindingError("fallback context silently relabels launch strategy")
            if resolution["fallback_ladder"] != ["snapshot", "conventional", "fail"]:
                raise ContextBindingError("fallback context is absent from catalog ladder")
        expected_commit_digest = canonical_digest(commit_request)
        if commit_response["context_commit_digest"] != expected_commit_digest:
            raise ContextBindingError("context commit receipt is not canonical")
        if commit_response["context_version"] != current_context["context_version"]:
            raise ContextBindingError("context commit response version differs")
        _same_fields(
            commit_request,
            commit_response,
            ("request_id", "attempt_id", "attempt_context_digest"),
            "context commit response",
        )
        previous_context = current_context
        previous_commit_digest = expected_commit_digest
    context = previous_context
    assert context is not None and previous_commit_digest is not None
    expected_commit_digest = previous_commit_digest

    exchanges = bundle["exchanges"]
    if not isinstance(exchanges, list):
        raise ContextBindingError("exchanges must be an array")
    by_operation: dict[str, dict[str, Any]] = {}
    for index, raw_exchange in enumerate(exchanges):
        exchange = _exact_keys(
            raw_exchange, {"operation", "request", "response"}, f"exchange[{index}]"
        )
        operation = exchange["operation"]
        if operation not in FRAGMENTS:
            raise ContextBindingError(f"unsupported exchange operation: {operation}")
        if operation in by_operation and operation != "ApplyNodeCommand":
            raise ContextBindingError(f"duplicate exchange operation: {operation}")
        request_def, response_def = FRAGMENTS[operation]
        _validate_fragment(exchange["request"], request_def, control_schema)
        _validate_fragment(exchange["response"], response_def, control_schema)
        request_identity = exchange["request"]
        if operation == "ApplyNodeCommand":
            request_identity = exchange["request"]["signed_command"]["payload"]
        _same_fields(context, request_identity, ("request_id", "attempt_id"), operation)
        if request_identity["attempt_context_commit_digest"] != expected_commit_digest:
            raise ContextBindingError(f"{operation} uses a stale attempt context")
        by_operation[operation] = exchange
    missing = REQUIRED_EXCHANGES - set(by_operation)
    if missing:
        raise ContextBindingError(f"missing required exchanges: {sorted(missing)}")

    dispatch = by_operation["DispatchInference"]
    validation = by_operation["ValidateResponse"]
    response_commit = by_operation["CommitResponse"]
    terminal_commit = by_operation["CommitAttempt"]
    chain_fields = (
        "request_id",
        "attempt_id",
        "attempt_context_commit_digest",
        "node_lease_id",
        "generation",
        "runtime_identity",
        "inference_receipt_digest",
    )
    _same_fields(
        context,
        dispatch["request"],
        ("request_id", "attempt_id", "node_lease_id", "generation", "input_digest"),
        "dispatch context",
    )
    if dispatch["request"]["catalog_resolution_digest"] != context["catalog_resolution_digest"]:
        raise ContextBindingError("dispatch uses a stale catalog resolution")
    if accept_response["accepted_input_ref"]["digest"] != accept_response["input_digest"]:
        raise ContextBindingError("accepted input reference digest differs")
    if dispatch["request"]["accepted_input_ref"] != accept_response["accepted_input_ref"]:
        raise ContextBindingError("dispatch input reference differs from acceptance")
    _same_fields(dispatch["request"], dispatch["response"], chain_fields[:-1], "dispatch receipt")
    _same_fields(dispatch["response"], validation["request"], chain_fields, "validation input")
    _same_fields(
        dispatch["response"],
        validation["request"],
        ("raw_output_ref", "raw_output_digest"),
        "validation raw output",
    )
    _same_fields(validation["request"], validation["response"], chain_fields, "semantic receipt")
    _same_fields(validation["response"], response_commit["request"], chain_fields, "response commit")
    _same_fields(
        validation["response"],
        response_commit["request"],
        ("semantic_receipt_digest", "validated_output_ref", "validated_output_digest"),
        "validated output commit",
    )
    _same_fields(
        response_commit["request"],
        response_commit["response"],
        ("request_id", "attempt_id", "attempt_context_commit_digest"),
        "client response",
    )
    if response_commit["response"]["output"] != response_commit["request"][
        "validated_output_ref"
    ] or response_commit["response"]["output_digest"] != response_commit[
        "request"
    ]["validated_output_digest"]:
        raise ContextBindingError("client response differs from validated output")
    if response_commit["response"]["semantic_receipt_digest"] != response_commit[
        "request"
    ]["semantic_receipt_digest"]:
        raise ContextBindingError("client response semantic receipt differs")
    if response_commit["response"]["response_commit_digest"] != canonical_digest(
        response_commit["request"]
    ):
        raise ContextBindingError("client response commit receipt is not canonical")
    terminal_data = terminal_event["data"]
    if terminal_event["observed_monotonic_ns"] <= response_commit["response"][
        "committed_at_monotonic_ns"
    ]:
        raise ContextBindingError("product terminal must follow response commit and delivery")
    _same_fields(
        terminal_event["recorder"],
        response_commit["response"],
        ("recorder_id", "clock_id", "boot_id"),
        "external terminal clock",
    )
    if "sha256:" + terminal_data["validator_sha256"] != context["validator_digest"]:
        raise ContextBindingError("product terminal validator differs from context")
    if "sha256:" + terminal_data["response_sha256"] != response_commit["request"][
        "validated_output_digest"
    ]:
        raise ContextBindingError("product terminal output differs from validated output")
    if (terminal_data["model_id"], terminal_data["model_version"]) != (
        context["model_id"],
        context["model_version"],
    ):
        raise ContextBindingError("product terminal model differs from context")
    _same_fields(
        context,
        terminal_commit["request"],
        ("request_id", "attempt_id"),
        "terminal attempt commit",
    )
    if terminal_commit["request"]["attempt_context_commit_digest"] != expected_commit_digest:
        raise ContextBindingError("terminal attempt commit uses a stale context")
    if terminal_commit["request"]["accepted_event_hash"] != accepted_hash:
        raise ContextBindingError("terminal attempt commit does not bind acceptance")
    if terminal_commit["request"]["terminal_event_digest"] != terminal_event_digest:
        raise ContextBindingError("terminal attempt commit does not bind product terminal")
    if terminal_commit["request"]["terminal_outcome"] != "success" or terminal_commit[
        "request"
    ]["failure"] is not None:
        raise ContextBindingError("successful ledger must commit a success outcome")
    if terminal_commit["request"]["response_commit_digest"] != response_commit[
        "response"
    ]["response_commit_digest"]:
        raise ContextBindingError("terminal attempt commit does not bind client response")
    _validate_terminal_evidence(
        terminal_commit["request"],
        terminal_commit["response"],
        trace_request,
        ledger_events,
    )


def _validate_failure_binding(bundle: dict[str, Any]) -> None:
    """Validate a terminal attempt that never produced a successful response."""
    bundle = _exact_keys(
        bundle,
        {
            "schema",
            "trace_request",
            "ledger_events",
            "accept_response",
            "lease",
            "placement",
            "context_commits",
            "failure",
            "terminal_commit",
        },
        "failure binding bundle",
    )
    control_schema = _load(CONTROL_SCHEMA_PATH)
    event_schema = _load(EVENT_SCHEMA_PATH)
    events = bundle["ledger_events"]
    if not isinstance(events, list) or not events:
        raise ContextBindingError("ledger_events must be a nonempty array")
    for index, event in enumerate(events, 1):
        jsonschema.Draft202012Validator(event_schema).validate(event)
        REQUEST_SLO._validate_event_shape(event, index)
    summary = REQUEST_SLO._validate_attempt(events, bundle["trace_request"])
    if summary["success"]:
        raise ContextBindingError("failure binding requires attempt.failed terminal")
    accepted = events[0]
    terminal = next(event for event in events if event["event_type"] == "attempt.failed")
    accepted_hash = canonical_digest(accepted)
    terminal_digest = canonical_digest(terminal)

    accept_response = bundle["accept_response"]
    _validate_fragment(accept_response, "AcceptRequestResponse", control_schema)
    _same_fields(accepted, accept_response, ("request_id", "attempt_id"), "accept response")
    if accept_response["accepted_event_hash"] != accepted_hash:
        raise ContextBindingError("failure acceptance hash differs")
    input_sha = accepted["data"]["input"]["payload_sha256"]
    if accept_response["input_digest"] != f"sha256:{input_sha}":
        raise ContextBindingError("failure acceptance input differs")
    if accept_response["accepted_input_ref"]["digest"] != accept_response["input_digest"]:
        raise ContextBindingError("failure accepted input reference digest differs")
    accepted_data = accepted["data"]
    if accepted_data.get("boundary") != "external-client-request-accepted/v1":
        raise ContextBindingError("failure accepted event uses the wrong boundary")
    unresolved = {
        "backend": "catalog-router-unresolved",
        "provider": "catalog-ingress",
        "node_id": None,
        "gpu_type": None,
        "gpu_count": 0,
        "image_digest": None,
    }
    if any(
        accepted_data.get("environment", {}).get(key) != value
        for key, value in unresolved.items()
    ):
        raise ContextBindingError(
            "failure request.accepted environment must remain target-neutral and unresolved"
        )
    target = accepted_data.get("target", {})
    if accept_response["requested_model_id"] != target.get("model_id"):
        raise ContextBindingError("failure accepted model differs from metric ledger")

    failure = bundle["failure"]
    _validate_fragment(failure, "ErrorEnvelope", control_schema)
    code = failure["error"]["code"]
    binding = FAILURE_CODE_BINDINGS.get(code)
    if binding is None:
        raise ContextBindingError("failure code lacks a typed terminal binding")
    operation, failure_class, context_required = binding
    if failure["operation"] != operation or failure["stage"] != "post_accept":
        raise ContextBindingError("failure operation/stage differs from its typed code")
    if failure["terminal"] is not True:
        raise ContextBindingError("terminal attempt embeds a nonterminal failure")
    _same_fields(accepted, failure, ("request_id", "attempt_id"), "failure envelope")
    if terminal["data"]["failure_class"] != failure_class:
        raise ContextBindingError("failure class differs from the typed error code")
    if terminal["data"]["reason"] != failure["error"]["message"] or terminal[
        "data"
    ]["retryable"] is not failure["error"]["retryable"]:
        raise ContextBindingError("attempt.failed details differ from typed error")

    context_commits = bundle["context_commits"]
    latest_commit_digest: str | None = None
    if context_required:
        if not isinstance(context_commits, list) or not context_commits:
            raise ContextBindingError("post-placement failure requires committed attempt context")
        if bundle["placement"] is None:
            raise ContextBindingError("post-placement failure requires placement binding")
        placement = _exact_keys(bundle["placement"], {"request", "response"}, "placement")
        _validate_fragment(placement["request"], "PlaceAttemptRequest", control_schema)
        _validate_fragment(placement["response"], "PlaceAttemptResponse", control_schema)
        placed_context = placement["response"]["attempt_context"]
        if placement["response"]["attempt_context_digest"] != canonical_digest(placed_context):
            raise ContextBindingError("failure placement context digest is not canonical")
        _same_fields(
            accepted,
            placed_context,
            ("request_id", "attempt_id"),
            "failure attempt context",
        )
        if placed_context["accepted_event_hash"] != accepted_hash:
            raise ContextBindingError("failure context does not bind acceptance")
        if placed_context["input_digest"] != accept_response["input_digest"]:
            raise ContextBindingError("failure context input differs")
        resolution = placement["request"]["catalog_resolution"]
        if placed_context["catalog_resolution_digest"] != canonical_digest(resolution):
            raise ContextBindingError("failure context does not bind catalog resolution")
        _same_fields(
            resolution,
            placed_context,
            ("catalog_digest", "model_id", "model_version", "api_contract_digest", "input_schema_digest", "image_digest", "validator_digest"),
            "failure catalog resolution",
        )
        if placed_context["artifact_digest"] != resolution["artifact"]["digest"]:
            raise ContextBindingError("failure context artifact differs from resolution")
        if placed_context["artifact_digest"] != "sha256:" + accepted["data"]["target"][
            "artifact_sha256"
        ]:
            raise ContextBindingError("failure context artifact differs from v1 benchmark target")
        if placed_context["backend"] not in resolution["policy"]["eligible_backends"]:
            raise ContextBindingError("failure context backend is not policy eligible")
        if placed_context["policy_digest"] != placement["request"]["policy_digest"]:
            raise ContextBindingError("failure context policy differs from placement")
        if placed_context["placement_decision_digest"] != placement_decision_digest(
            placement["request"], placement["response"]
        ):
            raise ContextBindingError(
                "failure context does not bind causal placement decision"
            )
        if placed_context["launch_strategy"] == "snapshot":
            checkpoint = resolution["checkpoint"]
            if checkpoint is None or placed_context["checkpoint_binding_digest"] != checkpoint[
                "binding_digest"
            ]:
                raise ContextBindingError("failure context checkpoint binding differs")
        elif placed_context["checkpoint_binding_digest"] is not None:
            raise ContextBindingError("failure conventional context retains checkpoint binding")
        if len(context_commits) not in {1, 2}:
            raise ContextBindingError("failure context commits must contain one launch/fallback chain")
        previous_commit_digest: str | None = None
        previous_context: dict[str, Any] | None = None
        for index, commit in enumerate(context_commits):
            commit = _exact_keys(commit, {"request", "response"}, f"context commit {index + 1}")
            _validate_fragment(commit["request"], "CommitAttemptContextRequest", control_schema)
            _validate_fragment(commit["response"], "CommitAttemptContextResponse", control_schema)
            context = commit["request"]["attempt_context"]
            if index == 0 and context != placed_context:
                raise ContextBindingError("failure first context differs from placement")
            _same_fields(
                placed_context,
                context,
                ("request_id", "attempt_id"),
                "failure context commit",
            )
            if previous_context is not None:
                mutable = {
                    "context_version",
                    "previous_context_commit_digest",
                    "transition",
                    "launch_strategy",
                    "checkpoint_binding_digest",
                    "created_at_utc",
                    "created_at_monotonic_ns",
                }
                if any(
                    context[key] != previous_context[key]
                    for key in set(previous_context) - mutable
                ):
                    raise ContextBindingError("failure fallback context changed immutable identity")
                if context["context_version"] != previous_context["context_version"] + 1:
                    raise ContextBindingError("failure fallback version is not contiguous")
                if context["previous_context_commit_digest"] != previous_commit_digest:
                    raise ContextBindingError("failure context chain is discontinuous")
                if previous_context["launch_strategy"] != "snapshot" or context[
                    "launch_strategy"
                ] != "conventional":
                    raise ContextBindingError("failure fallback silently relabels launch strategy")
                if resolution["fallback_ladder"] != ["snapshot", "conventional", "fail"]:
                    raise ContextBindingError("failure fallback is absent from catalog ladder")
            context_digest = canonical_digest(context)
            if commit["request"]["attempt_context_digest"] != context_digest:
                raise ContextBindingError("failure context digest is not canonical")
            latest_commit_digest = canonical_digest(commit["request"])
            if commit["response"]["context_commit_digest"] != latest_commit_digest:
                raise ContextBindingError("failure context receipt is not canonical")
            if commit["response"]["context_version"] != context["context_version"]:
                raise ContextBindingError("failure context receipt version differs")
            _same_fields(
                commit["request"],
                commit["response"],
                ("request_id", "attempt_id", "attempt_context_digest"),
                "failure context receipt",
            )
            previous_commit_digest = latest_commit_digest
            previous_context = context
        if placed_context["backend"] in {"kubernetes", "node-vm"}:
            if bundle["lease"] is None:
                raise ContextBindingError("internal failure context requires broker lease")
            lease = _exact_keys(bundle["lease"], {"request", "response"}, "resource lease")
            _validate_fragment(lease["request"], "LeaseResourcesRequest", control_schema)
            _validate_fragment(lease["response"], "LeaseResourcesResponse", control_schema)
            _same_fields(
                lease["request"],
                lease["response"],
                ("plan_digest", "project_id", "region", "resource_prefix", "owner_task_id", "dedicated"),
                "failure resource lease receipt",
            )
            expected_binding = {
                "kind": "internal_broker",
                "plan_digest": lease["request"]["plan_digest"],
                "lease_binding_digest": canonical_digest(lease),
                "project_id": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "resource_prefix": lease["request"]["resource_prefix"],
                "owner_task_id": lease["request"]["owner_task_id"],
                "dedicated": True,
                "exact_resource_ids": lease["response"]["exact_resource_ids"],
            }
            if placed_context["resource_binding"] != expected_binding:
                raise ContextBindingError("failure context differs from broker lease")
            if placed_context["node_lease_id"] != lease["response"]["lease_id"]:
                raise ContextBindingError("failure context uses a foreign resource lease")
            _validate_internal_lease_ownership(
                placed_context, lease, accepted_data["ownership"]
            )
        elif bundle["lease"] is not None:
            raise ContextBindingError("external failure context cannot claim an internal lease")
    else:
        if context_commits != [] or bundle["placement"] is not None or bundle["lease"] is not None:
            raise ContextBindingError("pre-context failure cannot invent placement or lease success")

    terminal_commit = _exact_keys(
        bundle["terminal_commit"], {"request", "response"}, "terminal commit"
    )
    _validate_fragment(terminal_commit["request"], "CommitAttemptRequest", control_schema)
    _validate_fragment(terminal_commit["response"], "CommitAttemptResponse", control_schema)
    request = terminal_commit["request"]
    _same_fields(accepted, request, ("request_id", "attempt_id"), "terminal failure commit")
    if request["accepted_event_hash"] != accepted_hash:
        raise ContextBindingError("terminal failure does not bind acceptance")
    if request["terminal_event_digest"] != terminal_digest:
        raise ContextBindingError("terminal failure does not bind attempt.failed")
    if request["terminal_outcome"] != "failure" or request["failure"] != failure:
        raise ContextBindingError("terminal failure does not embed the typed failure")
    if request["response_commit_digest"] is not None:
        raise ContextBindingError("failed attempt cannot invent a response commit")
    if request["attempt_context_commit_digest"] != latest_commit_digest:
        raise ContextBindingError("terminal failure uses the wrong context receipt")
    _validate_terminal_evidence(
        request,
        terminal_commit["response"],
        bundle["trace_request"],
        events,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        validate_binding(_load(args.bundle))
    except (
        OSError,
        json.JSONDecodeError,
        jsonschema.ValidationError,
        REQUEST_SLO.HarnessError,
        ContextBindingError,
    ) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: attempt context and inference/validation/commit receipts are bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
