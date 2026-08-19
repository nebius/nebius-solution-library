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

    def test_adversary_relocation_separate_from_measured_timing(self):
        """Adversary: the unmeasured relocation add-on must never blend into
        the measured lower-bound timing rows."""
        cold = self.internal["cost_classes"][1]["cold_switch"]
        for row in cold["amortization"]:
            self.assertNotIn("relocalization_traffic_usd", row)
            self.assertNotIn("traffic", json.dumps(row).lower())
        reloc = cold["unmeasured_relocation"]
        self.assertIn("UNMEASURED", reloc["provenance"])
        egress = self.inputs.unit_price("nebius-list-object-egress")
        self.assertEqual(
            reloc["per_preparation_usd"]["egress_billed"],
            str((Decimal(reloc["traffic_gib"]) * egress)
                .quantize(lib.CENT6)))
        self.assertEqual(reloc["per_preparation_usd"]["egress_free"],
                         "0.000000")

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
        self.assertEqual(len(rows), 120)
        for row in rows:
            comp = sum(Decimal(v) for v in row["components_usd"].values()
                       if v is not None)
            total = Decimal(row["per_success_usd_nominal"])
            # Components are display-rounded independently; the total is one
            # quantization of the exact sum, so drift is bounded by the
            # per-component display precision, never accumulated.
            self.assertLessEqual(abs(comp - total), Decimal("0.000003"))
            self.assertGreaterEqual(
                Decimal(row["per_success_usd_pessimistic"]), total)
            warm = Decimal(row["one_warm_gpu_plus_fixed_monthly_usd"])
            self.assertEqual(row["cheaper_than_one_warm_gpu"],
                             Decimal(row["monthly_usd_nominal"]) < warm)

    def test_adversary_no_early_rounding_in_monthly_totals(self):
        """Adversary: monthly totals must come from unrounded per-success
        values. Recompute one high-demand row exactly and require equality;
        the rounded-per-success shortcut differs at this demand."""
        row = next(r for r in self.internal["fully_loaded"]
                   if r["model"] == "OpenFold2"
                   and r["cost_class"] == "prepared_switch"
                   and r["offer"] == "preemptible"
                   and r["restores_between_captures"] == 1
                   and r["requests_per_month"] == 1000000)
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        p50 = Decimal(self.internal["cost_classes"][0]["prepared_switch"]
                      ["latency_seconds"]["p50"])
        capture_s = Decimal("272.426")
        fixed = (self.inputs.monthly_price("nebius-sfs-4096gib")
                 + self.inputs.monthly_price("nebius-cpu-d3-4v16g-od"))
        exact = (lib.gpu_seconds_cost_exact(p50, pre)
                 + lib.gpu_seconds_cost_exact(capture_s, pre)
                 + fixed / Decimal(1000000))
        self.assertEqual(Decimal(row["monthly_usd_nominal"]),
                         (exact * 1000000).quantize(Decimal("0.01")))
        rounded_shortcut = (Decimal(row["per_success_usd_nominal"])
                            * 1000000).quantize(Decimal("0.01"))
        self.assertNotEqual(Decimal(row["monthly_usd_nominal"]),
                            rounded_shortcut,
                            "rounded shortcut coincides; pick another row")

    def test_adversary_of2_capture_never_applied_to_boltz2(self):
        rows = self.internal["fully_loaded"]
        for row in rows:
            if row["model"] == "Boltz2":
                self.assertIsNone(row["restores_between_captures"], row)
                self.assertIsNone(row["components_usd"]["capture_amortized"])
                self.assertIn("UNAVAILABLE", row["capture_status"])
                self.assertIn("OpenFold2", row["capture_status"])
            else:
                self.assertEqual(row["capture_status"], "APPLIED")
                self.assertIsNotNone(
                    row["components_usd"]["capture_amortized"])
        of2_r = {r["restores_between_captures"] for r in rows
                 if r["model"] == "OpenFold2"}
        self.assertEqual(of2_r, {1, 10, 100, 1000})
        cap = self.internal["snapshot_capture_cost"]
        self.assertEqual(cap["applies_to_model"], "OpenFold2")

    def test_adversary_both_egress_variant_totals_emitted(self):
        cold_rows = [r for r in self.internal["fully_loaded"]
                     if r["cost_class"] == "cold_switch"]
        self.assertTrue(cold_rows)
        for row in cold_rows:
            addon = row["unmeasured_relocation_addon"]
            base = Decimal(row["per_success_usd_nominal"])
            billed = Decimal(
                addon["per_success_usd_nominal_with_addon"]["egress_billed"])
            free = Decimal(
                addon["per_success_usd_nominal_with_addon"]["egress_free"])
            self.assertEqual(free, base)
            # billed and free are each one quantization of exact values, so
            # their difference may differ from the separately-quantized addon
            # by at most one display ulp.
            self.assertLessEqual(
                abs((billed - free)
                    - Decimal(addon["per_success_usd"]["egress_billed"])),
                Decimal("0.000001"))
            self.assertIn("unmeasured", addon["provenance"])
            m = addon["monthly_usd_nominal_with_addon"]
            self.assertGreater(Decimal(m["egress_billed"]),
                               Decimal(m["egress_free"]))
        for row in self.internal["fully_loaded"]:
            self.assertIn("monthly_usd_pessimistic", row)

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

    def test_adversary_fallback_dearer_than_on_demand_above_breakeven(self):
        """Adversary: the rejected claim said the fallback stays at or below
        on-demand across the whole grid. At p=0.60 it must be dearer, the
        cheapest strategy must be on_demand_only, and the narrative must
        state the crossover instead of the false claim."""
        pe = self.frontier["sweeps"]["preemption"]
        for p in pe["points"]:
            if p["loss_probability"] == "0.60":
                self.assertGreater(
                    Decimal(p["fallback_pre_then_od_usd_per_success"]),
                    Decimal(p["on_demand_usd_per_success"]), p["model"])
                self.assertEqual(p["cheapest_strategy"], "on_demand_only")
        self.assertIn("ONLY below", pe["fallback_model"])
        self.assertNotIn("across the entire loss grid", self.md)

    def test_adversary_markdown_exposes_full_preemption_grid(self):
        grid = self.inputs.assumption("preemption_loss_probability_grid")
        body = self.md.split("## Preemption")[1].split("## Regional")[0]
        table_rows = [l for l in body.splitlines()
                      if l.startswith("| OpenFold2 |")
                      or l.startswith("| Boltz2 |")]
        self.assertEqual(len(table_rows), 2 * len(grid))

    def test_adversary_cerebrium_described_as_pending_not_measured(self):
        cere = self.frontier["backends"]["cerebrium"]
        self.assertEqual(cere["status"], "PENDING_MEASUREMENT")
        self.assertIn("not measured", cere["notes"])
        self.assertIn("prices only, never measured", self.md)

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
