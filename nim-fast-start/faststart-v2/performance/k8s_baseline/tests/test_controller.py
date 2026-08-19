from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from performance.k8s_baseline.controller import (
    EventSink,
    PhaseExecutionError,
    ScriptedBackend,
    run_trace,
)
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


class DeterministicControllerClock:
    """Thread-safe logical clock for synthetic recorder-contract tests only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._origin_ns = 8_000_000_000_000
        self._now_ns = self._origin_ns
        self._origin_utc = datetime(2026, 8, 19, tzinfo=UTC)

    def monotonic_ns(self) -> int:
        with self._lock:
            # A tiny logical tick preserves strict ledger ordering without
            # making the offered schedule depend on thread or fsync latency.
            self._now_ns += 10
            return self._now_ns

    def utc_now(self) -> datetime:
        with self._lock:
            elapsed = (self._now_ns - self._origin_ns) / 1_000_000_000
            return self._origin_utc + timedelta(seconds=elapsed)

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise AssertionError("logical sleep cannot be negative")
        with self._lock:
            self._now_ns += round(seconds * 1_000_000_000)


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
        backend = ScriptedBackend()
        receipt = run_trace(
            trace,
            backend,
            ledger,
            evidence,
            ledger_id=f"k8s-controller-test-ledger-{requests}",
            clock=DeterministicControllerClock(),
        )
        backend.write_evidence(evidence)
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
            0.001,
        )

    def test_synthetic_schedule_is_stable_across_repeated_runs(self) -> None:
        for _ in range(20):
            temporary, trace, ledger, _, receipt = self.run_smoke()
            try:
                attempts = validate_ledger(load_ledger(ledger), trace)
                self.assertEqual(receipt["attempt_count"], 24)
                self.assertLessEqual(
                    max(abs(item["acceptance_schedule_error_ms"]) for item in attempts),
                    0.001,
                )
            finally:
                temporary.cleanup()

    def test_explicit_clock_is_rejected_for_empirical_backends(self) -> None:
        trace = generate_trace(
            catalog(), distribution="adversarial", seed=1, request_count=1,
            trace_id="empirical-clock-refusal", interval_ms=20,
        )
        backend = ScriptedBackend()
        backend.classification = "empirical-kubernetes-performance-evidence"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                ValueError, "explicit clocks are permitted only for non-performance evidence"
            ):
                run_trace(
                    trace, backend, Path(directory) / "ledger.jsonl",
                    Path(directory) / "evidence.json", ledger_id="empirical-clock-refusal",
                    clock=DeterministicControllerClock(),
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

    def test_every_arm_hook_waits_until_t0_is_durable(self) -> None:
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
            entered = threading.Event()
            release = threading.Event()
            real_write = __import__("os").write

            def delayed_write(descriptor: int, payload: bytes) -> int:
                entered.set()
                release.wait(timeout=5)
                return real_write(descriptor, payload)

            result: list[dict] = []

            def accept() -> None:
                result.append(sink.accept(trace["requests"][0], backend))

            try:
                with patch("performance.k8s_baseline.controller.os.write", side_effect=delayed_write):
                    thread = threading.Thread(target=accept)
                    thread.start()
                    self.assertTrue(entered.wait(timeout=2))
                    self.assertTrue(thread.is_alive())
                    self.assertEqual(ledger.stat().st_size, 0)
                    release.set()
                    thread.join(timeout=2)
                    self.assertFalse(thread.is_alive())
                event = result[0]
                self.assertTrue(ledger.exists())
                self.assertIn(event["event_id"], ledger.read_text())
            finally:
                release.set()
                sink.close()

    def test_accepted_hook_exception_retains_failure_and_later_requests(self) -> None:
        class AcceptedFailureBackend(ScriptedBackend):
            def accepted(self, request, event):
                if request["sequence"] == 0:
                    raise RuntimeError("accepted fault")
                super().accepted(request, event)

        trace = generate_trace(
            catalog(), distribution="adversarial", seed=3, request_count=6,
            trace_id="accepted-failure", interval_ms=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = run_trace(
                trace, AcceptedFailureBackend(), root / "ledger", root / "evidence",
                ledger_id="accepted-failure-ledger",
            )
            attempts = validate_ledger(load_ledger(root / "ledger"), trace)
            self.assertEqual(receipt["attempt_count"], 6)
            self.assertEqual(len(attempts), 6)
            self.assertFalse(attempts[0]["success"])
            failed_catalog = next(
                event for event in load_ledger(root / "ledger")
                if event["attempt_id"] == trace["requests"][0]["attempt_id"]
                and event["event_type"] == "phase.finished"
                and event["data"]["phase"] == "catalog_selection"
            )
            self.assertIn("accepted hook failed", failed_catalog["data"]["reason"])

    def test_cleanup_exception_emits_failed_cleanup_and_valid_ledger(self) -> None:
        class CleanupFailureBackend(ScriptedBackend):
            def cleanup(self, request):
                if request["sequence"] == 0:
                    raise RuntimeError("cleanup fault")
                return super().cleanup(request)

        trace = generate_trace(
            catalog(), distribution="adversarial", seed=4, request_count=6,
            trace_id="cleanup-failure", interval_ms=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_trace(
                trace, CleanupFailureBackend(), root / "ledger", root / "evidence",
                ledger_id="cleanup-failure-ledger",
            )
            events = load_ledger(root / "ledger")
            attempts = validate_ledger(events, trace)
            cleanup = next(
                event for event in events
                if event["attempt_id"] == trace["requests"][0]["attempt_id"]
                and event["event_type"] == "cleanup.finished"
            )
            self.assertEqual(len(attempts), 6)
            self.assertEqual(cleanup["data"]["status"], "failed")
            self.assertTrue(cleanup["data"]["resources_retained"])

    def test_partial_transfer_bytes_survive_phase_exception(self) -> None:
        class PartialBytesBackend(ScriptedBackend):
            def run_phase(self, request, phase):
                if request["sequence"] == 1 and phase == "artifact_readiness":
                    raise PhaseExecutionError("localization interrupted", bytes_moved=9876)
                return super().run_phase(request, phase)

        trace = generate_trace(
            catalog(), distribution="adversarial", seed=5, request_count=6,
            trace_id="partial-bytes", interval_ms=20,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_trace(
                trace, PartialBytesBackend(), root / "ledger", root / "evidence",
                ledger_id="partial-bytes-ledger",
            )
            aggregate = aggregate_ledger(load_ledger(root / "ledger"), trace)
            failed = aggregate["attempts"]["results"][1]
            self.assertFalse(failed["success"])
            self.assertEqual(failed["bytes_moved_total"], 9876)

    def test_acceptance_metadata_faults_fail_attempt_and_retain_later_offers(self) -> None:
        for hook in ("environment", "ownership"):
            with self.subTest(hook=hook):
                class MetadataFailureBackend(ScriptedBackend):
                    pass

                original = getattr(ScriptedBackend, hook)

                def fault(self, request, *, _original=original):
                    if request["sequence"] == 0:
                        raise RuntimeError(f"{hook} fault")
                    return _original(self, request)

                setattr(MetadataFailureBackend, hook, fault)
                trace = generate_trace(
                    catalog(), distribution="adversarial", seed=6, request_count=6,
                    trace_id=f"{hook}-failure", interval_ms=1,
                )
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    receipt = run_trace(
                        trace, MetadataFailureBackend(), root / "ledger", root / "evidence",
                        ledger_id=f"{hook}-failure-ledger",
                    )
                    attempts = validate_ledger(load_ledger(root / "ledger"), trace)
                    self.assertEqual(receipt["attempt_count"], 6)
                    self.assertEqual(len(attempts), 6)
                    self.assertFalse(attempts[0]["success"])
                    self.assertIn(
                        f"{hook} hook failed",
                        next(
                            event["data"]["reason"]
                            for event in load_ledger(root / "ledger")
                            if event["attempt_id"] == trace["requests"][0]["attempt_id"]
                            and event["event_type"] == "phase.finished"
                            and event["data"]["phase"] == "catalog_selection"
                        ),
                    )

    def test_should_skip_fault_is_terminal_and_later_offers_survive(self) -> None:
        class SkipFailureBackend(ScriptedBackend):
            def should_skip(self, request, phase):
                if request["sequence"] == 0 and phase == "drain":
                    raise RuntimeError("skip fault")
                return super().should_skip(request, phase)

        trace = generate_trace(
            catalog(), distribution="adversarial", seed=7, request_count=6,
            trace_id="skip-failure", interval_ms=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = run_trace(
                trace, SkipFailureBackend(), root / "ledger", root / "evidence",
                ledger_id="skip-failure-ledger",
            )
            attempts = validate_ledger(load_ledger(root / "ledger"), trace)
            self.assertEqual(receipt["attempt_count"], 6)
            self.assertFalse(attempts[0]["success"])
            self.assertTrue(attempts[-1]["success"])

    def test_accounting_fault_is_explicit_and_never_zero_or_idle_fabricated(self) -> None:
        class AccountingFailureBackend(ScriptedBackend):
            def accounting(self, request, elapsed_seconds, bytes_moved):
                if request["sequence"] == 0:
                    raise RuntimeError("meter fault")
                return super().accounting(request, elapsed_seconds, bytes_moved)

        trace = generate_trace(
            catalog(), distribution="adversarial", seed=8, request_count=6,
            trace_id="accounting-failure", interval_ms=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_trace(
                trace, AccountingFailureBackend(), root / "ledger", root / "evidence",
                ledger_id="accounting-failure-ledger",
            )
            events = load_ledger(root / "ledger")
            validate_ledger(events, trace)
            first = trace["requests"][0]["attempt_id"]
            accounting = next(
                item["data"] for item in events
                if item["attempt_id"] == first and item["event_type"] == "accounting.recorded"
            )
            cleanup = next(
                item["data"] for item in events
                if item["attempt_id"] == first and item["event_type"] == "cleanup.finished"
            )
            self.assertEqual(accounting["cost_usd"], 1_000_000_000.0)
            self.assertGreater(accounting["gpu_active_seconds"], 0)
            self.assertEqual(accounting["gpu_idle_seconds"], 0)
            self.assertEqual(cleanup["status"], "failed")
            self.assertIn("meter fault", cleanup["reason"])


if __name__ == "__main__":
    unittest.main()
