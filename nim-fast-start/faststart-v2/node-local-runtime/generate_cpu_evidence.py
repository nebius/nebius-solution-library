#!/usr/bin/env python3
"""Generate canonical CPU integration/adversary evidence.

This exercises the real supervisor and shared external-T0 ledger contract with
the deterministic CPU backend. It is correctness evidence only: it must never
be reported as model, GPU, storage, or product-latency evidence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from performance.request_slo import harness

from node_runtime.cache import ContentAddressedCache, InjectedIngestCrash
from node_runtime.supervisor import DeterministicBackend
from tests.helpers import ARTIFACT_SHA, MODEL_A, PAYLOAD, binding, checkpoint_environment
from tests.helpers import environment, ownership, setup


HERE = Path(__file__).resolve().parent


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def conventional_command(fixture: dict[str, Any], suffix: str) -> dict[str, Any]:
    now = time.time_ns()
    return fixture["auth"].sign(
        fixture["trace"]["requests"][0],
        nonce=f"conventional-{suffix}-0123456789",
        launch_mode="conventional",
        issued_at_unix_ns=now - 1_000_000,
        expires_at_unix_ns=now + 30_000_000_000,
    )


def execute(
    root: Path,
    *,
    name: str,
    scenario: str = "a_to_b_local",
    launch_mode: str = "snapshot",
    fail_phase: str | None = None,
    failure_class: str = "backend",
    cleanup_fails: bool = False,
    accounting_fails: bool = False,
    cleanup_required: bool = False,
    stale_checkpoint: bool = False,
    corrupt_cache: bool = False,
    remote_miss: bool = False,
) -> dict[str, Any]:
    case = root / name
    case.mkdir()
    fixture = setup(case, scenario=scenario, suffix=name)
    if launch_mode == "conventional":
        fixture["command"] = conventional_command(fixture, name)
    if corrupt_cache:
        entry = fixture["cache"].objects / ARTIFACT_SHA
        payload = entry / "payload"
        os.chmod(entry, 0o700)
        os.chmod(payload, 0o600)
        payload.write_bytes(b"corrupt-cache-adversary")
    if remote_miss:
        entry = fixture["cache"].objects / ARTIFACT_SHA
        os.chmod(entry, 0o700)
        for child in entry.iterdir():
            child.unlink()
        entry.rmdir()
    backend = DeterministicBackend(
        None if scenario in {"idle_local", "capacity_miss"} else MODEL_A,
        fail_phase=fail_phase,
        failure_class=failure_class,
        cleanup_fails=cleanup_fails,
        accounting_fails=accounting_fails,
    )
    ledger = case / "ledger.jsonl"
    audit = case / "audit.jsonl"
    result = fixture["supervisor"].run(
        trace=fixture["trace"],
        command=fixture["command"],
        payload=PAYLOAD,
        backend=backend,
        environment=environment(),
        checkpoint_environment=checkpoint_environment(),
        ownership=ownership(cleanup_required),
        ledger_path=ledger,
        audit_path=audit,
        artifact_source=fixture["source"] if remote_miss else None,
        checkpoint_binding=binding(driver_version="stale-driver")
        if stale_checkpoint
        else binding(),
    )
    events = harness.load_ledger(ledger)
    aggregate = harness.aggregate_ledger(events, fixture["trace"])
    write_json(case / "receipt.json", result)
    write_json(case / "aggregate.json", aggregate)
    return {
        "name": name,
        "scenario": scenario,
        "launch_mode_requested": launch_mode,
        "launch_mode_effective": result["effective_launch_mode"],
        "success": result["attempt"]["success"],
        "failure_class": result["attempt"]["failure_class"],
        "cleanup_status": result["attempt"]["cleanup"]["status"],
        "bytes_moved_total": result["attempt"]["accounting"]["bytes_moved_total"],
        "ledger_sha256": harness.canonical_sha256(events),
        "audit_file_sha256": result["audit_file_sha256"],
        "offered": aggregate["attempts"]["offered"],
        "failures": aggregate["attempts"]["failures"],
    }


def replay_case(root: Path) -> list[dict[str, Any]]:
    case = root / "replay"
    case.mkdir()
    fixture = setup(case, suffix="replay")
    summaries: list[dict[str, Any]] = []
    for label in ("original", "replayed"):
        ledger = case / f"{label}-ledger.jsonl"
        audit = case / f"{label}-audit.jsonl"
        result = fixture["supervisor"].run(
            trace=fixture["trace"],
            command=fixture["command"],
            payload=PAYLOAD,
            backend=DeterministicBackend(MODEL_A),
            environment=environment(),
            checkpoint_environment=checkpoint_environment(),
            ownership=ownership(False),
            ledger_path=ledger,
            audit_path=audit,
            checkpoint_binding=binding(),
        )
        events = harness.load_ledger(ledger)
        aggregate = harness.aggregate_ledger(events, fixture["trace"])
        write_json(case / f"{label}-receipt.json", result)
        summaries.append(
            {
                "name": f"replay-{label}",
                "scenario": "a_to_b_local",
                "launch_mode_requested": "snapshot",
                "launch_mode_effective": result["effective_launch_mode"],
                "success": result["attempt"]["success"],
                "failure_class": result["attempt"]["failure_class"],
                "cleanup_status": result["attempt"]["cleanup"]["status"],
                "bytes_moved_total": result["attempt"]["accounting"]["bytes_moved_total"],
                "ledger_sha256": harness.canonical_sha256(events),
                "audit_file_sha256": result["audit_file_sha256"],
                "offered": aggregate["attempts"]["offered"],
                "failures": aggregate["attempts"]["failures"],
            }
        )
    return summaries


def cache_crash_case(root: Path) -> dict[str, Any]:
    case = root / "partial-ingest-crash"
    case.mkdir()
    cache = ContentAddressedCache(case / "cache", require_fsverity=False)
    source = case / "source"
    source.write_bytes(b"crash-window-artifact")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    refused = False
    try:
        cache.ingest(source, digest, crash_after_bytes=1)
    except InjectedIngestCrash:
        refused = True
    published = (cache.objects / digest).exists()
    removed = cache.collect_orphans()
    result = {
        "schema": "catalog-switch-cache-crash-evidence/v1",
        "injected_crash_observed": refused,
        "partial_entry_published": published,
        "orphan_count_removed": len(removed),
        "incoming_empty_after_cleanup": not any(cache.incoming.iterdir()),
    }
    write_json(case / "receipt.json", result)
    return result


def hot_path_import_proof() -> dict[str, Any]:
    source = HERE / "node_runtime" / "supervisor.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = sorted(
        {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
    )
    forbidden = sorted(set(imports) & {"boto3", "kubernetes", "nebius"})
    return {
        "schema": "catalog-switch-hot-path-import-proof/v1",
        "source": str(source.relative_to(HERE.parent)),
        "imports": imports,
        "forbidden_control_plane_or_object_store_clients": forbidden,
        "status": "PASS" if not forbidden else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if options.output.exists() or options.output.is_symlink():
        parser.error("--output must be a new path")
    options.output.mkdir(parents=True)

    summaries = [
        execute(
            options.output,
            name="idle-conventional",
            scenario="idle_local",
            launch_mode="conventional",
        ),
        execute(
            options.output,
            name="occupied-conventional",
            launch_mode="conventional",
        ),
        execute(options.output, name="occupied-snapshot"),
        execute(
            options.output,
            name="remote-artifact-miss",
            scenario="a_to_b_remote",
            launch_mode="conventional",
            remote_miss=True,
        ),
        execute(
            options.output,
            name="stale-checkpoint-fallback",
            scenario="checkpoint_fallback",
            stale_checkpoint=True,
        ),
        execute(options.output, name="corrupt-cache", corrupt_cache=True),
        execute(
            options.output,
            name="preempted-launch",
            fail_phase="runtime_launch",
            failure_class="preempted",
        ),
        execute(
            options.output,
            name="cancelled-inference",
            fail_phase="inference",
            failure_class="cancelled",
        ),
        execute(
            options.output,
            name="capacity-miss",
            scenario="capacity_miss",
            fail_phase="placement",
            failure_class="capacity",
        ),
        execute(
            options.output,
            name="cleanup-failure",
            cleanup_fails=True,
            cleanup_required=True,
        ),
        execute(
            options.output,
            name="accounting-failure",
            accounting_fails=True,
        ),
    ]
    summaries.extend(replay_case(options.output))
    crash = cache_crash_case(options.output)
    imports = hot_path_import_proof()
    write_json(options.output / "hot-path-import-proof.json", imports)
    offered = sum(item["offered"] for item in summaries)
    failures = sum(item["failures"] for item in summaries)
    summary = {
        "schema": "catalog-switch-node-cpu-evidence/v1",
        "classification": "cpu-correctness-only-not-product-gpu-storage-or-latency-evidence",
        "cases": summaries,
        "denominator": {
            "offered": offered,
            "successes": offered - failures,
            "failures": failures,
        },
        "partial_ingest_crash": crash,
        "hot_path_import_proof": imports,
    }
    write_json(options.output / "summary.json", summary)
    print(
        json.dumps(
            {
                "output": str(options.output),
                "offered": offered,
                "failures": failures,
                "hot_path_status": imports["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
