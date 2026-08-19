import hashlib
import json
import re
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
PROJECT_EU = "project-e00z6b02t8ddk96c49"
PROJECT_US = "project-u00tds8vpr00jaxa76s22d"


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

    def test_public_retrieved_at_is_the_archive_fetch_time(self):
        """Adversary: transcription-time guesses must not survive; the only
        retrieval timestamp on a public record is its archive's fetch time."""
        for rec in self.snap["records"]:
            if rec["source"]["kind"] != "public_list_price":
                continue
            self.assertEqual(
                rec["source"]["retrieved_at_utc"],
                rec["source"]["archived_payload"]["retrieved_at_utc"],
                rec["record_id"])
            self.assertNotIn(rec["source"]["retrieved_at_utc"],
                             ("2026-08-19T15:05:00Z", "2026-08-19T15:20:00Z"))

    def test_tenant_records_bind_region_from_project(self):
        expected = {"project-e00z6b02t8ddk96c49": "eu-north1",
                    "project-u00tds8vpr00jaxa76s22d": "us-central1"}
        for rec in self.snap["records"]:
            if rec["source"]["kind"] != "tenant_calculator_quote":
                continue
            project = rec["source"]["project"]
            self.assertEqual(rec["source"]["region"], expected[project],
                             rec["record_id"])
            self.assertEqual(rec["region_scope"], expected[project],
                             rec["record_id"])

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

    def test_public_records_hash_bound_to_archived_payloads(self):
        """Every public record must be offline-verifiable: archive exists,
        hash matches, and the quoted price string occurs in the payload."""
        for rec in self.snap["records"]:
            if rec["source"]["kind"] != "public_list_price":
                continue
            arch = rec["source"]["archived_payload"]
            payload = (CC / arch["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(),
                             arch["sha256"], rec["record_id"])
            self.assertIn(rec["unit_price"].encode(), payload,
                          rec["record_id"])

    def test_sources_manifest_hashes_match_files(self):
        manifest = json.loads(
            (CC / "inputs/raw/sources/sources_manifest.json").read_text())
        self.assertEqual(len(manifest["archives"]), 3)
        for arch in manifest["archives"]:
            payload = (CC / "inputs/raw/sources" / arch["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(),
                             arch["sha256"], arch["file"])
            self.assertEqual(len(payload), arch["bytes"], arch["file"])

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


class CaptureScriptConsistencyTest(unittest.TestCase):
    """The parameterized capture script must reproduce the committed raw
    evidence: same profile, same per-SKU project (and hence region)."""

    def test_committed_commands_use_the_scripted_projects(self):
        for path in sorted((CC / "inputs/raw").glob("quote-*.json")):
            raw = json.loads(path.read_text())
            m = re.search(r"parent-id (\S+)", raw["command"])
            self.assertIsNotNone(m, path.name)
            expect = PROJECT_US if "b200" in path.name else PROJECT_EU
            self.assertEqual(m.group(1), expect, path.name)
            self.assertIn("--profile sandbox", raw["command"], path.name)

    def test_script_parameterizes_projects_and_maps_b200_to_us(self):
        script = (CC / "inputs/raw/capture_quotes.sh").read_text()
        self.assertIn('PROJECT_EU="${PROJECT_EU:-%s}"' % PROJECT_EU, script)
        self.assertIn('PROJECT_US="${PROJECT_US:-%s}"' % PROJECT_US, script)
        self.assertIn('REGION_EU="${REGION_EU:-eu-north1}"', script)
        self.assertIn('REGION_US="${REGION_US:-us-central1}"', script)
        self.assertIn(
            "gpu-b200-sxm 1gpu-20vcpu-224gb $PROJECT_US $REGION_US", script)
        self.assertIn(
            "gpu-h100-sxm 1gpu-16vcpu-200gb $PROJECT_EU $REGION_EU", script)
        # No hardcoded bare project IDs outside the overridable defaults
        # (comment lines documenting the defaults are allowed).
        body = "\n".join(
            line for line in script.splitlines()
            if not line.lstrip().startswith("#")).replace(
            'PROJECT_EU="${PROJECT_EU:-%s}"' % PROJECT_EU, "").replace(
            'PROJECT_US="${PROJECT_US:-%s}"' % PROJECT_US, "")
        self.assertNotIn(PROJECT_EU, body)
        self.assertNotIn(PROJECT_US, body)

    def test_script_emits_region_project_parameters_metadata(self):
        """Adversary: overriding PROJECT_* must flow into the evidence.
        Future captures embed an explicit parameters block; downstream
        generation reads it (or, for the committed pre-block files, parses
        the command) and maps region through one attested table."""
        script = (CC / "inputs/raw/capture_quotes.sh").read_text()
        self.assertIn('"parameters": {"profile": profile, "project": project',
                      script)
        self.assertIn('"region": region, "tenant": tenant', script)

    def test_capacity_capture_used_the_scripted_tenant(self):
        raw = json.loads(
            (CC / "inputs/raw/capacity-resource-advice.json").read_text())
        self.assertIn("tenant-e00f3wdfzwfjgbcyfv", raw["command"])


class SubtreeWordingScanTest(unittest.TestCase):
    """Adversary: the PENDING/not-measured invariant for Cerebrium must hold
    in EVERY source and doc file of this subtree, not only in generated
    outputs. Archived third-party payloads (.html) are external content and
    excluded."""

    # Built by joining parts so this scanner never matches its own source.
    FORBIDDEN = tuple(" ".join(parts) for parts in (
        ("measured", "external", "comparator"),
        ("external", "measured"),
        ("measured", "comparator"),
        ("sole", "external", "measured")))

    def test_no_measured_comparator_wording_anywhere(self):
        scanned = 0
        for path in sorted(CC.rglob("*")):
            if not path.is_file() or path.suffix not in (
                    ".py", ".md", ".sh", ".json", ".tsv"):
                continue
            text = path.read_text(errors="replace").lower()
            for phrase in self.FORBIDDEN:
                self.assertNotIn(phrase, text,
                                 f"{path.relative_to(CC)}: '{phrase}'")
            scanned += 1
        self.assertGreater(scanned, 30)  # the scan really covers the subtree


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
        self.assertEqual(len(inputs.measured["simulation"]), 2)

    def test_checksum_drift_fails_closed_for_both_sections(self):
        inputs = lib.Inputs(ROOT)
        inputs.measured["measured"][0]["sha256"] = "0" * 64
        with self.assertRaises(lib.InputError):
            inputs._verify_measured_files()
        inputs = lib.Inputs(ROOT)
        inputs.measured["simulation"][0]["sha256"] = "0" * 64
        with self.assertRaises(lib.InputError):
            inputs._verify_measured_files()

    def test_simulation_entries_declare_placeholder_provenance(self):
        inputs = lib.Inputs(ROOT)
        for entry in inputs.measured["simulation"]:
            self.assertEqual(entry["kind"], "placeholder_derived_simulation")
            self.assertIn("placeholder", entry["input_provenance"].lower())

    def test_unmeasured_backends_declared(self):
        inputs = lib.Inputs(ROOT)
        self.assertEqual(inputs.unmeasured("cerebrium")["status"],
                         "PENDING_MEASUREMENT")
        self.assertEqual(inputs.unmeasured("internal-node-local-vm")["status"],
                         "PENDING_MEASUREMENT")
        self.assertEqual(inputs.unmeasured("modal")["status"],
                         "EXCLUDED_DOCUMENTATION_ONLY")

    def test_unmeasured_cost_classes_declared(self):
        inputs = lib.Inputs(ROOT)
        self.assertEqual(
            inputs.unmeasured_cost_class("cold_switch", "OpenFold2")["status"],
            "PENDING_MEASUREMENT")
        self.assertEqual(
            inputs.unmeasured_cost_class("node_provision_miss", "Boltz2")
            ["status"], "PENDING_MEASUREMENT")

    def test_capture_assumption_is_model_scoped(self):
        inputs = lib.Inputs(ROOT)
        cap = next(a for a in inputs.measured["assumptions"]
                   if a["name"] == "snapshot_capture_seconds_of2")
        self.assertEqual(cap["applies_to_model"], "OpenFold2")
        self.assertIn("MUST NOT", cap["why_assumption"])

    def test_assumptions_are_labeled(self):
        inputs = lib.Inputs(ROOT)
        names = set()
        for a in inputs.measured["assumptions"]:
            self.assertTrue(a["basis"], a["name"])
            self.assertTrue(a["why_assumption"], a["name"])
            names.add(a["name"])
        for required in ("preemption_loss_probability_grid",
                         "prep_reuse_grid", "restores_between_captures_grid",
                         "on_demand_loss_negligible",
                         "cross_region_relocalization"):
            self.assertIn(required, names)

    def test_cohorts_parse_to_expected_counts(self):
        inputs = lib.Inputs(ROOT)
        for entry_id in ("of2-n20-fresh", "boltz2-n20-fresh"):
            vals = lib.load_cohort_seconds(inputs, entry_id)
            self.assertEqual(len(vals), 20)
            warm = lib.load_cohort_seconds(
                inputs, entry_id, metric="semantic_request_2_seconds")
            self.assertEqual(len(warm), 20)
            self.assertTrue(all(v > 0 for v in vals + warm))
        with self.assertRaises(lib.InputError):
            lib.load_cohort_seconds(inputs, "of2-n20-fresh",
                                    metric="not_a_declared_metric")

    def test_boltz2_pret0_entry_matches_cold_start_metrics(self):
        inputs = lib.Inputs(ROOT)
        entry = inputs.measured_entry("boltz2-pret0-cache-read")
        doc = (ROOT / "performance/COLD_START_METRICS.md").read_text()
        self.assertIn("cache full read 422.854590", doc)
        self.assertEqual(entry["value_seconds"], "422.854590")
        self.assertIn(format(entry["cache_bytes"], ","), doc)
        self.assertIn(format(entry["artifact_bytes"], ","), doc)


if __name__ == "__main__":
    unittest.main()
