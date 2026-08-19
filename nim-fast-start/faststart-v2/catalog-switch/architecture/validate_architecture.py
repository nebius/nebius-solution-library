#!/usr/bin/env python3
"""Fail-closed semantic validation for the integrated architecture decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import jsonschema


ARCHITECTURE_DIR = Path(__file__).resolve().parent
FASTSTART_ROOT = ARCHITECTURE_DIR.parents[1]
ARCHITECTURE_PATH = ARCHITECTURE_DIR / "architecture.json"
API_CONTRACT_PATH = "catalog-switch/architecture/control-plane-api.schema.json"
CONTEXT_BINDING_PATH = "catalog-switch/architecture/attempt_context.py"

EMPIRICAL_BACKENDS = {"kubernetes", "node-vm", "cerebrium"}
INTERNAL_PROJECT_ALLOWLIST = {
    "project-e00z6b02t8ddk96c49",
    "project-u00tds8vpr00jaxa76s22d",
    "project-i00xz31gpr00xp9jhp982v",
}
SCENARIOS = {
    "same_model_hot",
    "idle_local",
    "a_to_b_local",
    "a_to_b_remote",
    "checkpoint_fallback",
    "capacity_miss",
}
RECOMMENDATION_STATUSES = {
    "approved",
    "experiment-required",
    "blocked",
    "rejected",
    "reference-only",
}
REQUIRED_RECOMMENDATION_IDS = {
    "R-METRIC",
    "R-CATALOG",
    "R-CONTROL-DATA-PLANE",
    "R-CACHE-PLACEMENT",
    "R-SNAPSHOT-FALLBACK",
    "R-CEREBRIUM",
    "R-MODAL-REFERENCE",
    "R-PRODUCTION-PROMOTION",
}
REQUIRED_GATE_IDS = {
    "G-CONTRACT",
    "G-LIVE-K8S",
    "G-LIVE-NODE",
    "G-LIVE-CEREBRIUM",
    "G-CEREBRIUM-SECURITY",
    "G-DRAIN",
    "G-SNAPSHOT",
    "G-COST",
    "G-CHAOS",
    "G-INDEPENDENT-REVIEW",
}
REQUIRED_BLOCKER_IDS = {
    "BLK-ACCEPTANCE-CONTRACT",
    "BLK-CONTROL-CHAIN",
    "BLK-DRAIN",
    "BLK-SNAPSHOT",
    "BLK-COST",
    "BLK-K8S-BROKER",
    "BLK-LIVE-BACKENDS",
    "BLK-CEREBRIUM-SECURITY",
    "BLK-STORAGE",
    "BLK-CHAOS",
    "BLK-PRODUCT-BUDGETS",
}
REQUIRED_EVIDENCE_STATUSES = {
    "E-METRIC-001": "accepted",
    "E-CATALOG-001": "accepted",
    "E-SECURITY-001": "accepted",
    "E-BROKER-001": "accepted",
    "E-OF2-PREPARED-001": "accepted",
    "E-BOLTZ-PREPARED-001": "accepted",
    "E-NODE-CPU-001": "accepted",
    "E-NODE-SUPERVISOR-001": "provisional",
    "E-K8S-CONTRACT-001": "provisional",
    "E-CEREBRIUM-001": "provisional",
    "E-CEREBRIUM-SECURITY-PENDING-001": "blocked",
    "E-SIM-001": "provisional",
    "E-STORAGE-CONTRACT-001": "provisional",
    "E-MODAL-REF-001": "reference-only",
    "E-DRAIN-REJECTED-001": "rejected",
    "E-SNAPSHOT-REJECTED-001": "rejected",
    "E-COST-PENDING-001": "blocked",
    "E-CHAOS-PENDING-001": "blocked",
}
REQUIRED_RECOMMENDATION_STATUSES = {
    "R-METRIC": "experiment-required",
    "R-CATALOG": "approved",
    "R-CONTROL-DATA-PLANE": "experiment-required",
    "R-CACHE-PLACEMENT": "experiment-required",
    "R-SNAPSHOT-FALLBACK": "approved",
    "R-CEREBRIUM": "experiment-required",
    "R-MODAL-REFERENCE": "reference-only",
    "R-PRODUCTION-PROMOTION": "blocked",
}
REQUIRED_GATE_REQUIREMENTS = {
    "G-CONTRACT": {
        "E-METRIC-001",
        "E-CATALOG-001",
        "E-SECURITY-001",
        API_CONTRACT_PATH,
        CONTEXT_BINDING_PATH,
        "BLK-ACCEPTANCE-CONTRACT",
        "BLK-CONTROL-CHAIN",
    },
    "G-LIVE-K8S": {"B-INTERNAL-SMALL", "B-INTERNAL-STORAGE", "B-INTERNAL-LARGE", "B-TRACE-REPLAY"},
    "G-LIVE-NODE": {"B-INTERNAL-SMALL", "B-INTERNAL-STORAGE", "B-TRACE-REPLAY"},
    "G-LIVE-CEREBRIUM": {"B-EXTERNAL-MATCHED-QWEN", "B-TRACE-REPLAY"},
    "G-CEREBRIUM-SECURITY": {"BLK-CEREBRIUM-SECURITY"},
    "G-DRAIN": {"BLK-DRAIN"},
    "G-SNAPSHOT": {"BLK-SNAPSHOT"},
    "G-COST": {"BLK-COST"},
    "G-CHAOS": {"B-CHAOS", "BLK-CHAOS"},
    "G-INDEPENDENT-REVIEW": {
        "catalog-switch/architecture/INDEPENDENT_REVIEW.md",
        "catalog-switch/architecture/review-records.v1.json@0c470620",
        "catalog-switch/architecture/evidence-index.v3.json",
        "catalog-switch/architecture/decision-matrix.v1.json",
    },
}
REQUIRED_BACKEND_GATES = {
    "kubernetes": {"G-LIVE-K8S", "G-DRAIN", "G-CHAOS", "G-COST"},
    "node-vm": {"G-LIVE-NODE", "G-DRAIN", "G-CHAOS", "G-COST"},
    "cerebrium": {"G-LIVE-CEREBRIUM", "G-CEREBRIUM-SECURITY", "G-CHAOS", "G-COST"},
}
EVIDENCE_STATUSES = {
    "accepted",
    "provisional",
    "rejected",
    "blocked",
    "reference-only",
}
REQUIRED_APIS = {
    "AcceptRequest",
    "ResolveCatalog",
    "PlaceAttempt",
    "CommitAttemptContext",
    "ApplyNodeCommand",
    "DispatchInference",
    "ValidateResponse",
    "CommitResponse",
    "LeaseResources",
    "CommitAttempt",
}
API_SPECS = {
    "AcceptRequest": ("edge-recorder", "AcceptRequestRequest", "AcceptRequestResponse"),
    "ResolveCatalog": ("catalog-control-plane", "ResolveCatalogRequest", "CatalogResolution"),
    "PlaceAttempt": ("router", "PlaceAttemptRequest", "PlaceAttemptResponse"),
    "CommitAttemptContext": (
        "evidence-ledger",
        "CommitAttemptContextRequest",
        "CommitAttemptContextResponse",
    ),
    "ApplyNodeCommand": ("node-agent", "ApplyNodeCommandRequest", "ApplyNodeCommandResponse"),
    "DispatchInference": ("data-plane-adapter", "DispatchInferenceRequest", "DispatchInferenceResponse"),
    "ValidateResponse": ("semantic-validator", "ValidateResponseRequest", "ValidateResponseResponse"),
    "CommitResponse": ("edge-recorder", "CommitResponseRequest", "CommitResponseResponse"),
    "LeaseResources": ("resource-broker", "LeaseResourcesRequest", "LeaseResourcesResponse"),
    "CommitAttempt": ("evidence-ledger", "CommitAttemptRequest", "CommitAttemptResponse"),
}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "generated_at",
    "decision_status",
    "evidence_index_update",
    "scope",
    "metric_contract",
    "evidence",
    "recommendations",
    "scenarios",
    "backends",
    "cache_policy",
    "budgets",
    "apis",
    "benchmark_matrix",
    "rollout_gates",
    "blockers",
}


class DuplicateKeyError(ValueError):
    """Raised when a JSON object contains a duplicate key."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _ids(items: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    values = [item.get("id") for item in items]
    missing = [index for index, value in enumerate(values) if not value]
    if missing:
        errors.append(f"{label} entries missing id at indexes {missing}")
    present = [value for value in values if isinstance(value, str)]
    if len(present) != len(set(present)):
        errors.append(f"{label} ids must be unique")
    return set(present)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _commit_exists(root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _source_blob_hash(root: Path, commit: str, relative_path: str) -> str | None:
    prefix_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-prefix"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if prefix_result.returncode != 0:
        return None
    repository_path = prefix_result.stdout.strip() + relative_path
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{repository_path}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return hashlib.sha256(result.stdout).hexdigest() if result.returncode == 0 else None


def _contains_forbidden_promotion_claim(value: str) -> bool:
    return bool(
        re.search(
            r"(?i)(wins?\s+production|production[- ]ready|production\s+(winner|eligible|proven)|product[- ]slo[- ]eligible|proves?.*\bwins?\b)",
            value,
        )
    )


def _schema_errors(data: dict[str, Any], root: Path) -> list[str]:
    schema_path = root / API_CONTRACT_PATH.replace(
        "control-plane-api.schema.json", "architecture.schema.json"
    )
    try:
        schema = load_json(schema_path)
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        return [
            "architecture schema: "
            + "/".join(str(part) for part in error.absolute_path)
            + f": {error.message}"
            for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path))
        ]
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        return [f"architecture schema unavailable or invalid: {exc}"]


