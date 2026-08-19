from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from performance.request_slo import harness


HERE = Path(__file__).resolve().parent
FASTSTART_ROOT = HERE.parents[2]


def catalog() -> dict[str, object]:
    return {
        "schema": harness.CATALOG_SCHEMA,
        "models": [
            {
                "model_id": "model-a",
                "model_version": "v1",
                "artifact_id": "artifact-a",
                "artifact_version": "av1",
                "artifact_sha256": "a" * 64,
                "input": {
                    "workload_id": "workload-a",
                    "input_id": "input-a",
                    "payload_sha256": "b" * 64,
                    "input_bytes": 100,
                },
            },
            {
                "model_id": "model-b",
                "model_version": "v2",
                "artifact_id": "artifact-b",
                "artifact_version": "av2",
                "artifact_sha256": "c" * 64,
                "input": {
                    "workload_id": "workload-b",
                    "input_id": "input-b",
                    "payload_sha256": "d" * 64,
                    "input_bytes": 200,
                },
            },
            {
                "model_id": "model-c",
                "model_version": "v3",
                "artifact_id": "artifact-c",
                "artifact_version": "av3",
                "artifact_sha256": "e" * 64,
                "input": {
                    "workload_id": "workload-c",
                    "input_id": "input-c",
                    "payload_sha256": "f" * 64,
                    "input_bytes": 300,
                },
            },
        ],
    }


def trace(count: int = 24) -> dict[str, object]:
    return harness.generate_trace(
        catalog(),
        distribution="adversarial",
        seed=2407,
        request_count=count,
        trace_id=f"test-trace-{count}",
        interval_ms=10,
    )


def renumber(events: list[dict[str, object]]) -> None:
    attempt_sequences: dict[str, int] = {}
    for index, event in enumerate(events):
        attempt_id = str(event["attempt_id"])
        sequence = attempt_sequences.get(attempt_id, 0)
        attempt_sequences[attempt_id] = sequence + 1
        event["ledger_sequence"] = index
        event["attempt_sequence"] = sequence
        event["event_id"] = f"{attempt_id}:{sequence:06d}"


class TraceTests(unittest.TestCase):
    def test_generators_are_deterministic_and_checksum_pinned(self) -> None:
        for distribution in ("uniform", "skewed", "adversarial"):
            with self.subTest(distribution=distribution):
                first = harness.generate_trace(
                    catalog(),
                    distribution=distribution,
                    seed=11,
                    request_count=30,
                    trace_id=f"{distribution}-trace",
                )
                second = harness.generate_trace(
                    catalog(),
                    distribution=distribution,
                    seed=11,
                    request_count=30,
                    trace_id=f"{distribution}-trace",
                )
                self.assertEqual(first, second)
                self.assertEqual(
                    {item["scenario"] for item in first["requests"]},
                    set(harness.SCENARIOS),
                )
                changed = copy.deepcopy(first)
                changed["requests"][0]["offered_at_offset_ms"] += 1
                with self.assertRaisesRegex(harness.HarnessError, "checksum"):
                    harness.validate_trace(changed)

    def test_property_many_seeds_remain_valid_and_reproducible(self) -> None:
        digests: set[str] = set()
        for seed in range(40):
            generated = harness.generate_trace(
                catalog(),
                distribution="skewed",
                seed=seed,
                request_count=18,
                trace_id=f"property-trace-{seed}",
                interval_ms=seed,
            )
            self.assertEqual(harness.validate_trace(generated), generated)
            reproduced = harness.generate_trace(
                catalog(),
                distribution="skewed",
                seed=seed,
                request_count=18,
                trace_id=f"property-trace-{seed}",
                interval_ms=seed,
            )
            self.assertEqual(generated["trace_sha256"], reproduced["trace_sha256"])
            digests.add(generated["trace_sha256"])
        self.assertEqual(len(digests), 40)

    def test_scenario_preconditions_fail_closed(self) -> None:
        generated = trace(6)
        request = generated["requests"][0]
        request["precondition"]["current_node_occupant"] = None
        generated["trace_sha256"] = harness.canonical_sha256(
            {key: value for key, value in generated.items() if key != "trace_sha256"}
        )
        with self.assertRaisesRegex(harness.HarnessError, "occupant"):
            harness.validate_trace(generated)


class LedgerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = trace()
        self.events = harness.synthetic_smoke_ledger(self.trace)

    def test_valid_ledger_preserves_all_attempts_and_boundaries(self) -> None:
        attempts = harness.validate_ledger(self.events, self.trace)
        self.assertEqual(len(attempts), 24)
        self.assertEqual(sum(item["success"] for item in attempts), 20)
        self.assertEqual(sum(not item["success"] for item in attempts), 4)
        self.assertEqual(
            {item["scenario"] for item in attempts}, set(harness.SCENARIOS)
        )

    def test_excluded_failure_is_rejected(self) -> None:
        removed = self.trace["requests"][-1]["attempt_id"]
        events = [
            copy.deepcopy(event)
            for event in self.events
            if event["attempt_id"] != removed
        ]
        renumber(events)
        with self.assertRaisesRegex(harness.HarnessError, "excludes or invents"):
            harness.validate_ledger(events, self.trace)

    def test_request_specific_setup_before_t0_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        first = events[0]
        second = next(
            event
            for event in events
            if event["attempt_id"] == first["attempt_id"]
            and event["event_type"] == "phase.started"
        )
        first["event_type"], second["event_type"] = (
            second["event_type"],
            first["event_type"],
        )
        first["data"], second["data"] = second["data"], first["data"]
        with self.assertRaisesRegex(harness.HarnessError, "moved before"):
            harness.validate_ledger(events, self.trace)

    def test_clock_drift_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        original = datetime.strptime(
            events[4]["observed_at_utc"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=UTC)
        events[4]["observed_at_utc"] = (original + timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        with self.assertRaisesRegex(harness.HarnessError, "clock"):
            harness.validate_ledger(events, self.trace)

    def test_stale_model_version_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        events[0]["data"]["target"]["model_version"] = "stale-v0"
        with self.assertRaisesRegex(harness.HarnessError, "differs from the trace"):
            harness.validate_ledger(events, self.trace)

    def test_mixed_workload_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        events[0]["data"]["input"]["workload_id"] = "other-workload"
        with self.assertRaisesRegex(harness.HarnessError, "differs from the trace"):
            harness.validate_ledger(events, self.trace)

    def test_mixed_event_request_identity_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        phase = next(
            event for event in events if event["event_type"] == "phase.started"
        )
        phase["request_id"] = "request-from-another-workload"
        with self.assertRaisesRegex(harness.HarnessError, "mixed request identity"):
            harness.validate_ledger(events, self.trace)

    def test_trace_acceptance_schedule_drift_is_rejected(self) -> None:
        changed_trace = copy.deepcopy(self.trace)
        request = changed_trace["requests"][-1]
        request["offered_at_offset_ms"] += 500
        changed_trace["trace_sha256"] = harness.canonical_sha256(
            {
                key: value
                for key, value in changed_trace.items()
                if key != "trace_sha256"
            }
        )
        events = copy.deepcopy(self.events)
        accepted = next(
            event
            for event in events
            if event["attempt_id"] == request["attempt_id"]
            and event["event_type"] == "request.accepted"
        )
        accepted["data"]["trace_request_sha256"] = harness.canonical_sha256(request)
        with self.assertRaisesRegex(harness.HarnessError, "acceptance schedule"):
            harness.validate_ledger(events, changed_trace)

    def test_incomplete_or_nonsemantic_response_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        response = next(
            event for event in events if event["event_type"] == "response.validated"
        )
        response["data"]["complete_body"] = False
        with self.assertRaisesRegex(harness.HarnessError, "not complete"):
            harness.validate_ledger(events, self.trace)

    def test_omitted_phase_is_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        attempt_id = self.trace["requests"][0]["attempt_id"]
        events = [
            event
            for event in events
            if not (
                event["attempt_id"] == attempt_id
                and event["data"].get("phase") == "storage_readiness"
            )
        ]
        renumber(events)
        with self.assertRaisesRegex(harness.HarnessError, "prerequisites|omitted"):
            harness.validate_ledger(events, self.trace)

    def test_hidden_bytes_are_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        accounting = next(
            event for event in events if event["event_type"] == "accounting.recorded"
        )
        accounting["data"]["bytes_moved_total"] += 1
        with self.assertRaisesRegex(harness.HarnessError, "bytes"):
            harness.validate_ledger(events, self.trace)

    def test_cleanup_cannot_invent_or_omit_owned_resources(self) -> None:
        events = copy.deepcopy(self.events)
        cleanup = next(
            event for event in events if event["event_type"] == "cleanup.finished"
        )
        cleanup["data"]["resources_deleted"] = ["unowned-resource"]
        with self.assertRaisesRegex(harness.HarnessError, "cleanup final state"):
            harness.validate_ledger(events, self.trace)

    def test_mixed_recorder_clocks_are_rejected(self) -> None:
        events = copy.deepcopy(self.events)
        events[-1]["recorder"]["clock_id"] = "backend-owned-clock"
        with self.assertRaisesRegex(harness.HarnessError, "recorder clocks"):
            harness.validate_ledger(events, self.trace)

    def test_noncanonical_and_duplicate_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.jsonl"
            path.write_text(json.dumps(self.events[0]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(harness.HarnessError, "not canonical"):
                harness.load_ledger(path)
            path.write_text(
                '{"schema":"x","schema":"y"}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(harness.HarnessError, "duplicate JSON key"):
                harness.load_ledger(path)

    def test_canonical_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.jsonl"
            trace_path = Path(temporary) / "trace.json"
            harness.write_ledger(ledger, self.events)
            harness.write_canonical_json(trace_path, self.trace)
            loaded_trace = harness.load_trace(trace_path)
            loaded_events = harness.load_ledger(ledger)
            self.assertEqual(
                harness.validate_ledger(loaded_events, loaded_trace),
                harness.validate_ledger(self.events, self.trace),
            )


class AggregateTests(unittest.TestCase):
    def test_percentiles_use_raw_totals_and_withhold_unsupported_values(self) -> None:
        generated = trace(24)
        events = harness.synthetic_smoke_ledger(generated)
        attempts = harness.validate_ledger(events, generated)
        result = harness.aggregate_ledger(events, generated)
        raw = sorted(item["terminal_seconds"] for item in attempts if item["success"])
        expected_p95 = raw[math.ceil(0.95 * len(raw)) - 1]
        self.assertEqual(result["product_latency_seconds"]["sample_count"], 20)
        self.assertEqual(result["product_latency_seconds"]["p95"], expected_p95)
        self.assertIsNone(result["product_latency_seconds"]["p99"])
        self.assertTrue(
            all(
                not phase["additive_to_product_percentiles"]
                for phase in result["phases"].values()
            )
        )
        self.assertEqual(result["attempts"]["offered"], 24)
        self.assertEqual(result["attempts"]["failures"], 4)

    def test_p99_is_only_emitted_with_one_hundred_valid_responses(self) -> None:
        generated = trace(120)
        events = harness.synthetic_smoke_ledger(generated)
        result = harness.aggregate_ledger(events, generated)
        self.assertEqual(result["product_latency_seconds"]["sample_count"], 100)
        self.assertIsNotNone(result["product_latency_seconds"]["p99"])

    def test_cache_cost_gpu_transfer_and_cleanup_are_reported(self) -> None:
        generated = trace(24)
        result = harness.aggregate_ledger(
            harness.synthetic_smoke_ledger(generated), generated
        )
        self.assertEqual(result["transfer"]["bytes_moved_total"], 16 * 1024)
        self.assertEqual(result["cost"]["total"], 0.0)
        self.assertEqual(result["gpu"]["active_seconds"], 0.0)
        self.assertEqual(result["cleanup"], {"not_required": 24})
        self.assertIn("remote_miss", result["cache"]["artifact"]["states"])
        self.assertGreater(result["phases"]["placement"]["outcomes"]["skipped"], 0)
        self.assertEqual(result["environments"][0]["attempt_count"], 24)
        self.assertEqual(result["resource_ownership"][0]["attempt_count"], 24)
        self.assertIn("artifact_version", result["attempts"]["results"][0])


class LegacyAdapterTests(unittest.TestCase):
    def test_real_published_cohorts_import_read_only_as_internal_stage(self) -> None:
        sources = {
            "openfold2": FASTSTART_ROOT
            / "performance/openfold2/fresh-cohort-n20-results.tsv",
            "boltz2": FASTSTART_ROOT / "boltz2-native/fresh-cohort-n20-results.tsv",
        }
        for model, path in sources.items():
            with self.subTest(model=model):
                before = harness.file_sha256(path)
                imported = harness.import_legacy_cohort(path, model)
                after = harness.file_sha256(path)
                self.assertEqual(before, after)
                self.assertEqual(imported["source"]["sha256"], before)
                self.assertEqual(imported["source"]["sample_rows"], 20)
                self.assertEqual(imported["source"]["excluded_published_summary_rows"], 3)
                self.assertEqual(
                    imported["evidence_classification"],
                    "prepared-node-internal-stage-only",
                )
                self.assertFalse(imported["eligible_for_product_slo"])
                self.assertIsNone(imported["product_boundary"])


class SchemaAndRecorderTests(unittest.TestCase):
    def test_versioned_json_schemas_are_parseable_and_closed(self) -> None:
        for filename, expected in (
            ("event.schema.json", "catalog-switch-ledger-event-v1"),
            ("trace.schema.json", "catalog-switch-trace-v1"),
        ):
            with self.subTest(filename=filename):
                schema = json.loads((HERE.parent / filename).read_text(encoding="utf-8"))
                self.assertIn(expected, schema["$id"])
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_reference_recorder_appends_canonical_sequenced_events(self) -> None:
        recorder = {
            "recorder_id": "test-recorder",
            "clock_id": "test-clock",
            "boot_id": "test-boot",
            "utc_sync_source": "test-source",
            "max_error_ms": 50.0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.jsonl"
            first = harness.append_event(
                path,
                ledger_id="ledger-one",
                trace_id="trace-one",
                request_id="request-one",
                attempt_id="attempt-one",
                recorder=recorder,
                event_type="phase.started",
                data={"phase": "queue", "occurrence": 0},
            )
            second = harness.append_event(
                path,
                ledger_id="ledger-one",
                trace_id="trace-one",
                request_id="request-one",
                attempt_id="attempt-one",
                recorder=recorder,
                event_type="phase.finished",
                data={
                    "phase": "queue",
                    "occurrence": 0,
                    "outcome": "completed",
                    "reason": "test",
                    "bytes_moved": 0,
                },
            )
            loaded = harness.load_ledger(path)
            self.assertEqual(loaded, [first, second])
            self.assertEqual(second["ledger_sequence"], 1)
            self.assertEqual(second["attempt_sequence"], 1)


if __name__ == "__main__":
    unittest.main()
