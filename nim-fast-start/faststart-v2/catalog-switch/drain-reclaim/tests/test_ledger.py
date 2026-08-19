from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO_ROOT))

from ledger import SwitchLedgerBridge  # noqa: E402
from state_machine import (  # noqa: E402
    SEMANTIC_PROBE_SCHEMA,
    ModelRef,
    RuntimeIdentity,
    SemanticInferenceReceipt,
    SemanticProbeProof,
)
from performance.request_slo.harness import (  # noqa: E402
    EVENT_SCHEMA,
    SCENARIOS,
    T0_BOUNDARY,
    TRACE_SCHEMA,
    aggregate_ledger,
    append_event,
    canonical_sha256,
    load_ledger,
    validate_ledger,
)


def make_trace() -> dict:
    request = {
        "sequence": 0,
        "request_id": "switch-request-1",
        "attempt_id": "switch-attempt-1",
        "offered_at_offset_ms": 0,
        "scenario": "a_to_b_local",
        "target": {
            "model_id": "model-b",
            "model_version": "2",
            "artifact_id": "artifact-b",
            "artifact_version": "2",
            "artifact_sha256": "b" * 64,
        },
        "input": {
            "workload_id": "semantic-probe-b",
            "input_id": "input-b-1",
            "payload_sha256": "1" * 64,
            "input_bytes": 128,
        },
        "precondition": {
            "current_node_occupant": {
                "model_id": "model-a",
                "model_version": "1",
            },
            "cache": {
                "image": "local_verified",
                "artifact": "node_local_hit",
                "checkpoint": "missing",
                "storage": "ready",
            },
            "capacity": "allocated",
            "queue_depth": 0,
        },
    }
    trace = {
        "schema": TRACE_SCHEMA,
        "trace_id": "drain-reclaim-ledger-test",
        "distribution": "adversarial",
        "seed": 2407,
        "catalog_sha256": "2" * 64,
        "request_count": 1,
        "scenario_labels": list(SCENARIOS),
        "requests": [request],
    }
    trace["trace_sha256"] = canonical_sha256(trace)
    return trace


def recorder() -> dict:
    return {
        "recorder_id": "test-external-recorder",
        "clock_id": "test-clock",
        "boot_id": "test-boot",
        "utc_sync_source": "test-source",
        "max_error_ms": 100.0,
    }


def acceptance_data(trace: dict) -> dict:
    request = trace["requests"][0]
    return {
        "boundary": T0_BOUNDARY,
        "trace_request_sha256": canonical_sha256(request),
        "scenario": request["scenario"],
        "target": request["target"],
        "input": request["input"],
        "precondition": request["precondition"],
        "environment": {
            "backend": "node-vm",
            "backend_version": "drain-reclaim-v1",
            "provider": "local-test",
            "project_id": "local-test",
            "region": "local",
            "node_id": "node-test",
            "gpu_type": "H100",
            "gpu_count": 1,
            "image_digest": None,
            "code_revision": "0" * 40,
            "config_sha256": "3" * 64,
            "experiment_id": "drain-reclaim-ledger-test",
        },
        "ownership": {
            "owner_task_id": "catalog-switch-drain-reclaim-state-machine",
            "resource_prefix": "local-test",
            "dedicated": True,
            "cleanup_required": False,
            "resources": [],
        },
    }


def write_acceptance(path: Path, trace: dict, rec: dict) -> None:
    append_event(
        path,
        ledger_id="drain-reclaim-ledger-1",
        trace_id=trace["trace_id"],
        request_id="switch-request-1",
        attempt_id="switch-attempt-1",
        recorder=rec,
        event_type="request.accepted",
        data=acceptance_data(trace),
    )


def bridge(path: Path, trace: dict, rec: dict) -> SwitchLedgerBridge:
    return SwitchLedgerBridge(
        path=path,
        trace=trace,
        ledger_id="drain-reclaim-ledger-1",
        request_id="switch-request-1",
        attempt_id="switch-attempt-1",
        recorder=rec,
    )


