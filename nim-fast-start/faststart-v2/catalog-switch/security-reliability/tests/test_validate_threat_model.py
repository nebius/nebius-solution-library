from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
sys.path.insert(0, str(MODULE_DIR))

import validate_threat_model as vtm  # noqa: E402


def load() -> tuple[dict, str]:
    doc = json.loads((MODULE_DIR / "threat_model.json").read_text())
    md = (MODULE_DIR / "THREAT_MODEL.md").read_text()
    return doc, md


class ShippedDocumentTest(unittest.TestCase):
    def test_shipped_threat_model_validates(self) -> None:
        doc, md = load()
        self.assertEqual(vtm.validate(doc, md), [])

    def test_cli_passes_on_shipped_files(self) -> None:
        self.assertEqual(vtm.main([]), 0)

    def test_required_failure_categories_are_present(self) -> None:
        doc, _ = load()
        categories = {a["category"] for a in doc["adversaries"]}
        for required in vtm.REQUIRED_ADVERSARY_CATEGORIES:
            self.assertIn(required, categories)

    def test_all_pilots_have_tests(self) -> None:
        doc, _ = load()
        pilots = {p for t in doc["tests"] for p in t["pilots"]}
        self.assertEqual(pilots, set(vtm.PILOT_IDS))

    def test_every_control_names_cost_and_critical_path(self) -> None:
        doc, _ = load()
        for control in doc["controls"]:
            self.assertIsInstance(control["cost"]["critical_path"], bool, control["id"])
            self.assertTrue(control["cost"]["risk_if_weakened"].strip(), control["id"])


