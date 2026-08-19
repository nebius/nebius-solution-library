from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ARCH_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "evidence_index_validator", ARCH_DIR / "validate_evidence_index.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class EvidenceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = VALIDATOR.load_json(ARCH_DIR / "evidence-index.v3.json")
        cls.matrix = VALIDATOR.load_json(ARCH_DIR / "decision-matrix.v1.json")
        cls.budgets = VALIDATOR.load_json(ARCH_DIR / "budget-placeholders.v1.json")
        cls.architecture = VALIDATOR.load_json(ARCH_DIR / "architecture.json")

    def assert_has(self, errors: list[str], fragment: str) -> None:
        self.assertTrue(errors, "mutation unexpectedly validated")
        self.assertTrue(any(fragment in error for error in errors), errors)

    def index_entry(self, document: dict, entry_id: str) -> dict:
        return next(item for item in document["entries"] if item["id"] == entry_id)

    def backend(self, document: dict, backend_id: str) -> dict:
        return next(item for item in document["backends"] if item["id"] == backend_id)

    def test_shipped_evidence_update_passes(self) -> None:
        self.assertEqual([], VALIDATOR.validate_all())

    def test_generated_index_is_byte_identical(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ARCH_DIR / "build_evidence_index_v3.py"), "--check"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_review_bundle_hash_is_exact(self) -> None:
        mutated = copy.deepcopy(self.index)
        mutated["review_record_bundle"]["blob_sha256"] = "0" * 64
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "review record bundle binding changed",
        )

    def test_review_bundle_commit_is_exact(self) -> None:
        mutated = copy.deepcopy(self.index)
        mutated["review_record_bundle"]["commit_sha"] = (
            "7dc39ea7903c8aa19fe8a8269ab435268a7ae4b7"
        )
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "review record bundle binding changed",
        )

    def test_unresolved_task_deck_uri_is_forbidden(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-BROKER-D40-REJECTED")
        item["allowed_claim"] = "task-deck://mutable-review"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "must not contain unresolved task-deck",
        )

    def test_review_record_id_is_exact(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-K8S-4E63-PENDING")
        item["review_record_id"] = "RR1-STORAGE-75E3-REJECTED"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "review record binding changed",
        )

    def test_owner_claim_cannot_become_positive_evidence(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-METRIC-BA49")
        item["positive_evidence_eligible"] = True
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "lacks a content-bound independent acceptance record",
        )

    def test_embedded_review_metadata_is_rejected_by_schema(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-CATALOG-9ABD")
        item["review"] = {"verdict": "accepted", "authority": "independent-review"}
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "Additional properties are not allowed",
        )

    def test_source_blob_is_bound_to_exact_commit(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-DRAIN-3963-REJECTED")
        item["provenance"]["blob_sha256"] = "0" * 64
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "source commit/path blob sha256 mismatch",
        )

    def test_complete_k8s_negative_entry_cannot_disappear(self) -> None:
        mutated = copy.deepcopy(self.index)
        mutated["entries"] = [
            item for item in mutated["entries"] if item["id"] != "EV3-K8S-4E63-PENDING"
        ]
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "evidence snapshot entry set is incomplete",
        )

    def test_storage_rejection_cannot_become_unreviewed(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-STORAGE-75E3-REJECTED")
        item["classification"] = "pending"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "rejected disposition changed",
        )

    def test_pending_successor_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-STORAGE-999F-PENDING")
        item["classification"] = "rejected"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "pending replacement was promoted",
        )

    def test_boltz_hidden_setup_stays_unverified(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-BOLTZ-HIDDEN-SETUP-75E3")
        item["classification"] = "pending"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "Boltz hidden setup must remain an unverified observation",
        )

    def test_boltz_numeric_claim_requires_raw_receipts(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-BOLTZ-HIDDEN-SETUP-75E3")
        item["allowed_claim"] = "The copy took 440 seconds."
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "numeric setup values are forbidden",
        )

    def test_modal_remains_documentation_only_and_unscored(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV3-MODAL-530F-REFERENCE")
        item["measurement_kind"] = "offline-test"
        errors = VALIDATOR.validate_index(mutated)
        self.assertTrue(errors)

    def test_backend_winner_is_forbidden(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        mutated["winner"] = "kubernetes"
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "no winner and no final ADR",
        )

    def test_matched_cohort_count_cannot_be_invented(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        self.backend(mutated, "cerebrium")["matched_measured_cohorts"] = 1
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "measured cohort count must remain zero",
        )

    def test_modal_cannot_receive_a_score(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        self.backend(mutated, "modal")["score"] = 1
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "score/rank is forbidden",
        )

    def test_decision_inputs_remain_empty(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        mutated["decision_inputs"].append("EV3-METRIC-BA49")
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "decision inputs must remain empty",
        )

    def test_negative_review_set_is_complete(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        mutated["negative_review_evidence"].remove("EV3-STORAGE-75E3-REJECTED")
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "negative replacement review history is incomplete",
        )

    def test_pending_review_set_is_complete(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        mutated["pending_review_evidence"].remove("EV3-DRAIN-E365-PENDING")
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "pending replacement review history is incomplete",
        )

    def test_all_ten_arm_a_arm_b_remains_missing(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        requirement = next(
            item
            for item in mutated["qualification_requirements"]
            if item["id"] == "all-10-arm-a-arm-b"
        )
        requirement["accepted"] = 20
        requirement["status"] = "complete"
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "missing evidence was falsely accepted",
        )

    def test_latency_budget_must_remain_null(self) -> None:
        mutated = copy.deepcopy(self.budgets)
        mutated["latency"][0]["p95_max"] = 30
        self.assert_has(
            VALIDATOR.validate_budgets(mutated),
            "latency budget must remain null",
        )

    def test_cost_budget_must_remain_null(self) -> None:
        mutated = copy.deepcopy(self.budgets)
        mutated["cost"][0]["campaign_cap"] = 27
        self.assert_has(
            VALIDATOR.validate_budgets(mutated),
            "cost budget must remain null",
        )

    def test_reopened_update_stops_at_pending_review(self) -> None:
        mutated = copy.deepcopy(self.architecture)
        gate = next(
            item
            for item in mutated["rollout_gates"]
            if item["id"] == "G-INDEPENDENT-REVIEW"
        )
        gate["status"] = "conditional-sign-off"
        self.assert_has(
            VALIDATOR.validate_architecture_link(mutated),
            "must stop at pending independent review",
        )

    def test_preserved_7dc_link_cannot_change(self) -> None:
        mutated = copy.deepcopy(self.architecture)
        mutated["evidence_index_update"]["rejected_predecessor_commit"] = "0" * 40
        self.assert_has(
            VALIDATOR.validate_architecture_link(mutated),
            "link set changed or is incomplete",
        )


if __name__ == "__main__":
    unittest.main()
