#!/usr/bin/env python3
"""CLI for the Kubernetes request-time catalog-switch baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from performance.request_slo.harness import (
    CATALOG_SCHEMA,
    aggregate_ledger,
    canonical_json,
    generate_trace,
    load_ledger,
    load_trace,
    validate_ledger,
    write_canonical_json,
)

from .contract import BaselineError, load_plan, safe_output_path
from .controller import ScriptedBackend, run_trace
from .kubernetes_backend import KubernetesBackend
from .sealing import (
    atomic_write_bytes,
    atomic_write_json,
    file_sha256,
    seal_run,
    seal_staging,
    verify_seal,
)
from .stratification import (
    require_promotion_cohorts,
    stratify_aggregate,
    validate_broker_release,
)


def _smoke_catalog() -> dict[str, Any]:
    return {
        "schema": CATALOG_SCHEMA,
        "models": [
            {
                "model_id": "k8s-smoke-a",
                "model_version": "v1",
                "artifact_id": "k8s-smoke-artifact-a",
                "artifact_version": "v1",
                "artifact_sha256": "a" * 64,
                "input": {
                    "workload_id": "controller-smoke",
                    "input_id": "smoke-input-a",
                    "payload_sha256": "b" * 64,
                    "input_bytes": 128,
                },
            },
            {
                "model_id": "k8s-smoke-b",
                "model_version": "v1",
                "artifact_id": "k8s-smoke-artifact-b",
                "artifact_version": "v1",
                "artifact_sha256": "c" * 64,
                "input": {
                    "workload_id": "controller-smoke",
                    "input_id": "smoke-input-b",
                    "payload_sha256": "d" * 64,
                    "input_bytes": 256,
                },
            },
        ],
    }


def _validate_plan(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_plan(args.plan, require_live=args.live)
    result = {
        "schema": "archvteams.nebius.ai/k8s-baseline-plan-validation/v1",
        "status": "PASS",
        "experiment_id": plan["experiment_id"],
        "variant": plan["variant"],
        "project_id": plan["project_id"],
        "region": plan["region"],
        "trace_sha256": plan["trace_sha256"],
        "config_sha256": plan["_resolved"]["config_sha256"],
        "lease_loaded": plan["_resolved"]["lease_loaded"],
        "live_gate": args.live,
    }
    print(canonical_json(result))
    return result


def _synthetic_smoke(args: argparse.Namespace) -> dict[str, Any]:
    output = safe_output_path(args.output_dir)
    output.mkdir(mode=0o700)
    trace = generate_trace(
        _smoke_catalog(),
        distribution="adversarial",
        seed=2407,
        request_count=args.requests,
        trace_id="catalog-switch-k8s-controller-smoke",
        interval_ms=args.interval_ms,
    )
    trace_path = output / "trace.json"
    ledger_path = output / "ledger.jsonl"
    evidence_path = output / "backend-evidence.json"
    aggregate_path = output / "aggregate.json"
    write_canonical_json(trace_path, trace)
    backend = ScriptedBackend()
    result = run_trace(
        trace,
        backend,
        ledger_path,
        evidence_path,
        ledger_id="catalog-switch-k8s-controller-smoke-ledger",
    )
    backend.write_evidence(evidence_path)
    raw = aggregate_ledger(load_ledger(ledger_path), trace)
    aggregate = stratify_aggregate(
        raw,
        trace,
        plan=None,
        qualification=result["two_call_qualification"],
        classification="synthetic-controller-contract-test-not-performance-evidence",
        events=load_ledger(ledger_path),
    )
    atomic_write_json(aggregate_path, aggregate)
    result["backend_evidence_sha256"] = file_sha256(evidence_path)
    result["aggregate_path"] = str(aggregate_path)
    result["p95_supported"] = any(
        item["request_to_first_semantic_validation_seconds"]["p95"] is not None
        for item in aggregate["strata"]
    )
    write_canonical_json(output / "receipt.json", result)
    print(canonical_json(result))
    return result


def _run_live(args: argparse.Namespace) -> dict[str, Any]:
    if not args.execute:
        raise BaselineError("live run is fail-closed without --execute")
    output = safe_output_path(args.output_dir)
    plan = load_plan(args.plan, require_live=True)
    if plan["campaign_arm"] != "A_prepared_node":
        raise BaselineError(
            "arm B requires broker provisioning, Kubernetes bootstrap, and localization after T0; "
            "the prepared-node backend cannot execute it"
        )
    output.mkdir(mode=0o700)
    trace = load_trace(Path(plan["_resolved"]["trace_path"]))
    backend = KubernetesBackend(plan)
    ledger_path = output / "ledger.jsonl"
    evidence_path = output / "backend-evidence.json"
    cleanup: dict[str, Any]
    result: dict[str, Any] | None = None
    aggregate: dict[str, Any] | None = None
    run_error: Exception | None = None
    try:
        result = run_trace(
            trace,
            backend,
            ledger_path,
            evidence_path,
            ledger_id=f"{plan['experiment_id']}-ledger",
        )
        events = load_ledger(ledger_path)
        validate_ledger(events, trace)
        raw = aggregate_ledger(events, trace)
        aggregate = stratify_aggregate(
            raw,
            trace,
            plan=plan,
            qualification=result["two_call_qualification"],
            classification="live-kubernetes-product-slo-evidence",
            events=events,
        )
    except Exception as exc:
        run_error = exc
        backend._record(
            "campaign_failure",
            error=f"{type(exc).__name__}: {exc}"[:1000],
            promotable=False,
        )
    finally:
        try:
            cleanup = backend.final_cleanup()
        except Exception as exc:
            cleanup = {
                "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
                "status": "FAIL",
                "reason": f"final cleanup raised: {type(exc).__name__}: {exc}"[:1000],
                "lease_state": backend.lease.get("state"),
                "lease_cleanup_required": True,
            }
            backend._final_cleanup_receipt = cleanup
            backend._record("final_cleanup", receipt=cleanup)
    if (
        run_error is None
        and cleanup.get("status") != "WORKLOAD_PASS_BROKER_RELEASE_REQUIRED"
    ):
        run_error = BaselineError(
            "workload final cleanup did not reach the broker-release handoff state"
        )
    cleanup_path = output / "cohort-cleanup.json"
    aggregate_path = output / "aggregate.json"
    if run_error is not None:
        if not os.path.lexists(ledger_path):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(ledger_path, flags, 0o600)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        partial_aggregate = aggregate
        aggregate = {
            "schema": "archvteams.nebius.ai/catalog-switch-k8s-failed-run/v2",
            "status": "FAILED_UNPROMOTABLE",
            "error": f"{type(run_error).__name__}: {run_error}"[:1000],
            "ledger_complete": partial_aggregate is not None,
            "mixed_headline_percentile": None,
            "retained_partial_stratified_aggregate": partial_aggregate,
        }
        result = {
            "classification": "failed-live-kubernetes-evidence-not-performance-evidence",
            "status": "FAILED_UNPROMOTABLE",
            "error": f"{type(run_error).__name__}: {run_error}"[:1000],
            "ledger_sha256": file_sha256(ledger_path),
        }
    assert aggregate is not None and result is not None
    result.update(
        {
            "status": (
                "STAGED_AWAITING_BROKER_RELEASE"
                if run_error is None
                else "STAGED_FAILED_AWAITING_BROKER_RELEASE"
            ),
            "promotion_allowed": False,
            "experiment_id": plan["experiment_id"],
            "plan_config_sha256": plan["_resolved"]["config_sha256"],
            "plan_file_sha256": file_sha256(args.plan),
            "plan_variant": plan["variant"],
            "required_next_step": "finalize-live with typed broker final cleanup receipt",
            "expected_broker_lease": {
                "lease_id": backend.lease["lease_id"],
                "request_sha256": backend.lease["request_sha256"],
                "project_id": backend.lease["project_id"],
                "region": backend.lease["region"],
                "cost_estimate": backend.lease["cost_estimate"],
                "audit_chain": {
                    key: backend.lease["audit_chain"][key]
                    for key in ("chain_id", "genesis_sha256", "head_sha256", "event_count")
                },
                "credential": {
                    key: plan["security"]["credentials"][key]
                    for key in (
                        "secret_uid", "scope_sha256", "receipt_sha256", "revoke_by_utc"
                    )
                },
                "resources": [
                    {"kind": item["kind"], "id": item["id"]}
                    for item in sorted(backend.lease["resources"], key=lambda item: item["id"])
                ],
            },
        }
    )
    atomic_write_json(cleanup_path, cleanup)
    atomic_write_json(aggregate_path, aggregate)
    # Workload-level cleanup is complete and immutable before staging evidence
    # is written. Cloud lease release is a separate broker step and produces a
    # new final seal; this staging directory is never rewritten.
    backend.write_evidence(evidence_path)
    result.update(
        {
            "aggregate_path": str(aggregate_path),
            "cohort_cleanup_path": str(cleanup_path),
            "cloud_lease_state": cleanup.get("lease_state", "UNKNOWN"),
            "backend_evidence_sha256": file_sha256(evidence_path),
            "aggregate_sha256": file_sha256(aggregate_path),
            "cohort_cleanup_sha256": file_sha256(cleanup_path),
        }
    )
    sealed = seal_staging(
        output, receipt_payload=result, ledger_path=ledger_path,
        evidence_path=evidence_path, aggregate_path=aggregate_path,
        cleanup_path=cleanup_path,
    )
    print(canonical_json(sealed))
    message = (
        f"workload failed and evidence was staged: {type(run_error).__name__}: {run_error}; "
        if run_error is not None
        else "workload evidence was staged successfully; "
    )
    raise BaselineError(
        message + "broker must release the exact lease and finalize-live must consume its "
        "typed cleanup receipt"
    ) from run_error


def _load_regular_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BaselineError(f"{label} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load {label}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise BaselineError(f"{label} must contain an object")
    return value


def _finalize_live(args: argparse.Namespace) -> dict[str, Any]:
    """Create the only final seal after consuming the broker's RELEASED receipt."""

    staging = args.staging_dir.resolve()
    staging_manifest = verify_seal(staging)
    if staging_manifest["schema"] != "archvteams.nebius.ai/k8s-workload-staging-seal/v1":
        raise BaselineError("finalize-live requires an immutable workload staging seal")
    staged_receipt = _load_regular_json(staging / "receipt.json", "staging receipt")
    staging_failed = staged_receipt.get("status") == "STAGED_FAILED_AWAITING_BROKER_RELEASE"
    if (
        staged_receipt.get("status")
        not in {"STAGED_AWAITING_BROKER_RELEASE", "STAGED_FAILED_AWAITING_BROKER_RELEASE"}
        or staged_receipt.get("promotion_allowed") is not False
    ):
        raise BaselineError("staging receipt is not awaiting broker release")
    expected_lease = staged_receipt.get("expected_broker_lease")
    if not isinstance(expected_lease, dict):
        raise BaselineError("staging receipt lacks the exact broker lease graph")
    cleanup = _load_regular_json(args.broker_final_cleanup, "broker final cleanup receipt")
    aggregate = _load_regular_json(staging / "aggregate.json", "staged aggregate")
    validate_broker_release(
        cleanup, expected_lease=expected_lease, expected_aggregate=aggregate
    )
    comparison_attestation = None
    promotion_error: BaselineError | None = None
    if args.promote:
        # A per-run-Service leg ends by deleting the active target and GPU
        # scrubbing the node.  Reusing its original initial-state receipt for
        # the precreated-Service leg would therefore be false.  Promotion is
        # deliberately disabled until the resource broker implements the
        # versioned pair-handoff/rearm receipt frozen in the campaign contract.
        promotion_error = BaselineError(
            "hot-path promotion is blocked until the broker returns a versioned "
            "pair-handoff/rearm receipt after baseline cleanup and before candidate T0"
        )

    output = safe_output_path(args.output_dir)
    output.mkdir(mode=0o700)
    for name in ("ledger.jsonl", "aggregate.json"):
        source = staging / name
        if source.is_symlink() or not source.is_file():
            raise BaselineError(f"staging evidence member is unsafe or absent: {name}")
        atomic_write_bytes(output / name, source.read_bytes())
    staging_evidence = _load_regular_json(
        staging / "backend-evidence.json", "staging backend evidence"
    )
    final_evidence = {
        "schema": "archvteams.nebius.ai/k8s-final-backend-evidence/v1",
        "staging_backend_evidence_sha256": file_sha256(staging / "backend-evidence.json"),
        "staging_backend_evidence": staging_evidence,
        "workload_cleanup": _load_regular_json(
            staging / "cohort-cleanup.json", "staging workload cleanup"
        ),
        "final_cleanup": cleanup,
        "two_call_qualification": staging_evidence.get("two_call_qualification"),
        "two_call_qualification_sha256": staging_evidence.get(
            "two_call_qualification_sha256"
        ),
    }
    atomic_write_json(output / "backend-evidence.json", final_evidence)
    cleanup_path = output / "cohort-cleanup.json"
    atomic_write_json(cleanup_path, cleanup)
    aggregate = _load_regular_json(output / "aggregate.json", "final aggregate")
    staged_payload = {
        key: value
        for key, value in staged_receipt.items()
        if key not in {
            "evidence_seal_path", "evidence_seal_sha256", "aggregate_path",
            "cohort_cleanup_path", "cloud_lease_state", "backend_evidence_sha256",
            "aggregate_sha256", "cohort_cleanup_sha256", "status", "promotion_allowed",
            "required_next_step",
        }
    }
    result = {
        **staged_payload,
        "status": "FINAL" if not staging_failed else "FINAL_UNPROMOTABLE_FAILED",
        "promotion_allowed": bool(args.promote and promotion_error is None),
        "comparison_attestation": comparison_attestation,
        "workload_staging_seal_sha256": staged_receipt["evidence_seal_sha256"],
        "cloud_lease_state": "RELEASED",
        "aggregate_path": str(output / "aggregate.json"),
        "cohort_cleanup_path": str(cleanup_path),
        "backend_evidence_sha256": file_sha256(output / "backend-evidence.json"),
        "aggregate_sha256": file_sha256(output / "aggregate.json"),
        "cohort_cleanup_sha256": file_sha256(cleanup_path),
    }
    sealed = seal_run(
        output, receipt_payload=result, ledger_path=output / "ledger.jsonl",
        evidence_path=output / "backend-evidence.json",
        aggregate_path=output / "aggregate.json", cleanup_path=cleanup_path,
    )
    if args.promote and promotion_error is None:
        require_promotion_cohorts(
            aggregate, final_cleanup=cleanup, expected_lease=expected_lease,
            seal_verified=True,
        )
    print(canonical_json(sealed))
    if promotion_error is not None:
        raise BaselineError(
            "broker cleanup was finalized and sealed, but promotion was rejected: "
            f"{promotion_error}"
        ) from promotion_error
    return sealed


