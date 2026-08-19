from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim import SCHEMA_VERSION  # noqa: E402
from catalog_sim.report import TSV_COLUMNS  # noqa: E402

SIM_DIR = Path(__file__).resolve().parents[1]


class PublishedResultsTest(unittest.TestCase):
    """The committed results must stay internally consistent."""

    @classmethod
    def setUpClass(cls):
        reports_path = SIM_DIR / "results" / "reports.json"
        if not reports_path.exists():
            raise unittest.SkipTest("results not generated yet")
        cls.doc = json.loads(reports_path.read_text())
        cls.summary = (SIM_DIR / "results" / "summary.tsv").read_text().splitlines()

    def test_schema_version_and_row_counts(self):
        self.assertEqual(self.doc["schema_version"], SCHEMA_VERSION)
        self.assertEqual(self.summary[0], "\t".join(TSV_COLUMNS))
        self.assertEqual(len(self.summary) - 1, len(self.doc["reports"]))

    def test_every_run_conserves_requests(self):
        for r in self.doc["reports"]:
            self.assertEqual(
                r["n_requests"],
                r["n_completed"] + r["n_rejected"] + r["n_failed"],
                (r["trace_family"], r["policy"], r["sensitivity"]),
            )

    def test_placeholder_table_embedded_with_sensitivity_ranges(self):
        for level in ("low", "base", "high"):
            table = self.doc["placeholders"][level]
            self.assertGreaterEqual(len(table), 10)
            for name, spec in table.items():
                self.assertEqual(spec["provenance"], "placeholder", name)
                self.assertLess(spec["low"], spec["high"], name)
                self.assertTrue(spec["rationale"].strip(), name)

    def test_reports_match_pinned_trace_checksums(self):
        pinned = json.loads((SIM_DIR / "traces" / "CHECKSUMS.json").read_text())
        self.assertEqual(pinned["sha256"], self.doc["trace_checksums"])
        for r in self.doc["reports"]:
            self.assertEqual(
                r["trace_checksum"], pinned["sha256"][r["trace_family"]]
            )

    def test_all_families_and_sensitivities_covered(self):
        rows = self.doc["reports"]
        self.assertEqual(
            {r["trace_family"] for r in rows},
            {"uniform", "zipf", "bursty", "correlated", "adversarial"},
        )
        self.assertEqual(
            {r["sensitivity"] for r in rows}, {"low", "base", "high"}
        )


if __name__ == "__main__":
    unittest.main()
