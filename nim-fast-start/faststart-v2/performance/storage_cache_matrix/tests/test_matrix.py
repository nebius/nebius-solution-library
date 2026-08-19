from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from performance.request_slo.harness import canonical_sha256
from performance.storage_cache_matrix.matrix import (
    MatrixError,
    _validate_environment,
    aggregate_matrix,
    load_attempts,
    load_plan,
    validate_matrix,
    write_attempts,
    write_canonical_json,
)
from performance.storage_cache_matrix.smoke import build_smoke


class MatrixContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan, self.attempts = build_smoke(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self, plan=None, attempts=None):
        return validate_matrix(plan or self.plan, attempts or self.attempts, self.root)

    def repin(self, plan, attempts):
        digest = canonical_sha256(plan)
        for attempt in attempts:
            attempt["plan_sha256"] = digest

    def attempt_for(self, cohort: str):
        return next(attempt for attempt in self.attempts if attempt["cohort"] == cohort)

    def test_smoke_is_bound_complete_and_not_performance_evidence(self) -> None:
        shaped = self.validate()
        self.assertEqual(len(shaped), 10)
        self.assertEqual(
            {item["raw"]["tier"] for item in shaped},
            {"local_nvme", "attached_block_pvc", "remote_artifact"},
        )
        self.assertEqual(
            {item["raw"]["cohort"] for item in shaped},
            set(
                (
                    "hot",
                    "warm",
                    "cold",
                    "eviction_repopulation",
                    "concurrent_fetch",
                    "corruption",
                    "boltz_external_tmp_hit",
                    "boltz_external_tmp_clone_miss",
                )
            ),
        )
        self.assertEqual(
            self.plan["evidence_classification"],
            "synthetic-smoke-not-performance-evidence",
        )

    def test_versioned_json_schemas_are_closed_and_parseable(self) -> None:
        package = Path(__file__).resolve().parents[1]
        for name in ("plan.schema.json", "attempt.schema.json"):
            schema = json.loads((package / name).read_text())
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_plan_and_attempt_ledger_require_canonical_json(self) -> None:
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan, indent=2) + "\n")
        with self.assertRaisesRegex(MatrixError, "canonical sorted compact"):
            load_plan(plan_path)
        write_canonical_json(plan_path, self.plan)
        attempts_path = self.root / "attempts.jsonl"
        attempts_path.write_text(json.dumps(self.attempts[0], indent=2) + "\n")
        with self.assertRaisesRegex(MatrixError, "invalid JSON|not canonical"):
            load_attempts(attempts_path)

    def test_metric_contract_and_boltz_contract_are_hash_pinned(self) -> None:
        metric = self.root / self.plan["metric_contract"]["path"]
        metric.write_text(metric.read_text() + "# drift\n")
        with self.assertRaisesRegex(MatrixError, "metric contract file differs"):
            self.validate()
        self.setUp_after_contract_mutation()
        boltz = self.root / self.plan["boltz_external_tmp"]["contract_path"]
        boltz.write_text(boltz.read_text() + "\n")
        with self.assertRaisesRegex(MatrixError, "Boltz external-/tmp contract digest differs"):
            self.validate()

    def setUp_after_contract_mutation(self) -> None:
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan, self.attempts = build_smoke(self.root)

    def test_plan_cannot_expand_project_scope_or_disable_nvme_gate(self) -> None:
        plan = copy.deepcopy(self.plan)
        attempts = copy.deepcopy(self.attempts)
        plan["environment_requirements"]["allowed_projects"].append("project-foreign")
        self.repin(plan, attempts)
        with self.assertRaisesRegex(MatrixError, "project allowlist"):
            self.validate(plan, attempts)
        plan = copy.deepcopy(self.plan)
        attempts = copy.deepcopy(self.attempts)
        plan["environment_requirements"]["local_nvme_requires_verified_entitlement"] = False
        self.repin(plan, attempts)
        with self.assertRaisesRegex(MatrixError, "entitlement gate"):
            self.validate(plan, attempts)

    def test_artifact_version_digest_size_and_payload_are_matched_across_tiers(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["artifact"]["bytes"] += 1
        with self.assertRaisesRegex(MatrixError, "byte/version matched"):
            self.validate(attempts=attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[1]["cache"]["artifact_sha256"] = "f" * 64
        with self.assertRaisesRegex(MatrixError, "digest differs"):
            self.validate(attempts=attempts)

    def test_request_specific_phase_before_external_t0_is_rejected(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        phase = attempts[0]["phases"][12]
        phase["started_monotonic_ns"] = attempts[0]["request"]["accepted_monotonic_ns"] - 1
        with self.assertRaisesRegex(MatrixError, "noncausal duration"):
            self.validate(attempts=attempts)

    def test_terminal_must_equal_bound_external_recorder_terminal(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["terminal"]["observed_monotonic_ns"] -= 1
        with self.assertRaisesRegex(MatrixError, "receipt terminal"):
            self.validate(attempts=attempts)

    def test_bound_trace_and_ledger_are_hash_and_semantically_validated(self) -> None:
        ledger = self.root / self.attempts[0]["request_slo_binding"]["ledger_path"]
        ledger.write_text(ledger.read_text() + "{}\n")
        with self.assertRaisesRegex(MatrixError, "bound request-SLO ledger digest differs"):
            self.validate()

    def test_phase_bytes_must_reconcile_with_accounting(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[5]["accounting"]["bytes_network_total"] += 1
        with self.assertRaisesRegex(MatrixError, "omits or double-counts"):
            self.validate(attempts=attempts)

    def test_hit_requires_age_and_exact_cache_version(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        hit = next(attempt for attempt in attempts if attempt["cache"]["state"] == "hit")
        hit["cache"]["age_seconds"] = None
        with self.assertRaisesRegex(MatrixError, "must be a number"):
            self.validate(attempts=attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["cache"]["artifact_version"] = "stale-version"
        with self.assertRaisesRegex(MatrixError, "version differs"):
            self.validate(attempts=attempts)

    def test_corrupt_generation_must_be_deleted_and_proved_absent(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        corrupt = next(attempt for attempt in attempts if attempt["cohort"] == "corruption")
        corrupt["cleanup"]["final_state"] = "SEALED_RETAINED"
        corrupt["cleanup"]["verified_absent"] = False
        corrupt["cleanup"]["reusable"] = True
        with self.assertRaisesRegex(MatrixError, "dirty/corrupt generation"):
            self.validate(attempts=attempts)

    def test_deleted_dirty_generation_cannot_be_reused(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        corrupt = next(attempt for attempt in attempts if attempt["cohort"] == "corruption")
        later = max(attempts, key=lambda item: item["request"]["accepted_monotonic_ns"])
        later["cache"]["generation_id"] = corrupt["cache"]["generation_id"]
        later["cleanup"]["generation_id"] = corrupt["cache"]["generation_id"]
        with self.assertRaisesRegex(MatrixError, "dirty/deleted generation was reused"):
            self.validate(attempts=attempts)

    def test_concurrent_fetches_have_unique_mutable_namespaces_and_real_overlap(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        concurrent = [attempt for attempt in attempts if attempt["cohort"] == "concurrent_fetch"]
        concurrent[1]["concurrency"]["mutable_namespace_id"] = concurrent[0]["concurrency"][
            "mutable_namespace_id"
        ]
        with self.assertRaisesRegex(MatrixError, "mutable namespace"):
            self.validate(attempts=attempts)
        attempts = copy.deepcopy(self.attempts)
        concurrent = [attempt for attempt in attempts if attempt["cohort"] == "concurrent_fetch"]
        first_fetch = next(phase for phase in concurrent[0]["phases"] if phase["name"] == "artifact_fetch")
        second_fetch = next(phase for phase in concurrent[1]["phases"] if phase["name"] == "artifact_fetch")
        second_fetch["started_monotonic_ns"] = first_fetch["finished_monotonic_ns"] + 1
        second_fetch["finished_monotonic_ns"] = second_fetch["started_monotonic_ns"] + 1
        with self.assertRaisesRegex(MatrixError, "does not overlap"):
            self.validate(attempts=attempts)

    def test_boltz_hit_is_clone_free_and_miss_clone_is_after_t0_with_bytes(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        hit = next(attempt for attempt in attempts if attempt["cohort"] == "boltz_external_tmp_hit")
        clone = next(phase for phase in hit["phases"] if phase["name"] == "clone")
        clone["outcome"] = "completed"
        clone["started_monotonic_ns"] = clone["finished_monotonic_ns"] - 1
        clone["started_at_utc"] = clone["finished_at_utc"]
        with self.assertRaisesRegex(MatrixError, "clone-free hit"):
            self.validate(attempts=attempts)
        attempts = copy.deepcopy(self.attempts)
        miss = next(
            attempt for attempt in attempts if attempt["cohort"] == "boltz_external_tmp_clone_miss"
        )
        clone = next(phase for phase in miss["phases"] if phase["name"] == "clone")
        clone["bytes_written"] = 0
        miss["accounting"]["bytes_written_total"] -= miss["artifact"]["bytes"]
        with self.assertRaisesRegex(MatrixError, "omits byte accounting"):
            self.validate(attempts=attempts)

    def test_boltz_cohort_cannot_be_relabelled_to_another_model(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        boltz = next(
            attempt for attempt in attempts if attempt["cohort"] == "boltz_external_tmp_hit"
        )
        protein = next(attempt for attempt in attempts if attempt["artifact"]["model_id"] == "proteinmpnn")
        boltz["artifact"] = copy.deepcopy(protein["artifact"])
        boltz["cache"]["artifact_version"] = protein["artifact"]["artifact_version"]
        boltz["cache"]["artifact_sha256"] = protein["artifact"]["sha256"]
        with self.assertRaises(MatrixError):
            self.validate(attempts=attempts)

    def test_measured_environment_is_allowlisted_and_nvme_is_entitlement_gated(self) -> None:
        environment = copy.deepcopy(self.attempts[1]["environment"])
        environment.update(
            {
                "project_id": "project-foreign",
                "region": "eu-north1",
                "node_id": "computeinstance-test",
                "gpu_type": "H100",
                "gpu_count": 1,
            }
        )
        with self.assertRaisesRegex(MatrixError, "outside the epic"):
            _validate_environment(environment, "measured-live-product-slo", "local_nvme")
        environment["project_id"] = "project-e00z6b02t8ddk96c49"
        with self.assertRaisesRegex(MatrixError, "entitlement/device proof"):
            _validate_environment(environment, "measured-live-product-slo", "local_nvme")

    def test_supporting_evidence_is_digest_pinned_and_symlink_rejected(self) -> None:
        marker = self.root / self.attempts[0]["supporting_evidence"][0]["path"]
        marker.write_text(marker.read_text() + "drift\n")
        with self.assertRaisesRegex(MatrixError, "supporting evidence digest differs"):
            self.validate()
        self.setUp_after_contract_mutation()
        real = self.root / "real-marker"
        real.write_text("x")
        link = self.root / "marker-link"
        link.symlink_to(real)
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["supporting_evidence"][0]["path"] = link.name
        attempts[0]["supporting_evidence"][0]["sha256"] = "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
        with self.assertRaisesRegex(MatrixError, "regular non-symlink"):
            self.validate(attempts=attempts)

    def test_matrix_minimum_counts_are_fail_closed(self) -> None:
        attempts = self.attempts[:-1]
        with self.assertRaisesRegex(MatrixError, "matrix is incomplete"):
            self.validate(attempts=attempts)

    def test_aggregate_retains_failures_raw_samples_and_percentile_thresholds(self) -> None:
        aggregate = aggregate_matrix(
            self.plan,
            self.attempts,
            self.root,
            evidence_source="synthetic test source",
        )
        self.assertEqual(aggregate["attempts"]["observed"], 10)
        self.assertEqual(aggregate["attempts"]["failures"], 2)
        self.assertEqual(aggregate["attempts"]["failure_classes"], {"capacity": 2})
        self.assertIsNotNone(aggregate["product_latency_seconds"]["p50"])
        self.assertIsNone(aggregate["product_latency_seconds"]["p95"])
        self.assertIsNone(aggregate["product_latency_seconds"]["p99"])
        self.assertEqual(len(aggregate["product_latency_seconds"]["samples"]), 8)

    def test_exports_supply_simulator_and_router_without_summing_phase_percentiles(self) -> None:
        aggregate = aggregate_matrix(
            self.plan,
            self.attempts,
            self.root,
            evidence_source="synthetic test source",
        )
        simulator = aggregate["simulator_overrides"]
        self.assertEqual(simulator["schema_version"], "1.0.0")
        self.assertEqual(simulator["kind"], "synthetic-contract-overrides-not-admissible")
        self.assertIn("l2_fetch_bytes_per_s", simulator["fleet"])
        self.assertIn("proteinmpnn", simulator["models"])
        router = aggregate["router_locality_costs"]
        self.assertIn("phase percentile summation is forbidden", router["cost_semantics"])
        self.assertEqual(len(router["cells"]), len(self.plan["matrix"]["cells"]))
        self.assertTrue(
            any(cell["localization_seconds_samples"] for cell in router["cells"])
        )

    def test_publication_cache_investment_and_request_cost_stay_separate(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["accounting"]["request_cost_usd"] = 1.0
        attempts[0]["accounting"]["publication_cost_usd"] = 2.0
        attempts[0]["accounting"]["node_cache_investment_cost_usd"] = 3.0
        aggregate = aggregate_matrix(
            self.plan, attempts, self.root, evidence_source="synthetic test source"
        )
        self.assertEqual(aggregate["totals"]["request_cost_usd"], 1.0)
        self.assertEqual(aggregate["totals"]["publication_cost_usd"], 2.0)
        self.assertEqual(aggregate["totals"]["node_cache_investment_cost_usd"], 3.0)

    def test_synthetic_boltz_coverage_is_never_promoted_to_measurement(self) -> None:
        aggregate = aggregate_matrix(
            self.plan,
            self.attempts,
            self.root,
            evidence_source="synthetic test source",
        )
        self.assertEqual(
            aggregate["boltz_external_tmp"]["status"],
            "synthetic_contract_coverage_not_measurement",
        )
        self.assertFalse(aggregate["boltz_external_tmp"]["projections_are_results"])


if __name__ == "__main__":
    unittest.main()
