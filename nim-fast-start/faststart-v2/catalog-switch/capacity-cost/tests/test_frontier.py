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
        cls.cost_rows = (cls.internal["complete_cost_totals"]
                         + cls.internal["incomplete_lower_bound_subtotals"])

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

    # ---- cost rows: two capacity models, strict completeness ------------
    def test_cost_row_count_and_capacity_models(self):
        rows = self.cost_rows
        self.assertEqual(len(rows), 180)
        self.assertEqual(len(self.internal["complete_cost_totals"]), 44)
        self.assertEqual(
            len(self.internal["incomplete_lower_bound_subtotals"]), 136)
        dedicated = [r for r in rows
                     if r["capacity_model"] == "dedicated_prepared_node"]
        marginal = [r for r in rows
                    if r["capacity_model"] == "marginal_zero_idle_bound"]
        self.assertEqual(len(dedicated), 60)
        self.assertEqual(len(marginal), 120)

    def test_adversary_collections_match_completeness_exactly(self):
        """Adversary: an incomplete subtotal must never sit in the complete
        collection, and vice versa — membership IS the label."""
        for row in self.internal["complete_cost_totals"]:
            self.assertEqual(row["completeness"], "COMPLETE")
        for row in self.internal["incomplete_lower_bound_subtotals"]:
            self.assertEqual(row["completeness"], "INCOMPLETE_LOWER_BOUND")
        self.assertNotIn("fully_loaded", self.internal)

    def test_adversary_no_fully_loaded_label_in_any_output(self):
        """Whole-output adversary: the fully_loaded label (any spelling)
        must not appear anywhere in frontier.json, FRONTIER.md, or
        breakeven.tsv — an incomplete lower-bound subtotal under such a
        label misreads as a full cost."""
        outputs = (
            json.dumps(self.frontier, indent=2, sort_keys=True),
            self.md,
            self.tsv,
        )
        for text in outputs:
            low = text.lower()
            for token in ("fully_loaded", "fully-loaded", "fully loaded"):
                self.assertNotIn(token, low)

    def test_adversary_incomplete_rows_null_totals_and_no_decisions(self):
        """Adversary: a row with any unavailable/unallocated required
        component must carry null complete totals, publish numbers only
        under lower-bound names, and forbid decisions. No decision field
        may exist anywhere in fully_loaded."""
        for row in self.cost_rows:
            self.assertNotIn("cheaper_than_one_warm_gpu", row)
            self.assertNotIn("one_warm_gpu_plus_fixed_monthly_usd", row)
            if row["completeness"] == "COMPLETE":
                self.assertEqual(row["missing_components"], [])
                for k in ("per_success_usd_nominal",
                          "per_success_usd_pessimistic",
                          "monthly_usd_nominal", "monthly_usd_pessimistic"):
                    self.assertIsNotNone(row[k], k)
                self.assertNotIn("lower_bound_subtotals_usd", row)
            else:
                self.assertEqual(row["completeness"],
                                 "INCOMPLETE_LOWER_BOUND")
                self.assertTrue(row["missing_components"])
                for k in ("per_success_usd_nominal",
                          "per_success_usd_pessimistic",
                          "monthly_usd_nominal", "monthly_usd_pessimistic"):
                    self.assertIsNone(row[k], k)
                lb = row["lower_bound_subtotals_usd"]
                for k in ("per_success_nominal", "per_success_pessimistic",
                          "monthly_nominal", "monthly_pessimistic"):
                    Decimal(lb[k])
                self.assertIn("FORBIDDEN", row["decision_policy"])

    def test_adversary_only_feasible_dedicated_of2_rows_are_complete(self):
        """COMPLETE requires every component: idle allocated (dedicated
        capacity model), capture available (OpenFold2 only), AND the node
        plan feasible within captured availability."""
        for row in self.cost_rows:
            feasible = (row.get("capacity_feasibility", {}).get("status")
                        == "FEASIBLE_AT_CAPTURE")
            expect_complete = (
                row["capacity_model"] == "dedicated_prepared_node"
                and row["model"] == "OpenFold2" and feasible)
            self.assertEqual(row["completeness"] == "COMPLETE",
                             expect_complete, str(row["model"]))
            if row["capacity_model"] == "marginal_zero_idle_bound":
                self.assertIn("idle_reserved_gpu_capacity_share",
                              row["missing_components"])

    def test_adversary_capacity_feasibility_gate(self):
        """Adversary: a COMPLETE dedicated row may never need more nodes
        than the largest single-fabric quota-clipped availability at
        capture. The on-demand 1M-demand OpenFold2 plan (7 nominal / 8
        pessimistic nodes vs 6 available) must be demoted with the
        capacity component named missing; the preemptible plan (76
        available) stays COMPLETE."""
        snap_avail = {"on_demand": 0, "preemptible": 0}
        for r in self.inputs.availability_rows(
                "eu-north1", "gpu-h100-sxm", 1):
            for offer in snap_avail:
                a = r["offers"][offer].get("available")
                if a is not None:
                    snap_avail[offer] = max(snap_avail[offer], a)
        self.assertEqual(snap_avail, {"on_demand": 6, "preemptible": 76})
        for row in self.cost_rows:
            if row["capacity_model"] != "dedicated_prepared_node":
                continue
            feas = row["capacity_feasibility"]
            self.assertEqual(
                feas["max_single_fabric_available_at_capture"],
                snap_avail[row["offer"]])
            needed = max(row["nodes_required"],
                         row["nodes_required_pessimistic"])
            expect_feasible = needed <= snap_avail[row["offer"]]
            self.assertEqual(
                feas["status"] == "FEASIBLE_AT_CAPTURE", expect_feasible)
            if not expect_feasible:
                self.assertIn("capacity_availability_at_capture",
                              row["missing_components"])
                self.assertIsNone(row["per_success_usd_nominal"])
            if row["completeness"] == "COMPLETE":
                self.assertLessEqual(needed, snap_avail[row["offer"]])
        demoted = [r for r in self.cost_rows
                   if r["model"] == "OpenFold2"
                   and r["capacity_model"] == "dedicated_prepared_node"
                   and r["offer"] == "on_demand"
                   and r["requests_per_month"] == 1000000]
        self.assertEqual(len(demoted), 4)  # one per capture-reuse R
        for row in demoted:
            self.assertEqual(row["completeness"], "INCOMPLETE_LOWER_BOUND")
            self.assertEqual(row["nodes_required"], 7)
            self.assertEqual(row["nodes_required_pessimistic"], 8)
        kept = next(r for r in self.cost_rows
                    if r["model"] == "OpenFold2"
                    and r["capacity_model"] == "dedicated_prepared_node"
                    and r["offer"] == "preemptible"
                    and r["requests_per_month"] == 1000000
                    and r["restores_between_captures"] == 100)
        self.assertEqual(kept["completeness"], "COMPLETE")

    def test_adversary_every_cost_row_pairs_evidence(self):
        """Adversary: every cost row must carry the latency/p99/goodput/
        error evidence that sized it — cost is never published alone."""
        for row in self.cost_rows:
            pe = row["paired_evidence"]
            self.assertIn("n20", pe["evidence"])
            self.assertEqual(pe["n"], 20)
            self.assertEqual(pe["failed_attempt_denominator"], "0/20")
            for k in ("p50", "p95", "p99", "min", "max"):
                Decimal(pe["latency_seconds"][k])
            self.assertIn("within_30s", pe["slo_goodput"])
            if row["cost_class"] == "cold_switch":
                Decimal(pe["cold_trigger_latency_seconds_p95"])

    def test_adversary_dedicated_rows_allocate_idle_capacity(self):
        """Adversary: dedicated rows must charge whole node-months with
        correct ceilings — utilization can never exceed 1 and monthly
        totals must equal nodes*instance + fixed (+ capture*D/R)."""
        month_seconds = Decimal(730) * 3600
        pre_month = self.inputs.monthly_price("nebius-h100-1g-pre")
        od_month = self.inputs.monthly_price("nebius-h100-1g-od")
        fixed = (self.inputs.monthly_price("nebius-sfs-4096gib")
                 + self.inputs.monthly_price("nebius-cpu-d3-4v16g-od"))
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        od = self.inputs.unit_price("nebius-h100-1g-od")
        for row in self.cost_rows:
            if row["capacity_model"] != "dedicated_prepared_node":
                continue
            model_idx = 0 if row["model"] == "OpenFold2" else 1
            p50 = Decimal(self.internal["cost_classes"][model_idx]
                          ["prepared_switch"]["latency_seconds"]["p50"])
            d = Decimal(row["requests_per_month"])
            busy = d * p50
            expected_nodes = max(build_frontier.ceil_pos(
                busy / month_seconds), 1)
            self.assertEqual(row["nodes_required"], expected_nodes)
            util = Decimal(row["utilization_busy_fraction"])
            self.assertLessEqual(util, Decimal(1))
            self.assertGreater(util, Decimal(0))
            inst = pre_month if row["offer"] == "preemptible" else od_month
            hourly = pre if row["offer"] == "preemptible" else od
            cap = Decimal(0)
            if row["restores_between_captures"] is not None:
                cap = (lib.gpu_seconds_cost_exact(Decimal("272.426"), hourly)
                       / Decimal(row["restores_between_captures"])) * d
            expected_monthly = (expected_nodes * inst + fixed + cap
                                ).quantize(Decimal("0.01"))
            got = (row["monthly_usd_nominal"] if row["completeness"] ==
                   "COMPLETE" else
                   row["lower_bound_subtotals_usd"]["monthly_nominal"])
            self.assertEqual(Decimal(got), expected_monthly, row["model"])

    def test_adversary_no_early_rounding_in_monthly_totals(self):
        """Adversary: monthly totals must come from unrounded per-success
        values. Recompute one high-demand marginal row exactly; the rounded
        per-success shortcut must differ."""
        row = next(r for r in self.cost_rows
                   if r["model"] == "OpenFold2"
                   and r["capacity_model"] == "marginal_zero_idle_bound"
                   and r["cost_class"] == "prepared_switch"
                   and r["offer"] == "preemptible"
                   and r["restores_between_captures"] == 1
                   and r["requests_per_month"] == 1000000)
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        p50 = Decimal(self.internal["cost_classes"][0]["prepared_switch"]
                      ["latency_seconds"]["p50"])
        fixed = (self.inputs.monthly_price("nebius-sfs-4096gib")
                 + self.inputs.monthly_price("nebius-cpu-d3-4v16g-od"))
        exact = (lib.gpu_seconds_cost_exact(p50, pre)
                 + lib.gpu_seconds_cost_exact(Decimal("272.426"), pre)
                 + fixed / Decimal(1000000))
        lb = row["lower_bound_subtotals_usd"]
        self.assertEqual(Decimal(lb["monthly_nominal"]),
                         (exact * 1000000).quantize(Decimal("0.01")))
        rounded_shortcut = (Decimal(lb["per_success_nominal"])
                            * 1000000).quantize(Decimal("0.01"))
        self.assertNotEqual(Decimal(lb["monthly_nominal"]), rounded_shortcut,
                            "rounded shortcut coincides; pick another row")

    def test_adversary_of2_capture_never_applied_to_boltz2(self):
        rows = self.cost_rows
        for row in rows:
            comp = row["components_usd"]
            if row["model"] == "Boltz2":
                self.assertIsNone(row["restores_between_captures"], row)
                cap_key = ("capture_amortized_monthly"
                           if row["capacity_model"] ==
                           "dedicated_prepared_node" else "capture_amortized")
                self.assertIsNone(comp[cap_key])
                self.assertIn("UNAVAILABLE", row["capture_status"])
                self.assertIn("OpenFold2", row["capture_status"])
                self.assertIn("capture_amortized", row["missing_components"])
            else:
                self.assertEqual(row["capture_status"], "APPLIED")
        for cm in ("dedicated_prepared_node", "marginal_zero_idle_bound"):
            of2_r = {r["restores_between_captures"] for r in rows
                     if r["model"] == "OpenFold2"
                     and r["capacity_model"] == cm}
            self.assertEqual(of2_r, {1, 10, 100, 1000}, cm)
        cap = self.internal["snapshot_capture_cost"]
        self.assertEqual(cap["applies_to_model"], "OpenFold2")

    def test_adversary_all_four_relocation_variants_emitted(self):
        """Adversary: the relocation add-on must publish nominal AND
        pessimistic totals under BOTH egress variants, per-success and
        monthly, consistent with the lower-bound subtotals."""
        cold_rows = [r for r in self.cost_rows
                     if r["cost_class"] == "cold_switch"]
        self.assertTrue(cold_rows)
        for row in cold_rows:
            addon = row["unmeasured_relocation_addon"]
            lb = row["lower_bound_subtotals_usd"]
            per = addon["per_success_lower_bound_with_addon"]
            monthly = addon["monthly_lower_bound_with_addon"]
            for block in (per, monthly):
                self.assertEqual(set(block), {"nominal", "pessimistic"})
                for variant in block.values():
                    self.assertEqual(set(variant),
                                     {"egress_billed", "egress_free"})
            self.assertEqual(Decimal(per["nominal"]["egress_free"]),
                             Decimal(lb["per_success_nominal"]))
            self.assertEqual(Decimal(per["pessimistic"]["egress_free"]),
                             Decimal(lb["per_success_pessimistic"]))
            self.assertEqual(Decimal(monthly["nominal"]["egress_free"]),
                             Decimal(lb["monthly_nominal"]))
            self.assertEqual(Decimal(monthly["pessimistic"]["egress_free"]),
                             Decimal(lb["monthly_pessimistic"]))
            for kind in ("nominal", "pessimistic"):
                self.assertGreater(Decimal(per[kind]["egress_billed"]),
                                   Decimal(per[kind]["egress_free"]))
                self.assertGreater(Decimal(monthly[kind]["egress_billed"]),
                                   Decimal(monthly[kind]["egress_free"]))
                # billed - free equals the addon within one display ulp.
                self.assertLessEqual(
                    abs((Decimal(per[kind]["egress_billed"])
                         - Decimal(per[kind]["egress_free"]))
                        - Decimal(addon["per_success_usd"]["egress_billed"])),
                    Decimal("0.000001"))
            self.assertGreaterEqual(
                Decimal(per["pessimistic"]["egress_billed"]),
                Decimal(per["nominal"]["egress_billed"]))
            self.assertIn("unmeasured", addon["provenance"])

    def test_adversary_traffic_arithmetic_uses_exact_bytes(self):
        """Adversary: relocation arithmetic must start from the measured
        byte count, never from the display-quantized GiB string."""
        entry = self.inputs.measured_entry("boltz2-pret0-cache-read")
        exact_gib = lib.bytes_to_gib_exact(
            entry["cache_bytes"] + entry["artifact_bytes"])
        egress = self.inputs.unit_price("nebius-list-object-egress")
        reloc = self.internal["cost_classes"][1]["cold_switch"][
            "unmeasured_relocation"]
        self.assertEqual(reloc["traffic_bytes"],
                         entry["cache_bytes"] + entry["artifact_bytes"])
        self.assertEqual(Decimal(reloc["per_preparation_usd"]
                                 ["egress_billed"]),
                         (exact_gib * egress).quantize(lib.CENT6))
        # Addon per-success at reuse=1 must equal the exact chain.
        row = next(r for r in self.cost_rows
                   if r["cost_class"] == "cold_switch"
                   and r["prep_reuse"] == 1)
        self.assertEqual(
            Decimal(row["unmeasured_relocation_addon"]["per_success_usd"]
                    ["egress_billed"]),
            (exact_gib * egress).quantize(lib.CENT6))

    def test_fully_loaded_covers_grids(self):
        rows = self.cost_rows
        boltz_cold = {r["prep_reuse"] for r in rows
                      if r["model"] == "Boltz2"
                      and r["cost_class"] == "cold_switch"}
        self.assertEqual(boltz_cold, {1, 2, 5, 10, 50})
        demands = {r["requests_per_month"] for r in rows}
        self.assertEqual(len(demands), 6)
        # OpenFold2 has no cold rows (fail-closed).
        self.assertFalse([r for r in rows if r["model"] == "OpenFold2"
                          and r["cost_class"] == "cold_switch"])

    def test_adversary_tsv_tables_named_by_completeness(self):
        """Adversary: TSV table names must state completeness explicitly —
        complete_* only for COMPLETE rows, incomplete_*_lower_bound with a
        no_decision flag for everything else; no fully_loaded prefix."""
        for line in self.tsv.splitlines():
            table = line.split("\t")[0]
            self.assertFalse(table.startswith("fully_loaded"), line)
            if table == "complete_dedicated_totals":
                self.assertTrue(line.endswith("\tcomplete"), line)
            if table.startswith("incomplete_"):
                self.assertIn("lower_bound", table, line)
                self.assertIn("no_decision", line, line)
        tables = {l.split("\t")[0] for l in self.tsv.splitlines()}
        self.assertIn("complete_dedicated_totals", tables)
        self.assertIn("incomplete_dedicated_lower_bound", tables)
        self.assertIn("incomplete_marginal_lower_bound", tables)
        self.assertIn("incomplete_relocation_addon_lower_bound", tables)
        self.assertIn("marginal_zero_idle_bound", self.md)
        self.assertIn("dedicated_prepared_node", self.md)

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
            if p["loss_probability"] == "0.00":
                # Exact two-way tie: fallback(0) equals preemptible-only.
                self.assertEqual(p["cheapest_strategies"],
                                 ["fallback_pre_then_od",
                                  "preemptible_only"])

    def test_adversary_boundary_strategy_selected_on_exact_values(self):
        """Adversary: at grid p=0.44155844, strictly below the exact
        break-even 1 - 2.15/3.85, all three strategies tie at the 1e-6
        display precision, but exactly the preemptible-only strategy is
        strictly cheapest. Selection must therefore happen on exact
        Decimals, and the displayed tie must not leak into the choice."""
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        od = self.inputs.unit_price("nebius-h100-1g-od")
        p = Decimal("0.44155844")
        for pt in self.frontier["sweeps"]["preemption"]["points"]:
            if pt["loss_probability"] != "0.44155844":
                continue
            # Displays tie three ways...
            self.assertEqual(pt["preemptible_only_usd_per_success"],
                             pt["fallback_pre_then_od_usd_per_success"])
            self.assertEqual(pt["preemptible_only_usd_per_success"],
                             pt["on_demand_usd_per_success"])
            # ...but the exact ordering is strict and must decide.
            model_idx = 0 if pt["model"] == "OpenFold2" else 1
            p95 = Decimal(self.internal["cost_classes"][model_idx]
                          ["prepared_switch"]["latency_seconds"]["p95"])
            exact_pre = lib.preemptible_expected_cost_exact(p95, pre, p)
            exact_fb = lib.fallback_blend_cost_exact(p95, pre, od, p)
            exact_od = lib.gpu_seconds_cost_exact(p95, od)
            self.assertLess(exact_pre, exact_fb)
            self.assertLess(exact_fb, exact_od)
            self.assertEqual(pt["cheapest_strategies"],
                             ["preemptible_only"])

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
                self.assertEqual(p["cheapest_strategies"],
                                 ["on_demand_only"])
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

    def test_adversary_capacity_curves_price_l1_storage(self):
        """Adversary: cache-capacity $/1k curves must consume the captured
        node-disk price records — recompute one point exactly, require
        storage to grow along the cache axis, stay constant along K, and
        appear in the legacy matrix too."""
        rates = {
            "network_ssd": self.inputs.unit_price(
                "nebius-disk-nssd-gib-hour"),
            "network_ssd_non_replicated": self.inputs.unit_price(
                "nebius-disk-nrd-gib-hour"),
        }
        sweeps = json.loads(
            (ROOT / "catalog-switch/capacity-cost/results/sweeps.json")
            .read_text())
        horizon_h = (Decimal(str(sweeps["scenario"]["horizon_seconds"]))
                     / 3600)
        nodes = sweeps["scenario"]["n_nodes"]
        cache_zipf = self.frontier["simulation_frontier"]["cache_sweep"][
            "curves"]["zipf"]
        prev = None
        for row in cache_zipf:
            gib = Decimal(row["sweep_value"])
            combo = row["cost_usd"]["preemptible/egress_billed"]
            for label, rate in rates.items():
                expect = (gib * nodes * horizon_h * rate).quantize(lib.CENT6)
                self.assertEqual(
                    Decimal(combo["l1_storage_usd"][label]), expect)
                self.assertGreater(
                    Decimal(combo["total_with_l1_storage"][label]),
                    Decimal(combo["total"]))
            storage = Decimal(
                combo["l1_storage_usd"]["network_ssd_non_replicated"])
            if prev is not None:
                self.assertGreater(storage, prev)
            prev = storage
        k_zipf = self.frontier["simulation_frontier"]["top_k_sweep"][
            "curves"]["zipf"]
        k_storage = {r["cost_usd"]["preemptible/egress_billed"]
                     ["l1_storage_usd"]["network_ssd_non_replicated"]
                     for r in k_zipf}
        self.assertEqual(len(k_storage), 1)  # constant 400 GiB base
        for rep in self.frontier["simulation_frontier"]["legacy_matrix"]:
            self.assertIn(
                "l1_storage_usd",
                rep["cost_usd"]["preemptible/egress_billed"])

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

    def test_breakeven_values_exact_through_division(self):
        be = self.frontier["breakeven"]
        pe = self.frontier["sweeps"]["preemption"]
        self.assertEqual(
            pe["breakeven_loss_probability"]["gpu-h100-sxm"], "0.44155844")
        self.assertEqual(
            be["storage_tier"]
            ["egress_billed_breakeven_refetches_per_gib_month"], "4.3533")
        pre = self.inputs.unit_price("nebius-h100-1g-pre")
        od = self.inputs.unit_price("nebius-h100-1g-od")
        rounded_differs_somewhere = False
        for row in be["warm_vs_switch"]:
            self.assertTrue(row["decision_forbidden"])
            self.assertIn("UPPER BOUND", row["bound"])
            model_idx = 0 if row["model"] == "OpenFold2" else 1
            p95 = Decimal(self.internal["cost_classes"][model_idx]
                          ["prepared_switch"]["latency_seconds"]["p95"])
            hourly = pre if row["switch_offer"] == "preemptible" else od
            exact = lib.gpu_seconds_cost_exact(p95, hourly)
            warm = Decimal(row["warm_gpu_month_usd_on_demand"])
            self.assertEqual(
                Decimal(row["breakeven_requests_per_month_upper_bound"]),
                (warm / exact).quantize(Decimal("0.01")))
            rounded = (warm / Decimal(row["per_switch_usd_p95"])
                       ).quantize(Decimal("0.01"))
            if rounded != Decimal(
                    row["breakeven_requests_per_month_upper_bound"]):
                rounded_differs_somewhere = True
        # Adversary: the rounded-intermediate shortcut must actually differ
        # for at least one row, proving the exact chain matters.
        self.assertTrue(rounded_differs_somewhere)


if __name__ == "__main__":
    unittest.main()