def _verify(args: argparse.Namespace) -> dict[str, Any]:
    result = verify_seal(args.output_dir)
    print(canonical_json(result))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-plan")
    validate.add_argument("--plan", required=True, type=Path)
    validate.add_argument("--live", action="store_true")
    validate.set_defaults(handler=_validate_plan)

    smoke = subparsers.add_parser("synthetic-smoke")
    smoke.add_argument("--output-dir", required=True, type=Path)
    smoke.add_argument("--requests", type=int, default=24)
    smoke.add_argument("--interval-ms", type=int, default=20)
    smoke.set_defaults(handler=_synthetic_smoke)

    run = subparsers.add_parser("run")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--execute", action="store_true")
    run.add_argument(
        "--promote",
        action="store_true",
        help="reserved for compatibility; run output remains staged until broker finalization",
    )
    run.set_defaults(handler=_run_live)

    finalize = subparsers.add_parser("finalize-live")
    finalize.add_argument("--staging-dir", required=True, type=Path)
    finalize.add_argument("--broker-final-cleanup", required=True, type=Path)
    finalize.add_argument("--output-dir", required=True, type=Path)
    finalize.add_argument("--comparison-contract", type=Path)
    finalize.add_argument("--baseline-final-dir", type=Path)
    finalize.add_argument(
        "--promote", action="store_true",
        help="promote every qualifying exact stratum; never create a mixed headline",
    )
    finalize.set_defaults(handler=_finalize_live)

    verify = subparsers.add_parser("verify-seal")
    verify.add_argument("--output-dir", required=True, type=Path)
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except (BaselineError, PermissionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
