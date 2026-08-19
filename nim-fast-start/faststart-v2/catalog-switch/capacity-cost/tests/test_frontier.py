import importlib.util
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

CC = Path(__file__).resolve().parent.parent
ROOT = CC.parent.parent
sys.path.insert(0, str(CC / "costmodel"))
import lib  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build_frontier", CC / "costmodel" / "build_frontier.py")
build_frontier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_frontier)


class PublishedResultsTest(unittest.TestCase):
    """The committed results must be exactly reproducible from inputs."""

    @classmethod
    def setUpClass(cls):
        cls.inputs = lib.Inputs(ROOT)
        cls.frontier, cls.md, cls.tsv = build_frontier.build(cls.inputs)

    def test_frontier_json_regenerates_identically(self):
        committed = (CC / "results" / "frontier.json").read_text()
        regenerated = json.dumps(self.frontier, indent=2, sort_keys=True) + "\n"
        self.assertEqual(committed, regenerated)

    def test_markdown_and_tsv_regenerate_identically(self):
        self.assertEqual((CC / "results" / "FRONTIER.md").read_text(), self.md)
        self.assertEqual((CC / "results" / "breakeven.tsv").read_text(),
                         self.tsv)

    def test_measured_backend_pairs_cost_with_latency_and_goodput(self):
        internal = self.frontier["backends"]["internal-k8s-snapshot"]
        self.assertEqual(internal["status"], "MEASURED")
        for m in internal["models"]:
            self.assertIn("p95", m["latency_seconds"])
            self.assertIn("within_30s", m["slo_goodput"])
            self.assertIn("preemptible/p95", m["per_request_cost_usd"])

    def test_of2_p95_matches_tsv_nearest_rank(self):
        vals = sorted(lib.load_cohort_seconds(self.inputs, "of2-n20-fresh"))
        p95 = str(lib.nearest_rank(vals, 95))
        of2 = self.frontier["backends"]["internal-k8s-snapshot"]["models"][0]
        self.assertEqual(of2["model"], "OpenFold2")
        self.assertEqual(of2["latency_seconds"]["p95"], p95)

    def test_boltz2_20s_goodput_is_honestly_zero(self):
        boltz = self.frontier["backends"]["internal-k8s-snapshot"]["models"][1]
        self.assertEqual(boltz["model"], "Boltz2")
        self.assertEqual(boltz["slo_goodput"]["within_20s"], "0.0000")

    def test_unmeasured_backends_get_no_costs_or_latency(self):
        for name in ("cerebrium", "internal-node-local-vm", "modal"):
            b = self.frontier["backends"][name]
            self.assertIsNone(b["per_request_cost_usd"], name)
            self.assertIsNone(b["latency_seconds"], name)
        self.assertEqual(self.frontier["backends"]["modal"]["status"],
                         "EXCLUDED_DOCUMENTATION_ONLY")
        self.assertIsNone(
            self.frontier["backends"]["modal"]["dated_unit_prices"])

    def test_modal_excluded_from_markdown_ranking_tables(self):
        # Modal may appear only as the excluded/documentation-only row.
        for line in self.md.splitlines():
            if "modal" in line.lower() and "|" in line:
                self.assertIn("EXCLUDED_DOCUMENTATION_ONLY", line, msg=line)

    def test_simulator_placeholder_prices_are_replaced(self):
        reports = self.frontier["simulator_frontier"]["reports"]
        self.assertEqual(len(reports), 75)
        sim = json.loads((ROOT / "catalog-sim/results/reports.json")
                         .read_text())
        raw = {(r["trace_family"], r["sensitivity"], r["policy"]): r
               for r in sim["reports"]}
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        for rep in reports:
            src = raw[(rep["trace_family"], rep["sensitivity"], rep["policy"])]
            expect = (Decimal(str(src["gpu"]["reserved_gpu_hours"])) * pre
                      ).quantize(lib.CENT6)
            self.assertEqual(
                rep["cost_usd"]["preemptible/egress_billed"]["gpu"],
                str(expect))
            # The simulator's own placeholder total must not appear.
            self.assertNotEqual(
                rep["cost_usd"]["on_demand/egress_billed"]["total"],
                str(src["cost_usd"]["total"]))

    def test_breakeven_values(self):
        be = self.frontier["breakeven"]
        self.assertEqual(be["preemption_loss_probability"]["gpu-h100-sxm"],
                         "0.44155844")
        self.assertEqual(
            be["storage_tier"]
            ["egress_billed_breakeven_refetches_per_gib_month"], "4.3533")
        for row in be["warm_vs_switch"]:
            per_switch = Decimal(row["per_switch_usd_p95"])
            warm = Decimal(row["warm_gpu_month_usd_on_demand"])
            self.assertEqual(
                Decimal(row["breakeven_requests_per_month"]),
                (warm / per_switch).quantize(Decimal("0.01")))

    def test_demand_sensitivity_is_consistent(self):
        for row in self.frontier["breakeven"]["demand_sensitivity"]:
            switch = Decimal(row["switch_every_request_usd_preemptible_p50"])
            warm = Decimal(row["one_warm_gpu_usd"])
            self.assertEqual(row["cheaper"],
                             "switch" if switch < warm else "warm")


if __name__ == "__main__":
    unittest.main()
