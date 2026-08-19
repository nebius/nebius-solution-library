from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from performance.k8s_baseline.controller import EventSink, ScriptedBackend, run_trace
from performance.request_slo.harness import (
    CATALOG_SCHEMA,
    aggregate_ledger,
    generate_trace,
    load_ledger,
    validate_ledger,
)


def catalog() -> dict:
    return {
        "schema": CATALOG_SCHEMA,
        "models": [
            {
                "model_id": "model-a",
                "model_version": "v1",
                "artifact_id": "artifact-a",
                "artifact_version": "v1",
                "artifact_sha256": "a" * 64,
                "input": {
                    "workload_id": "smoke",
                    "input_id": "input-a",
                    "payload_sha256": "b" * 64,
                    "input_bytes": 128,
                },
            },
            {
                "model_id": "model-b",
                "model_version": "v1",
                "artifact_id": "artifact-b",
                "artifact_version": "v1",
                "artifact_sha256": "c" * 64,
                "input": {
                    "workload_id": "smoke",
                    "input_id": "input-b",
                    "payload_sha256": "d" * 64,
                    "input_bytes": 256,
                },
            },
        ],
    }


class ControllerTests(unittest.TestCase):
    def run_smoke(self, requests: int = 24):
        trace = generate_trace(
            catalog(),
            distribution="adversarial",
            seed=2407,
            request_count=requests,
            trace_id=f"k8s-controller-test-{requests}",
            interval_ms=20,
        )
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        ledger = root / "ledger.jsonl"
        evidence = root / "evidence.json"
        receipt = run_trace(
            trace,
            ScriptedBackend(),
            ledger,
            evidence,
            ledger_id=f"k8s-controller-test-ledger-{requests}",
        )
        return temporary, trace, ledger, evidence, receipt

    def test_all_offered_attempts_validate_and_failures_are_retained(self) -> None:
        temporary, trace, ledger, _, receipt = self.run_smoke()
        self.addCleanup(temporary.cleanup)
        attempts = validate_ledger(load_ledger(ledger), trace)
        self.assertEqual(len(attempts), 24)
        self.assertEqual(receipt["attempt_count"], 24)
        self.assertEqual(receipt["success_count"], 20)
        self.assertEqual(receipt["failure_count"], 4)
        self.assertEqual(receipt["two_call_qualification"]["qualified_count"], 20)
        self.assertEqual(receipt["two_call_qualification"]["product_terminal_call"], 1)
        self.assertEqual(
            {item["failure_class"] for item in attempts if not item["success"]},
            {"capacity"},
        )

    def test_t0_remains_on_offered_schedule_while_worker_runs(self) -> None:
        temporary, trace, ledger, _, _ = self.run_smoke()
        self.addCleanup(temporary.cleanup)
        attempts = validate_ledger(load_ledger(ledger), trace)
        self.assertLessEqual(
            max(abs(item["acceptance_schedule_error_ms"]) for item in attempts),
            100.0,
        )

    def test_each_attempt_begins_with_external_acceptance(self) -> None:
        temporary, trace, ledger, _, _ = self.run_smoke(12)
        self.addCleanup(temporary.cleanup)
        events = load_ledger(ledger)
        for request in trace["requests"]:
            attempt = [
                item for item in events if item["attempt_id"] == request["attempt_id"]
            ]
            self.assertEqual(attempt[0]["event_type"], "request.accepted")
            self.assertEqual(
                attempt[0]["data"]["boundary"],
                "external-client-request-accepted/v1",
            )

    def test_product_percentiles_use_complete_attempts(self) -> None:
        temporary, trace, ledger, _, _ = self.run_smoke()
        self.addCleanup(temporary.cleanup)
        aggregate = aggregate_ledger(load_ledger(ledger), trace)
        self.assertEqual(aggregate["attempts"]["offered"], 24)
        self.assertEqual(len(aggregate["attempts"]["results"]), 24)
        self.assertIsNotNone(aggregate["product_latency_seconds"]["p95"])
        self.assertIsNone(aggregate["product_latency_seconds"]["p99"])

    def test_backend_evidence_is_explicitly_synthetic(self) -> None:
        temporary, _, _, evidence, receipt = self.run_smoke(12)
        self.addCleanup(temporary.cleanup)
        self.assertIn("not-performance-evidence", evidence.read_text())
        self.assertIn("not-performance-evidence", receipt["classification"])

    def test_existing_output_is_refused(self) -> None:
        trace = generate_trace(
            catalog(),
            distribution="adversarial",
            seed=1,
            request_count=6,
            trace_id="existing-output-test",
            interval_ms=20,
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            ledger.write_text("occupied\n")
            with self.assertRaisesRegex(ValueError, "ledger output must be new"):
                run_trace(
                    trace,
                    ScriptedBackend(),
                    ledger,
                    Path(directory) / "evidence.json",
                    ledger_id="existing-output-ledger",
                )

    def test_arm_b_hook_cannot_run_before_t0_is_durable(self) -> None:
        trace = generate_trace(
            catalog(),
            distribution="adversarial",
            seed=1,
            request_count=1,
            trace_id="durable-arm-b-t0",
            interval_ms=20,
        )
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            sink = EventSink(ledger, "durable-arm-b-ledger", trace["trace_id"])
            backend = ScriptedBackend()
            backend.requires_durable_t0_before_accepted_hook = True
            try:
                event = sink.accept(trace["requests"][0], backend)
                self.assertTrue(ledger.exists())
                self.assertIn(event["event_id"], ledger.read_text())
            finally:
                sink.close()


if __name__ == "__main__":
    unittest.main()
