#!/usr/bin/env python3
"""Run ISOLATED top-K and cache-size simulator sweeps.

Each sweep varies exactly one axis while every other input stays at the base
placeholder level, the base catalog, the committed traces, and the committed
seeds — unlike the simulator's own low/base/high sensitivity runs, which move
all placeholders together:

- top-K sweep: ``warm=topk-adaptive`` with K in ``K_GRID``; fleet and catalog
  are byte-identical across points;
- cache sweep: only ``l1_capacity_bytes`` is overridden per point; policy,
  catalog, and every other fleet parameter are byte-identical.

Trace checksums are asserted against the committed
``catalog-sim/traces/CHECKSUMS.json`` so the sweep is bound to the exact
reviewed traces. Output ``results/sweeps.json`` is deterministic (no clocks,
no fresh randomness) and labeled placeholder-derived simulation throughout.

Run from ``faststart-v2``:

    python3 catalog-switch/capacity-cost/costmodel/run_sweeps.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent  # faststart-v2
SIM_DIR = ROOT / "catalog-sim"
sys.path.insert(0, str(SIM_DIR))

from catalog_sim import SCHEMA_VERSION, __version__  # noqa: E402
from catalog_sim.catalog import (  # noqa: E402
    build_catalog,
    fleet_parameters,
    scenario_placeholders_json,
)
from catalog_sim.engine import Simulator  # noqa: E402
from catalog_sim.policies import PolicyConfig  # noqa: E402
from catalog_sim.traces import TRACE_SEED, generate_all  # noqa: E402
from catalog_sim.units import gib_to_bytes  # noqa: E402

# Mirror the committed simulation scenario exactly (run_simulation.py).
N_MODELS = 200
N_NODES = 24
HORIZON_SECONDS = 7200.0
MEAN_RATE_PER_S = 0.25
SIM_SEED = 7

K_GRID = (1, 2, 4, 8, 16)
# The cache grid floor is 150 GiB because the simulator fails closed if the
# largest base-catalog artifact (143.19 GiB, a synthetic Evo2-40B-scaled row)
# cannot fit in L1 at all; smaller caches are invalid configurations for this
# catalog, not data points.
CACHE_GIB_GRID = (150, 200, 400, 800, 1600)

RESULTS = HERE.parent / "results"


def build_scenario():
    catalog, _ = build_catalog(N_MODELS, "base")
    model_ids = sorted(catalog)
    traces = generate_all(
        model_ids,
        horizon_seconds=HORIZON_SECONDS,
        mean_rate_per_s=MEAN_RATE_PER_S,
        seed=TRACE_SEED,
    )
    committed = json.loads(
        (SIM_DIR / "traces" / "CHECKSUMS.json").read_text())["sha256"]
    for family in sorted(traces):
        actual = traces[family].checksum()
        expect = committed[family]
        if actual != expect:
            raise SystemExit(
                f"trace checksum drift for {family}: {actual} != {expect}")
    return catalog, traces


def run_point(catalog, trace, config, fleet, axis, value):
    sim = Simulator(
        catalog=catalog, trace=trace, config=config, fleet=fleet,
        n_nodes=N_NODES, seed=SIM_SEED, enable_failures=True,
    )
    report = sim.run()
    report["sensitivity"] = "base"
    report["sweep_axis"] = axis
    report["sweep_value"] = value
    report["input_provenance"] = (
        "placeholder-derived simulation; only this sweep axis varies, all "
        "other inputs fixed at base")
    return report


def main() -> int:
    catalog, traces = build_scenario()
    base_fleet = fleet_parameters("base")

    k_reports = []
    for family in sorted(traces):
        for k in K_GRID:
            config = PolicyConfig(
                strategy="snapshot", placement="shortest-switch-cost",
                eviction="lru", warm="topk-adaptive", warm_k=k)
            report = run_point(
                catalog, traces[family], config, dict(base_fleet),
                "warm_top_k", k)
            k_reports.append(report)
            print(f"[k-sweep] {family:<12} K={k:<3} "
                  f"p95={report['latency_seconds']['p95']}", flush=True)

    cache_reports = []
    for family in sorted(traces):
        for gib in CACHE_GIB_GRID:
            fleet = dict(base_fleet)
            fleet["l1_capacity_bytes"] = gib_to_bytes(float(gib))
            config = PolicyConfig(
                strategy="snapshot", placement="shortest-switch-cost",
                eviction="lru")
            report = run_point(
                catalog, traces[family], config, fleet,
                "l1_capacity_gib", gib)
            cache_reports.append(report)
            print(f"[cache-sweep] {family:<12} GiB={gib:<5} "
                  f"p95={report['latency_seconds']['p95']}", flush=True)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generator": f"catalog_sim {__version__} via capacity-cost run_sweeps",
        "statement": (
            "Placeholder-derived simulation, never measurement. Each sweep "
            "isolates one axis; every other placeholder stays at base. The "
            "simulator's placeholder prices are ignored downstream; "
            "build_frontier re-prices reserved GPU-hours and fetched GiB "
            "with the sourced price snapshot."),
        "scenario": {
            "n_models": N_MODELS,
            "n_nodes": N_NODES,
            "horizon_seconds": HORIZON_SECONDS,
            "mean_rate_per_s": MEAN_RATE_PER_S,
            "sim_seed": SIM_SEED,
            "k_grid": list(K_GRID),
            "cache_gib_grid": list(CACHE_GIB_GRID),
        },
        "base_placeholders": scenario_placeholders_json("base"),
        "trace_checksums": json.loads(
            (SIM_DIR / "traces" / "CHECKSUMS.json").read_text())["sha256"],
        "k_sweep": k_reports,
        "cache_sweep": cache_reports,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "sweeps.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"k points: {len(k_reports)}, cache points: {len(cache_reports)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