class LedgerBridgeTests(unittest.TestCase):
    def test_bridge_refuses_any_work_before_external_t0(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Exception):
                bridge(Path(directory) / "missing.jsonl", make_trace(), recorder())

    def test_success_keeps_drain_and_gpu_release_in_valid_causal_ledger(self) -> None:
        trace = make_trace()
        rec = recorder()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            write_acceptance(path, trace, rec)
            writer = bridge(path, trace, rec)
            for phase in (
                "catalog_selection",
                "queue",
                "drain",
                "gpu_release",
                "placement",
                "image_readiness",
                "artifact_readiness",
                "storage_readiness",
                "cache_readiness",
                "runtime_launch",
                "service_readiness",
                "inference",
            ):
                writer.start_phase(phase)
                reason = (
                    "state-machine/v1 exact-runtime-and-NVML-proof"
                    if phase == "gpu_release"
                    else "state-machine/v1 completed"
                )
                writer.finish_phase(phase, outcome="completed", reason=reason)
            terminal = writer.record_success(
                {
                    "boundary": "first-complete-semantically-valid-response/v1",
                    "validator_id": "model-b-validator-v1",
                    "validator_sha256": "4" * 64,
                    "response_sha256": "5" * 64,
                    "response_bytes": 256,
                    "complete_body": True,
                    "semantically_valid": True,
                    "model_id": "model-b",
                    "model_version": "2",
                }
            )
            runtime = RuntimeIdentity(
                runtime_uid="runtime-b-2",
                backend="node-local",
                runtime_generation=2,
                model=ModelRef("model-b", "2", "b" * 64),
                gpu_uuid="GPU-00000000-0000-0000-0000-000000000001",
                host_pid=1234,
                process_start_ticks=999,
                cgroup_path="/catalog-switch/runtime-b-2",
            )
            semantic = SemanticProbeProof(
                schema=SEMANTIC_PROBE_SCHEMA,
                switch_id="switch-1",
                runtime_identity_sha256=runtime.digest,
                runtime_generation=2,
                model_id="model-b",
                model_version="2",
                validator_sha256="4" * 64,
                product_terminal_event_sha256=canonical_sha256(terminal),
                inferences=(
                    SemanticInferenceReceipt(
                        1,
                        "6" * 64,
                        "5" * 64,
                        True,
                        True,
                        terminal["observed_monotonic_ns"],
                    ),
                    SemanticInferenceReceipt(
                        2,
                        "7" * 64,
                        "8" * 64,
                        True,
                        True,
                        terminal["observed_monotonic_ns"] + 1,
                    ),
                ),
            )
            semantic_receipt = writer.validate_semantic_probe(semantic, runtime)
            writer.record_accounting(
                {
                    "currency": "USD",
                    "cost_usd": 0.0,
                    "gpu_active_seconds": 0.0,
                    "gpu_idle_seconds": 0.0,
                    "billed_seconds": 0.0,
                    "bytes_moved_total": 0,
                }
            )
            writer.record_cleanup(
                {
                    "required": False,
                    "status": "not_required",
                    "resources_deleted": [],
                    "resources_retained": [],
                    "receipt_sha256": None,
                    "reason": "local test creates no resources",
                }
            )
            terminal_receipt = writer.terminal_receipt_sha256()
            events = load_ledger(path)
            results = validate_ledger(events, trace)
            aggregate = aggregate_ledger(events, trace)
        self.assertTrue(results[0]["success"])
        self.assertEqual(len(terminal_receipt), 64)
        self.assertEqual(len(semantic_receipt), 64)
        self.assertEqual(aggregate["attempts"]["offered"], 1)
        self.assertEqual(aggregate["attempts"]["valid_responses"], 1)
        self.assertIn("drain", aggregate["phases"])
        self.assertIn("gpu_release", aggregate["phases"])

    def test_failure_remains_in_denominator_and_closes_every_phase(self) -> None:
        trace = make_trace()
        rec = recorder()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            write_acceptance(path, trace, rec)
            writer = bridge(path, trace, rec)
            for phase in ("catalog_selection", "queue", "drain", "gpu_release"):
                writer.start_phase(phase)
                writer.finish_phase(
                    phase,
                    outcome="completed",
                    reason="measured state-machine phase",
                )
            writer.fail_attempt(
                failed_phase="runtime_launch",
                failure_class="backend",
                reason="partial B launch failed after GPU reclaim",
                retryable=True,
                accounting={
                    "currency": "USD",
                    "cost_usd": 0.0,
                    "gpu_active_seconds": 0.0,
                    "gpu_idle_seconds": 0.0,
                    "billed_seconds": 0.0,
                    "bytes_moved_total": 0,
                },
                cleanup={
                    "required": False,
                    "status": "not_required",
                    "resources_deleted": [],
                    "resources_retained": [],
                    "receipt_sha256": None,
                    "reason": "local test creates no resources",
                },
            )
            events = load_ledger(path)
            results = validate_ledger(events, trace)
            aggregate = aggregate_ledger(events, trace)
        self.assertFalse(results[0]["success"])
        self.assertEqual(aggregate["attempts"]["offered"], 1)
        self.assertEqual(aggregate["attempts"]["failures"], 1)
        self.assertEqual(aggregate["attempts"]["failure_classes"], {"backend": 1})

    def test_phase_replay_is_idempotent_only_for_exact_data(self) -> None:
        trace = make_trace()
        rec = recorder()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            write_acceptance(path, trace, rec)
            writer = bridge(path, trace, rec)
            first = writer.start_phase("catalog_selection")
            second = writer.start_phase("catalog_selection")
            self.assertEqual(first, second)
            writer.finish_phase(
                "catalog_selection", outcome="completed", reason="catalog pinned"
            )
            same = writer.finish_phase(
                "catalog_selection", outcome="completed", reason="catalog pinned"
            )
            self.assertEqual(same["data"]["reason"], "catalog pinned")
            with self.assertRaises(Exception):
                writer.finish_phase(
                    "catalog_selection", outcome="completed", reason="different replay"
                )


if __name__ == "__main__":
    unittest.main()
