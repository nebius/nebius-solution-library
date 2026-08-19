#!/usr/bin/env python3
"""CLI for the Kubernetes request-time catalog-switch baseline."""

from __future__ import annotations

import argparse
import json
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
    result = run_trace(
        trace,
        ScriptedBackend(),
        ledger_path,
        evidence_path,
        ledger_id="catalog-switch-k8s-controller-smoke-ledger",
    )
    aggregate = aggregate_ledger(load_ledger(ledger_path), trace)
    aggregate["evidence_classification"] = (
        "synthetic-controller-contract-test-not-performance-evidence"
    )
    write_canonical_json(aggregate_path, aggregate)
    result["aggregate_path"] = str(aggregate_path)
    result["p95_supported"] = aggregate["product_latency_seconds"]["p95"] is not None
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
        aggregate = aggregate_ledger(events, trace)
        aggregate["evidence_classification"] = "live-kubernetes-product-slo-evidence"
        write_canonical_json(output / "aggregate.json", aggregate)
    finally:
        cleanup = backend.final_cleanup()
        write_canonical_json(output / "cohort-cleanup.json", cleanup)
        # The broker lease remains ACTIVE only so another admitted variant may
        # run. The runbook requires exact-ID broker cleanup after the final
        # cohort and does not treat this cohort receipt as cloud teardown.
        backend.write_evidence(evidence_path)
    result.update(
        {
            "aggregate_path": str(output / "aggregate.json"),
            "cohort_cleanup_path": str(output / "cohort-cleanup.json"),
            "cloud_lease_state": "ACTIVE-cleanup-still-required",
        }
    )
    write_canonical_json(output / "receipt.json", result)
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
    run.set_defaults(handler=_run_live)
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
