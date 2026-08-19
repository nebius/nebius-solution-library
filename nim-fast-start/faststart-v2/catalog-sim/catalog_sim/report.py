"""Result aggregation: percentiles, SLO goodput, hit rates, bytes, cost.

Percentiles use the repository's nearest-rank convention (1-indexed rank
``ceil(p/100 * n)``) with failed/rejected requests sorted after successful
samples, mirroring ``aggregate_fresh_cohort.py``. A failed or rejected request
therefore counts against tail percentiles as an unbounded latency instead of
silently leaving the denominator.
"""

from __future__ import annotations

import math
from typing import List, Optional

from .units import BYTES_PER_GIB, micros_to_hours, micros_to_seconds

PERCENTILES = (50, 95, 99)


def nearest_rank(
    ordered_finite: List[int], n_unbounded: int, p: float
) -> Optional[float]:
    """Nearest-rank percentile in seconds; None when the rank lands on an
    unbounded (failed/rejected) sample."""
    n = len(ordered_finite) + n_unbounded
    if n == 0:
        return None
    rank = max(1, min(n, math.ceil(p * n / 100)))
    if rank > len(ordered_finite):
        return None  # the rank falls on a failed/rejected request
    return micros_to_seconds(ordered_finite[rank - 1])


def build_report(sim) -> dict:
    latencies = sorted(r.response_at - r.arrival for r in sim.completed)
    n_unbounded = len(sim.rejected) + len(sim.failed)
    n_total = len(sim.requests)

    tiers = {"L0": 0, "L1-warm": 0, "L1-cold": 0, "L2": 0}
    phase_sums = {k: 0 for k in ("wait", "teardown", "fetch", "prewarm", "setup", "inference")}
    retried = 0
    for r in sim.completed:
        tiers[r.cache_tier] += 1
        for k in phase_sums:
            phase_sums[k] += r.phases.get(k, 0)
        if r.retries:
            retried += 1

    eviction_count = sum(n.cache.eviction_count for n in sim.nodes)
    evicted_bytes = sum(n.cache.evicted_bytes for n in sim.nodes)
    reserved_gpu_hours = sum(micros_to_hours(n.online_micros) for n in sim.nodes)
    busy_gpu_hours = sum(micros_to_hours(n.busy_micros) for n in sim.nodes)
    warm_gpu_hours = sum(micros_to_hours(n.warm_setup_micros) for n in sim.nodes)
    node_failures = sum(n.failures for n in sim.nodes)

    gpu_cost = reserved_gpu_hours * sim.fleet["gpu_hour_usd"]
    egress_cost = (
        sim.bytes_fetched_total / BYTES_PER_GIB * sim.fleet["l2_egress_usd_per_gib"]
    )

    report = {
        "trace": sim.trace.name,
        "trace_family": sim.trace.family,
        "trace_checksum": sim.trace.checksum(),
        "policy": sim.config.label(),
        "n_requests": n_total,
        "n_completed": len(sim.completed),
        "n_rejected": len(sim.rejected),
        "n_failed": len(sim.failed),
        "n_retried_completions": retried,
        "node_failures": node_failures,
        "latency_seconds": {
            f"p{p}": nearest_rank(latencies, n_unbounded, p) for p in PERCENTILES
        },
        "latency_max_seconds": (
            micros_to_seconds(latencies[-1]) if latencies else None
        ),
        "latency_mean_seconds": (
            micros_to_seconds(sum(latencies)) / len(latencies) if latencies else None
        ),
        "slo_goodput": {
            f"within_{int(s)}s": (
                sum(1 for v in latencies if v <= s * 1_000_000) / n_total
                if n_total
                else None
            )
            for s in sim.slo_seconds
        },
        "cache": {
            "tier_counts": tiers,
            "hot_hit_rate": tiers["L0"] / len(sim.completed) if sim.completed else None,
            "l1_hit_rate": (
                (tiers["L0"] + tiers["L1-warm"] + tiers["L1-cold"]) / len(sim.completed)
                if sim.completed
                else None
            ),
            "eviction_count": eviction_count,
            "evicted_gib": evicted_bytes / BYTES_PER_GIB,
        },
        "bytes": {
            "fetched_gib": sim.bytes_fetched_total / BYTES_PER_GIB,
            "prefetch_gib": sim.prefetch_bytes / BYTES_PER_GIB,
        },
        "gpu": {
            "reserved_gpu_hours": reserved_gpu_hours,
            "busy_gpu_hours": busy_gpu_hours,
            "warm_setup_gpu_hours": warm_gpu_hours,
            "utilization": (
                busy_gpu_hours / reserved_gpu_hours if reserved_gpu_hours else None
            ),
        },
        "cost_usd": {
            "gpu": gpu_cost,
            "l2_egress": egress_cost,
            "total": gpu_cost + egress_cost,
        },
        "phase_mean_seconds": {
            k: (micros_to_seconds(v) / len(sim.completed) if sim.completed else None)
            for k, v in phase_sums.items()
        },
    }
    return report


TSV_COLUMNS = (
    "trace_family",
    "policy",
    "sensitivity",
    "n_requests",
    "n_completed",
    "n_rejected",
    "n_failed",
    "p50_s",
    "p95_s",
    "p99_s",
    "goodput_30s",
    "goodput_60s",
    "goodput_120s",
    "hot_hit_rate",
    "l1_hit_rate",
    "evictions",
    "fetched_gib",
    "reserved_gpu_hours",
    "utilization",
    "cost_usd",
)


def report_tsv_row(report: dict, sensitivity: str) -> str:
    def fmt(value, digits=6):
        if value is None:
            return "unbounded"
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        return str(value)

    lat = report["latency_seconds"]
    slo = report["slo_goodput"]
    return "\t".join(
        (
            report["trace_family"],
            report["policy"],
            sensitivity,
            str(report["n_requests"]),
            str(report["n_completed"]),
            str(report["n_rejected"]),
            str(report["n_failed"]),
            fmt(lat["p50"]),
            fmt(lat["p95"]),
            fmt(lat["p99"]),
            fmt(slo["within_30s"], 4),
            fmt(slo["within_60s"], 4),
            fmt(slo["within_120s"], 4),
            fmt(report["cache"]["hot_hit_rate"], 4),
            fmt(report["cache"]["l1_hit_rate"], 4),
            str(report["cache"]["eviction_count"]),
            fmt(report["bytes"]["fetched_gib"], 2),
            fmt(report["gpu"]["reserved_gpu_hours"], 2),
            fmt(report["gpu"]["utilization"], 4),
            fmt(report["cost_usd"]["total"], 2),
        )
    )
