import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

CC = Path(__file__).resolve().parent.parent
ROOT = CC.parent.parent  # faststart-v2
sys.path.insert(0, str(CC / "costmodel"))
import lib  # noqa: E402

ALLOWED_SOURCE_KINDS = {"tenant_calculator_quote", "public_list_price",
                        "derived"}
ALLOWED_PROJECTS = {"project-e00z6b02t8ddk96c49",
                    "project-u00tds8vpr00jaxa76s22d",
                    "project-i00xz31gpr00xp9jhp982v"}


def load(name):
    return json.loads((CC / "inputs" / name).read_text())


class PriceSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = load("price_snapshot.json")

    def test_schema_and_dating(self):
        self.assertEqual(self.snap["schema_version"],
                         "capacity-cost-price-snapshot/v1")
        self.assertEqual(self.snap["as_of_date"], "2026-08-19")

    def test_records_unique_sourced_and_usd(self):
        ids = [r["record_id"] for r in self.snap["records"]]
        self.assertEqual(len(ids), len(set(ids)))
        for rec in self.snap["records"]:
            kind = rec["source"]["kind"]
            self.assertIn(kind, ALLOWED_SOURCE_KINDS, rec["record_id"])
            self.assertEqual(rec["currency"], "USD")
            Decimal(rec["unit_price"])  # parses exactly
            if kind == "public_list_price":
                self.assertTrue(rec["source"]["url"].startswith("https://"))
                self.assertIn("2026-08-19", rec["source"]["retrieved_at_utc"])
            elif kind == "tenant_calculator_quote":
                self.assertIn(rec["source"]["project"], ALLOWED_PROJECTS)
                self.assertIn("2026-08-19", rec["source"]["retrieved_at_utc"])
            else:
                self.assertTrue(rec["source"]["derived_from"])
                self.assertTrue(rec["source"]["derivation"])

    def test_tenant_quotes_match_raw_evidence(self):
        for rec in self.snap["records"]:
            if rec["source"]["kind"] != "tenant_calculator_quote":
                continue
            raw = json.loads(
                (CC / rec["source"]["evidence_file"]).read_text())
            resp = raw["response"]
            self.assertEqual(raw["exit_code"], 0, rec["record_id"])
            self.assertEqual(
                rec["unit_price"],
                resp["hourly_cost"]["general"]["total"]["cost"],
                rec["record_id"])
            self.assertEqual(
                rec["monthly_price"],
                resp["monthly_cost"]["general"]["total"]["cost"],
                rec["record_id"])
            self.assertEqual(rec["source"]["retrieved_at_utc"],
                             raw["captured_at_utc"])

    def test_public_list_cross_checks_tenant_quotes(self):
        by_id = {r["record_id"]: r for r in self.snap["records"]}
        for list_id, quote_id in (
                ("nebius-list-h100-od", "nebius-h100-1g-od"),
                ("nebius-list-h100-pre", "nebius-h100-1g-pre"),
                ("nebius-list-h200-od", "nebius-h200-1g-od"),
                ("nebius-list-h200-pre", "nebius-h200-1g-pre"),
                ("nebius-list-b200-od", "nebius-b200-1g-od"),
                ("nebius-list-b200-pre", "nebius-b200-1g-pre")):
            self.assertEqual(Decimal(by_id[list_id]["unit_price"]),
                             Decimal(by_id[quote_id]["unit_price"]), list_id)

    def test_monthly_quotes_use_730_hours(self):
        by_id = {r["record_id"]: r for r in self.snap["records"]}
        for rid in ("nebius-h100-1g-od", "nebius-h100-1g-pre",
                    "nebius-h200-1g-od", "nebius-b200-1g-od"):
            rec = by_id[rid]
            self.assertEqual(Decimal(rec["monthly_price"]),
                             Decimal(rec["unit_price"]) * 730, rid)

    def test_modal_never_priced_here(self):
        # No price record may belong to Modal; the snapshot statement is the
        # only allowed mention (it documents the exclusion itself).
        text = json.dumps(self.snap["records"]).lower()
        self.assertNotIn("modal", text)


class CapacitySnapshotTest(unittest.TestCase):
    def test_matches_raw_capture(self):
        snap = load("capacity_snapshot.json")
        raw = json.loads(
            (CC / "inputs/raw/capacity-resource-advice.json").read_text())
        raw_ci = [i for i in raw["response"]["items"]
                  if i["spec"].get("compute_instance")]
        self.assertEqual(len(snap["rows"]), len(raw_ci))
        self.assertEqual(snap["as_of_utc"], raw["captured_at_utc"])
        h100 = [r for r in snap["rows"]
                if r["platform"] == "gpu-h100-sxm" and r["gpu_count"] == 1]
        self.assertEqual(len(h100), 4)  # one row per eu-north1 fabric
        for row in h100:
            for offer in ("on_demand", "preemptible"):
                self.assertIn("availability_level", row["offers"][offer])
                self.assertIn("effective_at", row["offers"][offer])


class MeasuredInputsTest(unittest.TestCase):
    def test_inputs_load_with_pinned_checksums(self):
        inputs = lib.Inputs(ROOT)
        self.assertEqual(len(inputs.measured["measured"]), 4)

    def test_checksum_drift_fails_closed(self):
        inputs = lib.Inputs(ROOT)
        inputs.measured["measured"][0]["sha256"] = "0" * 64
        with self.assertRaises(lib.InputError):
            inputs._verify_measured_files()

    def test_unmeasured_backends_declared(self):
        inputs = lib.Inputs(ROOT)
        self.assertEqual(inputs.unmeasured("cerebrium")["status"],
                         "PENDING_MEASUREMENT")
        self.assertEqual(inputs.unmeasured("internal-node-local-vm")["status"],
                         "PENDING_MEASUREMENT")
        self.assertEqual(inputs.unmeasured("modal")["status"],
                         "EXCLUDED_DOCUMENTATION_ONLY")

    def test_assumptions_are_labeled(self):
        inputs = lib.Inputs(ROOT)
        for a in inputs.measured["assumptions"]:
            self.assertTrue(a["basis"], a["name"])
            self.assertTrue(a["why_assumption"], a["name"])

    def test_cohorts_parse_to_expected_counts(self):
        inputs = lib.Inputs(ROOT)
        for entry_id in ("of2-n20-fresh", "boltz2-n20-fresh"):
            vals = lib.load_cohort_seconds(inputs, entry_id)
            self.assertEqual(len(vals), 20)
            self.assertTrue(all(v > 0 for v in vals))


if __name__ == "__main__":
    unittest.main()
