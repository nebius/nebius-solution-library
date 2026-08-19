#!/usr/bin/env python3
"""Build the measured capacity/cost frontier (corrected candidate, v2).

Reads the committed snapshots and checksum-pinned artifacts, consumes the
isolated top-K/cache sweeps and the legacy simulator reports as
placeholder-derived simulation (never measurement), and emits deterministic
results:

- ``results/frontier.json``
- ``results/FRONTIER.md``
- ``results/breakeven.tsv``

Cost classes per model (prepared versus request-triggered, with amortization):

- ``warm_hit``: the model is already serving; measured second-call latency.
- ``prepared_switch``: request-triggered switch on a node whose pre-T0
  preparation already happened; measured n=20 T0-to-second-response.
- ``cold_switch``: request-triggered switch including pre-T0 preparation;
  measured lower bound for Boltz2 (422.854590 s cache full read), amortized
  over the prep_reuse_grid; fail-closed PENDING_MEASUREMENT for OpenFold2.
- ``node_provision_miss``: declared, fail-closed PENDING_MEASUREMENT.

Run from the ``faststart-v2`` directory:

    python3 catalog-switch/capacity-cost/costmodel/build_frontier.py

No network, no cloud calls, no run-time clocks: output is a pure function of
committed inputs, so regeneration is byte-identical.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lib  # noqa: E402

ROOT = HERE.parent.parent.parent  # faststart-v2
RESULTS = HERE.parent / "results"

SLO_THRESHOLDS = (Decimal(20), Decimal(30), Decimal(60))
WARM_POOL_K = (1, 2, 4, 8, 16)
GIB = Decimal(2) ** 30
CAPTURE_AMORT_HEADLINE_R = 100


def _stats(values: list[Decimal]) -> dict:
    values = sorted(values)
    return {
        "p50": str(lib.nearest_rank(values, 50)),
        "p95": str(lib.nearest_rank(values, 95)),
        "min": str(values[0]),
        "max": str(values[-1]),
    }


def _goodput(values: list[Decimal]) -> dict:
    return {f"within_{int(t)}s": str(lib.goodput_within(sorted(values), t))
            for t in SLO_THRESHOLDS}


def _gpu_costs(seconds: Decimal, od: Decimal, pre: Decimal,
               pess: Decimal) -> dict:
    out = {}
    for offer, hourly in (("on_demand", od), ("preemptible", pre)):
        nominal = lib.gpu_seconds_cost(seconds, hourly)
        out[offer] = {
            "gpu_usd": str(nominal),
            "gpu_usd_pessimistic": str((nominal * pess).quantize(lib.CENT6)),
        }
    return out


class Ctx:
    """Shared prices/assumptions resolved once."""

    def __init__(self, inputs: lib.Inputs):
        self.inputs = inputs
        self.od = inputs.unit_price("nebius-h100-1g-od")
        self.pre = inputs.unit_price("nebius-h100-1g-pre")
        self.egress = inputs.unit_price("nebius-list-object-egress")
        self.warm_month = inputs.monthly_price("nebius-h100-1g-od")
        self.fixed_month = (
            inputs.monthly_price("nebius-sfs-4096gib")
            + inputs.monthly_price("nebius-cpu-d3-4v16g-od"))
        self.pess = lib.retry_multiplier(Decimal(
            inputs.assumption("failure_rate_upper_bound_rule_of_three")))
        self.prep_reuse_grid = inputs.assumption("prep_reuse_grid")
        self.capture_r_grid = inputs.assumption(
            "restores_between_captures_grid")
        self.demand_grid = inputs.assumption("monthly_demand_grid_requests")
        self.loss_grid = [Decimal(p) for p in inputs.assumption(
            "preemption_loss_probability_grid")]


# --------------------------------------------------------------------------
# Cost classes per model
# --------------------------------------------------------------------------

def model_cost_classes(ctx: Ctx, entry_id: str) -> dict:
    inputs = ctx.inputs
    entry = inputs.measured_entry(entry_id)
    switch_vals = lib.load_cohort_seconds(inputs, entry_id)
    warm_vals = lib.load_cohort_seconds(
        inputs, entry_id, metric=entry["warm_hit_metric"])
    switch_p95 = lib.nearest_rank(sorted(switch_vals), 95)
    switch_p50 = lib.nearest_rank(sorted(switch_vals), 50)

    warm_hit = {
        "status": "MEASURED",
        "evidence": f"{entry_id}:{entry['warm_hit_metric']}",
        "latency_seconds": _stats(warm_vals),
        "slo_goodput": _goodput(warm_vals),
        "per_request_cost_usd": _gpu_costs(
            lib.nearest_rank(sorted(warm_vals), 50), ctx.od, ctx.pre,
            ctx.pess),
        "notes": ("Marginal GPU-seconds of an already-serving model; the "
                  "node itself is paid for by the warm-pool or switching "
                  "economics below."),
    }

    prepared = {
        "status": "MEASURED",
        "evidence": f"{entry_id}:{entry['metric']}",
        "n": entry["n"],
        "failed_attempt_denominator": entry["failed_attempt_denominator"],
        "latency_seconds": _stats(switch_vals),
        "slo_goodput": _goodput(switch_vals),
        "per_request_cost_usd": {
            stat: _gpu_costs(secs, ctx.od, ctx.pre, ctx.pess)
            for stat, secs in (("p50", switch_p50), ("p95", switch_p95))},
        "notes": ("Request-triggered switch on a prepared node (image "
                  "resident, storage attached, pre-T0 preparation already "
                  "done). GPU critical path T0 through second semantic "
                  "response; pessimistic = rule-of-three retry bound from "
                  "the measured 0/20 denominator."),
    }

    if entry["model"] == "Boltz2":
        prep = inputs.measured_entry("boltz2-pret0-cache-read")
        prep_s = Decimal(prep["value_seconds"])
        prep_traffic_gib = ((Decimal(prep["cache_bytes"])
                             + Decimal(prep["artifact_bytes"])) / GIB
                            ).quantize(Decimal("0.000001"))
        rows = []
        for reuse in ctx.prep_reuse_grid:
            s = Decimal(reuse)
            amortized_seconds = (prep_s / s + switch_p95).quantize(
                Decimal("0.000001"))
            traffic_billed = (prep_traffic_gib * ctx.egress / s).quantize(
                lib.CENT6)
            row = {
                "prep_reuse": reuse,
                "amortized_gpu_seconds_p95": str(amortized_seconds),
                "per_request_cost_usd": _gpu_costs(
                    amortized_seconds, ctx.od, ctx.pre, ctx.pess),
                "relocalization_traffic_usd": {
                    "egress_billed": str(traffic_billed),
                    "egress_free": "0.000000",
                },
            }
            rows.append(row)
        cold = {
            "status": "MEASURED_LOWER_BOUND",
            "evidence": "boltz2-pret0-cache-read + " + entry_id,
            "prep_seconds": str(prep_s),
            "prep_traffic_gib": str(prep_traffic_gib),
            "understatement_vs_prepared": str(
                ((prep_s + switch_p95) / switch_p95).quantize(
                    Decimal("0.001"))),
            "triggering_request_latency_seconds_p95": str(
                (prep_s + switch_p95).quantize(Decimal("0.000001"))),
            "amortization": rows,
            "notes": ("Lower bound: measured 422.854590 s pre-T0 cache full "
                      "read; the M3 artifact is read O_DIRECT inside the T0 "
                      "window (already charged) and image pull is excluded "
                      "because residency was proven pre-T0. prep_reuse=1 is "
                      "the fully request-triggered worst case; larger reuse "
                      "amortizes one preparation over later switches, whose "
                      "own latency is the prepared_switch class."),
        }
    else:
        decl = inputs.unmeasured_cost_class("cold_switch", entry["model"])
        cold = {"status": decl["status"], "reason": decl["reason"],
                "per_request_cost_usd": None, "latency_seconds": None}

    miss = inputs.unmeasured_cost_class("node_provision_miss", entry["model"])
    node_miss = {"status": miss["status"], "reason": miss["reason"],
                 "per_request_cost_usd": None, "latency_seconds": None}

    return {
        "model": entry["model"],
        "warm_hit": warm_hit,
        "prepared_switch": prepared,
        "cold_switch": cold,
        "node_provision_miss": node_miss,
    }


# --------------------------------------------------------------------------
# Fully-loaded per-success and monthly totals
# --------------------------------------------------------------------------

def fully_loaded_rows(ctx: Ctx, classes: dict) -> list[dict]:
    """Complete per-success and monthly totals across the demand grid.

    Components: switch GPU (p50 central), prep GPU+traffic amortized (cold
    class), capture amortized at the headline R, fixed SFS+controller share,
    retry sensitivity (nominal and rule-of-three pessimistic on the
    attempt-scaled GPU components).
    """
    inputs = ctx.inputs
    capture_s = Decimal(inputs.assumption("snapshot_capture_seconds_of2"))
    model = classes["model"]
    prepared_p50 = Decimal(classes["prepared_switch"]["latency_seconds"]["p50"])

    variants = [("prepared_switch", None, prepared_p50, Decimal(0))]
    if classes["cold_switch"].get("status") == "MEASURED_LOWER_BOUND":
        prep_s = Decimal(classes["cold_switch"]["prep_seconds"])
        traffic_gib = Decimal(classes["cold_switch"]["prep_traffic_gib"])
        prepared_p50_cold = Decimal(
            classes["prepared_switch"]["latency_seconds"]["p50"])
        for reuse in ctx.prep_reuse_grid:
            s = Decimal(reuse)
            variants.append((
                "cold_switch", reuse,
                (prep_s / s + prepared_p50_cold),
                traffic_gib / s))

    rows = []
    for cls, reuse, gpu_seconds, traffic_gib in variants:
        for offer, hourly in (("preemptible", ctx.pre),
                              ("on_demand", ctx.od)):
            gpu_usd = lib.gpu_seconds_cost(gpu_seconds, hourly)
            capture_usd = (lib.gpu_seconds_cost(capture_s, hourly)
                           / Decimal(CAPTURE_AMORT_HEADLINE_R)).quantize(
                               lib.CENT6)
            traffic_billed = (traffic_gib * ctx.egress).quantize(lib.CENT6)
            for demand in ctx.demand_grid:
                d = Decimal(demand)
                fixed_share = (ctx.fixed_month / d).quantize(lib.CENT6)
                nominal = (gpu_usd + capture_usd + traffic_billed
                           + fixed_share).quantize(lib.CENT6)
                pessimistic = ((gpu_usd * ctx.pess) + capture_usd
                               + traffic_billed + fixed_share).quantize(
                                   lib.CENT6)
                monthly = (nominal * d).quantize(Decimal("0.01"))
                rows.append({
                    "model": model,
                    "cost_class": cls,
                    "prep_reuse": reuse,
                    "offer": offer,
                    "requests_per_month": demand,
                    "components_usd": {
                        "gpu_switch_p50": str(gpu_usd),
                        "capture_amortized_r100": str(capture_usd),
                        "prep_traffic_egress_billed": str(traffic_billed),
                        "fixed_sfs_controller_share": str(fixed_share),
                    },
                    "per_success_usd_nominal": str(nominal),
                    "per_success_usd_pessimistic": str(pessimistic),
                    "monthly_usd_nominal": str(monthly),
                    "one_warm_gpu_plus_fixed_monthly_usd": str(
                        (ctx.warm_month + ctx.fixed_month).quantize(
                            Decimal("0.01"))),
                    "cheaper_than_one_warm_gpu": bool(
                        monthly < ctx.warm_month + ctx.fixed_month),
                })
    return rows


# --------------------------------------------------------------------------
# Preemption / fallback / regional-loss sweeps
# --------------------------------------------------------------------------

def preemption_sweep(ctx: Ctx, classes_list: list[dict]) -> dict:
    points = []
    for classes in classes_list:
        p95 = Decimal(classes["prepared_switch"]["latency_seconds"]["p95"])
        for p in ctx.loss_grid:
            pre_only = lib.expected_cost_per_success(
                lib.gpu_seconds_cost(p95, ctx.pre), p)
            fallback = lib.fallback_blend_cost(p95, ctx.pre, ctx.od, p)
            points.append({
                "model": classes["model"],
                "cost_class": "prepared_switch",
                "loss_probability": str(p),
                "preemptible_only_usd_per_success": str(pre_only),
                "fallback_pre_then_od_usd_per_success": str(fallback),
                "on_demand_usd_per_success": str(
                    lib.gpu_seconds_cost(p95, ctx.od)),
                "expected_extra_latency_seconds": str(
                    (p * p95).quantize(Decimal("0.000001"))),
            })
    return {
        "grid_assumption": "preemption_loss_probability_grid",
        "fallback_model": ("one preemptible attempt, then one on-demand "
                           "attempt (on_demand_loss_negligible assumption); "
                           "expected extra latency = p * attempt p95"),
        "breakeven_loss_probability": {
            "gpu-h100-sxm": str(lib.preemption_breakeven(ctx.pre, ctx.od)),
            "gpu-h200-sxm": str(lib.preemption_breakeven(
                ctx.inputs.unit_price("nebius-h200-1g-pre"),
                ctx.inputs.unit_price("nebius-h200-1g-od"))),
            "gpu-b200-sxm": str(lib.preemption_breakeven(
                ctx.inputs.unit_price("nebius-b200-1g-pre"),
                ctx.inputs.unit_price("nebius-b200-1g-od"))),
        },
        "points": points,
    }


def regional_loss_options(ctx: Ctx) -> dict:
    inputs = ctx.inputs
    prep = inputs.measured_entry("boltz2-pret0-cache-read")
    reloc_gib = ((Decimal(prep["cache_bytes"])
                  + Decimal(prep["artifact_bytes"])) / GIB).quantize(
                      Decimal("0.000001"))
    reloc_billed = (reloc_gib * ctx.egress).quantize(lib.CENT6)

    def level(region, platform, gpus, offer):
        try:
            rows = inputs.availability_rows(region, platform, gpus)
        except lib.InputError:
            return "NOT_IN_SNAPSHOT"
        levels = sorted({r["offers"].get(offer, {}).get(
            "availability_level", "ABSENT") for r in rows})
        return ",".join(levels)

    options = [
        {"option": "same-region on-demand H100",
         "price_record": "nebius-h100-1g-od",
         "usd_per_hour": str(ctx.od),
         "availability_at_capture": level(
             "eu-north1", "gpu-h100-sxm", 1, "on_demand"),
         "relocalization": "none (same nodes/storage)"},
        {"option": "same-region H200 preemptible",
         "price_record": "nebius-h200-1g-pre",
         "usd_per_hour": str(inputs.unit_price("nebius-h200-1g-pre")),
         "availability_at_capture": level(
             "eu-north1", "gpu-h200-sxm", 1, "preemptible"),
         "relocalization": "same region; storage reattach, no cross-region "
                           "artifact transfer"},
        {"option": "cross-region B200 preemptible (us-central1)",
         "price_record": "nebius-b200-1g-pre",
         "usd_per_hour": str(inputs.unit_price("nebius-b200-1g-pre")),
         "availability_at_capture": level(
             "us-central1", "gpu-b200-sxm", 1, "preemptible"),
         "relocalization": f"measured Boltz2 artifact+cache {reloc_gib} GiB; "
                           f"egress-billed {reloc_billed} USD, egress-free "
                           f"0 USD, per node"},
    ]
    return {
        "scenario": ("eu-north1 preemptible H100 pool unavailable "
                     "(regional capacity loss); options priced from the "
                     "snapshot, availability from the capacity capture"),
        "latency": ("UNMEASURED for cross-region and cross-platform "
                    "fallbacks (cross_region_relocalization assumption); "
                    "these rows carry cost and capacity only"),
        "options": options,
    }


# --------------------------------------------------------------------------
# Simulation (placeholder-derived) repricing and curves
# --------------------------------------------------------------------------

def _sweep_curves(ctx: Ctx, reports: list[dict], axis: str) -> dict:
    curves: dict = {}
    for rep in reports:
        repriced = lib.reprice_simulator_report(
            rep, {"on_demand": ctx.od, "preemptible": ctx.pre}, ctx.egress)
        repriced["sweep_value"] = rep["sweep_value"]
        repriced["input_provenance"] = rep["input_provenance"]
        curves.setdefault(rep["trace_family"], []).append(repriced)
    best = {}
    for family, rows in sorted(curves.items()):
        rows.sort(key=lambda r: r["sweep_value"])
        p95s = [Decimal(str(r["latency_seconds"]["p95"])) for r in rows]
        floor = min(p95s)
        tolerance = floor * Decimal("1.02")
        chosen = next(r for r, p in zip(rows, p95s) if p <= tolerance)
        best[family] = {
            "smallest_value_within_2pct_of_best_p95": chosen["sweep_value"],
            "best_p95_seconds": str(floor),
            "cost_at_that_point_per_1000_pre_egress_billed":
                chosen["cost_usd"]["preemptible/egress_billed"]
                ["per_1000_completed"],
        }
    return {"axis": axis, "curves": curves, "knee": best}


def build(inputs: lib.Inputs) -> tuple[dict, str, str]:
    ctx = Ctx(inputs)
    h100_avail = inputs.availability_rows("eu-north1", "gpu-h100-sxm", 1)

    of2 = model_cost_classes(ctx, "of2-n20-fresh")
    boltz2 = model_cost_classes(ctx, "boltz2-n20-fresh")
    classes_list = [of2, boltz2]

    capture_s = Decimal(inputs.assumption("snapshot_capture_seconds_of2"))
    capture = {
        "assumption": "snapshot_capture_seconds_of2",
        "seconds": str(capture_s),
        "per_capture_usd": {
            "on_demand": str(lib.gpu_seconds_cost(capture_s, ctx.od)),
            "preemptible": str(lib.gpu_seconds_cost(capture_s, ctx.pre)),
        },
        "amortization": [{
            "restores_between_captures": r,
            "per_restore_usd_preemptible": str(
                (lib.gpu_seconds_cost(capture_s, ctx.pre) / Decimal(r))
                .quantize(lib.CENT6)),
            "per_restore_usd_on_demand": str(
                (lib.gpu_seconds_cost(capture_s, ctx.od) / Decimal(r))
                .quantize(lib.CENT6)),
        } for r in ctx.capture_r_grid],
        "notes": ("Per model-version capture, never on any request's "
                  "critical path; assumption-flagged because the raw log "
                  "lives on another branch."),
    }

    internal = {
        "status": "MEASURED",
        "gpu_platform": "gpu-h100-sxm 1gpu-16vcpu-200gb, eu-north1",
        "availability_at_capture": [
            {"fabric": r["fabric"], "offers": r["offers"]}
            for r in h100_avail],
        "cost_classes": classes_list,
        "snapshot_capture_cost": capture,
        "fixed_monthly_overheads_usd": {
            "sfs_4096gib_artifact_tier": str(
                inputs.monthly_price("nebius-sfs-4096gib")),
            "controller_cpu_d3_4vcpu_16gb": str(
                inputs.monthly_price("nebius-cpu-d3-4v16g-od")),
            "total": str(ctx.fixed_month),
            "notes": ("As-deployed measured-tier shapes: one 4 TiB "
                      "network_ssd SFS holding artifacts/caches and one "
                      "cpu-d3 controller node; included in every "
                      "fully-loaded row."),
        },
        "fully_loaded": (fully_loaded_rows(ctx, of2)
                         + fully_loaded_rows(ctx, boltz2)),
    }

    cere = inputs.unmeasured("cerebrium")
    cerebrium = {
        "status": cere["status"],
        "reason": cere["reason"],
        "dated_unit_prices": {
            "H100_usd_per_gpu_hour_equivalent": str(
                inputs.unit_price("cerebrium-h100-h")),
            "H200_usd_per_gpu_hour_equivalent": str(
                inputs.unit_price("cerebrium-h200-h")),
            "B200_usd_per_gpu_hour_equivalent": str(
                inputs.unit_price("cerebrium-b200-h")),
            "plan_standard_usd_per_month": str(
                inputs.unit_price("cerebrium-plan-standard")),
        },
        "per_request_cost_usd": None,
        "latency_seconds": None,
        "notes": ("Prices hash-bound to the archived payload. No per-request "
                  "cost is computable fail-closed until the sibling "
                  "benchmark produces measured request latency."),
    }
    nl = inputs.unmeasured("internal-node-local-vm")
    node_local = {
        "status": nl["status"], "reason": nl["reason"],
        "dated_unit_prices": {
            "h100_on_demand_usd_per_hour": str(ctx.od),
            "h100_preemptible_usd_per_hour": str(ctx.pre),
        },
        "per_request_cost_usd": None, "latency_seconds": None,
    }
    mo = inputs.unmeasured("modal")
    modal = {
        "status": mo["status"], "reason": mo["reason"],
        "reference": "catalog-switch/capacity-cost/MODAL_APPENDIX.md",
        "per_request_cost_usd": None, "latency_seconds": None,
        "dated_unit_prices": None,
    }

    # Placeholder-derived simulation: legacy matrix + isolated sweeps.
    sim_doc = json.loads(
        (ROOT / inputs.simulation_entry("catalog-sim-reports")["file"])
        .read_text())
    gpu_hourly = {"on_demand": ctx.od, "preemptible": ctx.pre}
    legacy = []
    for r in sim_doc["reports"]:
        rep = lib.reprice_simulator_report(r, gpu_hourly, ctx.egress)
        rep["input_provenance"] = (
            "placeholder-derived simulation (provenance:placeholder MTBF/"
            "bandwidth/cache/drain/reprovision inputs); low/base/high move "
            "all placeholders together; prices replaced with sourced quotes")
        legacy.append(rep)
    legacy.sort(key=lambda r: (r["trace_family"], r["sensitivity"],
                               r["policy"]))

    sweeps_doc = json.loads(
        (ROOT / inputs.simulation_entry("capacity-cost-sweeps")["file"])
        .read_text())
    k_curves = _sweep_curves(ctx, sweeps_doc["k_sweep"], "warm_top_k")
    cache_curves = _sweep_curves(
        ctx, sweeps_doc["cache_sweep"], "l1_capacity_gib")

    # Break-even blocks (measured-anchored).
    warm_rows = []
    for classes in classes_list:
        p95 = Decimal(classes["prepared_switch"]["latency_seconds"]["p95"])
        for offer, hourly in (("preemptible", ctx.pre),
                              ("on_demand", ctx.od)):
            per_switch = lib.gpu_seconds_cost(p95, hourly)
            warm_rows.append({
                "model": classes["model"],
                "cost_class": "prepared_switch",
                "switch_offer": offer,
                "per_switch_usd_p95": str(per_switch),
                "warm_gpu_month_usd_on_demand": str(ctx.warm_month),
                "breakeven_requests_per_month": str(
                    lib.warm_breakeven_requests_per_month(
                        ctx.warm_month, per_switch)),
                "bound": ("upper bound: every request pays a full prepared "
                          "switch; cache hits lower it. Cold-switch "
                          "economics are in fully_loaded rows."),
            })

    storage_be = {
        "sfs_usd_per_gib_month": str(inputs.unit_price("nebius-sfs-gib-month")),
        "object_usd_per_gib_month": str(
            inputs.unit_price("nebius-list-object-volume")),
        "object_egress_usd_per_gib": str(ctx.egress),
        "egress_billed_breakeven_refetches_per_gib_month": str(
            lib.storage_breakeven_refetches_per_gib_month(
                inputs.unit_price("nebius-sfs-gib-month"),
                inputs.unit_price("nebius-list-object-volume"),
                ctx.egress)),
        "egress_free_variant": (
            "if intra-cloud object reads are not billed as egress, object "
            "storage dominates SFS on cost at any refetch rate and the "
            "decision is latency-only"),
    }

    warm_pool = [{
        "k_warm_gpus": k,
        "monthly_usd_on_demand": str(
            (ctx.warm_month * k + ctx.fixed_month).quantize(Decimal("0.01"))),
        "includes": "K warm H100 + 4 TiB SFS + controller",
        "simulated_counterpart": ("k_sweep curves at warm_top_k=%d "
                                  "(placeholder-derived)" % k),
    } for k in WARM_POOL_K]

    frontier = {
        "schema_version": "capacity-cost-frontier/v2",
        "as_of_date": inputs.price["as_of_date"],
        "generated_by": "catalog-switch/capacity-cost/costmodel/build_frontier.py",
        "statement": (
            "Corrected candidate. Prepared versus request-triggered cost "
            "classes with explicit amortization; measured and "
            "placeholder-derived provenance separated end to end; "
            "preemption/regional-loss/fallback sweeps consume their "
            "assumption grids; per-success and monthly totals include GPU, "
            "capture amortization, traffic, fixed SFS/controller, and retry "
            "sensitivity. Cerebrium stays PENDING_MEASUREMENT and Modal "
            "documentation-only. Every USD value traces to a dated record "
            "in inputs/price_snapshot.json (public records hash-bound to "
            "archived payloads) and every latency to a checksum-pinned "
            "measured artifact; cost is always paired with the latency and "
            "goodput of the same evidence."),
        "backends": {
            "internal-k8s-snapshot": internal,
            "internal-node-local-vm": node_local,
            "cerebrium": cerebrium,
            "modal": modal,
        },
        "sweeps": {
            "preemption": preemption_sweep(ctx, classes_list),
            "regional_loss": regional_loss_options(ctx),
        },
        "simulation_frontier": {
            "provenance": ("placeholder-derived simulation, never "
                           "measurement; capacity outputs re-priced with "
                           "sourced quotes, placeholder prices discarded"),
            "gpu_price_records": ["nebius-h100-1g-od", "nebius-h100-1g-pre"],
            "egress_price_record": "nebius-list-object-egress",
            "legacy_matrix": legacy,
            "top_k_sweep": k_curves,
            "cache_sweep": cache_curves,
        },
        "breakeven": {
            "warm_vs_switch": warm_rows,
            "storage_tier": storage_be,
            "warm_pool_monthly": warm_pool,
        },
    }
    return frontier, render_markdown(frontier), render_tsv(frontier)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_markdown(f: dict) -> str:
    internal = f["backends"]["internal-k8s-snapshot"]
    lines = [
        "# Capacity/cost frontier v2 (as of %s)" % f["as_of_date"],
        "",
        f["statement"],
        "",
        "## Measured cost classes (1x H100, eu-north1)",
        "",
        "| Model | Class | Status | p50 s | p95 s | ≤30s | cost p95 pre / od (USD) |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for m in internal["cost_classes"]:
        for cls in ("warm_hit", "prepared_switch", "cold_switch",
                    "node_provision_miss"):
            c = m[cls]
            if c["status"].startswith("PENDING"):
                lines.append("| %s | %s | %s | — | — | — | — |" % (
                    m["model"], cls, c["status"]))
                continue
            if cls == "cold_switch":
                lat = c["triggering_request_latency_seconds_p95"]
                worst = c["amortization"][0]["per_request_cost_usd"]
                lines.append(
                    "| %s | %s (reuse=1) | %s | — | %s | — | %s / %s |" % (
                        m["model"], cls, c["status"], lat[:9],
                        worst["preemptible"]["gpu_usd"],
                        worst["on_demand"]["gpu_usd"]))
                continue
            cost = (c["per_request_cost_usd"]["p95"]
                    if cls == "prepared_switch"
                    else c["per_request_cost_usd"])
            lines.append("| %s | %s | %s | %s | %s | %s | %s / %s |" % (
                m["model"], cls, c["status"],
                c["latency_seconds"]["p50"][:9],
                c["latency_seconds"]["p95"][:9],
                c["slo_goodput"]["within_30s"],
                cost["preemptible"]["gpu_usd"],
                cost["on_demand"]["gpu_usd"]))
    boltz_cold = internal["cost_classes"][1]["cold_switch"]
    lines += [
        "",
        "Boltz2 cold switch is a measured LOWER BOUND: %s s preparation + "
        "%s s p95 switch = %sx the prepared-switch cost at reuse=1; the "
        "amortization grid (reuse 1/2/5/10/50) is in frontier.json." % (
            boltz_cold["prep_seconds"],
            internal["cost_classes"][1]["prepared_switch"]
            ["latency_seconds"]["p95"],
            boltz_cold["understatement_vs_prepared"]),
        "OpenFold2 cold switch and all node-provision-miss rows are "
        "fail-closed PENDING_MEASUREMENT.",
        "",
        "## Fully-loaded per-success cost (sample: 100k req/month, "
        "preemptible, nominal)",
        "",
        "| Model | Class | GPU p50 | Capture(R=100) | Traffic | Fixed share | Total | Monthly |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in internal["fully_loaded"]:
        if (row["requests_per_month"] != 100000
                or row["offer"] != "preemptible"
                or (row["cost_class"] == "cold_switch"
                    and row["prep_reuse"] not in (1, 10))):
            continue
        label = row["cost_class"] + (
            f" (reuse={row['prep_reuse']})" if row["prep_reuse"] else "")
        comp = row["components_usd"]
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["model"], label, comp["gpu_switch_p50"],
            comp["capture_amortized_r100"],
            comp["prep_traffic_egress_billed"],
            comp["fixed_sfs_controller_share"],
            row["per_success_usd_nominal"], row["monthly_usd_nominal"]))
    pe = f["sweeps"]["preemption"]
    lines += [
        "",
        "Retry sensitivity: pessimistic totals apply the rule-of-three "
        "x1.176 bound to the GPU components (full grid in frontier.json).",
        "",
        "## Preemption / fallback sweep (prepared switch, per success)",
        "",
        "Break-even loss probability: " + ", ".join(
            "%s %s" % (k, v) for k, v in sorted(
                pe["breakeven_loss_probability"].items())),
        "",
        "| Model | p(loss) | Preemptible-only | Pre-then-OD fallback | On-demand |",
        "|---|---:|---:|---:|---:|",
    ]
    for pt in pe["points"]:
        if pt["loss_probability"] not in ("0.00", "0.10", "0.30",
                                          "0.44155844"):
            continue
        lines.append("| %s | %s | %s | %s | %s |" % (
            pt["model"], pt["loss_probability"],
            pt["preemptible_only_usd_per_success"],
            pt["fallback_pre_then_od_usd_per_success"],
            pt["on_demand_usd_per_success"]))
    rl = f["sweeps"]["regional_loss"]
    lines += [
        "",
        "## Regional capacity loss fallbacks (%s)" % rl["scenario"],
        "",
        "| Option | USD/h | Availability at capture | Relocalization |",
        "|---|---:|---|---|",
    ]
    for opt in rl["options"]:
        lines.append("| %s | %s | %s | %s |" % (
            opt["option"], opt["usd_per_hour"],
            opt["availability_at_capture"], opt["relocalization"]))
    lines += [
        "",
        rl["latency"] + ".",
        "",
        "## Isolated top-K and cache curves (placeholder-derived simulation)",
        "",
        "Each sweep varies exactly one axis at base placeholders on the "
        "committed traces (checksums asserted). Zipf family shown; all five "
        "families are in frontier.json.",
        "",
        "| Axis | Value | p95 s | ≤60s goodput | USD/1k (pre, egress-billed) |",
        "|---|---:|---:|---:|---:|",
    ]
    for block in (f["simulation_frontier"]["top_k_sweep"],
                  f["simulation_frontier"]["cache_sweep"]):
        for row in block["curves"]["zipf"]:
            lines.append("| %s | %s | %.1f | %.3f | %s |" % (
                block["axis"], row["sweep_value"],
                row["latency_seconds"]["p95"],
                row["slo_goodput"]["within_60s"],
                row["cost_usd"]["preemptible/egress_billed"]
                ["per_1000_completed"][:8]))
    lines += [
        "",
        "Knees (smallest value within 2% of best p95 per family): " +
        "; ".join(
            "%s: K=%s" % (fam, k["smallest_value_within_2pct_of_best_p95"])
            for fam, k in sorted(
                f["simulation_frontier"]["top_k_sweep"]["knee"].items())) +
        " | cache: " + "; ".join(
            "%s: %s GiB" % (fam, k["smallest_value_within_2pct_of_best_p95"])
            for fam, k in sorted(
                f["simulation_frontier"]["cache_sweep"]["knee"].items())),
        "",
        "## Unmeasured backends (fail-closed)",
        "",
        "| Backend | Status |",
        "|---|---|",
        "| Cerebrium | %s |" % f["backends"]["cerebrium"]["status"],
        "| Node-local VM | %s |" % (
            f["backends"]["internal-node-local-vm"]["status"]),
        "| Modal | %s |" % f["backends"]["modal"]["status"],
        "",
        "Storage: SFS %s vs object %s USD/GiB-month; egress-billed "
        "break-even %s refetches/GiB-month." % (
            f["breakeven"]["storage_tier"]["sfs_usd_per_gib_month"],
            f["breakeven"]["storage_tier"]["object_usd_per_gib_month"],
            f["breakeven"]["storage_tier"]
            ["egress_billed_breakeven_refetches_per_gib_month"]),
        "",
        "Full detail: `frontier.json`; grid tables: `breakeven.tsv`; "
        "isolated sweep raw points: `sweeps.json`.",
        "",
    ]
    return "\n".join(lines)


def render_tsv(f: dict) -> str:
    internal = f["backends"]["internal-k8s-snapshot"]
    rows = ["table\tmodel\tclass_or_axis\tkey\tusd\tcomparator_usd\tflag"]
    for r in f["breakeven"]["warm_vs_switch"]:
        rows.append("warm_vs_switch\t%s\t%s\tbreakeven=%s\t%s\t%s\t-" % (
            r["model"], r["switch_offer"],
            r["breakeven_requests_per_month"], r["per_switch_usd_p95"],
            r["warm_gpu_month_usd_on_demand"]))
    for r in internal["fully_loaded"]:
        key = "D=%s,offer=%s,reuse=%s" % (
            r["requests_per_month"], r["offer"], r["prep_reuse"])
        rows.append("fully_loaded\t%s\t%s\t%s\t%s\t%s\t%s" % (
            r["model"], r["cost_class"], key, r["per_success_usd_nominal"],
            r["monthly_usd_nominal"],
            "cheaper_than_warm" if r["cheaper_than_one_warm_gpu"]
            else "warm_cheaper"))
    for pt in f["sweeps"]["preemption"]["points"]:
        rows.append("preemption_sweep\t%s\tp=%s\tpre_only\t%s\t%s\t-" % (
            pt["model"], pt["loss_probability"],
            pt["preemptible_only_usd_per_success"],
            pt["fallback_pre_then_od_usd_per_success"]))
    for block in (f["simulation_frontier"]["top_k_sweep"],
                  f["simulation_frontier"]["cache_sweep"]):
        for family, curve in sorted(block["curves"].items()):
            for row in curve:
                rows.append(
                    "%s\t%s\t%s\tp95=%s\t%s\t%s\tplaceholder-derived" % (
                        block["axis"], family, row["sweep_value"],
                        row["latency_seconds"]["p95"],
                        row["cost_usd"]["preemptible/egress_billed"]
                        ["per_1000_completed"],
                        row["cost_usd"]["on_demand/egress_billed"]
                        ["per_1000_completed"]))
    for r in f["breakeven"]["warm_pool_monthly"]:
        rows.append("warm_pool_monthly\t-\tk=%d\t-\t%s\t-\t-" % (
            r["k_warm_gpus"], r["monthly_usd_on_demand"]))
    return "\n".join(rows) + "\n"


def main() -> int:
    inputs = lib.Inputs(ROOT)
    frontier, md, tsv = build(inputs)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "frontier.json").write_text(
        json.dumps(frontier, indent=2, sort_keys=True) + "\n")
    (RESULTS / "FRONTIER.md").write_text(md)
    (RESULTS / "breakeven.tsv").write_text(tsv)
    print("backends:", len(frontier["backends"]))
    print("legacy repriced:",
          len(frontier["simulation_frontier"]["legacy_matrix"]))
    print("fully-loaded rows:",
          len(frontier["backends"]["internal-k8s-snapshot"]["fully_loaded"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
