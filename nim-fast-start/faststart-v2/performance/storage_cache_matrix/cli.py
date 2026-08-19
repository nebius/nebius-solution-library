#!/usr/bin/env python3
"""CLI for validating and aggregating storage/cache matrix evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .matrix import (
    MatrixError,
    aggregate_matrix,
    load_attempts,
    load_plan,
    validate_matrix,
    write_canonical_json,
)
from .smoke import build_smoke


def _paths(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    plan = load_plan(args.plan)
    attempts = load_attempts(args.attempts)
    if args.plan.resolve().parent != args.attempts.resolve().parent:
        raise MatrixError("plan and attempt ledger must share one immutable evidence root")
    return plan, attempts, args.plan.resolve().parent


def _validate(args: argparse.Namespace) -> dict[str, Any]:
    plan, attempts, root = _paths(args)
    shaped = validate_matrix(plan, attempts, root)
    result = {
        "status": "PASS",
        "plan_id": plan["plan_id"],
        "evidence_classification": plan["evidence_classification"],
        "attempt_count": len(shaped),
        "valid_response_count": sum(
            item["terminal"]["type"] == "response.validated" for item in shaped
        ),
        "failure_count": sum(
            item["terminal"]["type"] == "attempt.failed" for item in shaped
        ),
        "request_slo_bound": True,
        "dirty_generation_reuse": 0,
    }
    if args.output:
        write_canonical_json(args.output, result)
    return result


def _aggregate(args: argparse.Namespace) -> dict[str, Any]:
    plan, attempts, root = _paths(args)
    aggregate = aggregate_matrix(
        plan,
        attempts,
        root,
        evidence_source=args.evidence_source,
    )
    if args.output:
        write_canonical_json(args.output, aggregate)
    if args.simulator_output:
        write_canonical_json(args.simulator_output, aggregate["simulator_overrides"])
    if args.router_output:
        write_canonical_json(args.router_output, aggregate["router_locality_costs"])
    return aggregate


def _smoke(args: argparse.Namespace) -> dict[str, Any]:
    plan, attempts = build_smoke(args.output_dir)
    aggregate = aggregate_matrix(
        plan,
        attempts,
        args.output_dir,
        evidence_source="synthetic contract smoke; not performance evidence",
    )
    write_canonical_json(args.output_dir / "aggregate.json", aggregate)
    write_canonical_json(
        args.output_dir / "simulator-overrides.json", aggregate["simulator_overrides"]
    )
    write_canonical_json(
        args.output_dir / "router-locality-costs.json", aggregate["router_locality_costs"]
    )
    return {
        "status": "PASS",
        "classification": plan["evidence_classification"],
        "output_dir": str(args.output_dir),
        "attempt_count": aggregate["attempts"]["observed"],
        "valid_responses": aggregate["attempts"]["valid_responses"],
        "failures": aggregate["attempts"]["failures"],
        "boltz_external_tmp_status": aggregate["boltz_external_tmp"]["status"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a complete evidence root")
    validate.add_argument("--plan", required=True, type=Path)
    validate.add_argument("--attempts", required=True, type=Path)
    validate.add_argument("--output", type=Path)
    validate.set_defaults(handler=_validate)

    aggregate = subparsers.add_parser(
        "aggregate", help="validate and produce raw-distribution exports"
    )
    aggregate.add_argument("--plan", required=True, type=Path)
    aggregate.add_argument("--attempts", required=True, type=Path)
    aggregate.add_argument("--evidence-source", required=True)
    aggregate.add_argument("--output", type=Path)
    aggregate.add_argument("--simulator-output", type=Path)
    aggregate.add_argument("--router-output", type=Path)
    aggregate.set_defaults(handler=_aggregate)

    smoke = subparsers.add_parser(
        "smoke", help="write and validate synthetic non-performance evidence"
    )
    smoke.add_argument("--output-dir", required=True, type=Path)
    smoke.set_defaults(handler=_smoke)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (MatrixError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
