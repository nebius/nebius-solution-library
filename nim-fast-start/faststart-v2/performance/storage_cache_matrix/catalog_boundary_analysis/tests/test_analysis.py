from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from performance.request_slo.harness import (
    canonical_json,
    canonical_sha256,
    load_ledger,
    load_trace,
    validate_ledger,
)
from performance.storage_cache_matrix.catalog_boundary_analysis.analysis import (
    ATTEMPT_SCHEMA,
    AnalysisError,
    analyze_capacity,
    load_attempts,
    validate_attempts,
    validate_source_manifest,
    verify_pinned_sources,
)
from performance.storage_cache_matrix.smoke import build_smoke


PACKAGE = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[6]
TASK_DECK_ROOT = Path("/home/tux/dashboard/data")
ZERO_DIGEST = "0" * 64


def _load(name: str):
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


class CatalogBoundaryAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = _load("source_manifest.json")
        self.config = _load("analysis_config.json")
        _, matrix_attempts = build_smoke(self.root)
        trace = load_trace(self.root / "request-slo-trace.json")
        events = load_ledger(self.root / "request-slo-ledger.jsonl")
        results = {
            result["attempt_id"]: result for result in validate_ledger(events, trace)
        }
        by_cohort: dict[str, list[dict]] = {}
        for attempt in matrix_attempts:
            by_cohort.setdefault(attempt["cohort"], []).append(attempt)
        sources = {
            "A_materialized_hit": by_cohort["boltz_external_tmp_hit"][0],
            "B_node_seed_post_t0_materialization": by_cohort["corruption"][0],
            "C_remote_miss_post_t0": by_cohort["cold"][0],
            "D_active_a_to_b_reclaim": by_cohort[
                "boltz_external_tmp_clone_miss"
            ][0],
        }
        marker = self.root / "storage-operation-source.txt"
        marker.write_text("synthetic contract fixture; not performance evidence\n")
        marker_sha = __import__("hashlib").sha256(marker.read_bytes()).hexdigest()
        self.attempts = [
            self._build_attempt(state, source, results[source["attempt_id"]], marker_sha)
            for state, source in sources.items()
        ]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _build_attempt(self, state, source, slo_result, marker_sha):
        artifact = source["artifact"]
        size = artifact["bytes"]
        t0 = source["request"]["accepted_monotonic_ns"]
        active = slo_result["current_node_occupant"]
        source_flags = {
            "A_materialized_hit": (True, False, False, "materialized_generation"),
            "B_node_seed_post_t0_materialization": (
                False,
                True,
                False,
                "immutable_node_local_seed",
            ),
            "C_remote_miss_post_t0": (
                False,
                False,
                True,
                "immutable_remote_artifact",
            ),
            "D_active_a_to_b_reclaim": (
                False,
                True,
                False,
                "immutable_node_local_seed",
            ),
        }[state]
        complete = {"catalog_selection", "queue", "first_read"}
        if state == "B_node_seed_post_t0_materialization":
            complete |= {"clone", "materialization", "hash"}
        elif state == "C_remote_miss_post_t0":
            complete |= {"artifact_fetch", "materialization", "hash"}
        elif state == "D_active_a_to_b_reclaim":
            complete |= {
                "drain",
                "gpu_release",
                "eviction",
                "clone",
                "materialization",
                "hash",
            }
        operations = []
        for index, name in enumerate(
            (
                "catalog_selection",
                "queue",
                "drain",
                "gpu_release",
                "eviction",
                "artifact_fetch",
                "clone",
                "materialization",
                "hash",
                "first_read",
            ),
            1,
        ):
            completed = name in complete
            byte_fields = {
                "logical_bytes": 0,
                "bytes_read": 0,
                "bytes_written": 0,
                "bytes_network": 0,
                "bytes_deleted": 0,
            }
            if completed and name in {
                "artifact_fetch",
                "clone",
                "materialization",
                "hash",
                "first_read",
                "eviction",
            }:
                byte_fields["logical_bytes"] = size
            if completed and name == "artifact_fetch":
                byte_fields["bytes_network"] = size
            if completed and name == "clone":
                byte_fields["bytes_read"] = size
                byte_fields["bytes_written"] = size
            if completed and name == "materialization":
                byte_fields["bytes_written"] = size
            if completed and name in {"hash", "first_read"}:
                byte_fields["bytes_read"] = size
            if completed and name == "eviction":
                byte_fields["bytes_deleted"] = size
            operations.append(
                {
                    "name": name,
                    "outcome": "completed" if completed else "skipped",
                    "started_monotonic_ns": t0 + index * 10_000_000
                    if completed
                    else None,
                    "finished_monotonic_ns": t0 + index * 10_000_000 + 1_000_000
                    if completed
                    else None,
                    **byte_fields,
                    "reason": "synthetic fixture operation"
                    if completed
                    else "not required by this cache state",
                    "evidence_sha256": marker_sha,
                }
            )
        totals = {
            key: sum(operation[key.replace("_total", "")] for operation in operations)
            for key in (
                "bytes_read_total",
                "bytes_written_total",
                "bytes_network_total",
                "bytes_deleted_total",
            )
        }
        investment = {
            "publication_bytes": size if state == "C_remote_miss_post_t0" else 0,
            "publication_cost_usd": 0.0,
            "node_seed_bytes": size
            if state
            in {
                "B_node_seed_post_t0_materialization",
                "D_active_a_to_b_reclaim",
            }
            else 0,
            "node_seed_prehydration_bytes": size
            if state
            in {
                "B_node_seed_post_t0_materialization",
                "D_active_a_to_b_reclaim",
            }
            else 0,
            "node_seed_prehydration_cost_usd": 0.0,
            "node_seed_residency_seconds": 60.0
            if state
            in {
                "B_node_seed_post_t0_materialization",
                "D_active_a_to_b_reclaim",
            }
            else 0.0,
            "node_seed_residency_cost_usd": 0.0,
            "materialized_bytes": size if state == "A_materialized_hit" else 0,
            "materialized_prehydration_bytes": size
            if state == "A_materialized_hit"
            else 0,
            "materialized_prehydration_cost_usd": 0.0,
            "materialized_residency_seconds": 60.0
            if state == "A_materialized_hit"
            else 0.0,
            "materialized_residency_cost_usd": 0.0,
            "price_source": "synthetic-zero-cost-contract-fixture",
            "included_in_request_totals": False,
        }
        return {
            "schema": ATTEMPT_SCHEMA,
            "source_manifest_sha256": canonical_sha256(self.manifest),
            "evidence_classification": (
                "synthetic-contract-smoke-not-performance-evidence"
            ),
            "attempt_id": source["attempt_id"],
            "request_id": source["request_id"],
            "cache_state": state,
            "demand_label": {
                "A_materialized_hit": "cache_hit",
                "B_node_seed_post_t0_materialization": "unknown_model_cold_start",
                "C_remote_miss_post_t0": "unknown_model_cold_start",
                "D_active_a_to_b_reclaim": "active_a_to_b_switch",
            }[state],
            "target": {
                "model_id": artifact["model_id"],
                "model_version": artifact["model_version"],
                "artifact_id": artifact["artifact_id"],
                "artifact_version": artifact["artifact_version"],
                "artifact_sha256": artifact["sha256"],
                "artifact_bytes": size,
            },
            "starting_state": {
                "selected_node_id": f"synthetic-node-{state[0].lower()}",
                "target_materialized": source_flags[0],
                "immutable_node_local_seed_present": source_flags[1],
                "remote_artifact_required": source_flags[2],
                "target_source": source_flags[3],
                "source_artifact_version": artifact["artifact_version"],
                "source_artifact_sha256": artifact["sha256"],
                "source_age_seconds": 60.0,
                "active_model": active,
            },
            "request": copy.deepcopy(source["request"]),
            "request_slo_binding": copy.deepcopy(source["request_slo_binding"]),
            "pre_t0_investment": investment,
            "operations": operations,
            "accounting": {
                **totals,
                "request_slo_bytes_moved_total": slo_result["accounting"][
                    "bytes_moved_total"
                ],
                "request_slo_cost_usd": slo_result["accounting"]["cost_usd"],
            },
            "concurrency": {
                "group_id": None,
                "peer_attempt_ids": [],
                "mutable_namespace_id": f"mutable-{state[0].lower()}",
                "source_read_only": True,
            },
            "cleanup": {
                "generation_id": f"generation-{state[0].lower()}",
                "final_state": "SEALED_RETAINED"
                if state == "A_materialized_hit"
                else "ABSENT",
                "dirty": state != "A_materialized_hit",
                "reusable": state == "A_materialized_hit",
                "verified_absent": state != "A_materialized_hit",
                "receipt_sha256": marker_sha,
            },
            "supporting_evidence": [
                {
                    "kind": "synthetic-fixture",
                    "path": "storage-operation-source.txt",
                    "sha256": marker_sha,
                }
            ],
        }

    def validate(self, attempts=None):
        return validate_attempts(
            self.manifest, attempts or self.attempts, self.root
        )

    def test_source_manifest_is_fail_closed_and_offline(self) -> None:
        manifest = validate_source_manifest(self.manifest)
        self.assertFalse(manifest["execution_gate"]["live_execution_permitted"])
        self.assertEqual(manifest["execution_gate"]["created_resource_ids"], [])
        self.assertEqual(
            manifest["execution_gate"]["local_nvme"]["status"],
            "unavailable-entitlement-not-proven",
        )

    def test_pinned_git_sources_and_manager_observation_verify(self) -> None:
        result = verify_pinned_sources(
            self.manifest,
            REPO_ROOT,
            TASK_DECK_ROOT if TASK_DECK_ROOT.exists() else None,
        )
        self.assertEqual(result["verified_file_count"], 10)
        checked_in = json.loads(
            (PACKAGE / "results/source-verification.json").read_text()
        )
        for key in (
            "source_manifest_sha256",
            "verified_file_count",
            "boltz_status_observation",
            "live_execution_permitted",
            "created_resource_ids",
        ):
            self.assertEqual(checked_in[key], result[key])
        if TASK_DECK_ROOT.exists():
            self.assertEqual(
                result["boltz_status_observation"], "verified-in-task-deck"
            )

    def test_boltz_status_is_not_promoted_to_external_t0_result(self) -> None:
        result = analyze_capacity(self.manifest, self.config)
        boltz = result["boltz_external_tmp"]
        self.assertEqual(boltz["bytes_per_attempt"], 1_826_220_898)
        self.assertEqual(boltz["elapsed_seconds_range"], [440, 442])
        self.assertIsNone(boltz["external_t0_latency_distribution"])

    def test_capacity_math_is_deterministic_and_labeled_projection(self) -> None:
        first = analyze_capacity(self.manifest, self.config)
        second = analyze_capacity(self.manifest, self.config)
        self.assertEqual(first, second)
        self.assertEqual(
            first["evidence_classification"],
            "projection-from-pinned-sources-not-measurement",
        )
        self.assertEqual(first["catalog_summary"]["planning_models"], 200)
        self.assertEqual(first["catalog_summary"]["unknown_or_added_models"], 55)
        self.assertEqual(first["simulator_input"]["latency_samples"], [])

    def test_checked_in_capacity_summary_matches_generated_analysis(self) -> None:
        result = analyze_capacity(self.manifest, self.config)
        summary = json.loads((PACKAGE / "results/capacity-summary.json").read_text())
        self.assertEqual(
            summary["source_manifest_sha256"], result["source_manifest_sha256"]
        )
        self.assertEqual(
            summary["analysis_config_sha256"], result["analysis_config_sha256"]
        )
        self.assertEqual(summary["full_catalog_capacity"], result["full_catalog_capacity"])
        capacity = {
            (row["cache_gib"], row["size_profile"]): row["fit_models"]
            for row in result["cache_budget_sensitivity"]
        }
        for row in summary["cache_budget_fit_models"]:
            for profile in (
                "catalog-known-canonical-median",
                "catalog-known-canonical-p90",
            ):
                self.assertEqual(row[profile], capacity[(row["cache_gib"], profile)])
        reuse = {
            (row["reuse_exponent"], row["top_k"]): row["cache_hit_probability"]
            for row in result["top_k_reuse_sensitivity"]
        }
        for row in summary["selected_top_k_hit_probabilities"]:
            self.assertEqual(
                row["cache_hit_probability"],
                reuse[(row["reuse_exponent"], row["top_k"])],
            )

    def test_top_k_and_reuse_sensitivity_has_closed_form_uniform_points(self) -> None:
        result = analyze_capacity(self.manifest, self.config)
        rows = result["top_k_reuse_sensitivity"]
        for top_k in (0, 20, 50, 100, 200):
            row = next(
                item
                for item in rows
                if item["reuse_exponent"] == 0.0 and item["top_k"] == top_k
            )
            self.assertEqual(row["cache_hit_probability"], top_k / 200)
        self.assertGreater(
            next(
                item["cache_hit_probability"]
                for item in rows
                if item["reuse_exponent"] == 2.0 and item["top_k"] == 20
            ),
            0.95,
        )

    def test_state_mix_is_mutually_exclusive_and_conserves_requests(self) -> None:
        result = analyze_capacity(self.manifest, self.config)
        for row in result["request_state_sensitivity"]:
            probabilities = row["state_probabilities"]
            self.assertEqual(set(probabilities), {item["cache_state"] for item in self.attempts})
            self.assertAlmostEqual(sum(probabilities.values()), 1.0, places=9)

    def test_all_four_state_contract_fixtures_validate(self) -> None:
        shaped = self.validate()
        self.assertEqual(
            {item["raw"]["cache_state"] for item in shaped},
            {
                "A_materialized_hit",
                "B_node_seed_post_t0_materialization",
                "C_remote_miss_post_t0",
                "D_active_a_to_b_reclaim",
            },
        )

    def test_all_four_states_and_exact_source_age_version_are_required(self) -> None:
        with self.assertRaisesRegex(AnalysisError, "all four"):
            self.validate(self.attempts[:-1])
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["starting_state"]["source_artifact_version"] = "stale"
        with self.assertRaisesRegex(AnalysisError, "version/digest"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["starting_state"]["source_age_seconds"] = -1
        with self.assertRaisesRegex(AnalysisError, "source_age_seconds"):
            self.validate(attempts)

    def test_prepared_clone_cannot_be_labeled_unknown_model_cold_start(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        state_b = attempts[1]
        state_b["starting_state"].update(
            {
                "target_materialized": True,
                "immutable_node_local_seed_present": False,
                "target_source": "materialized_generation",
            }
        )
        with self.assertRaisesRegex(
            AnalysisError, "prepared clone cannot be labeled unknown-model cold start"
        ):
            self.validate(attempts)

    def test_b_through_d_operation_before_t0_is_rejected(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        state_b = attempts[1]
        clone = next(item for item in state_b["operations"] if item["name"] == "clone")
        clone["started_monotonic_ns"] = state_b["request"]["accepted_monotonic_ns"] - 1
        with self.assertRaisesRegex(AnalysisError, "before external T0"):
            self.validate(attempts)

    def test_state_a_localization_and_missing_residency_are_rejected(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["pre_t0_investment"]["materialized_residency_seconds"] = 0
        with self.assertRaisesRegex(AnalysisError, "residency duration"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        clone = next(item for item in attempts[0]["operations"] if item["name"] == "clone")
        clone.update(
            {
                "outcome": "completed",
                "started_monotonic_ns": attempts[0]["request"]["accepted_monotonic_ns"] + 1,
                "finished_monotonic_ns": attempts[0]["request"]["accepted_monotonic_ns"] + 2,
                "logical_bytes": attempts[0]["target"]["artifact_bytes"],
                "bytes_read": attempts[0]["target"]["artifact_bytes"],
                "bytes_written": attempts[0]["target"]["artifact_bytes"],
            }
        )
        attempts[0]["accounting"]["bytes_read_total"] += attempts[0]["target"][
            "artifact_bytes"
        ]
        attempts[0]["accounting"]["bytes_written_total"] += attempts[0]["target"][
            "artifact_bytes"
        ]
        with self.assertRaisesRegex(AnalysisError, "request-time localization"):
            self.validate(attempts)

    def test_remote_miss_and_node_seed_require_full_byte_accounting(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        remote = next(
            item for item in attempts if item["cache_state"] == "C_remote_miss_post_t0"
        )
        fetch = next(item for item in remote["operations"] if item["name"] == "artifact_fetch")
        fetch["bytes_network"] -= 1
        remote["accounting"]["bytes_network_total"] -= 1
        with self.assertRaisesRegex(AnalysisError, "full remote"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        seed = next(
            item
            for item in attempts
            if item["cache_state"] == "B_node_seed_post_t0_materialization"
        )
        digest = next(item for item in seed["operations"] if item["name"] == "hash")
        digest["bytes_read"] -= 1
        seed["accounting"]["bytes_read_total"] -= 1
        with self.assertRaisesRegex(AnalysisError, "full clone"):
            self.validate(attempts)

    def test_active_switch_requires_drain_release_eviction_and_deleted_bytes(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        switch = attempts[3]
        eviction = next(item for item in switch["operations"] if item["name"] == "eviction")
        switch["accounting"]["bytes_deleted_total"] -= eviction["bytes_deleted"]
        eviction["bytes_deleted"] = 0
        with self.assertRaisesRegex(AnalysisError, "eviction/reclaim bytes"):
            self.validate(attempts)

    def test_physical_totals_and_request_slo_binding_are_fail_closed(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[2]["accounting"]["bytes_network_total"] += 1
        with self.assertRaisesRegex(AnalysisError, "omits or double-counts"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[2]["accounting"]["request_slo_bytes_moved_total"] += 1
        with self.assertRaisesRegex(AnalysisError, "request-SLO byte total"):
            self.validate(attempts)

    def test_closed_execution_gate_rejects_measured_receipts(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        for attempt in attempts:
            attempt["evidence_classification"] = "measured-live-product-slo"
        with self.assertRaisesRegex(AnalysisError, "execution gate is closed"):
            self.validate(attempts)

    def test_operation_and_cleanup_digests_must_bind_supporting_evidence(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["operations"][0]["evidence_sha256"] = ZERO_DIGEST
        with self.assertRaisesRegex(AnalysisError, "lacks pinned supporting evidence"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["cleanup"]["receipt_sha256"] = ZERO_DIGEST
        with self.assertRaisesRegex(AnalysisError, "lacks pinned supporting evidence"):
            self.validate(attempts)

    def test_dirty_generation_and_mutable_namespace_cannot_be_reused(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[2]["cleanup"]["generation_id"] = attempts[1]["cleanup"]["generation_id"]
        with self.assertRaisesRegex(AnalysisError, "dirty/deleted generation was reused"):
            self.validate(attempts)
        attempts = copy.deepcopy(self.attempts)
        attempts[2]["concurrency"]["mutable_namespace_id"] = attempts[1]["concurrency"][
            "mutable_namespace_id"
        ]
        with self.assertRaisesRegex(AnalysisError, "mutable namespace"):
            self.validate(attempts)

    def test_attempt_ledger_requires_canonical_json_lines(self) -> None:
        path = self.root / "attempts.jsonl"
        path.write_text(json.dumps(self.attempts[0], indent=2) + "\n")
        with self.assertRaisesRegex(AnalysisError, "invalid JSON|canonical JSON"):
            load_attempts(path)
        path.write_text("".join(canonical_json(item) + "\n" for item in self.attempts))
        self.assertEqual(len(load_attempts(path)), 4)

    def test_schema_files_are_closed_and_parseable(self) -> None:
        for name in (
            "source_manifest.schema.json",
            "analysis_config.schema.json",
            "attempt.schema.json",
        ):
            schema = json.loads((PACKAGE / name).read_text())
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema["additionalProperties"])

    def test_source_manifest_hash_pin_rejects_attempt_drift(self) -> None:
        attempts = copy.deepcopy(self.attempts)
        attempts[0]["source_manifest_sha256"] = ZERO_DIGEST
        with self.assertRaisesRegex(AnalysisError, "exact source manifest"):
            self.validate(attempts)


if __name__ == "__main__":
    unittest.main()