def _resolve_local_ref(schema: dict[str, Any], ref: str) -> dict[str, Any] | None:
    prefix = f"{API_CONTRACT_PATH}#/$defs/"
    if not ref.startswith(prefix):
        return None
    definition = schema.get("$defs", {}).get(ref[len(prefix) :])
    return definition if isinstance(definition, dict) else None


def _control_schema_errors(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / API_CONTRACT_PATH
    try:
        schema = load_json(path)
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        return [f"control-plane API schema unavailable or invalid: {exc}"]

    definitions = schema.get("$defs", {})
    required_definitions = {
        "ErrorEnvelope",
        "InputPayload",
        "ImmutablePayloadRef",
        "CheckpointBinding",
        "AttemptContext",
        "FallbackTransition",
        "InternalResourceBinding",
        "ProviderResourceBinding",
        "SignedNodeCommand",
    } | {name for _, request, response in API_SPECS.values() for name in (request, response)}
    missing = required_definitions - set(definitions)
    if missing:
        errors.append(f"control-plane API schema missing definitions: {sorted(missing)}")
    for name in required_definitions - {"InputPayload"}:
        definition = definitions.get(name, {})
        if definition.get("type") != "object" or definition.get("additionalProperties") is not False:
            errors.append(f"control-plane API definition {name} must be a closed object")
        if not definition.get("required"):
            errors.append(f"control-plane API definition {name} must require fields")

    digest = "sha256:" + "a" * 64
    identifier = "id-1"
    payload_ref = {
        "kind": "immutable_ref",
        "uri": "https://artifacts.invalid/input/1",
        "digest": digest,
        "bytes": 1,
        "media_type": "application/json",
    }
    resolution = {
        "catalog_digest": digest,
        "model_id": "model-1",
        "model_version": "v1",
        "workload": "generation",
        "api_contract_digest": digest,
        "input_schema_digest": digest,
        "image_digest": digest,
        "artifact": {"digest": digest, "bytes": 1, "publication_id": identifier},
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
        "fallback_ladder": ["snapshot", "conventional", "fail"],
        "policy": {
            "tenant_eligible": True,
            "license_eligible": True,
            "required_secret_refs": [],
            "egress_policy_digest": digest,
            "eligible_backends": ["kubernetes"],
        },
    }
    probes: list[tuple[str, str, dict[str, Any], bool]] = [
        (
            "external request accepts model plus inline input without artifact authority",
            "AcceptRequestRequest",
            {
                "model_id": "model-1",
                "input": {"kind": "inline", "media_type": "application/json", "value": {"prompt": "x"}},
                "idempotency_key": identifier,
                "deadline_utc": "2026-08-19T16:00:00Z",
                "tenant_id": "tenant-1",
                "trace_context": {},
            },
            True,
        ),
        (
            "client cannot assert artifact authority",
            "AcceptRequestRequest",
            {
                "model_id": "model-1",
                "artifact_digest": digest,
                "input": payload_ref,
                "idempotency_key": identifier,
                "deadline_utc": "2026-08-19T16:00:00Z",
                "tenant_id": "tenant-1",
                "trace_context": {},
            },
            False,
        ),
        ("eligible snapshot ladder", "CatalogResolution", resolution, True),
        (
            "eligible conventional-only ladder",
            "CatalogResolution",
            {**resolution, "fallback_ladder": ["conventional", "fail"]},
            True,
        ),
        (
            "snapshot-only ladder is forbidden",
            "CatalogResolution",
            {**resolution, "fallback_ladder": ["snapshot"]},
            False,
        ),
        (
            "eligible snapshot requires immutable binding evidence",
            "CatalogResolution",
            {**resolution, "checkpoint": None},
            False,
        ),
        (
            "ineligible snapshot is forbidden",
            "CatalogResolution",
            {**resolution, "snapshot_status": "ineligible"},
            False,
        ),
        (
            "successful resolution requires eligible tenant policy",
            "CatalogResolution",
            {
                **resolution,
                "policy": {**resolution["policy"], "tenant_eligible": False},
            },
            False,
        ),
        (
            "pre-accept authentication error needs no request id",
            "ErrorEnvelope",
            {
                "error_schema_version": "catalog-switch-error/v1",
                "correlation_id": identifier,
                "operation": "AcceptRequest",
                "stage": "pre_accept",
                "terminal": True,
                "error": {"code": "authentication_denied", "message": "denied", "retryable": False, "details_digest": digest},
            },
            True,
        ),
        (
            "post-accept error requires request identity",
            "ErrorEnvelope",
            {
                "error_schema_version": "catalog-switch-error/v1",
                "correlation_id": identifier,
                "operation": "DispatchInference",
                "stage": "post_accept",
                "terminal": True,
                "error": {"code": "runtime_failed", "message": "failed", "retryable": False, "details_digest": digest},
            },
            False,
        ),
        (
            "signed node command exposes replay and binding fields",
            "ApplyNodeCommandRequest",
            {
                "idempotency_key": identifier,
                "signed_command": {
                    "schema_version": "catalog-switch-signed-node-command/v1",
                    "command_id": "command-1",
                    "node_command_sequence": 1,
                    "issued_at_utc": "2026-08-19T15:00:00Z",
                    "expires_at_utc": "2026-08-19T16:00:00Z",
                    "signer_key_id": "key-1",
                    "signature_algorithm": "Ed25519",
                    "signature": "signature",
                    "payload": {
                        "request_id": "request-1",
                        "attempt_id": "attempt-1",
                        "command_kind": "launch",
                        "attempt_context_commit_digest": digest,
                        "node_lease_id": "lease-1",
                        "instance_id": "instance-1",
                        "boot_id": "boot-1",
                        "generation": 1,
                        "model_binding_digest": digest,
                        "input_digest": digest,
                        "nonce": "nonce-1",
                        "from_state": "localized",
                        "to_state": "launched",
                        "parameters_digest": digest,
                    },
                },
            },
            True,
        ),
        (
            "opaque node command is forbidden",
            "ApplyNodeCommandRequest",
            {"idempotency_key": identifier, "signed_command": "opaque"},
            False,
        ),
        (
            "broker control error needs no request identity",
            "ErrorEnvelope",
            {
                "error_schema_version": "catalog-switch-error/v1",
                "correlation_id": identifier,
                "operation": "LeaseResources",
                "stage": "control",
                "terminal": True,
                "error": {"code": "capacity_miss", "message": "none", "retryable": True, "details_digest": digest},
            },
            True,
        ),
    ]
    resolver = jsonschema.RefResolver.from_schema(schema)
    for label, definition_name, instance, should_pass in probes:
        definition = definitions.get(definition_name)
        if not isinstance(definition, dict):
            continue
        validator = jsonschema.Draft202012Validator(
            definition,
            resolver=resolver,
            format_checker=jsonschema.FormatChecker(),
        )
        passed = not list(validator.iter_errors(instance))
        if passed != should_pass:
            errors.append(f"control-plane API semantic probe failed: {label}")
    root_validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    if root_validator.is_valid({"operation": "AcceptRequest", "request": {}}):
        errors.append("control-plane API root must reject an untyped empty request")
    return errors


def validate_document(data: dict[str, Any], root: Path = FASTSTART_ROOT) -> list[str]:
    errors: list[str] = _schema_errors(data, root)

    missing_top = REQUIRED_TOP_LEVEL - set(data)
    extra_top = set(data) - REQUIRED_TOP_LEVEL
    if missing_top:
        errors.append(f"missing top-level keys: {sorted(missing_top)}")
    if extra_top:
        errors.append(f"unknown top-level keys: {sorted(extra_top)}")
    if data.get("schema_version") != "catalog-switch-production-architecture/v1":
        errors.append("unexpected schema_version")
    if data.get("decision_status") != "conditional":
        errors.append("decision must remain conditional while blockers are open")

    scope = data.get("scope", {})
    empirical = set(scope.get("empirical_backends", []))
    if empirical != EMPIRICAL_BACKENDS:
        errors.append(f"empirical backends must be exactly {sorted(EMPIRICAL_BACKENDS)}")
    if set(scope.get("reference_only", [])) != {"modal"}:
        errors.append("Modal must be the sole reference-only backend")
    if set(scope.get("forbidden_empirical", [])) != {"modal"}:
        errors.append("Modal must be explicitly forbidden from empirical work")
    if scope.get("jira_mutation_allowed") is not False:
        errors.append("Jira mutation must be false")
    if set(scope.get("internal_project_allowlist", [])) != INTERNAL_PROJECT_ALLOWLIST:
        errors.append("internal project allowlist must match the exact three approved projects")

    metric = data.get("metric_contract", {})
    if set(metric.get("required_scenarios", [])) != SCENARIOS:
        errors.append("metric contract must name exactly the six canonical scenarios")
    if metric.get("t0") != "external-client-request-accepted/v1":
        errors.append("T0 boundary changed")
    if metric.get("success") != "first-complete-semantically-valid-response/v1":
        errors.append("success boundary changed")
    if metric.get("all_attempts_retained") is not True:
        errors.append("all attempts must remain in the denominator")
    if metric.get("phase_percentiles_additive") is not False:
        errors.append("phase percentiles cannot be additive")
    if metric.get("request_specific_work_before_t0_allowed") is not False:
        errors.append("request-specific work before T0 is forbidden")
    if metric.get("ingress_compatibility") != "blocked-v2-model-input-acceptance-required":
        errors.append("v1 metric/product-ingress incompatibility must remain explicit")
    if metric.get("compatibility_blocker") != "BLK-ACCEPTANCE-CONTRACT":
        errors.append("metric compatibility must bind BLK-ACCEPTANCE-CONTRACT")
    minimums = metric.get("percentile_minimum_samples", {})
    if minimums != {"p50": 2, "p95": 20, "p99": 100}:
        errors.append("percentile sample gates changed")

    evidence = data.get("evidence", [])
    evidence_ids = _ids(evidence, "evidence", errors)
    if evidence_ids != set(REQUIRED_EVIDENCE_STATUSES):
        errors.append("evidence ids must match the exact normative v1 set")
    evidence_by_id = {item.get("id"): item for item in evidence if item.get("id")}
    for item in evidence:
        evidence_id = item.get("id", "<missing>")
        if item.get("status") not in EVIDENCE_STATUSES:
            errors.append(f"{evidence_id}: invalid evidence status")
        if item.get("status") != REQUIRED_EVIDENCE_STATUSES.get(evidence_id):
            errors.append(f"{evidence_id}: evidence status changed from the normative v1 decision")
        path_value = item.get("path")
        expected_hash = item.get("sha256")
        if path_value is None:
            if item.get("status") not in {"rejected", "blocked"}:
                errors.append(f"{evidence_id}: only rejected/blocked evidence may lack a path")
            if expected_hash is not None:
                errors.append(f"{evidence_id}: pathless evidence cannot claim a file hash")
        else:
            raw_path = Path(path_value) if isinstance(path_value, str) else Path(".")
            path = root / raw_path
            contained = (
                isinstance(path_value, str)
                and not raw_path.is_absolute()
                and ".." not in raw_path.parts
                and path.resolve().is_relative_to(root.resolve())
                and not path.is_symlink()
            )
            if not contained:
                errors.append(f"{evidence_id}: evidence path must be a contained regular file")
            elif not path.is_file():
                errors.append(f"{evidence_id}: evidence path missing: {path_value}")
            elif _sha256(path) != expected_hash:
                errors.append(f"{evidence_id}: sha256 mismatch for {path_value}")
        source_commit = item.get("source_commit")
        if item.get("status") != "blocked" and source_commit is None:
            errors.append(f"{evidence_id}: non-blocked evidence requires source_commit")
        if source_commit is not None:
            if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{7,40}", source_commit):
                errors.append(f"{evidence_id}: source_commit must be a hexadecimal Git commit")
            elif not _commit_exists(root, source_commit):
                errors.append(f"{evidence_id}: source_commit is not present in repository history")
            elif path_value is not None and _source_blob_hash(root, source_commit, path_value) != expected_hash:
                errors.append(f"{evidence_id}: source_commit/path blob does not match sha256")
        claim = str(item.get("allowed_claim", ""))
        if _contains_forbidden_promotion_claim(claim):
            errors.append(f"{evidence_id}: allowed_claim contains a forbidden production/winner claim")
        if item.get("kind") == "prepared-node-internal-stage" and item.get(
            "product_slo_eligible"
        ):
            errors.append(f"{evidence_id}: prepared-node evidence cannot be product eligible")
        if item.get("status") != "accepted" and item.get("product_slo_eligible"):
            errors.append(f"{evidence_id}: non-accepted evidence cannot be product eligible")
    if data.get("decision_status") == "conditional" and any(
        item.get("product_slo_eligible") for item in evidence
    ):
        errors.append("conditional package cannot contain product-SLO-eligible evidence")
    security_evidence = evidence_by_id.get("E-SECURITY-001", {})
    if set(security_evidence.get("applicable_backends", [])) != {"kubernetes", "node-vm"}:
        errors.append("reviewed security evidence must be bounded to internal backends")
    if set(security_evidence.get("excluded_backends", [])) != {"cerebrium", "modal"}:
        errors.append("reviewed security evidence must explicitly exclude Cerebrium and Modal")
    expected_security_counts = {
        "source_control_count": 21,
        "source_test_family_count": 17,
        "internal_control_count": 20,
        "internal_test_family_count": 16,
        "legacy_modal_only_controls": ["CTL-17"],
        "legacy_modal_only_test_families": ["TST-14"],
    }
    if any(security_evidence.get(key) != value for key, value in expected_security_counts.items()):
        errors.append("reviewed security evidence must preserve exact source/internal coverage counts")
    cerebrium_security = evidence_by_id.get("E-CEREBRIUM-SECURITY-PENDING-001", {})
    if cerebrium_security.get("status") != "blocked":
        errors.append("missing blocked Cerebrium provider-boundary security evidence")

    recommendations = data.get("recommendations", [])
    recommendation_ids = _ids(recommendations, "recommendation", errors)
    if recommendation_ids != REQUIRED_RECOMMENDATION_IDS:
        errors.append("recommendation ids must match the exact normative v1 set")
    for recommendation in recommendations:
        recommendation_id = recommendation.get("id", "<missing>")
        status = recommendation.get("status")
        if status not in RECOMMENDATION_STATUSES:
            errors.append(f"{recommendation_id}: invalid recommendation status")
        if status != REQUIRED_RECOMMENDATION_STATUSES.get(recommendation_id):
            errors.append(f"{recommendation_id}: recommendation status changed from the normative v1 decision")
        refs = recommendation.get("evidence_ids", [])
        if not refs:
            errors.append(f"{recommendation_id}: must cite evidence")
        dangling = set(refs) - evidence_ids
        if dangling:
            errors.append(f"{recommendation_id}: unknown evidence ids {sorted(dangling)}")
        if status == "approved" and not any(
            evidence_by_id.get(ref, {}).get("status") == "accepted" for ref in refs
        ):
            errors.append(f"{recommendation_id}: approved recommendation lacks accepted evidence")
        if _contains_forbidden_promotion_claim(str(recommendation.get("statement", ""))):
            errors.append(f"{recommendation_id}: statement contains a forbidden production/winner claim")

    scenarios = data.get("scenarios", [])
    scenario_names = {item.get("name") for item in scenarios}
    if scenario_names != SCENARIOS or len(scenarios) != len(SCENARIOS):
        errors.append("scenario routing must cover each canonical scenario exactly once")
    for scenario in scenarios:
        for key in ("route", "fallback", "implementation_status", "required_tier"):
            if not scenario.get(key):
                errors.append(f"scenario {scenario.get('name')}: missing {key}")

    backends = data.get("backends", [])
    backend_names = {item.get("name") for item in backends}
    if backend_names != EMPIRICAL_BACKENDS or len(backends) != len(EMPIRICAL_BACKENDS):
        errors.append("backend dispositions must cover exactly Kubernetes, node-vm, Cerebrium")
    for backend in backends:
        if backend.get("production_disposition") != "not-promoted":
            errors.append(f"{backend.get('name')}: no backend may be promoted yet")
        if not backend.get("promotion_gates"):
            errors.append(f"{backend.get('name')}: missing promotion gates")
        if set(backend.get("promotion_gates", [])) != REQUIRED_BACKEND_GATES.get(
            backend.get("name"), set()
        ):
            errors.append(f"{backend.get('name')}: promotion gates changed from the normative v1 set")
        dangling = set(backend.get("evidence_ids", [])) - evidence_ids
        if dangling:
            errors.append(f"{backend.get('name')}: unknown evidence ids {sorted(dangling)}")

    matrix = data.get("benchmark_matrix", [])
    matrix_ids = _ids(matrix, "benchmark", errors)
    for cell in matrix:
        cell_id = cell.get("id", "<missing>")
        cell_backends = set(cell.get("backends", []))
        if not cell_backends or not cell_backends <= EMPIRICAL_BACKENDS:
            errors.append(f"{cell_id}: invalid empirical backend set")
        if "modal" in json.dumps(cell).lower():
            errors.append(f"{cell_id}: Modal is forbidden in benchmark rows")
        cell_scenarios = set(cell.get("scenarios", []))
        if not cell_scenarios or not cell_scenarios <= SCENARIOS:
            errors.append(f"{cell_id}: invalid scenarios")
        if cell.get("attempts_per_homogeneous_cell", 0) < minimums.get("p95", 20):
            errors.append(f"{cell_id}: too few attempts for p95")
        if cell.get("status") != "blocked":
            errors.append(f"{cell_id}: all live benchmark rows must remain blocked")

    blockers = data.get("blockers", [])
    blocker_ids = _ids(blockers, "blocker", errors)
    if blocker_ids != REQUIRED_BLOCKER_IDS:
        errors.append("blocker ids must match the exact normative v1 set")
    if "BLK-CEREBRIUM-SECURITY" not in blocker_ids:
        errors.append("Cerebrium security blocker is required")
    for blocker in blockers:
        if not blocker.get("owner_task") or not blocker.get("exit"):
            errors.append(f"{blocker.get('id')}: blocker needs owner and exit criteria")

    gates = data.get("rollout_gates", [])
    gate_ids = _ids(gates, "rollout gate", errors)
    if gate_ids != REQUIRED_GATE_IDS:
        errors.append("rollout gate ids must match the exact normative v1 set")
    allowed_gate_refs = evidence_ids | matrix_ids | blocker_ids | {
        "catalog-switch/architecture/INDEPENDENT_REVIEW.md",
        "catalog-switch/architecture/review-records.v1.json@0c470620",
        "catalog-switch/architecture/evidence-index.v3.json",
        "catalog-switch/architecture/decision-matrix.v1.json",
        API_CONTRACT_PATH,
        CONTEXT_BINDING_PATH,
    }
    for gate in gates:
        gate_id = gate.get("id", "<missing>")
        unknown = set(gate.get("requires", [])) - allowed_gate_refs
        if unknown:
            errors.append(f"{gate_id}: unknown requirements {sorted(unknown)}")
        if gate.get("status") == "pass":
            errors.append(f"{gate_id}: no gate may pass while acceptance v2 is blocked")
        if set(gate.get("requires", [])) != REQUIRED_GATE_REQUIREMENTS.get(gate_id, set()):
            errors.append(f"{gate_id}: requirements changed from the normative v1 gate")
        if gate_id == "G-CONTRACT" and gate.get("status") != "blocked":
            errors.append("G-CONTRACT must remain blocked on acceptance v2")
        elif gate_id == "G-INDEPENDENT-REVIEW" and gate.get("status") not in {
            "pending",
            "conditional-sign-off",
        }:
            errors.append("G-INDEPENDENT-REVIEW must remain pending or conditional-sign-off")
        elif gate_id not in {"G-CONTRACT", "G-INDEPENDENT-REVIEW"} and gate.get("status") != "blocked":
            errors.append(f"{gate_id}: unresolved promotion gate must remain blocked")
    contract_gate = next((gate for gate in gates if gate.get("id") == "G-CONTRACT"), {})
    expected_contract_requirements = {
        "E-METRIC-001",
        "E-CATALOG-001",
        "E-SECURITY-001",
        API_CONTRACT_PATH,
        CONTEXT_BINDING_PATH,
        "BLK-ACCEPTANCE-CONTRACT",
        "BLK-CONTROL-CHAIN",
    }
    if contract_gate.get("status") != "blocked" or set(contract_gate.get("requires", [])) != expected_contract_requirements:
        errors.append("G-CONTRACT must remain blocked with the exact contract requirements")
    for evidence_id in expected_contract_requirements & evidence_ids:
        if evidence_by_id.get(evidence_id, {}).get("status") != "accepted":
            errors.append(f"G-CONTRACT requirement {evidence_id} must be accepted")
    if not (root / CONTEXT_BINDING_PATH).is_file():
        errors.append("G-CONTRACT attempt-context binding validator is missing")
    backend_gate_refs = {
        value for backend in backends for value in backend.get("promotion_gates", [])
    }
    if backend_gate_refs - gate_ids:
        errors.append(f"backend references unknown gates: {sorted(backend_gate_refs - gate_ids)}")
    cerebrium_backend = next(
        (backend for backend in backends if backend.get("name") == "cerebrium"), {}
    )
    if "G-CEREBRIUM-SECURITY" not in cerebrium_backend.get("promotion_gates", []):
        errors.append("Cerebrium backend must depend on its provider-boundary security gate")

    budgets = data.get("budgets", {})
    universal = budgets.get("universal_promotion", {})
    if universal.get("minimum_attempts", 0) < 100:
        errors.append("universal promotion requires enough samples for p99")
    if universal.get("success_rate_min") != 0.99:
        errors.append("success_rate_min must remain 0.99")
    for zero_field in (
        "semantic_invalid_successes_max",
        "duplicate_responses_max",
        "unaccounted_attempts_max",
    ):
        if universal.get(zero_field) != 0:
            errors.append(f"{zero_field} must remain zero")
    for full_field in ("cleanup_receipt_rate", "gpu_scrub_receipt_rate", "cost_receipt_rate"):
        if universal.get(full_field) != 1.0:
            errors.append(f"{full_field} must remain 1.0")
    latency_classes = {item.get("name"): item for item in budgets.get("latency_classes", [])}
    if set(latency_classes) != {"fast-switch", "standard-on-demand", "large-multi-gpu"}:
        errors.append("latency classes are incomplete")
    for name in ("fast-switch", "standard-on-demand", "large-multi-gpu"):
        budget = latency_classes.get(name, {})
        if budget.get("p95_seconds_max") is not None:
            errors.append(f"{name}: absolute p95 cannot be invented before ratification")
        if budget.get("p99_seconds_max") is not None:
            errors.append(f"{name}: absolute p99 cannot be invented before ratification")
        if budget.get("status") != "blocking-owner-ratification":
            errors.append(f"{name}: missing owner-ratification placeholder")
    if budgets.get("capacity_formula") != {
        "version": "catalog-switch-capacity-formula/v1",
        "arrival_rate_statistic": "p95_per_second",
        "occupancy_statistic": "p95_seconds",
        "utilization_target": 0.7,
        "minimum_base_slots": 1,
        "preemptible_failover_slots_input": True,
        "implementation": "catalog-switch/architecture/capacity_budget.py",
    }:
        errors.append("capacity formula must match the executable provisional v1 contract")
    if not (root / "catalog-switch/architecture/capacity_budget.py").is_file():
        errors.append("capacity formula implementation is missing")
    if any(
        value is not None
        for value in budgets.get("campaign_hard_caps_usd", {}).values()
    ):
        errors.append("campaign cost caps must remain null placeholders until approved")

    apis = data.get("apis", [])
    api_names = {item.get("name") for item in apis}
    if api_names != REQUIRED_APIS:
        errors.append(f"API surface must be exactly {sorted(REQUIRED_APIS)}")
    try:
        api_schema = load_json(root / API_CONTRACT_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        api_schema = {}
        errors.append(f"control-plane API schema unavailable or invalid: {exc}")
    for api in apis:
        name = api.get("name")
        expected = API_SPECS.get(name)
        if expected is None:
            continue
        owner, request_name, response_name = expected
        expected_request = f"{API_CONTRACT_PATH}#/$defs/{request_name}"
        expected_response = f"{API_CONTRACT_PATH}#/$defs/{response_name}"
        expected_failure = f"{API_CONTRACT_PATH}#/$defs/ErrorEnvelope"
        if api.get("owner") != owner:
            errors.append(f"{name}: owner must be {owner}")
        if api.get("request_schema") != expected_request or _resolve_local_ref(api_schema, expected_request) is None:
            errors.append(f"{name}: request schema is missing or incorrect")
        if api.get("response_schema") != expected_response or _resolve_local_ref(api_schema, expected_response) is None:
            errors.append(f"{name}: response schema is missing or incorrect")
        if api.get("failure_schema") != expected_failure or _resolve_local_ref(api_schema, expected_failure) is None:
            errors.append(f"{name}: failure schema is missing or incorrect")
        if not api.get("idempotency"):
            errors.append(f"{name}: idempotency semantics are required")
    errors.extend(_control_schema_errors(root))

    cache_policy = data.get("cache_policy", {})
    if [tier.get("name") for tier in cache_policy.get("tiers", [])] != [
        "L0_gpu_resident",
        "L1_verified_local",
        "L2_remote_immutable",
    ]:
        errors.append("cache tiers must remain ordered L0/L1/L2")
    if cache_policy.get("prefetch_default") != "disabled":
        errors.append("prefetch must default disabled until measured")
    if cache_policy.get("eviction", {}).get("status") != "unranked":
        errors.append("eviction policy cannot be ranked from placeholders")

    threat_path = root / "catalog-switch/security-reliability/threat_model.json"
    if threat_path.is_file():
        threat = load_json(threat_path)
        if threat.get("status") != "reviewed":
            errors.append("threat model is not reviewed")
        if len(threat.get("controls", [])) != 21:
            errors.append("expected 21 reviewed security controls")
        internal_controls = [
            control
            for control in threat.get("controls", [])
            if any(
                control.get("backends", {}).get(backend) != "not-applicable"
                for backend in ("k8s", "k8s-hotpath", "node-vm")
            )
        ]
        if len(internal_controls) != 20:
            errors.append("expected exactly 20 internal security controls")
        modal_only_controls = {
            control.get("id")
            for control in threat.get("controls", [])
            if control not in internal_controls
        }
        if modal_only_controls != {"CTL-17"}:
            errors.append("expected CTL-17 to be the sole legacy Modal-only control")
        internal_tests = [
            test
            for test in threat.get("tests", [])
            if any(pilot != "modal" for pilot in test.get("pilots", []))
        ]
        if len(threat.get("tests", [])) != 17 or len(internal_tests) != 16:
            errors.append("expected 17 total and 16 internal security test families")
        modal_only_tests = {
            test.get("id")
            for test in threat.get("tests", [])
            if test not in internal_tests
        }
        if modal_only_tests != {"TST-14"}:
            errors.append("expected TST-14 to be the sole legacy Modal-only test family")
        threat_backends = {backend.get("id") for backend in threat.get("backends", [])}
        if threat_backends != {"k8s", "k8s-hotpath", "node-vm", "modal"}:
            errors.append("unexpected reviewed threat-model backend scope")
        if "cerebrium" in threat_backends:
            errors.append("legacy threat model must not be mislabeled as Cerebrium coverage")
        open_findings = [
            finding.get("id")
            for finding in threat.get("review_findings", [])
            if finding.get("status") != "closed"
        ]
        if open_findings:
            errors.append(f"threat model has open findings: {open_findings}")
    else:
        errors.append("reviewed threat model is missing")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ARCHITECTURE_PATH)
    args = parser.parse_args()
    try:
        data = load_json(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    errors = validate_document(data)
    if errors:
        print("FAIL: architecture decision is invalid")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "PASS: conditional architecture validated "
        f"({len(data['evidence'])} evidence entries, "
        f"{len(data['recommendations'])} recommendations, "
        f"{len(data['blockers'])} explicit blockers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
