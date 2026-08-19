from __future__ import annotations

import copy
import importlib.util
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
        cls.index = VALIDATOR.load_json(ARCH_DIR / "evidence-index.v2.json")
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

    def test_only_exact_independently_accepted_commit_can_be_positive(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-BROKER-D40-REJECTED")
        item["classification"] = "positive-contract"
        item["positive_evidence_eligible"] = True
        item["review"]["verdict"] = "accepted"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "not independently accepted positive evidence",
        )

    def test_positive_review_must_bind_same_exact_commit(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-METRIC-BA49")
        item["review"]["reviewed_commit_sha"] = (
            "9abd49204e7dbfb9be17ebf6c3f213227a88e5ca"
        )
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "reviewed commit must equal the exact source commit",
        )

    def test_positive_review_must_be_independent(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-CATALOG-9ABD")
        item["review"]["authority"] = "manager-scope"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "positive evidence lacks independent acceptance",
        )

    def test_source_blob_is_bound_to_exact_commit(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-DRAIN-E2DA-REJECTED")
        item["provenance"]["blob_sha256"] = "0" * 64
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "source commit/path blob sha256 mismatch",
        )

    def test_rejected_commit_and_reason_set_are_pinned(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-QWEN-27C2-REJECTED")
        item["review"]["reasons"] = ["looks fine now"]
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "required review reason missing",
        )

    def test_old_rejections_cannot_disappear(self) -> None:
        mutated = copy.deepcopy(self.index)
        mutated["entries"] = [
            item
            for item in mutated["entries"]
            if item["id"] != "EV2-DRAIN-34D-REJECTED"
        ]
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "required replacement review evidence is missing",
        )

    def test_unreviewed_storage_projection_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-STORAGE-75E3-UNREVIEWED")
        item["review"]["verdict"] = "accepted"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "unreviewed evidence cannot be promoted",
        )

    def test_modal_remains_documentation_only_and_unscored(self) -> None:
        mutated = copy.deepcopy(self.index)
        item = self.index_entry(mutated, "EV2-MODAL-530F-REFERENCE")
        item["measurement_kind"] = "offline-test"
        self.assert_has(
            VALIDATOR.validate_index(mutated),
            "Modal must remain documentation-only",
        )

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

    def test_rejected_replacement_cannot_enter_decision_inputs(self) -> None:
        mutated = copy.deepcopy(self.matrix)
        mutated["decision_inputs"].append("EV2-DRAIN-E2DA-REJECTED")
        self.assert_has(
            VALIDATOR.validate_matrix(mutated, self.index),
            "decision inputs must be only independently accepted exact contracts",
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

    def test_preserved_baseline_link_cannot_change(self) -> None:
        mutated = copy.deepcopy(self.architecture)
        mutated["evidence_index_update"]["baseline_commit"] = "0" * 40
        self.assert_has(
            VALIDATOR.validate_architecture_link(mutated),
            "link set changed or is incomplete",
        )


if __name__ == "__main__":
    unittest.main()
