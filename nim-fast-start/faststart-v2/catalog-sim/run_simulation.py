#!/usr/bin/env python3
"""Run the catalog switch policy simulation matrix and write results.

Outputs are deterministic (no wall-clock content) so the committed artifacts
under ``results/`` and ``traces/CHECKSUMS.json`` are reproducible byte-for-byte
by re-running this script.

Usage:
    python3 run_simulation.py [--quick] [--out-dir results]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from catalog_sim import SCHEMA_VERSION, __version__  # noqa: E402
from catalog_sim.catalog import (  # noqa: E402
    CATALOG_SEED,
    build_catalog,
    fleet_parameters,
    scenario_placeholders_json,
)
from catalog_sim.engine import Simulator  # noqa: E402
from catalog_sim.policies import PolicyConfig  # noqa: E402
from catalog_sim.report import TSV_COLUMNS, report_tsv_row  # noqa: E402
from catalog_sim.traces import TRACE_SEED, generate_all  # noqa: E402

N_MODELS = 200
N_NODES = 24
HORIZON_SECONDS = 7200.0
# 0.25 req/s over 24 nodes keeps the fleet in a stable-but-stressed regime:
# bursty phases (4x the mean rate) transiently exceed switch capacity while
# the long-run offered load stays below it, so tails reflect policy quality
# rather than unbounded saturation collapse.
MEAN_RATE_PER_S = 0.25
SIM_SEED = 7

BASE_CONFIGS = [
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="lru"),
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="lfu"),
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="size"),
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="gdsf"),
    PolicyConfig(strategy="snapshot", placement="least-loaded", eviction="lru"),
    PolicyConfig(strategy="conventional", placement="shortest-switch-cost", eviction="lru"),
    PolicyConfig(
        strategy="snapshot", placement="shortest-switch-cost", eviction="lru",
        warm="topk-adaptive", warm_k=8,
    ),
    PolicyConfig(
        strategy="snapshot", placement="shortest-switch-cost", eviction="lru",
        admission="bounded-queue", max_queue_per_node=12,
    ),
    PolicyConfig(
        strategy="snapshot", placement="shortest-switch-cost", eviction="lru",
        prefetch="pipeline-next",
    ),
]

# Sensitivity sweep runs low/high placeholder settings on headline configs to
# show whether relative policy ordering is stable across the assumption range.
SENSITIVITY_CONFIGS = [
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="lru"),
    PolicyConfig(strategy="snapshot", placement="shortest-switch-cost", eviction="gdsf"),
    PolicyConfig(strategy="conventional", placement="shortest-switch-cost", eviction="lru"),
]


def run_matrix(quick: bool = False) -> dict:
    catalogs = {level: build_catalog(N_MODELS, level)[0] for level in ("low", "base", "high")}
    model_ids = sorted(catalogs["base"])
    traces = generate_all(
        model_ids,
        horizon_seconds=HORIZON_SECONDS if not quick else 1800.0,
        mean_rate_per_s=MEAN_RATE_PER_S,
        seed=TRACE_SEED,
    )
    plan = [("base", config) for config in BASE_CONFIGS]
    if not quick:
        for level in ("low", "high"):
            plan.extend((level, config) for config in SENSITIVITY_CONFIGS)

    reports = []
    for family in sorted(traces):
        trace = traces[family]
        for level, config in plan:
            sim = Simulator(
                catalog=catalogs[level],
                trace=trace,
                config=config,
                fleet=fleet_parameters(level),
                n_nodes=N_NODES,
                seed=SIM_SEED,
                enable_failures=True,
            )
            report = sim.run()
            report["sensitivity"] = level
            reports.append(report)
            print(
                f"[done] {family:<12} {config.label():<60} {level:<5} "
                f"p95={report['latency_seconds']['p95']}",
                flush=True,
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "generator": f"catalog_sim {__version__}",
        "scenario": {
            "n_models": N_MODELS,
            "n_nodes": N_NODES,
            "horizon_seconds": HORIZON_SECONDS if not quick else 1800.0,
            "mean_rate_per_s": MEAN_RATE_PER_S,
            "catalog_seed": CATALOG_SEED,
            "trace_seed": TRACE_SEED,
            "sim_seed": SIM_SEED,
            "slo_note": (
                "Provisional internal scenario. Placeholder-derived rows must "
                "not be read as product SLO evidence; see HANDOFF.md."
            ),
        },
        "placeholders": {
            level: scenario_placeholders_json(level)
            for level in ("low", "base", "high")
        },
        "trace_checksums": {f: traces[f].checksum() for f in sorted(traces)},
        "reports": reports,
    }


def write_outputs(doc: dict, out_dir: Path, traces_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reports.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True) + "\n"
    )
    lines = ["\t".join(TSV_COLUMNS)]
    for report in doc["reports"]:
        lines.append(report_tsv_row(report, report["sensitivity"]))
    (out_dir / "summary.tsv").write_text("\n".join(lines) + "\n")
    checksums = {
        "schema_version": doc["schema_version"],
        "trace_seed": doc["scenario"]["trace_seed"],
        "horizon_seconds": doc["scenario"]["horizon_seconds"],
        "mean_rate_per_s": doc["scenario"]["mean_rate_per_s"],
        "n_models": doc["scenario"]["n_models"],
        "sha256": doc["trace_checksums"],
    }
    (traces_dir / "CHECKSUMS.json").write_text(
        json.dumps(checksums, indent=1, sort_keys=True) + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="short smoke run")
    parser.add_argument("--out-dir", default=str(HERE / "results"))
    args = parser.parse_args()
    doc = run_matrix(quick=args.quick)
    write_outputs(doc, Path(args.out_dir), HERE / "traces")
    print(f"wrote {len(doc['reports'])} reports to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
