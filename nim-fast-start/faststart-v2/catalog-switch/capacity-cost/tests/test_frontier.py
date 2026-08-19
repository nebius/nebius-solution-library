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
        cls.internal = cls.frontier["backends"]["internal-k8s-snapshot"]

    def test_frontier_json_regenerates_identically(self):
        committed = (CC / "results" / "frontier.json").read_text()
        regenerated = json.dumps(self.frontier, indent=2, sort_keys=True) + "\n"
        self.assertEqual(committed, regenerated)

    def test_markdown_and_tsv_regenerate_identically(self):
        self.assertEqual((CC / "results" / "FRONTIER.md").read_text(), self.md)
        self.assertEqual((CC / "results" / "breakeven.tsv").read_text(),
                         self.tsv)

    # ---- cost classes --------------------------------------------------
    def test_measured_classes_pair_cost_latency_goodput(self):
        for m in self.internal["cost_classes"]:
            for cls in ("warm_hit", "prepared_switch"):
                c = m[cls]
                self.assertEqual(c["status"], "MEASURED")
                self.assertIn("p95", c["latency_seconds"])
                self.assertIn("within_30s", c["slo_goodput"])

    def test_of2_cold_and_all_node_miss_fail_closed(self):
        of2, boltz2 = self.internal["cost_classes"]
        self.assertEqual(of2["model"], "OpenFold2")
        self.assertEqual(of2["cold_switch"]["status"], "PENDING_MEASUREMENT")
        self.assertIsNone(of2["cold_switch"]["per_request_cost_usd"])
        for m in (of2, boltz2):
            self.assertEqual(m["node_provision_miss"]["status"],
                             "PENDING_MEASUREMENT")
            self.assertIsNone(m["node_provision_miss"]["latency_seconds"])

    def test_boltz2_cold_switch_lower_bound_math(self):
        cold = self.internal["cost_classes"][1]["cold_switch"]
        self.assertEqual(cold["status"], "MEASURED_LOWER_BOUND")
        prep = Decimal(cold["prep_seconds"])
        self.assertEqual(prep, Decimal("422.854590"))
        p95 = Decimal(self.internal["cost_classes"][1]["prepared_switch"]
                      ["latency_seconds"]["p95"])
        self.assertEqual(cold["understatement_vs_prepared"],
                         str(((prep + p95) / p95).quantize(Decimal("0.001"))))
        self.assertEqual(Decimal(cold["understatement_vs_prepared"]),
                         Decimal("14.951"))
        # reuse=1 worst case charges the full preparation.
        worst = cold["amortization"][0]
        self.assertEqual(worst["prep_reuse"], 1)
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        self.assertEqual(
            worst["per_request_cost_usd"]["preemptible"]["gpu_usd"],
            str(lib.gpu_seconds_cost(prep + p95, pre)))
        # Larger reuse strictly reduces the amortized cost.
        costs = [Decimal(r["per_request_cost_usd"]["preemptible"]["gpu_usd"])
                 for r in cold["amortization"]]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_warm_hit_is_measured_second_call(self):
        of2 = self.internal["cost_classes"][0]
        vals = sorted(lib.load_cohort_seconds(
            self.inputs, "of2-n20-fresh",
            metric="semantic_request_2_seconds"))
        self.assertEqual(of2["warm_hit"]["latency_seconds"]["p95"],
                         str(lib.nearest_rank(vals, 95)))

    def test_boltz2_20s_goodput_is_honestly_zero(self):
        boltz = self.internal["cost_classes"][1]["prepared_switch"]
        self.assertEqual(boltz["slo_goodput"]["within_20s"], "0.0000")

    # ---- fully loaded ---------------------------------------------------
    def test_fully_loaded_components_sum_and_scale(self):
        rows = self.internal["fully_loaded"]
        self.assertEqual(len(rows), 84)
        for row in rows:
            comp = {k: Decimal(v) for k, v in row["components_usd"].items()}
            total = Decimal(row["per_success_usd_nominal"])
            self.assertEqual(total, sum(comp.values()).quantize(lib.CENT6))
            self.assertGreaterEqual(
                Decimal(row["per_success_usd_pessimistic"]), total)
            self.assertEqual(
                Decimal(row["monthly_usd_nominal"]),
                (total * row["requests_per_month"]).quantize(Decimal("0.01")))
            warm = Decimal(row["one_warm_gpu_plus_fixed_monthly_usd"])
            self.assertEqual(row["cheaper_than_one_warm_gpu"],
                             Decimal(row["monthly_usd_nominal"]) < warm)

    def test_fully_loaded_covers_grids(self):
        rows = self.internal["fully_loaded"]
        boltz_cold = {r["prep_reuse"] for r in rows
                      if r["model"] == "Boltz2"
                      and r["cost_class"] == "cold_switch"}
        self.assertEqual(boltz_cold, {1, 2, 5, 10, 50})
        demands = {r["requests_per_month"] for r in rows}
        self.assertEqual(len(demands), 6)
        # OpenFold2 has no cold rows (fail-closed).
        self.assertFalse([r for r in rows if r["model"] == "OpenFold2"
                          and r["cost_class"] == "cold_switch"])

    # ---- sweeps ----------------------------------------------------------
    def test_preemption_sweep_consumes_full_grid(self):
        pts = self.frontier["sweeps"]["preemption"]["points"]
        grid = self.inputs.assumption("preemption_loss_probability_grid")
        for model in ("OpenFold2", "Boltz2"):
            got = [p["loss_probability"] for p in pts
                   if p["model"] == model]
            self.assertEqual(got, list(grid))
        for p in pts:
            if p["loss_probability"] == "0.00":
                self.assertEqual(p["preemptible_only_usd_per_success"],
                                 p["fallback_pre_then_od_usd_per_success"])
            if p["loss_probability"] == "0.44155844":
                self.assertEqual(p["preemptible_only_usd_per_success"],
                                 p["on_demand_usd_per_success"])

    def test_regional_loss_options_cost_only(self):
        rl = self.frontier["sweeps"]["regional_loss"]
        self.assertEqual(len(rl["options"]), 3)
        self.assertIn("UNMEASURED", rl["latency"])
        for opt in rl["options"]:
            Decimal(opt["usd_per_hour"])
            self.assertNotIn("latency", json.dumps(opt).lower())

    def test_isolated_sweep_curves_complete(self):
        for block, grid in (
                (self.frontier["simulation_frontier"]["top_k_sweep"],
                 [1, 2, 4, 8, 16]),
                (self.frontier["simulation_frontier"]["cache_sweep"],
                 [150, 200, 400, 800, 1600])):
            self.assertEqual(len(block["curves"]), 5)  # trace families
            for family, rows in block["curves"].items():
                self.assertEqual([r["sweep_value"] for r in rows], grid)
                for r in rows:
                    self.assertIn("placeholder", r["input_provenance"])
            self.assertEqual(set(block["knee"]), set(block["curves"]))

    # ---- provenance and exclusions ---------------------------------------
    def test_simulation_never_labeled_measured(self):
        sim = self.frontier["simulation_frontier"]
        self.assertIn("placeholder-derived", sim["provenance"])
        for rep in sim["legacy_matrix"]:
            self.assertIn("placeholder", rep["input_provenance"])
        blob = json.dumps(sim).lower()
        self.assertNotIn('"status": "measured"', blob)

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
        for line in self.md.splitlines():
            if "modal" in line.lower() and "|" in line:
                self.assertIn("EXCLUDED_DOCUMENTATION_ONLY", line, msg=line)

    def test_simulator_placeholder_prices_are_replaced(self):
        legacy = self.frontier["simulation_frontier"]["legacy_matrix"]
        self.assertEqual(len(legacy), 75)
        sim = json.loads((ROOT / "catalog-sim/results/reports.json")
                         .read_text())
        raw = {(r["trace_family"], r["sensitivity"], r["policy"]): r
               for r in sim["reports"]}
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        for rep in legacy:
            src = raw[(rep["trace_family"], rep["sensitivity"], rep["policy"])]
            expect = (Decimal(str(src["gpu"]["reserved_gpu_hours"])) * pre
                      ).quantize(lib.CENT6)
            self.assertEqual(
                rep["cost_usd"]["preemptible/egress_billed"]["gpu"],
                str(expect))
            self.assertNotEqual(
                rep["cost_usd"]["on_demand/egress_billed"]["total"],
                str(src["cost_usd"]["total"]))

    def test_breakeven_values(self):
        be = self.frontier["breakeven"]
        pe = self.frontier["sweeps"]["preemption"]
        self.assertEqual(
            pe["breakeven_loss_probability"]["gpu-h100-sxm"], "0.44155844")
        self.assertEqual(
            be["storage_tier"]
            ["egress_billed_breakeven_refetches_per_gib_month"], "4.3533")
        for row in be["warm_vs_switch"]:
            per_switch = Decimal(row["per_switch_usd_p95"])
            warm = Decimal(row["warm_gpu_month_usd_on_demand"])
            self.assertEqual(
                Decimal(row["breakeven_requests_per_month"]),
                (warm / per_switch).quantize(Decimal("0.01")))


if __name__ == "__main__":
    unittest.main()
