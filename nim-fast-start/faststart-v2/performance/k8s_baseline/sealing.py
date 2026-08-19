#!/usr/bin/env python3
"""Atomic final-evidence sealing and replay verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from performance.request_slo.harness import canonical_json, canonical_sha256

from .contract import BaselineError


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, value: Any) -> None:
    """Create one canonical JSON file via fsync + atomic rename, never overwrite."""

    if os.path.lexists(path):
        raise BaselineError(f"sealed output already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        payload = (canonical_json(value) + "\n").encode()
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Create one immutable byte-for-byte evidence member via fsync + rename."""

    if os.path.lexists(path):
        raise BaselineError(f"sealed output already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def seal_run(
    output: Path,
    *,
    receipt_payload: dict[str, Any],
    ledger_path: Path,
    evidence_path: Path,
    aggregate_path: Path,
    cleanup_path: Path,
) -> dict[str, Any]:
    """Jointly bind final cleanup, evidence, aggregate, ledger, and receipt payload."""

    files = {
        "ledger.jsonl": ledger_path,
        "backend-evidence.json": evidence_path,
        "aggregate.json": aggregate_path,
        "cohort-cleanup.json": cleanup_path,
    }
    for name, path in files.items():
        if not path.is_file() or path.is_symlink():
            raise BaselineError(f"cannot seal missing/non-regular {name}")
    manifest = {
        "schema": "archvteams.nebius.ai/k8s-evidence-seal/v2",
        "files": {name: file_sha256(path) for name, path in sorted(files.items())},
        "receipt_payload_sha256": canonical_sha256(receipt_payload),
        "final_cleanup_sha256": file_sha256(cleanup_path),
    }
    seal_path = output / "evidence-seal.json"
    atomic_write_json(seal_path, manifest)
    receipt = {
        **receipt_payload,
        "evidence_seal_path": str(seal_path),
        "evidence_seal_sha256": file_sha256(seal_path),
    }
    atomic_write_json(output / "receipt.json", receipt)
    verify_seal(output)
    return receipt


def seal_staging(
    output: Path,
    *,
    receipt_payload: dict[str, Any],
    ledger_path: Path,
    evidence_path: Path,
    aggregate_path: Path,
    cleanup_path: Path,
) -> dict[str, Any]:
    """Seal immutable workload evidence while broker release is still pending."""

    files = {
        "ledger.jsonl": ledger_path,
        "backend-evidence.json": evidence_path,
        "aggregate.json": aggregate_path,
        "cohort-cleanup.json": cleanup_path,
    }
    for name, path in files.items():
        if not path.is_file() or path.is_symlink():
            raise BaselineError(f"cannot stage missing/non-regular {name}")
    manifest = {
        "schema": "archvteams.nebius.ai/k8s-workload-staging-seal/v1",
        "files": {name: file_sha256(path) for name, path in sorted(files.items())},
        "receipt_payload_sha256": canonical_sha256(receipt_payload),
        "workload_cleanup_sha256": file_sha256(cleanup_path),
        "promotion_allowed": False,
        "required_next_step": "consume typed broker final-cleanup receipt into a new final seal",
    }
    seal_path = output / "evidence-seal.json"
    atomic_write_json(seal_path, manifest)
    receipt = {
        **receipt_payload,
        "evidence_seal_path": str(seal_path),
        "evidence_seal_sha256": file_sha256(seal_path),
    }
    atomic_write_json(output / "receipt.json", receipt)
    verify_seal(output)
    return receipt


