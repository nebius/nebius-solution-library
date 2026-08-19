#!/usr/bin/env python3
"""Build the measured capacity/cost frontier.

Reads the committed snapshots and measured artifacts (checksum-pinned),
re-prices the policy simulator's capacity outputs with sourced prices, and
emits deterministic results:

- ``results/frontier.json``
- ``results/FRONTIER.md``
- ``results/breakeven.tsv``

Run from the ``faststart-v2`` directory:

    python3 catalog-switch/capacity-cost/costmodel/build_frontier.py

No network, no cloud calls, no timestamps generated at run time: output is a
pure function of committed inputs, so regeneration is byte-identical.
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


def cohort_row(inputs: lib.Inputs, entry_id: str) -> dict:
    entry = inputs.measured_entry(entry_id)
    values = sorted(lib.load_cohort_seconds(inputs, entry_id))
    p50 = lib.nearest_rank(values, 50)
    p95 = lib.nearest_rank(values, 95)
    od = inputs.unit_price("nebius-h100-1g-od")
    pre = inputs.unit_price("nebius-h100-1g-pre")
    pess = lib.retry_multiplier(
        Decimal(inputs.assumption("failure_rate_upper_bound_rule_of_three")))
    costs = {}
    for offer, hourly in (("on_demand", od), ("preemptible", pre)):
        for stat, secs in (("p50", p50), ("p95", p95)):
            nominal = lib.gpu_seconds_cost(secs, hourly)
            costs[f"{offer}/{stat}"] = {
                "gpu_critical_path_usd": str(nominal),
                "gpu_critical_path_usd_pessimistic": str(
                    (nominal * pess).quantize(lib.CENT6)),
            }
    return {
        "model": entry["model"],
        "evidence": entry_id,
        "metric": entry["metric"],
        "n": entry["n"],
        "failed_attempt_denominator": entry["failed_attempt_denominator"],
        "latency_seconds": {"p50": str(p50), "p95": str(p95),
                            "min": str(values[0]), "max": str(values[-1])},
        "slo_goodput": {
            f"within_{int(t)}s": str(lib.goodput_within(values, t))
            for t in SLO_THRESHOLDS},
        "per_request_cost_usd": costs,
        "cost_notes": (
            "GPU critical path only (T0 through second semantic response on "
            "a 1x H100 instance quote). Node provision, pre-T0 setup, warm "
            "idle, storage, and controller costs are separate rows. "
            "Pessimistic = rule-of-three retry multiplier from the measured "
            "0/20 failure denominator."),
    }


def build(inputs: lib.Inputs) -> tuple[dict, str, str]:
    od = inputs.unit_price("nebius-h100-1g-od")
    pre = inputs.unit_price("nebius-h100-1g-pre")
    egress = inputs.unit_price("nebius-list-object-egress")
    h100_avail = inputs.availability_rows("eu-north1", "gpu-h100-sxm", 1)

    # --- measured internal backend ------------------------------------
    of2 = cohort_row(inputs, "of2-n20-fresh")
    boltz2 = cohort_row(inputs, "boltz2-n20-fresh")

    capture_s = Decimal(inputs.assumption("snapshot_capture_seconds_of2"))
    capture_cost = {
        "assumption": "snapshot_capture_seconds_of2",
        "seconds": str(capture_s),
        "on_demand_usd_per_capture": str(lib.gpu_seconds_cost(capture_s, od)),
        "preemptible_usd_per_capture": str(
            lib.gpu_seconds_cost(capture_s, pre)),
        "notes": (
            "Capture is per model-version, amortized over all restores "
            "between recaptures; it is not part of any request's critical "
            "path."),
    }

    internal = {
        "status": "MEASURED",
        "gpu_platform": "gpu-h100-sxm 1gpu-16vcpu-200gb, eu-north1",
        "availability_at_capture": [
            {"fabric": r["fabric"], "offers": r["offers"]}
            for r in h100_avail],
        "models": [of2, boltz2],
        "snapshot_capture_cost": capture_cost,
        "fixed_monthly_overheads_usd": {
            "sfs_4096gib_artifact_tier": str(
                inputs.monthly_price("nebius-sfs-4096gib")),
            "controller_cpu_d3_4vcpu_16gb": str(
                inputs.monthly_price("nebius-cpu-d3-4v16g-od")),
            "notes": (
                "As-deployed measured-tier shapes: one 4 TiB network_ssd SFS "
                "holding artifacts/caches and one cpu-d3 controller node."),
        },
    }

    # --- unmeasured backends (fail-closed) ------------------------------
    cerebrium_decl = inputs.unmeasured("cerebrium")
    cerebrium = {
        "status": cerebrium_decl["status"],
        "reason": cerebrium_decl["reason"],
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
        "notes": (
            "Cerebrium bills GPU+CPU+memory per second only while an app is "
            "active. Its H100-hour equivalent is below the Nebius on-demand "
            "H100 quote and above the preemptible quote, but no per-request "
            "cost is computable fail-closed until the sibling benchmark "
            "produces measured request latency."),
    }
    node_local_decl = inputs.unmeasured("internal-node-local-vm")
    node_local = {
        "status": node_local_decl["status"],
        "reason": node_local_decl["reason"],
        "dated_unit_prices": {
            "h100_on_demand_usd_per_hour": str(od),
            "h100_preemptible_usd_per_hour": str(pre),
        },
        "per_request_cost_usd": None,
        "latency_seconds": None,
    }
    modal_decl = inputs.unmeasured("modal")
    modal = {
        "status": modal_decl["status"],
        "reason": modal_decl["reason"],
        "reference": "catalog-switch/capacity-cost/MODAL_APPENDIX.md",
        "per_request_cost_usd": None,
        "latency_seconds": None,
        "dated_unit_prices": None,
    }

    # --- simulator repricing --------------------------------------------
    sim_doc = json.loads(
        (inputs.root / inputs.measured_entry("catalog-sim-reports")["file"])
        .read_text())
    gpu_hourly = {"on_demand": od, "preemptible": pre}
    repriced = [lib.reprice_simulator_report(r, gpu_hourly, egress)
                for r in sim_doc["reports"]]
    repriced.sort(key=lambda r: (r["trace_family"], r["sensitivity"],
                                 r["policy"]))

    # --- break-even curves ------------------------------------------------
    preempt_be = {}
    for plat, od_id, pre_id in (
            ("gpu-h100-sxm", "nebius-h100-1g-od", "nebius-h100-1g-pre"),
            ("gpu-h200-sxm", "nebius-h200-1g-od", "nebius-h200-1g-pre"),
            ("gpu-b200-sxm", "nebius-b200-1g-od", "nebius-b200-1g-pre")):
        preempt_be[plat] = str(lib.preemption_breakeven(
            inputs.unit_price(pre_id), inputs.unit_price(od_id)))

    warm_month = inputs.monthly_price("nebius-h100-1g-od")
    warm_rows = []
    for row in (of2, boltz2):
        p95 = Decimal(row["latency_seconds"]["p95"])
        for offer, hourly in (("preemptible", pre), ("on_demand", od)):
            per_switch = lib.gpu_seconds_cost(p95, hourly)
            warm_rows.append({
                "model": row["model"],
                "switch_offer": offer,
                "per_switch_usd_p95": str(per_switch),
                "warm_gpu_month_usd_on_demand": str(warm_month),
                "breakeven_requests_per_month": str(
                    lib.warm_breakeven_requests_per_month(
                        warm_month, per_switch)),
                "latency_tradeoff": (
                    f"warm hit ~= second-call latency; switch p95 = {p95}s"),
                "bound": (
                    "upper bound: assumes every request pays a full switch; "
                    "any cache hit rate lowers the effective switch cost"),
            })

    storage_be = {
        "sfs_usd_per_gib_month": str(inputs.unit_price("nebius-sfs-gib-month")),
        "object_usd_per_gib_month": str(
            inputs.unit_price("nebius-list-object-volume")),
        "object_egress_usd_per_gib": str(egress),
        "egress_billed_breakeven_refetches_per_gib_month": str(
            lib.storage_breakeven_refetches_per_gib_month(
                inputs.unit_price("nebius-sfs-gib-month"),
                inputs.unit_price("nebius-list-object-volume"),
                egress)),
        "egress_free_variant": (
            "if intra-cloud object reads are not billed as egress, object "
            "storage dominates SFS on cost at any refetch rate and the "
            "decision is latency-only"),
    }

    warm_pool = [{
        "k_warm_gpus": k,
        "monthly_usd_on_demand": str(
            (warm_month * k
             + inputs.monthly_price("nebius-sfs-4096gib")
             + inputs.monthly_price("nebius-cpu-d3-4v16g-od"))
            .quantize(Decimal("0.01"))),
        "includes": "K warm H100 + 4 TiB SFS + controller",
    } for k in WARM_POOL_K]

    demand_rows = []
    for row in (of2, boltz2):
        p50_cost_pre = Decimal(
            row["per_request_cost_usd"]["preemptible/p50"]
            ["gpu_critical_path_usd"])
        for demand in inputs.assumption("monthly_demand_grid_requests"):
            demand_rows.append({
                "model": row["model"],
                "requests_per_month": demand,
                "switch_every_request_usd_preemptible_p50": str(
                    (p50_cost_pre * Decimal(demand)).quantize(Decimal("0.01"))),
                "one_warm_gpu_usd": str(warm_month),
                "cheaper": ("switch" if p50_cost_pre * Decimal(demand)
                            < warm_month else "warm"),
            })

    frontier = {
        "schema_version": "capacity-cost-frontier/v1",
        "as_of_date": inputs.price["as_of_date"],
        "generated_by": "catalog-switch/capacity-cost/costmodel/build_frontier.py",
        "statement": (
            "Measured internal Kubernetes snapshot backend versus Cerebrium "
            "(sole external comparator, latency pending) with Modal excluded "
            "as documentation-only. Every USD value traces to a dated record "
            "in inputs/price_snapshot.json and every latency to a "
            "checksum-pinned measured artifact. Cost values are always "
            "paired with the p50/p95 and SLO goodput of the same evidence."),
        "backends": {
            "internal-k8s-snapshot": internal,
            "internal-node-local-vm": node_local,
            "cerebrium": cerebrium,
            "modal": modal,
        },
        "simulator_frontier": {
            "source": "catalog-sim/results/reports.json (placeholder prices replaced)",
            "gpu_price_records": ["nebius-h100-1g-od", "nebius-h100-1g-pre"],
            "egress_price_record": "nebius-list-object-egress",
            "reports": repriced,
        },
        "breakeven": {
            "preemption_loss_probability": preempt_be,
            "warm_vs_switch": warm_rows,
            "storage_tier": storage_be,
            "warm_pool_monthly": warm_pool,
            "demand_sensitivity": demand_rows,
        },
    }
    return frontier, render_markdown(frontier), render_tsv(frontier)


def render_markdown(f: dict) -> str:
    b = f["backends"]
    internal = b["internal-k8s-snapshot"]
    lines = [
        "# Capacity/cost frontier (as of %s)" % f["as_of_date"],
        "",
        f["statement"],
        "",
        "## Measured internal Kubernetes snapshot backend (1x H100, eu-north1)",
        "",
        "| Model | n | p50 s | p95 s | ≤20s | ≤30s | ≤60s | switch cost p95 pre / od (USD) |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for m in internal["models"]:
        c = m["per_request_cost_usd"]
        lines.append(
            "| {model} | {n} | {p50} | {p95} | {g20} | {g30} | {g60} | {pre} / {od} |".format(
                model=m["model"], n=m["n"],
                p50=m["latency_seconds"]["p50"][:7],
                p95=m["latency_seconds"]["p95"][:7],
                g20=m["slo_goodput"]["within_20s"],
                g30=m["slo_goodput"]["within_30s"],
                g60=m["slo_goodput"]["within_60s"],
                pre=c["preemptible/p95"]["gpu_critical_path_usd"],
                od=c["on_demand/p95"]["gpu_critical_path_usd"]))
    lines += [
        "",
        "Failed-attempt denominators are the measured 0/20; the pessimistic "
        "column in frontier.json applies the rule-of-three ×1.176 bound.",
        "",
        "H100 availability at capture (quota-clipped, per fabric): " + "; ".join(
            "%s od=%s pre=%s (%s/%s)" % (
                row["fabric"],
                row["offers"]["on_demand"]["availability_level"]
                .replace("AVAILABILITY_LEVEL_", ""),
                row["offers"]["preemptible"]["availability_level"]
                .replace("AVAILABILITY_LEVEL_", ""),
                row["offers"]["preemptible"]["available"],
                row["offers"]["preemptible"]["limit"])
            for row in internal["availability_at_capture"]) + ".",
        "",
        "Snapshot capture (assumption-flagged, per capture): %s s -> %s USD "
        "preemptible / %s USD on-demand." % (
            internal["snapshot_capture_cost"]["seconds"],
            internal["snapshot_capture_cost"]["preemptible_usd_per_capture"],
            internal["snapshot_capture_cost"]["on_demand_usd_per_capture"]),
        "",
        "## Unmeasured backends (fail-closed)",
        "",
        "| Backend | Status | Dated price basis |",
        "|---|---|---|",
        "| Cerebrium | %s | H100 %s, H200 %s, B200 %s USD/GPU-h equivalent + %s USD/mo plan |" % (
            b["cerebrium"]["status"],
            b["cerebrium"]["dated_unit_prices"]["H100_usd_per_gpu_hour_equivalent"],
            b["cerebrium"]["dated_unit_prices"]["H200_usd_per_gpu_hour_equivalent"],
            b["cerebrium"]["dated_unit_prices"]["B200_usd_per_gpu_hour_equivalent"],
            b["cerebrium"]["dated_unit_prices"]["plan_standard_usd_per_month"]),
        "| Node-local VM | %s | same Nebius instance quotes as internal |" % (
            b["internal-node-local-vm"]["status"]),
        "| Modal | %s | MODAL_APPENDIX.md only |" % b["modal"]["status"],
        "",
        "## Break-even summary",
        "",
        "Preemption loss probability where preemptible stops paying: " + ", ".join(
            "%s %s" % (k, v) for k, v in sorted(
                f["breakeven"]["preemption_loss_probability"].items())),
        "",
        "| Model | Switch offer | Per-switch p95 USD | Warm break-even req/mo |",
        "|---|---|---:|---:|",
    ]
    for row in f["breakeven"]["warm_vs_switch"]:
        lines.append("| %s | %s | %s | %s |" % (
            row["model"], row["switch_offer"], row["per_switch_usd_p95"],
            row["breakeven_requests_per_month"]))
    st = f["breakeven"]["storage_tier"]
    lines += [
        "",
        "Storage: SFS %s vs object %s USD/GiB-month; egress-billed break-even "
        "%s refetches/GiB-month; egress-free variant favors object storage on "
        "cost at any rate." % (
            st["sfs_usd_per_gib_month"], st["object_usd_per_gib_month"],
            st["egress_billed_breakeven_refetches_per_gib_month"]),
        "",
        "## Repriced simulator frontier (base sensitivity, adversarial trace)",
        "",
        "| Policy | p95 s | ≤60s goodput | USD/1k req (pre, egress-billed) | USD/1k req (od, egress-billed) |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in f["simulator_frontier"]["reports"]:
        if r["sensitivity"] != "base" or r["trace_family"] != "adversarial":
            continue
        lines.append("| %s | %.1f | %.3f | %s | %s |" % (
            r["policy"], r["latency_seconds"]["p95"],
            r["slo_goodput"]["within_60s"],
            r["cost_usd"]["preemptible/egress_billed"]["per_1000_completed"][:8],
            r["cost_usd"]["on_demand/egress_billed"]["per_1000_completed"][:8]))
    lines += [
        "",
        "Full detail, every sensitivity/trace/policy and both egress "
        "variants: `frontier.json`. Demand-grid and warm-pool tables: "
        "`breakeven.tsv`.",
        "",
    ]
    return "\n".join(lines)


def render_tsv(f: dict) -> str:
    rows = ["table\tmodel\toffer_or_k\trequests_per_month\tusd\tcomparator_usd\tcheaper"]
    for r in f["breakeven"]["warm_vs_switch"]:
        rows.append("warm_vs_switch\t%s\t%s\tbreakeven=%s\t%s\t%s\t-" % (
            r["model"], r["switch_offer"], r["breakeven_requests_per_month"],
            r["per_switch_usd_p95"], r["warm_gpu_month_usd_on_demand"]))
    for r in f["breakeven"]["demand_sensitivity"]:
        rows.append("demand_sensitivity\t%s\tpreemptible_p50\t%s\t%s\t%s\t%s" % (
            r["model"], r["requests_per_month"],
            r["switch_every_request_usd_preemptible_p50"],
            r["one_warm_gpu_usd"], r["cheaper"]))
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
    print("frontier backends:", len(frontier["backends"]))
    print("repriced reports:", len(frontier["simulator_frontier"]["reports"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
