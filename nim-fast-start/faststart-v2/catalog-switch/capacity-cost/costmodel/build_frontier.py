#!/usr/bin/env python3
"""Build the measured capacity/cost frontier (corrected candidate, v7).

Reads the committed snapshots and checksum-pinned artifacts, consumes the
isolated top-K/cache sweeps and the legacy simulator matrix as
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
  measured lower bound for Boltz2 (422.854590 s local cache full read),
  amortized over the prep_reuse_grid; fail-closed PENDING_MEASUREMENT for
  OpenFold2. Unmeasured relocation (moving the measured bytes from object
  storage) is kept in a separate add-on block, never blended into the
  measured lower-bound timing.
- ``node_provision_miss``: declared, fail-closed PENDING_MEASUREMENT.

Model-scoped inputs stay model-scoped: the OpenFold2-only capture-time
assumption is applied to OpenFold2 alone; Boltz2 capture cost is UNAVAILABLE
and fails closed. Completeness contract: cost rows are published in two
disjoint collections — ``complete_cost_totals`` (every required component
available and idle capacity allocated) and
``incomplete_lower_bound_subtotals`` (anything else). An incomplete row
carries null complete totals and null decision fields; its numbers exist
only under explicit measured-anchored LOWER-BOUND SUBTOTAL names, on which
ranking and break-even decisions are forbidden. No incomplete subtotal ever
appears under a complete/total-sounding label.
All composite arithmetic is exact (28-digit Decimal context) with a single
quantization at emission; monthly totals are computed from unrounded
per-success values.

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
CENT2 = Decimal("0.01")


def ceil_pos(value: Decimal) -> int:
    """Ceiling of a positive Decimal ratio (Decimal // truncates toward
    zero, so the -(-a//b) idiom is NOT a ceiling for Decimals)."""
    whole = int(value)
    return whole if value == whole else whole + 1


def q6(value: Decimal) -> str:
    return str(value.quantize(lib.CENT6))


def q2(value: Decimal) -> str:
    return str(value.quantize(CENT2))


def _stats(values: list[Decimal]) -> dict:
    values = sorted(values)
    return {
        "p50": str(lib.nearest_rank(values, 50)),
        "p95": str(lib.nearest_rank(values, 95)),
        "p99": str(lib.nearest_rank(values, 99)),
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
        exact = lib.gpu_seconds_cost_exact(seconds, hourly)
        out[offer] = {
            "gpu_usd": q6(exact),
            "gpu_usd_pessimistic": q6(exact * pess),
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
        capture = next(a for a in inputs.measured["assumptions"]
                       if a["name"] == "snapshot_capture_seconds_of2")
        self.capture_seconds = Decimal(capture["value"])
        self.capture_model = capture["applies_to_model"]
        self.l1_disk_rates = {
            "network_ssd": inputs.unit_price("nebius-disk-nssd-gib-hour"),
            "network_ssd_non_replicated": inputs.unit_price(
                "nebius-disk-nrd-gib-hour"),
        }
        # Conservative capacity gate: the largest quota-clipped 'available'
        # count on any single eu-north1 H100 fabric at capture time (a node
        # group lives in one fabric, so counts are not summed across them).
        self.h100_max_available = {}
        for row in inputs.availability_rows("eu-north1", "gpu-h100-sxm", 1):
            for offer in ("on_demand", "preemptible"):
                avail = row["offers"][offer].get("available")
                if avail is None:
                    continue
                self.h100_max_available[offer] = max(
                    self.h100_max_available.get(offer, 0), avail)


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
            stat: _gpu_costs(
                Decimal(_stats(switch_vals)[stat]), ctx.od, ctx.pre, ctx.pess)
            for stat in ("p50", "p95")},
        "notes": ("Request-triggered switch on a prepared node (image "
                  "resident, storage attached, pre-T0 preparation already "
                  "done). GPU critical path T0 through second semantic "
                  "response; pessimistic = rule-of-three retry bound from "
                  "the measured 0/20 denominator."),
    }

    if entry["model"] == "Boltz2":
        prep = inputs.measured_entry("boltz2-pret0-cache-read")
        prep_s = Decimal(prep["value_seconds"])
        prep_traffic_gib_exact = lib.bytes_to_gib_exact(
            prep["cache_bytes"] + prep["artifact_bytes"])
        rows = []
        for reuse in ctx.prep_reuse_grid:
            amortized_seconds = prep_s / Decimal(reuse) + switch_p95
            rows.append({
                "prep_reuse": reuse,
                "amortized_gpu_seconds_p95": q6(amortized_seconds),
                "per_request_cost_usd": _gpu_costs(
                    amortized_seconds, ctx.od, ctx.pre, ctx.pess),
            })
        cold = {
            "status": "MEASURED_LOWER_BOUND",
            "evidence": "boltz2-pret0-cache-read + " + entry_id,
            "prep_seconds": str(prep_s),
            "understatement_vs_prepared": str(
                ((prep_s + switch_p95) / switch_p95).quantize(
                    Decimal("0.001"))),
            "triggering_request_latency_seconds_p95": q6(prep_s + switch_p95),
            "amortization": rows,
            "unmeasured_relocation": {
                "provenance": ("UNMEASURED scenario, kept separate from the "
                               "measured lower-bound timing above: the "
                               "measured preparation read the bytes from "
                               "attached SFS, not from object storage. If "
                               "the bytes must first move from object "
                               "storage, this add-on prices the measured "
                               "byte counts; its duration is unmeasured."),
                "traffic_gib": q6(prep_traffic_gib_exact),
                "traffic_bytes": prep["cache_bytes"] + prep["artifact_bytes"],
                "per_preparation_usd": {
                    "egress_billed": q6(prep_traffic_gib_exact * ctx.egress),
                    "egress_free": "0.000000",
                },
            },
            "notes": ("Lower bound: measured 422.854590 s pre-T0 cache full "
                      "read from attached SFS; the M3 artifact is read "
                      "O_DIRECT inside the T0 window (already charged) and "
                      "image pull is excluded because residency was proven "
                      "pre-T0. prep_reuse=1 is the fully request-triggered "
                      "worst case; larger reuse amortizes one preparation "
                      "over later switches, whose own latency is the "
                      "prepared_switch class."),
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
# Complete cost totals and incomplete lower-bound subtotals
# --------------------------------------------------------------------------

def cost_total_rows(ctx: Ctx, classes: dict) -> list[dict]:
    """Per-success and monthly totals across the demand grid, under two
    explicit capacity models.

    ``dedicated_prepared_node``: prepared capacity is held as whole
    dedicated H100 instance(s); idle and reserved GPU time is fully
    allocated (nodes_required = ceil(busy-seconds / node-month), whole
    monthly instance quotes charged, utilization emitted). COMPLETE only
    when every component is available (Boltz2 capture is not, so its
    dedicated rows are lower-bound subtotals).

    ``marginal_zero_idle_bound``: charges only measured request/prep GPU
    seconds plus fixed overheads — the perfect-sharing, zero-idle floor. It
    is ALWAYS an INCOMPLETE_LOWER_BOUND because idle/reserved GPU capacity
    is unallocated by construction (missing component
    ``idle_reserved_gpu_capacity_share``); ranking and break-even decisions
    are forbidden on it. Shared-pool allocation with real contention lives
    in simulation_frontier, is placeholder-derived, and charges reserved
    GPU-hours in full there.

    All arithmetic exact; every emitted number quantized exactly once;
    monthly totals computed from unrounded values.
    """
    model = classes["model"]
    prepared_p50 = Decimal(classes["prepared_switch"]["latency_seconds"]["p50"])
    capture_available = model == ctx.capture_model
    prepared = classes["prepared_switch"]
    paired_evidence_base = {
        "evidence": prepared["evidence"],
        "n": prepared["n"],
        "failed_attempt_denominator": prepared["failed_attempt_denominator"],
        "latency_seconds": prepared["latency_seconds"],
        "slo_goodput": prepared["slo_goodput"],
        "notes": ("Cost rows pair with the prepared_switch cohort whose "
                  "per-request duration also sizes busy GPU seconds "
                  "(conservative: a pinned node answering warm hits is "
                  "faster, so node counts and utilization are upper "
                  "bounds). p99 at n=20 is the nearest-rank maximum. "
                  "Errors: the measured 0/20 failed-attempt denominator."),
    }
    month_hours = Decimal(730)
    month_seconds = month_hours * Decimal(3600)
    cap_pre_exact = lib.gpu_seconds_cost_exact(ctx.capture_seconds, ctx.pre)
    cap_od_exact = lib.gpu_seconds_cost_exact(ctx.capture_seconds, ctx.od)
    capture_status = ("APPLIED" if capture_available else
                      "UNAVAILABLE: the snapshot_capture_seconds_of2 "
                      "assumption applies to %s only; no %s capture "
                      "duration exists in this program, so capture cost is "
                      "excluded rather than borrowed." % (ctx.capture_model,
                                                          model))

    def lower_bound_block(nominal, pessimistic, d, missing):
        return {
            "per_success_usd_nominal": None,
            "per_success_usd_pessimistic": None,
            "monthly_usd_nominal": None,
            "monthly_usd_pessimistic": None,
            "lower_bound_subtotals_usd": {
                "per_success_nominal": q6(nominal),
                "per_success_pessimistic": q6(pessimistic),
                "monthly_nominal": q2(nominal * d),
                "monthly_pessimistic": q2(pessimistic * d),
            },
            "decision_policy": (
                "measured-anchored LOWER-BOUND SUBTOTALS only: the true "
                "total is >= these values because %s unavailable/"
                "unallocated; ranking and break-even decisions are "
                "FORBIDDEN on them." % ", ".join(missing)),
        }

    rows = []

    # --- capacity model A: dedicated prepared node(s), idle allocated ----
    monthly_by_offer = {
        "preemptible": ctx.inputs.monthly_price("nebius-h100-1g-pre"),
        "on_demand": ctx.inputs.monthly_price("nebius-h100-1g-od"),
    }
    capture_r_axis = ctx.capture_r_grid if capture_available else [None]
    for offer in ("preemptible", "on_demand"):
        inst_month = monthly_by_offer[offer]
        cap_exact_full = (cap_pre_exact if offer == "preemptible"
                          else cap_od_exact)
        for r_value in capture_r_axis:
            cap_per_restore = (cap_exact_full / Decimal(r_value)
                               if r_value is not None else Decimal(0))
            for demand in ctx.demand_grid:
                d = Decimal(demand)
                busy_seconds = d * prepared_p50
                nodes = max(ceil_pos(busy_seconds / month_seconds), 1)
                utilization = busy_seconds / (Decimal(nodes) * month_seconds)
                monthly_exact = (Decimal(nodes) * inst_month
                                 + ctx.fixed_month + cap_per_restore * d)
                per_success_exact = monthly_exact / d
                # Retry pessimism adds busy seconds, not idle: the
                # pessimistic view re-evaluates node count and utilization
                # under the rule-of-three attempt bound.
                busy_pess = busy_seconds * ctx.pess
                nodes_pess = max(ceil_pos(busy_pess / month_seconds), 1)
                monthly_pess = (Decimal(nodes_pess) * inst_month
                                + ctx.fixed_month + cap_per_restore * d)
                per_success_pess = monthly_pess / d
                missing = [] if capture_available else ["capture_amortized"]
                max_avail = ctx.h100_max_available[offer]
                feasible = max(nodes, nodes_pess) <= max_avail
                if not feasible:
                    missing = missing + ["capacity_availability_at_capture"]
                row_complete = capture_available and feasible
                row = {
                    "model": model,
                    "capacity_model": "dedicated_prepared_node",
                    "cost_class": "pinned_dedicated",
                    "prep_reuse": None,
                    "offer": offer,
                    "restores_between_captures": r_value,
                    "capture_status": capture_status,
                    "completeness": ("COMPLETE" if row_complete
                                     else "INCOMPLETE_LOWER_BOUND"),
                    "missing_components": missing,
                    "requests_per_month": demand,
                    "nodes_required": nodes,
                    "nodes_required_pessimistic": nodes_pess,
                    "capacity_feasibility": {
                        "status": ("FEASIBLE_AT_CAPTURE" if feasible
                                   else "EXCEEDS_CAPTURED_AVAILABILITY"),
                        "offer": offer,
                        "max_single_fabric_available_at_capture": max_avail,
                        "gate": "max(nodes_required, "
                                "nodes_required_pessimistic) <= available",
                        "aggregation": ("conservative: largest single-fabric "
                                        "quota-clipped 'available' from the "
                                        "capacity snapshot; fabrics are not "
                                        "summed"),
                    },
                    "reserved_gpu_hours_month": str(
                        Decimal(nodes) * month_hours),
                    "utilization_busy_fraction": q6(utilization),
                    "paired_evidence": paired_evidence_base,
                    "components_usd": {
                        "dedicated_instances_monthly": q2(
                            Decimal(nodes) * inst_month),
                        "capture_amortized_monthly": (
                            q2(cap_per_restore * d)
                            if capture_available else None),
                        "fixed_sfs_controller_monthly": q2(ctx.fixed_month),
                    },
                    "retention_note": (
                        "preemptible retention of a 24/7 dedicated node is "
                        "subject to preemption; see the preemption sweep "
                        "and availability_at_capture"
                        if offer == "preemptible" else ""),
                }
                if row_complete:
                    row.update({
                        "per_success_usd_nominal": q6(per_success_exact),
                        "per_success_usd_pessimistic": q6(per_success_pess),
                        "monthly_usd_nominal": q2(monthly_exact),
                        "monthly_usd_pessimistic": q2(monthly_pess),
                    })
                else:
                    row.update({
                        "per_success_usd_nominal": None,
                        "per_success_usd_pessimistic": None,
                        "monthly_usd_nominal": None,
                        "monthly_usd_pessimistic": None,
                        "lower_bound_subtotals_usd": {
                            "per_success_nominal": q6(per_success_exact),
                            "per_success_pessimistic": q6(per_success_pess),
                            "monthly_nominal": q2(monthly_exact),
                            "monthly_pessimistic": q2(monthly_pess),
                        },
                        "decision_policy": (
                            "measured-anchored LOWER-BOUND SUBTOTALS only: "
                            "the true total is >= these values because %s "
                            "unavailable/unsupported (a plan exceeding "
                            "captured availability must source capacity "
                            "elsewhere at >= this cost); ranking and "
                            "break-even decisions are FORBIDDEN on them."
                            % ", ".join(missing)),
                    })
                rows.append(row)

    # --- capacity model B: marginal zero-idle sharing bound --------------
    variants = [("prepared_switch", None, prepared_p50, Decimal(0))]
    if classes["cold_switch"].get("status") == "MEASURED_LOWER_BOUND":
        prep_s = Decimal(classes["cold_switch"]["prep_seconds"])
        # Recompute exact GiB from the measured byte count; never consume
        # the display-quantized traffic_gib string in arithmetic.
        traffic_gib_exact = lib.bytes_to_gib_exact(
            classes["cold_switch"]["unmeasured_relocation"]["traffic_bytes"])
        for reuse in ctx.prep_reuse_grid:
            s = Decimal(reuse)
            variants.append(("cold_switch", reuse,
                             prep_s / s + prepared_p50,
                             traffic_gib_exact / s))

    for cls, reuse, gpu_seconds, addon_traffic_gib in variants:
        for offer, hourly in (("preemptible", ctx.pre),
                              ("on_demand", ctx.od)):
            gpu_exact = lib.gpu_seconds_cost_exact(gpu_seconds, hourly)
            for r_value in capture_r_axis:
                cap_exact = (Decimal(0) if r_value is None
                             else ((cap_pre_exact if offer == "preemptible"
                                    else cap_od_exact) / Decimal(r_value)))
                addon_exact = addon_traffic_gib * ctx.egress
                missing = ["idle_reserved_gpu_capacity_share"]
                if not capture_available:
                    missing = missing + ["capture_amortized"]
                for demand in ctx.demand_grid:
                    d = Decimal(demand)
                    fixed_exact = ctx.fixed_month / d
                    nominal = gpu_exact + cap_exact + fixed_exact
                    pessimistic = (gpu_exact * ctx.pess + cap_exact
                                   + fixed_exact)
                    row = {
                        "model": model,
                        "capacity_model": "marginal_zero_idle_bound",
                        "cost_class": cls,
                        "prep_reuse": reuse,
                        "offer": offer,
                        "restores_between_captures": r_value,
                        "capture_status": capture_status,
                        "completeness": "INCOMPLETE_LOWER_BOUND",
                        "missing_components": missing,
                        "requests_per_month": demand,
                        "paired_evidence": (
                            paired_evidence_base if cls != "cold_switch"
                            else {**paired_evidence_base,
                                  "cold_trigger_latency_seconds_p95":
                                      classes["cold_switch"]
                                      ["triggering_request_latency_"
                                       "seconds_p95"]}),
                        "components_usd": {
                            "gpu_switch_p50": q6(gpu_exact),
                            "capture_amortized": (
                                q6(cap_exact) if r_value is not None
                                else None),
                            "fixed_sfs_controller_share": q6(fixed_exact),
                        },
                    }
                    row.update(lower_bound_block(
                        nominal, pessimistic, d, missing))
                    if cls == "cold_switch":
                        row["unmeasured_relocation_addon"] = {
                            "per_success_usd": {
                                "egress_billed": q6(addon_exact),
                                "egress_free": "0.000000",
                            },
                            "per_success_lower_bound_with_addon": {
                                "nominal": {
                                    "egress_billed": q6(
                                        nominal + addon_exact),
                                    "egress_free": q6(nominal),
                                },
                                "pessimistic": {
                                    "egress_billed": q6(
                                        pessimistic + addon_exact),
                                    "egress_free": q6(pessimistic),
                                },
                            },
                            "monthly_lower_bound_with_addon": {
                                "nominal": {
                                    "egress_billed": q2(
                                        (nominal + addon_exact) * d),
                                    "egress_free": q2(nominal * d),
                                },
                                "pessimistic": {
                                    "egress_billed": q2(
                                        (pessimistic + addon_exact) * d),
                                    "egress_free": q2(pessimistic * d),
                                },
                            },
                            "provenance": ("unmeasured relocation scenario; "
                                           "see cold_switch."
                                           "unmeasured_relocation"),
                        }
                    rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Preemption / fallback / regional-loss sweeps
# --------------------------------------------------------------------------

def preemption_sweep(ctx: Ctx, classes_list: list[dict]) -> dict:
    points = []
    for classes in classes_list:
        p95 = Decimal(classes["prepared_switch"]["latency_seconds"]["p95"])
        for p in ctx.loss_grid:
            # Strategy selection happens on EXACT values: near the
            # break-even probability the strategies differ only below the
            # display precision, so a post-quantization min ties and picks
            # the wrong strategy. Emission quantizes each field once, after
            # selection. Exact ties (e.g. p=0) break deterministically by
            # sorted strategy name.
            exact = {
                "preemptible_only": lib.preemptible_expected_cost_exact(
                    p95, ctx.pre, p),
                "fallback_pre_then_od": lib.fallback_blend_cost_exact(
                    p95, ctx.pre, ctx.od, p),
                "on_demand_only": lib.gpu_seconds_cost_exact(p95, ctx.od),
            }
            floor_value = min(exact.values())
            winners = sorted(k for k, v in exact.items()
                             if v == floor_value)
            points.append({
                "model": classes["model"],
                "cost_class": "prepared_switch",
                "loss_probability": str(p),
                "preemptible_only_usd_per_success": q6(
                    exact["preemptible_only"]),
                "fallback_pre_then_od_usd_per_success": q6(
                    exact["fallback_pre_then_od"]),
                "on_demand_usd_per_success": q6(exact["on_demand_only"]),
                "cheapest_strategies": winners,
                "expected_extra_latency_seconds": q6(p * p95),
            })
    return {
        "grid_assumption": "preemption_loss_probability_grid",
        "fallback_model": (
            "one preemptible attempt, then one on-demand attempt "
            "(on_demand_loss_negligible assumption); expected extra latency "
            "= p * attempt p95. The fallback is cheaper than on-demand-only "
            "ONLY below the platform break-even p* = 1 - pre/od; above p* "
            "(e.g. p=0.60 on H100) on-demand-only is the cheapest strategy "
            "and the fallback's remaining value is bounding latency to one "
            "extra attempt."),
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
    reloc_gib_exact = lib.bytes_to_gib_exact(
        prep["cache_bytes"] + prep["artifact_bytes"])
    reloc_gib = q6(reloc_gib_exact)
    reloc_billed = q6(reloc_gib_exact * ctx.egress)

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
         "relocation": "none (same nodes/storage)"},
        {"option": "same-region H200 preemptible",
         "price_record": "nebius-h200-1g-pre",
         "usd_per_hour": str(inputs.unit_price("nebius-h200-1g-pre")),
         "availability_at_capture": level(
             "eu-north1", "gpu-h200-sxm", 1, "preemptible"),
         "relocation": "same region; storage reattach, no cross-region "
                       "artifact transfer"},
        {"option": "cross-region B200 preemptible (us-central1)",
         "price_record": "nebius-b200-1g-pre",
         "usd_per_hour": str(inputs.unit_price("nebius-b200-1g-pre")),
         "availability_at_capture": level(
             "us-central1", "gpu-b200-sxm", 1, "preemptible"),
         "relocation": f"measured Boltz2 artifact+cache {reloc_gib} GiB; "
                       f"egress-billed {reloc_billed} USD, egress-free "
                       f"0 USD, per node (unmeasured duration)"},
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

def _sweep_curves(ctx: Ctx, reports: list[dict], axis: str,
                  scenario: dict, capacity_of) -> dict:
    """Reprice sweep points including the L1 cache tier's storage cost —
    a capacity curve that prices only GPU + egress omits the very resource
    the axis varies. ``capacity_of(report)`` returns the per-node L1 GiB."""
    horizon_hours = Decimal(str(scenario["horizon_seconds"])) / Decimal(3600)
    curves: dict = {}
    for rep in reports:
        repriced = lib.reprice_simulator_report(
            rep, {"on_demand": ctx.od, "preemptible": ctx.pre}, ctx.egress,
            l1_storage={
                "capacity_gib": capacity_of(rep),
                "node_count": scenario["n_nodes"],
                "horizon_hours": horizon_hours,
                "rates": ctx.l1_disk_rates,
            })
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

    capture = {
        "assumption": "snapshot_capture_seconds_of2",
        "applies_to_model": ctx.capture_model,
        "seconds": str(ctx.capture_seconds),
        "per_capture_usd": {
            "on_demand": str(lib.gpu_seconds_cost(
                ctx.capture_seconds, ctx.od)),
            "preemptible": str(lib.gpu_seconds_cost(
                ctx.capture_seconds, ctx.pre)),
        },
        "amortization": [{
            "restores_between_captures": r,
            "per_restore_usd_preemptible": q6(lib.gpu_seconds_cost_exact(
                ctx.capture_seconds, ctx.pre) / Decimal(r)),
            "per_restore_usd_on_demand": q6(lib.gpu_seconds_cost_exact(
                ctx.capture_seconds, ctx.od) / Decimal(r)),
        } for r in ctx.capture_r_grid],
        "notes": ("Per model-version capture, never on any request's "
                  "critical path. OpenFold2-only: no Boltz2 capture "
                  "duration exists, so Boltz2 rows exclude capture cost "
                  "(fail-closed) instead of borrowing this value."),
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
                      "cpu-d3 controller node; included in every cost "
                      "row of both collections."),
        },
    }
    all_cost_rows = cost_total_rows(ctx, of2) + cost_total_rows(ctx, boltz2)
    internal["complete_cost_totals"] = [
        r for r in all_cost_rows if r["completeness"] == "COMPLETE"]
    internal["incomplete_lower_bound_subtotals"] = [
        r for r in all_cost_rows if r["completeness"] != "COMPLETE"]

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
        "notes": ("PENDING, not measured: Cerebrium has dated, hash-bound "
                  "public prices only. No per-request cost or rank is "
                  "computable fail-closed until the sibling benchmark "
                  "produces measured request latency."),
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
    legacy_horizon_hours = (Decimal(str(sim_doc["scenario"]
                                        ["horizon_seconds"]))
                            / Decimal(3600))
    legacy = []
    for r in sim_doc["reports"]:
        rep = lib.reprice_simulator_report(
            r, gpu_hourly, ctx.egress,
            l1_storage={
                "capacity_gib": Decimal(str(
                    sim_doc["placeholders"][r["sensitivity"]]
                    ["l1_capacity_gib"]["selected"])),
                "node_count": sim_doc["scenario"]["n_nodes"],
                "horizon_hours": legacy_horizon_hours,
                "rates": ctx.l1_disk_rates,
            })
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
    base_l1_gib = Decimal(str(
        sweeps_doc["base_placeholders"]["l1_capacity_gib"]["selected"]))
    k_curves = _sweep_curves(
        ctx, sweeps_doc["k_sweep"], "warm_top_k", sweeps_doc["scenario"],
        lambda rep: base_l1_gib)
    cache_curves = _sweep_curves(
        ctx, sweeps_doc["cache_sweep"], "l1_capacity_gib",
        sweeps_doc["scenario"], lambda rep: Decimal(rep["sweep_value"]))

    # Break-even blocks (measured-anchored).
    warm_rows = []
    for classes in classes_list:
        p95 = Decimal(classes["prepared_switch"]["latency_seconds"]["p95"])
        for offer, hourly in (("preemptible", ctx.pre),
                              ("on_demand", ctx.od)):
            per_switch_exact = lib.gpu_seconds_cost_exact(p95, hourly)
            warm_rows.append({
                "model": classes["model"],
                "cost_class": "prepared_switch",
                "switch_offer": offer,
                "per_switch_usd_p95": q6(per_switch_exact),
                "warm_gpu_month_usd_on_demand": str(ctx.warm_month),
                "breakeven_requests_per_month_upper_bound": str(
                    lib.warm_breakeven_requests_per_month(
                        ctx.warm_month, per_switch_exact)),
                "decision_forbidden": True,
                "bound": ("UPPER BOUND on the break-even demand, computed "
                          "against the zero-idle perfect-sharing per-switch "
                          "cost (idle/reserved GPU capacity unallocated on "
                          "the switching side). Real switching capacity "
                          "also pays idle, so the true break-even demand "
                          "is at most this value; no ranking or deployment "
                          "decision may be taken from it. The division "
                          "uses the exact unrounded per-switch cost."),
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
        "monthly_usd_on_demand": q2(ctx.warm_month * k + ctx.fixed_month),
        "includes": "K warm H100 + 4 TiB SFS + controller",
        "simulated_counterpart": ("k_sweep curves at warm_top_k=%d "
                                  "(placeholder-derived)" % k),
    } for k in WARM_POOL_K]

    frontier = {
        "schema_version": "capacity-cost-frontier/v7",
        "as_of_date": inputs.price["as_of_date"],
        "generated_by": "catalog-switch/capacity-cost/costmodel/build_frontier.py",
        "statement": (
            "Corrected candidate v7. Prepared versus request-triggered cost "
            "classes with explicit amortization; model-scoped inputs stay "
            "model-scoped (the OpenFold2 capture assumption is never applied "
            "to Boltz2); unmeasured relocation is separated from the "
            "measured cold-switch lower bound and emitted under both egress "
            "variants; complete totals and incomplete lower-bound "
            "subtotals are published in disjoint collections spanning the "
            "capture-reuse grid with "
            "nominal and pessimistic monthly values; the preemption sweep "
            "exposes its full grid with exact-Decimal strategy selection "
            "and explicit exact ties (p=0 ties preemptible-only with the "
            "fallback rather than crowning one winner); "
            "capacity curves price the L1 cache tier's storage from the "
            "captured node-disk quotes alongside GPU and egress; COMPLETE "
            "dedicated rows are additionally gated on captured "
            "quota-clipped availability (a plan needing more nodes than "
            "any single fabric offered at capture is demoted to a "
            "lower-bound subtotal) and every cost row pairs with the "
            "latency/p99/goodput/error evidence that sized it; "
            "rows missing a required component carry null complete totals "
            "and null decisions, publishing only explicitly-named "
            "lower-bound subtotals on which ranking and break-even "
            "decisions are forbidden; idle/reserved GPU capacity is "
            "explicitly allocated in the dedicated_prepared_node capacity "
            "model (whole-instance monthly quotes, node counts, "
            "utilization), while the marginal zero-idle bound is always an "
            "incomplete lower bound and the warm-vs-switch break-even is "
            "published only as a decision-forbidden upper bound; "
            "public prices are hash-bound to archived payloads whose exact "
            "fetch timestamps are the recorded retrieval times; all "
            "composite arithmetic is exact with one quantization at "
            "emission. Cerebrium is PENDING_MEASUREMENT (prices only, never "
            "measured) and Modal documentation-only. Cost is always paired "
            "with the latency and goodput of the same evidence."),
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
        "# Capacity/cost frontier v7 (as of %s)" % f["as_of_date"],
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
    reloc = boltz_cold["unmeasured_relocation"]
    lines += [
        "",
        "Boltz2 cold switch is a measured LOWER BOUND: %s s preparation "
        "(local SFS cache read) + %s s p95 switch = %sx the prepared-switch "
        "cost at reuse=1; the amortization grid (reuse 1/2/5/10/50) is in "
        "frontier.json. Relocating the measured %s GiB from object storage "
        "is a SEPARATE UNMEASURED add-on: %s USD egress-billed / 0 USD "
        "egress-free per preparation, duration unmeasured." % (
            boltz_cold["prep_seconds"],
            internal["cost_classes"][1]["prepared_switch"]
            ["latency_seconds"]["p95"],
            boltz_cold["understatement_vs_prepared"],
            reloc["traffic_gib"],
            reloc["per_preparation_usd"]["egress_billed"]),
        "OpenFold2 cold switch and all node-provision-miss rows are "
        "fail-closed PENDING_MEASUREMENT. Snapshot capture cost "
        "(%s s, %s) applies to %s only; Boltz2 rows exclude it fail-closed." % (
            internal["snapshot_capture_cost"]["seconds"],
            internal["snapshot_capture_cost"]["assumption"],
            internal["snapshot_capture_cost"]["applies_to_model"]),
        "",
        "## Per-success and monthly cost under explicit capacity models",
        "",
        "Capacity model A, dedicated_prepared_node: idle and reserved GPU "
        "capacity fully allocated as whole dedicated H100 instance(s) "
        "(nodes = ceil(busy-seconds / node-month), whole monthly instance "
        "quotes charged, utilization shown). COMPLETE only where every "
        "component is available; Boltz2 capture is unavailable, so its "
        "dedicated rows are lower-bound subtotals (>=). Capacity model B, "
        "marginal_zero_idle_bound: only measured request/prep GPU seconds "
        "plus fixed overheads — ALWAYS an INCOMPLETE_LOWER_BOUND because "
        "idle/reserved capacity is unallocated by construction; ranking "
        "and break-even decisions are FORBIDDEN on every lower-bound row. "
        "Shared-pool allocation with contention is placeholder-derived and "
        "lives in the simulation frontier, where reserved GPU-hours are "
        "charged in full.",
        "",
        "### A: dedicated prepared node(s) (sample: preemptible, "
        "OpenFold2 at R=100)",
        "",
        "| Model | Completeness | D req/mo | Nodes | Feasibility (max avail) | Utilization | Per-success | Monthly nom/pess |",
        "|---|---|---:|---:|---|---:|---:|---:|",
    ]
    for row in (internal["complete_cost_totals"]
                + internal["incomplete_lower_bound_subtotals"]):
        if (row["capacity_model"] != "dedicated_prepared_node"
                or row["offer"] != "preemptible"
                or row["restores_between_captures"] not in (None, 100)
                or row["requests_per_month"] not in (10000, 100000, 1000000)):
            continue
        if row["completeness"] == "COMPLETE":
            per = row["per_success_usd_nominal"]
            monthly = "%s / %s" % (row["monthly_usd_nominal"],
                                   row["monthly_usd_pessimistic"])
        else:
            lb = row["lower_bound_subtotals_usd"]
            per = ">= %s" % lb["per_success_nominal"]
            monthly = ">= %s / >= %s" % (lb["monthly_nominal"],
                                         lb["monthly_pessimistic"])
        feas = row["capacity_feasibility"]
        feas_cell = "%s (%d)" % (
            "FEASIBLE" if feas["status"] == "FEASIBLE_AT_CAPTURE"
            else "EXCEEDS_AVAIL",
            feas["max_single_fabric_available_at_capture"])
        lines.append("| %s | %s | %s | %d | %s | %s | %s | %s |" % (
            row["model"], row["completeness"], row["requests_per_month"],
            row["nodes_required"], feas_cell,
            row["utilization_busy_fraction"], per, monthly))
    lines += [
        "",
        "### B: marginal zero-idle sharing bound (sample: 100k req/mo, "
        "preemptible; every row is a lower-bound subtotal, no decisions)",
        "",
        "| Model | Class | GPU p50 | Capture | Fixed share | Per-success | Monthly nom/pess | +Relocation (billed/free) |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in internal["incomplete_lower_bound_subtotals"]:
        if (row["capacity_model"] != "marginal_zero_idle_bound"
                or row["requests_per_month"] != 100000
                or row["offer"] != "preemptible"
                or row["restores_between_captures"] not in (None, 100)
                or (row["cost_class"] == "cold_switch"
                    and row["prep_reuse"] not in (1, 10))):
            continue
        label = row["cost_class"] + (
            f" (reuse={row['prep_reuse']})" if row["prep_reuse"] else "")
        comp = row["components_usd"]
        addon = row.get("unmeasured_relocation_addon")
        lb = row["lower_bound_subtotals_usd"]
        per = ">= %s" % lb["per_success_nominal"]
        monthly = ">= %s / >= %s" % (lb["monthly_nominal"],
                                     lb["monthly_pessimistic"])
        addon_cell = (">= %s / >= %s" % (
            addon["per_success_lower_bound_with_addon"]["nominal"]
            ["egress_billed"],
            addon["per_success_lower_bound_with_addon"]["nominal"]
            ["egress_free"])
            if addon else "n/a")
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["model"], label, comp["gpu_switch_p50"],
            comp["capture_amortized"] or "unavailable",
            comp["fixed_sfs_controller_share"], per, monthly, addon_cell))
    pe = f["sweeps"]["preemption"]
    lines += [
        "",
        "Full grids (capture-reuse 1/10/100/1000, demand, reuse, both "
        "offers, pessimistic monthly, both egress variants for the "
        "relocation add-on) are in frontier.json and breakeven.tsv.",
        "",
        "## Preemption / fallback sweep (prepared switch, per success, "
        "full grid)",
        "",
        pe["fallback_model"],
        "",
        "Break-even loss probability: " + ", ".join(
            "%s %s" % (k, v) for k, v in sorted(
                pe["breakeven_loss_probability"].items())),
        "",
        "| Model | p(loss) | Preemptible-only | Pre-then-OD fallback | On-demand | Cheapest |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for pt in pe["points"]:
        winners = pt["cheapest_strategies"]
        cell = (winners[0] if len(winners) == 1
                else "exact tie: " + " = ".join(winners))
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            pt["model"], pt["loss_probability"],
            pt["preemptible_only_usd_per_success"],
            pt["fallback_pre_then_od_usd_per_success"],
            pt["on_demand_usd_per_success"], cell))
    rl = f["sweeps"]["regional_loss"]
    lines += [
        "",
        "## Regional capacity loss fallbacks (%s)" % rl["scenario"],
        "",
        "| Option | USD/h | Availability at capture | Relocation |",
        "|---|---:|---|---|",
    ]
    for opt in rl["options"]:
        lines.append("| %s | %s | %s | %s |" % (
            opt["option"], opt["usd_per_hour"],
            opt["availability_at_capture"], opt["relocation"]))
    lines += [
        "",
        rl["latency"] + ".",
        "",
        "## Isolated top-K and cache curves (placeholder-derived simulation)",
        "",
        "Each sweep varies exactly one axis at base placeholders on the "
        "committed traces (checksums asserted). The +L1 storage columns "
        "price the node-local cache capacity itself from the captured "
        "disk quotes (non-replicated and network SSD per-GiB-hour). Zipf "
        "family shown; all five families are in frontier.json.",
        "",
        "| Axis | Value | p95 s | ≤60s goodput | USD/1k (pre, billed) | USD/1k +L1 storage (NRD / NSSD) |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for block in (f["simulation_frontier"]["top_k_sweep"],
                  f["simulation_frontier"]["cache_sweep"]):
        for row in block["curves"]["zipf"]:
            combo = row["cost_usd"]["preemptible/egress_billed"]
            with_l1 = combo["per_1000_completed_with_l1_storage"]
            lines.append("| %s | %s | %.1f | %.3f | %s | %s / %s |" % (
                block["axis"], row["sweep_value"],
                row["latency_seconds"]["p95"],
                row["slo_goodput"]["within_60s"],
                combo["per_1000_completed"][:8],
                with_l1["network_ssd_non_replicated"][:8],
                with_l1["network_ssd"][:8]))
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
        "| Cerebrium | %s (prices only, never measured) |" % (
            f["backends"]["cerebrium"]["status"]),
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
        rows.append("warm_vs_switch_upper_bound\t%s\t%s\t"
                    "breakeven_upper_bound=%s\t%s\t%s\tno_decision" % (
                        r["model"], r["switch_offer"],
                        r["breakeven_requests_per_month_upper_bound"],
                        r["per_switch_usd_p95"],
                        r["warm_gpu_month_usd_on_demand"]))
    for r in (internal["complete_cost_totals"]
              + internal["incomplete_lower_bound_subtotals"]):
        key = "D=%s,offer=%s,reuse=%s,R=%s" % (
            r["requests_per_month"], r["offer"], r["prep_reuse"],
            r["restores_between_captures"])
        addon = r.get("unmeasured_relocation_addon")
        if r["capacity_model"] == "dedicated_prepared_node":
            key += ",nodes=%d" % r["nodes_required"]
            if r["completeness"] == "COMPLETE":
                rows.append(
                    "complete_dedicated_totals\t%s\t%s\t%s\t%s\t%s\t"
                    "complete" % (
                        r["model"], r["cost_class"], key,
                        r["per_success_usd_nominal"],
                        "%s/%s" % (r["monthly_usd_nominal"],
                                   r["monthly_usd_pessimistic"])))
            else:
                lb = r["lower_bound_subtotals_usd"]
                rows.append(
                    "incomplete_dedicated_lower_bound\t%s\t%s\t%s\t%s"
                    "\t%s\tincomplete_lower_bound_no_decision" % (
                        r["model"], r["cost_class"], key,
                        lb["per_success_nominal"],
                        "%s/%s" % (lb["monthly_nominal"],
                                   lb["monthly_pessimistic"])))
            continue
        lb = r["lower_bound_subtotals_usd"]
        rows.append(
            "incomplete_marginal_lower_bound\t%s\t%s\t%s\t%s\t%s\t"
            "incomplete_lower_bound_no_decision" % (
                r["model"], r["cost_class"], key,
                lb["per_success_nominal"],
                "%s/%s" % (lb["monthly_nominal"],
                           lb["monthly_pessimistic"])))
        if addon:
            with_addon = addon["per_success_lower_bound_with_addon"]
            rows.append(
                "incomplete_relocation_addon_lower_bound\t%s\t%s\t%s"
                "\t%s\t%s\tunmeasured_scenario_no_decision" % (
                    r["model"], r["cost_class"], key,
                    "%s/%s" % (with_addon["nominal"]["egress_billed"],
                               with_addon["pessimistic"]["egress_billed"]),
                    "%s/%s" % (with_addon["nominal"]["egress_free"],
                               with_addon["pessimistic"]["egress_free"])))
    for pt in f["sweeps"]["preemption"]["points"]:
        rows.append("preemption_sweep\t%s\tp=%s\tcheapest=%s\t%s\t%s\t%s" % (
            pt["model"], pt["loss_probability"],
            "+".join(pt["cheapest_strategies"]),
            pt["preemptible_only_usd_per_success"],
            pt["fallback_pre_then_od_usd_per_success"],
            pt["on_demand_usd_per_success"]))
    for block in (f["simulation_frontier"]["top_k_sweep"],
                  f["simulation_frontier"]["cache_sweep"]):
        for family, curve in sorted(block["curves"].items()):
            for row in curve:
                pre_c = row["cost_usd"]["preemptible/egress_billed"]
                od_c = row["cost_usd"]["on_demand/egress_billed"]
                rows.append(
                    "%s\t%s\t%s\tp95=%s\t%s\t%s\tplaceholder-derived" % (
                        block["axis"], family, row["sweep_value"],
                        row["latency_seconds"]["p95"],
                        "%s/%s" % (
                            pre_c["per_1000_completed"],
                            pre_c["per_1000_completed_with_l1_storage"]
                            ["network_ssd_non_replicated"]),
                        "%s/%s" % (
                            od_c["per_1000_completed"],
                            od_c["per_1000_completed_with_l1_storage"]
                            ["network_ssd_non_replicated"])))
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
    internal = frontier["backends"]["internal-k8s-snapshot"]
    print("complete cost totals:", len(internal["complete_cost_totals"]))
    print("incomplete lower-bound subtotals:",
          len(internal["incomplete_lower_bound_subtotals"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