class MutationTest(unittest.TestCase):
    """Every class of matrix gap must be rejected, not warned about."""

    def setUp(self) -> None:
        self.doc, self.md = load()

    def errors(self) -> list[str]:
        return vtm.validate(self.doc, self.md)

    def assert_rejected(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(
            any(fragment in e for e in errors),
            f"expected an error containing {fragment!r}, got: {errors}",
        )

    def test_wrong_schema_rejected(self) -> None:
        self.doc["schema"] = "something/else"
        self.assert_rejected("schema:")

    def test_unknown_status_rejected(self) -> None:
        self.doc["status"] = "approved"
        self.assert_rejected("status:")

    def test_missing_backend_rejected(self) -> None:
        self.doc["backends"] = self.doc["backends"][:3]
        self.assert_rejected("backends: expected exactly")

    def test_unenforced_invariant_rejected(self) -> None:
        self.doc["invariants"].append(
            {"id": "INV-99", "statement": "orphan", "rationale": "orphan"}
        )
        self.assert_rejected("invariant INV-99: not enforced")

    def test_control_without_test_rejected(self) -> None:
        self.doc["controls"][0]["tests"] = []
        self.assert_rejected("must map to at least one test")

    def test_control_without_evidence_rejected(self) -> None:
        self.doc["controls"][0]["evidence_fields"] = []
        self.assert_rejected("must name at least one evidence field")

    def test_undeclared_evidence_field_rejected(self) -> None:
        self.doc["tests"][0]["evidence_fields"].append("made_up_field")
        self.assert_rejected("undeclared evidence field")

    def test_unused_evidence_field_rejected(self) -> None:
        self.doc["evidence_fields"].append(
            {"name": "dangling_field", "type": "string", "description": "unused"}
        )
        self.assert_rejected("declared but never used")

    def test_control_not_exercised_by_adversary_rejected(self) -> None:
        for adversary in self.doc["adversaries"]:
            adversary["controls"] = [c for c in adversary["controls"] if c != "CTL-04"]
            if not adversary["controls"]:
                adversary["controls"] = ["CTL-05"]
        self.assert_rejected("control CTL-04: not exercised")

    def test_missing_required_category_rejected(self) -> None:
        self.doc["adversaries"] = [
            a for a in self.doc["adversaries"] if a["category"] != "foreign-replacement"
        ]
        self.assert_rejected("required category 'foreign-replacement'")

    def test_fails_open_without_exception_marker_rejected(self) -> None:
        for adversary in self.doc["adversaries"]:
            if adversary["id"] == "ADV-01":
                adversary["fails_closed"] = False
                adversary["fail_note"] = "probably fine"
        self.assert_rejected("fails_closed=false requires")

    def test_pilot_without_tests_rejected(self) -> None:
        for test in self.doc["tests"]:
            test["pilots"] = [p for p in test["pilots"] if p != "modal"]
            if not test["pilots"]:
                test["pilots"] = ["k8s"]
        self.assert_rejected("pilot 'modal' has no mapped test")

    def test_orphan_test_rejected(self) -> None:
        self.doc["tests"].append(
            {
                "id": "TST-99",
                "name": "orphan",
                "pilots": ["k8s"],
                "procedure": "unreferenced by any control",
                "evidence_fields": ["switch_id"],
            }
        )
        self.md += " TST-99"
        self.assert_rejected("test TST-99: not required by any control")

    def test_non_required_backend_needs_delegation_note(self) -> None:
        for control in self.doc["controls"]:
            if control["id"] == "CTL-01":
                control["backends"]["modal"] = "delegated"
        self.assert_rejected("requires a delegation_note")

    def test_state_machine_unknown_state_rejected(self) -> None:
        self.doc["reliability"]["state_machines"]["switch"]["transitions"].append(
            {"from": "SERVING_A", "to": "NOWHERE", "on": "bad edge"}
        )
        self.assert_rejected("unknown to-state 'NOWHERE'")

    def test_missing_rollback_machine_rejected(self) -> None:
        del self.doc["reliability"]["state_machines"]["rollback"]
        self.assert_rejected("state machine 'rollback' is missing")

    def test_md_must_mention_every_id(self) -> None:
        self.md = self.md.replace("ADV-14", "ADV-XX")
        self.assert_rejected("does not mention 'ADV-14'")

    def test_reviewed_status_requires_closed_findings(self) -> None:
        self.doc["status"] = "reviewed"
        self.doc["review_findings"] = []
        self.assert_rejected("requires at least one recorded review finding")
        self.doc["review_findings"] = [
            {
                "id": "RF-01",
                "source": "review",
                "finding": "gap",
                "resolution": "",
                "status": "open",
            }
        ]
        self.assert_rejected("requires all findings closed")

    def test_backend_missing_invariant_coverage_rejected(self) -> None:
        for backend in self.doc["backends"]:
            if backend["id"] == "modal":
                backend["invariant_exceptions"] = []
        self.assert_rejected(
            "backend modal: invariant INV-08 has no required control"
        )

    def test_redundant_invariant_exception_rejected(self) -> None:
        for backend in self.doc["backends"]:
            if backend["id"] == "modal":
                backend["invariant_exceptions"].append(
                    {"invariant": "INV-02", "note": "already covered by CTL-01"}
                )
        self.assert_rejected("redundant invariant exception for INV-02")

    def test_adversary_without_trust_boundary_rejected(self) -> None:
        self.doc["adversaries"][0]["trust_boundaries"] = []
        self.assert_rejected("must name at least one trust boundary")

    def test_adversary_without_assets_rejected(self) -> None:
        self.doc["adversaries"][0]["assets_at_risk"] = []
        self.assert_rejected("must name at least one asset at risk")

    def test_unreferenced_asset_rejected(self) -> None:
        self.doc["assets"].append(
            {"id": "AST-99", "name": "orphan", "classification": "x", "description": "x"}
        )
        self.md += " AST-99"
        self.assert_rejected("asset AST-99: not referenced")

    def test_field_produced_by_no_test_rejected(self) -> None:
        for test in self.doc["tests"]:
            test["evidence_fields"] = [
                f for f in test["evidence_fields"] if f != "co_residency_receipt"
            ]
        self.assert_rejected("'co_residency_receipt': produced by no test")

    def test_control_tests_must_produce_its_evidence(self) -> None:
        for control in self.doc["controls"]:
            if control["id"] == "CTL-19":
                control["evidence_fields"] = ["boot_id"]
        self.assert_rejected(
            "control CTL-19: none of its evidence fields are produced"
        )

    def test_invariant_exception_requires_scoring_adversary(self) -> None:
        for backend in self.doc["backends"]:
            for exception in backend.get("invariant_exceptions", []):
                exception.pop("scored_by", None)
        self.assert_rejected("must name the adversary (scored_by)")

    def test_invariant_exception_scoring_adversary_must_exist(self) -> None:
        for backend in self.doc["backends"]:
            for exception in backend.get("invariant_exceptions", []):
                exception["scored_by"] = "ADV-99"
        self.assert_rejected("scored_by names unknown adversary 'ADV-99'")

    def test_duplicate_ids_rejected(self) -> None:
        clone = copy.deepcopy(self.doc["controls"][0])
        self.doc["controls"].append(clone)
        self.assert_rejected("duplicate id")

    def test_load_and_validate_raises_on_broken_doc(self) -> None:
        broken = copy.deepcopy(self.doc)
        broken["controls"][0]["tests"] = []
        with self.assertRaises(vtm.ThreatModelError):
            errors = vtm.validate(broken, self.md)
            if errors:
                raise vtm.ThreatModelError("\n".join(errors))


if __name__ == "__main__":
    unittest.main()