def verify_seal(output: Path) -> dict[str, Any]:
    """Replay a final seal and reject any stale or mutated evidence member."""

    seal_path = output / "evidence-seal.json"
    receipt_path = output / "receipt.json"
    try:
        manifest = json.loads(seal_path.read_text())
        receipt = json.loads(receipt_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError("sealed evidence is unreadable") from exc
    schema = manifest.get("schema")
    if schema not in {
        "archvteams.nebius.ai/k8s-evidence-seal/v2",
        "archvteams.nebius.ai/k8s-workload-staging-seal/v1",
    }:
        raise BaselineError("evidence seal schema is invalid")
    if receipt.get("evidence_seal_sha256") != file_sha256(seal_path):
        raise BaselineError("receipt points to a stale evidence seal")
    payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"evidence_seal_path", "evidence_seal_sha256"}
    }
    if manifest.get("receipt_payload_sha256") != canonical_sha256(payload):
        raise BaselineError("receipt payload differs from the joint seal")
    receipt_hash_fields = {
        "ledger_sha256": "ledger.jsonl",
        "backend_evidence_sha256": "backend-evidence.json",
        "aggregate_sha256": "aggregate.json",
        "cohort_cleanup_sha256": "cohort-cleanup.json",
    }
    for field, name in receipt_hash_fields.items():
        if field in payload and payload[field] != manifest.get("files", {}).get(name):
            raise BaselineError(f"receipt {field} is stale")
    for name, expected in manifest.get("files", {}).items():
        path = output / name
        if not path.is_file() or path.is_symlink() or file_sha256(path) != expected:
            raise BaselineError(f"sealed evidence member drifted: {name}")
    try:
        evidence = json.loads((output / "backend-evidence.json").read_text())
        aggregate = json.loads((output / "aggregate.json").read_text())
        cleanup = json.loads((output / "cohort-cleanup.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError("sealed aggregate/backend evidence cannot be replayed") from exc
    qualification_hash = evidence.get("two_call_qualification_sha256")
    if (
        aggregate.get("schema")
        == "archvteams.nebius.ai/catalog-switch-k8s-stratified-aggregate/v2"
        and (
            not isinstance(qualification_hash, str)
            or qualification_hash != canonical_sha256(evidence.get("two_call_qualification"))
            or aggregate.get("two_call_qualification_sha256") != qualification_hash
        )
    ):
        raise BaselineError("aggregate and backend two-call/cleanup evidence are not jointly bound")
    cleanup_field = (
        "final_cleanup_sha256"
        if schema == "archvteams.nebius.ai/k8s-evidence-seal/v2"
        else "workload_cleanup_sha256"
    )
    if manifest.get(cleanup_field) != manifest["files"].get("cohort-cleanup.json"):
        raise BaselineError("cleanup stage is not jointly sealed")
    if schema.endswith("workload-staging-seal/v1") and manifest.get("promotion_allowed") is not False:
        raise BaselineError("workload staging seal cannot allow promotion")
    if evidence.get("schema") == "archvteams.nebius.ai/k8s-final-backend-evidence/v1":
        staged_evidence = evidence.get("staging_backend_evidence")
        staged_hash = (
            hashlib.sha256((canonical_json(staged_evidence) + "\n").encode()).hexdigest()
            if isinstance(staged_evidence, dict)
            else None
        )
        if (
            not isinstance(staged_evidence, dict)
            or evidence.get("staging_backend_evidence_sha256") != staged_hash
            or evidence.get("workload_cleanup") != staged_evidence.get("final_cleanup")
            or evidence.get("final_cleanup") != cleanup
        ):
            raise BaselineError(
                "final backend evidence does not bind staging and broker cleanup states"
            )
        from .stratification import validate_broker_release

        validate_broker_release(
            cleanup,
            expected_lease=receipt.get("expected_broker_lease"),
            expected_aggregate=aggregate,
        )
    if receipt.get("promotion_allowed") is True:
        comparison = receipt.get("comparison_attestation")
        if (
            schema != "archvteams.nebius.ai/k8s-evidence-seal/v2"
            or evidence.get("schema")
            != "archvteams.nebius.ai/k8s-final-backend-evidence/v1"
            or not isinstance(comparison, dict)
            or comparison.get("schema")
            != "archvteams.nebius.ai/k8s-one-variable-comparison-attestation/v1"
            or comparison.get("candidate_config_sha256")
            != receipt.get("plan_config_sha256")
            or comparison.get("candidate_variant") != "precreated_service"
            or comparison.get("candidate_experiment_id") != receipt.get("experiment_id")
            or comparison.get("baseline_final_status") != "FINAL"
            or not isinstance(comparison.get("baseline_final_seal_sha256"), str)
            or len(comparison.get("baseline_final_seal_sha256", "")) != 64
            or not isinstance(comparison.get("baseline_aggregate_sha256"), str)
            or len(comparison.get("baseline_aggregate_sha256", "")) != 64
            or not isinstance(comparison.get("comparison_contract_sha256"), str)
            or len(comparison.get("comparison_contract_sha256", "")) != 64
        ):
            raise BaselineError(
                "promoted receipt lacks final broker-bound evidence and sealed pair attestation"
            )
        from .stratification import require_promotion_cohorts

        require_promotion_cohorts(
            aggregate,
            final_cleanup=cleanup,
            expected_lease=receipt.get("expected_broker_lease"),
            seal_verified=True,
        )
    return manifest
