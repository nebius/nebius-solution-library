from __future__ import annotations

import ast
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from performance.request_slo import harness

from node_runtime.audit import AuditError
from node_runtime.supervisor import DeterministicBackend

from .helpers import (
    ARTIFACT_SHA,
    MODEL_A,
    PAYLOAD,
    binding,
    checkpoint_environment,
    environment,
    ownership,
    setup,
)


class SupervisorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_once(
        self,
        fixture: dict[str, object],
        backend: DeterministicBackend,
        *,
        suffix: str,
        checkpoint: dict[str, object] | None = None,
        required_cleanup: bool = False,
        cleanup_disposition: str = "complete",
    ) -> tuple[dict[str, object], Path, Path]:
        ledger = self.root / f"ledger-{suffix}.jsonl"
        audit = self.root / f"audit-{suffix}.jsonl"
        result = fixture["supervisor"].run(
            trace=fixture["trace"],
            command=fixture["command"],
            payload=PAYLOAD,
            backend=backend,
            environment=environment(),
            checkpoint_environment=checkpoint_environment(),
            ownership=ownership(required_cleanup),
            ledger_path=ledger,
            audit_path=audit,
            checkpoint_binding=binding() if checkpoint is None else checkpoint,
            cleanup_disposition=cleanup_disposition,
        )
        return result, ledger, audit

    def test_external_t0_full_a_to_b_snapshot_and_semantic_terminal(self) -> None:
        fixture = setup(self.root, suffix="success")
        backend = DeterministicBackend(MODEL_A)
        result, ledger, audit = self.run_once(fixture, backend, suffix="success")
        self.assertTrue(result["attempt"]["success"])
        self.assertEqual(result["effective_launch_mode"], "snapshot")
        events = harness.load_ledger(ledger)
        self.assertEqual(events[0]["event_type"], "request.accepted")
        self.assertEqual(events[0]["data"]["boundary"], harness.T0_BOUNDARY)
        self.assertEqual(events[-3]["event_type"], "response.validated")
        self.assertEqual(events[-3]["data"]["boundary"], harness.TERMINAL_BOUNDARY)
        self.assertEqual({item["data"]["phase"] for item in events if item["event_type"] == "phase.finished"}, set(harness.PHASES))
        self.assertEqual(backend.calls[:3], ["drain", "gpu_release", "placement"])
        gpu_receipt = result["phase_receipts"]["gpu_release"]
        self.assertEqual(gpu_receipt["evidence"]["scrub_method"], "cpu-fixture-surrogate")
        gpu_event = next(
            event
            for event in events
            if event["event_type"] == "phase.finished"
            and event["data"]["phase"] == "gpu_release"
        )
        self.assertIn(gpu_receipt["receipt_sha256"], gpu_event["data"]["reason"])
        self.assertTrue(result["audit"]["complete"])

    def test_stale_checkpoint_descends_once_to_conventional_without_drift(self) -> None:
        fixture = setup(self.root, scenario="checkpoint_fallback", suffix="fallback")
        stale = binding(driver_version="stale-driver")
        backend = DeterministicBackend(MODEL_A)
        result, ledger, _ = self.run_once(
            fixture, backend, suffix="fallback", checkpoint=stale
        )
        self.assertTrue(result["attempt"]["success"])
        self.assertEqual(result["effective_launch_mode"], "conventional")
        cache_finish = next(
            event
            for event in harness.load_ledger(ledger)
            if event["event_type"] == "phase.finished" and event["data"]["phase"] == "cache_readiness"
        )
        self.assertIn("descending once", cache_finish["data"]["reason"])
        self.assertEqual(fixture["trace"]["requests"][0]["target"]["artifact_sha256"], ARTIFACT_SHA)

    def test_payload_mismatch_is_rejected_before_t0_or_backend_work(self) -> None:
        fixture = setup(self.root, suffix="payload-mismatch")
        backend = DeterministicBackend(MODEL_A)
        ledger = self.root / "mismatch-ledger.jsonl"
        audit = self.root / "mismatch-audit.jsonl"
        with self.assertRaisesRegex(ValueError, "payload bytes differ"):
            fixture["supervisor"].run(
                trace=fixture["trace"],
                command=fixture["command"],
                payload=PAYLOAD + b"tampered",
                backend=backend,
                environment=environment(),
                checkpoint_environment=checkpoint_environment(),
                ownership=ownership(False),
                ledger_path=ledger,
                audit_path=audit,
                checkpoint_binding=binding(),
            )
        self.assertFalse(ledger.exists())
        self.assertFalse(audit.exists())
        self.assertEqual(backend.calls, [])

    def test_preemption_cancellation_and_capacity_failure_keep_denominator(self) -> None:
        cases = (
            ("a_to_b_local", "runtime_launch", "preempted"),
            ("a_to_b_local", "inference", "cancelled"),
            ("capacity_miss", "placement", "capacity"),
        )
        for index, (scenario, phase, failure_class) in enumerate(cases):
            with self.subTest(failure_class=failure_class):
                case_root = self.root / f"case-{index}"
                case_root.mkdir()
                fixture = setup(case_root, scenario=scenario, suffix=f"fail{index}")
                backend = DeterministicBackend(
                    MODEL_A if scenario != "capacity_miss" else None,
                    fail_phase=phase,
                    failure_class=failure_class,
                )
                result = fixture["supervisor"].run(
                    trace=fixture["trace"],
                    command=fixture["command"],
                    payload=PAYLOAD,
                    backend=backend,
                    environment=environment(),
                    checkpoint_environment=checkpoint_environment(),
                    ownership=ownership(False),
                    ledger_path=case_root / "ledger.jsonl",
                    audit_path=case_root / "audit.jsonl",
                    checkpoint_binding=binding(),
                )
                self.assertFalse(result["attempt"]["success"])
                self.assertEqual(result["attempt"]["failure_class"], failure_class)
                aggregate = harness.aggregate_ledger(
                    harness.load_ledger(case_root / "ledger.jsonl"), fixture["trace"]
                )
                self.assertEqual(aggregate["attempts"]["offered"], 1)
                self.assertEqual(aggregate["attempts"]["failures"], 1)

    def test_replay_and_valid_concurrent_launch_are_refused_after_t0(self) -> None:
        fixture = setup(self.root, suffix="replay")
        first = fixture["supervisor"].run(
            trace=fixture["trace"],
            command=fixture["command"],
            payload=PAYLOAD,
            backend=DeterministicBackend(MODEL_A),
            environment=environment(),
            checkpoint_environment=checkpoint_environment(),
            ownership=ownership(False),
            ledger_path=self.root / "first-ledger.jsonl",
            audit_path=self.root / "first-audit.jsonl",
            checkpoint_binding=binding(),
        )
        self.assertTrue(first["attempt"]["success"])
        replay = fixture["supervisor"].run(
            trace=fixture["trace"],
            command=fixture["command"],
            payload=PAYLOAD,
            backend=DeterministicBackend(MODEL_A),
            environment=environment(),
            checkpoint_environment=checkpoint_environment(),
            ownership=ownership(False),
            ledger_path=self.root / "replay-ledger.jsonl",
            audit_path=self.root / "replay-audit.jsonl",
            checkpoint_binding=binding(),
        )
        self.assertFalse(replay["attempt"]["success"])
        self.assertIn("replayed", replay["terminal_failure"])
        self.assertEqual(harness.load_ledger(self.root / "replay-ledger.jsonl")[0]["event_type"], "request.accepted")

        other_root = self.root / "concurrent"
        other_root.mkdir()
        other = setup(other_root, suffix="concurrent")
        other["supervisor"].node_lease.acquire("already-serving")
        refused = other["supervisor"].run(
            trace=other["trace"],
            command=other["command"],
            payload=PAYLOAD,
            backend=DeterministicBackend(MODEL_A),
            environment=environment(),
            checkpoint_environment=checkpoint_environment(),
            ownership=ownership(False),
            ledger_path=other_root / "ledger.jsonl",
            audit_path=other_root / "audit.jsonl",
            checkpoint_binding=binding(),
        )
        self.assertFalse(refused["attempt"]["success"])
        self.assertIn("concurrent launch", refused["terminal_failure"])

    def test_cleanup_failure_quarantines_and_chain_gap_is_detected(self) -> None:
        fixture = setup(self.root, suffix="cleanup")
        result, ledger, audit = self.run_once(
            fixture,
            DeterministicBackend(MODEL_A, cleanup_fails=True),
            suffix="cleanup",
            required_cleanup=True,
        )
        self.assertTrue(result["attempt"]["success"])
        self.assertEqual(result["attempt"]["cleanup"]["status"], "failed")
        self.assertIn("quarantined", result["attempt"]["cleanup"]["reason"])
        lines = audit.read_text(encoding="utf-8").splitlines()
        audit.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")
        with self.assertRaises(AuditError):
            fixture["supervisor"].cache  # keep fixture alive for the assertion context
            from node_runtime.audit import AuditChain

            AuditChain(audit).verify_events(harness.load_ledger(ledger))

    def test_accounting_failure_fails_attempt_but_still_cleans_up(self) -> None:
        fixture = setup(self.root, suffix="accounting")
        backend = DeterministicBackend(MODEL_A, accounting_fails=True)
        result, ledger, _ = self.run_once(fixture, backend, suffix="accounting")
        self.assertFalse(result["attempt"]["success"])
        self.assertEqual(result["attempt"]["failure_class"], "infrastructure")
        self.assertIn("accounting", result["accounting_failure"])
        self.assertEqual(backend.calls[-1], "cleanup")
        self.assertEqual(result["attempt"]["cleanup"]["status"], "not_required")
        self.assertEqual(
            harness.aggregate_ledger(harness.load_ledger(ledger), fixture["trace"])[
                "attempts"
            ]["failures"],
            1,
        )

    def test_hot_path_source_has_no_control_plane_or_object_store_client_import(self) -> None:
        source = Path(__file__).parents[1] / "node_runtime" / "supervisor.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(imports.isdisjoint({"kubernetes", "nebius", "boto3"}))


if __name__ == "__main__":
    unittest.main()
