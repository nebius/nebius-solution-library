#!/usr/bin/env python3
"""Command-line interface for the catalog-switch SLO contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .harness import (
    AGGREGATE_SCHEMA,
    CATALOG_SCHEMA,
    EVENT_SCHEMA,
    EVENT_TYPES,
    LEGACY_IMPORT_SCHEMA,
    TRACE_SCHEMA,
    HarnessError,
    aggregate_ledger,
    append_event,
    canonical_json,
    default_recorder,
    file_sha256,
    generate_trace,
    import_legacy_cohort,
    load_ledger,
    load_trace,
    synthetic_smoke_ledger,
    validate_ledger,
    write_canonical_json,
    write_ledger,
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HarnessError(f"duplicate JSON key in CLI input: {key}")
        result[key] = value
    return result


def _load_json_file(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise HarnessError(f"{label} must be a regular non-symlink file")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read {label}: {type(exc).__name__}") from exc


def _load_json_argument(value: str, label: str) -> Any:
    if value.startswith("@"):
        return _load_json_file(Path(value[1:]), label)
    try:
        return json.loads(value, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{label} is invalid JSON") from exc


def _emit(value: Any, output: Path | None) -> None:
    if output is None:
        print(canonical_json(value))
    else:
        write_canonical_json(output, value)


def _cmd_generate(args: argparse.Namespace) -> dict[str, Any]:
    catalog = _load_json_file(args.catalog, "catalog")
    trace = generate_trace(
        catalog,
        distribution=args.distribution,
        seed=args.seed,
        request_count=args.requests,
        trace_id=args.trace_id,
        interval_ms=args.interval_ms,
    )
    _emit(trace, args.output)
    return {
        "schema": TRACE_SCHEMA,
        "trace_id": trace["trace_id"],
        "trace_sha256": trace["trace_sha256"],
        "request_count": trace["request_count"],
    }


def _cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    trace = load_trace(args.trace)
    events = load_ledger(args.ledger)
    attempts = validate_ledger(events, trace)
    result = {
        "schema": "archvteams.nebius.ai/catalog-switch-validation-receipt/v1",
        "status": "PASS",
        "trace_id": trace["trace_id"],
        "trace_sha256": trace["trace_sha256"],
        "ledger_sha256": file_sha256(args.ledger),
        "attempt_count": len(attempts),
        "valid_response_count": sum(item["success"] for item in attempts),
        "failure_count": sum(not item["success"] for item in attempts),
        "boundary": {
            "t0": "external-client-request-accepted/v1",
            "terminal": "first-complete-semantically-valid-response/v1",
        },
    }
    _emit(result, args.output)
    return result


def _cmd_aggregate(args: argparse.Namespace) -> dict[str, Any]:
    trace = load_trace(args.trace)
    events = load_ledger(args.ledger)
    result = aggregate_ledger(events, trace)
    _emit(result, args.output)
    return result


def _cmd_import_legacy(args: argparse.Namespace) -> dict[str, Any]:
    result = import_legacy_cohort(args.input, args.model)
    _emit(result, args.output)
    return result


def _cmd_record(args: argparse.Namespace) -> dict[str, Any]:
    data = _load_json_argument(args.data, "event data")
    if not isinstance(data, dict):
        raise HarnessError("event data must be a JSON object")
    if args.recorder is None:
        recorder = default_recorder(
            args.recorder_id, max_error_ms=args.max_clock_error_ms
        )
    else:
        recorder = _load_json_argument(args.recorder, "recorder")
    if not isinstance(recorder, dict):
        raise HarnessError("recorder must be a JSON object")
    event = append_event(
        args.ledger,
        ledger_id=args.ledger_id,
        trace_id=args.trace_id,
        request_id=args.request_id,
        attempt_id=args.attempt_id,
        recorder=recorder,
        event_type=args.event_type,
        data=data,
    )
    print(canonical_json(event))
    return event


def _smoke_catalog() -> dict[str, Any]:
    return {
        "schema": CATALOG_SCHEMA,
        "models": [
            {
                "model_id": "smoke-model-a",
                "model_version": "v1",
                "artifact_id": "smoke-artifact-a",
                "artifact_version": "v1",
                "artifact_sha256": "a" * 64,
                "input": {
                    "workload_id": "semantic-smoke",
                    "input_id": "input-a",
                    "payload_sha256": "b" * 64,
                    "input_bytes": 128,
                },
            },
            {
                "model_id": "smoke-model-b",
                "model_version": "v2",
                "artifact_id": "smoke-artifact-b",
                "artifact_version": "v2",
                "artifact_sha256": "c" * 64,
                "input": {
                    "workload_id": "semantic-smoke",
                    "input_id": "input-b",
                    "payload_sha256": "d" * 64,
                    "input_bytes": 256,
                },
            },
        ],
    }


def _cmd_smoke(args: argparse.Namespace) -> dict[str, Any]:
    trace = generate_trace(
        _smoke_catalog(),
        distribution="adversarial",
        seed=2407,
        request_count=24,
        trace_id="catalog-switch-contract-smoke",
        interval_ms=10,
    )
    events = synthetic_smoke_ledger(trace)
    attempts = validate_ledger(events, trace)
    aggregate = aggregate_ledger(events, trace)
    aggregate["evidence_classification"] = "synthetic-contract-smoke-not-performance-evidence"
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_canonical_json(args.output_dir / "trace.json", trace)
        write_ledger(args.output_dir / "ledger.jsonl", events)
        write_canonical_json(args.output_dir / "aggregate.json", aggregate)
    result = {
        "status": "PASS",
        "classification": "synthetic-contract-smoke-not-performance-evidence",
        "schemas": [EVENT_SCHEMA, TRACE_SCHEMA, AGGREGATE_SCHEMA, LEGACY_IMPORT_SCHEMA],
        "trace_sha256": trace["trace_sha256"],
        "attempts": len(attempts),
        "valid_responses": sum(item["success"] for item in attempts),
        "failures": sum(not item["success"] for item in attempts),
        "p95_supported": aggregate["product_latency_seconds"]["p95"] is not None,
        "p99_withheld": aggregate["product_latency_seconds"]["p99"] is None,
    }
    print(canonical_json(result))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate-trace", help="build a pinned trace")
    generate.add_argument("--catalog", type=Path, required=True)
    generate.add_argument(
        "--distribution", choices=("uniform", "skewed", "adversarial"), required=True
    )
    generate.add_argument("--seed", type=int, required=True)
    generate.add_argument("--requests", type=int, required=True)
    generate.add_argument("--trace-id", required=True)
    generate.add_argument("--interval-ms", type=int, default=1000)
    generate.add_argument("--output", type=Path)
    generate.set_defaults(handler=_cmd_generate)

    validate = subparsers.add_parser("validate", help="validate trace and ledger")
    validate.add_argument("--trace", type=Path, required=True)
    validate.add_argument("--ledger", type=Path, required=True)
    validate.add_argument("--output", type=Path)
    validate.set_defaults(handler=_cmd_validate)

    aggregate = subparsers.add_parser(
        "aggregate", help="aggregate admitted raw attempts"
    )
    aggregate.add_argument("--trace", type=Path, required=True)
    aggregate.add_argument("--ledger", type=Path, required=True)
    aggregate.add_argument("--output", type=Path)
    aggregate.set_defaults(handler=_cmd_aggregate)

    legacy = subparsers.add_parser(
        "import-legacy", help="label a published prepared-node cohort"
    )
    legacy.add_argument("--model", choices=("openfold2", "boltz2"), required=True)
    legacy.add_argument("--input", type=Path, required=True)
    legacy.add_argument("--output", type=Path)
    legacy.set_defaults(handler=_cmd_import_legacy)

    record = subparsers.add_parser("record", help="append an external observation")
    record.add_argument("--ledger", type=Path, required=True)
    record.add_argument("--ledger-id", required=True)
    record.add_argument("--trace-id", required=True)
    record.add_argument("--request-id", required=True)
    record.add_argument("--attempt-id", required=True)
    record.add_argument("--event-type", choices=EVENT_TYPES, required=True)
    record.add_argument("--data", required=True, help="JSON or @path")
    record.add_argument("--recorder", help="recorder JSON or @path")
    record.add_argument("--recorder-id", default="catalog-switch-external-client")
    record.add_argument("--max-clock-error-ms", type=float, default=50.0)
    record.set_defaults(handler=_cmd_record)

    smoke = subparsers.add_parser("smoke", help="run an offline synthetic contract smoke")
    smoke.add_argument("--output-dir", type=Path)
    smoke.set_defaults(handler=_cmd_smoke)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.handler(args)
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
