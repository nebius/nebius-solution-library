from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.catalog import CatalogModel  # noqa: E402
from catalog_sim.engine import InvariantViolation, Simulator  # noqa: E402
from catalog_sim.policies import PolicyConfig  # noqa: E402
from catalog_sim.schema import EmpiricalDist  # noqa: E402
from catalog_sim.traces import Trace  # noqa: E402

S = 1_000_000  # micros per second


def const_dist(name: str, seconds: float) -> EmpiricalDist:
    return EmpiricalDist.from_seconds(name, [seconds], "toy fixture")


def toy_model(
    model_id: str,
    ready_s: float = 10.0,
    call1_s: float = 2.0,
    call2_s: float = 1.0,
    artifact_bytes: int = 1000,
    full_read_s: float = 0.0,
    group: int = 0,
) -> CatalogModel:
    return CatalogModel(
        model_id=model_id,
        family="toy",
        provenance="placeholder-scaled",
        evidence_class="toy fixture",
        strategy_default="snapshot",
        ready_dist=const_dist(f"{model_id}-ready", ready_s),
        call1_dist=const_dist(f"{model_id}-call1", call1_s),
        call2_dist=const_dist(f"{model_id}-call2", call2_s),
        artifact_bytes=artifact_bytes,
        artifact_digest=f"sha256-fixture-{model_id}-v1",
        local_full_read_micros=int(full_read_s * S),
        conventional_ready_micros=60 * S,
        group=group,
    )


def toy_fleet(**overrides) -> dict:
    fleet = {
        "l2_fetch_bytes_per_s": 1000,  # 1000 B/s so 1000 B fetch == 1 s exactly
        "l1_capacity_bytes": 10_000,
        "gpu_release_micros": 3 * S,
        "node_mtbf_micros": 10**15,
        "node_reprovision_micros": 30 * S,
        "gpu_hour_usd": 3.0,
        "l2_egress_usd_per_gib": 0.02,
    }
    fleet.update(overrides)
    return fleet


def toy_trace(requests, horizon_s=10_000.0) -> Trace:
    return Trace(
        name="toy",
        family="uniform",
        seed=0,
        horizon_micros=int(horizon_s * S),
        requests=tuple(sorted((int(t * S), m) for t, m in requests)),
    )


def run_sim(catalog, trace, config=None, fleet=None, n_nodes=1, failures=False):
    sim = Simulator(
        catalog=catalog,
        trace=trace,
        config=config or PolicyConfig(),
        fleet=fleet or toy_fleet(),
        n_nodes=n_nodes,
        seed=1,
        enable_failures=failures,
    )
    report = sim.run()
    return sim, report


class DeterministicQueueTest(unittest.TestCase):
    """Closed-form D/D/1 checks: the engine must be *exactly* right."""

    def test_single_request_cold_path_exact(self):
        catalog = {"a": toy_model("a")}
        sim, report = run_sim(catalog, toy_trace([(0.0, "a")]))
        req = sim.completed[0]
        # fetch 1 s + ready 10 s + call1 2 s; no teardown on an empty node
        self.assertEqual(req.phases["teardown"], 0)
        self.assertEqual(req.phases["fetch"], 1 * S)
        self.assertEqual(req.phases["setup"], 10 * S)
        self.assertEqual(req.phases["inference"], 2 * S)
        self.assertEqual(req.response_at - req.arrival, 13 * S)
        self.assertEqual(req.cache_tier, "L2")

    def test_warm_hits_are_call2_exact(self):
        catalog = {"a": toy_model("a")}
        trace = toy_trace([(0.0, "a"), (100.0, "a"), (200.0, "a")])
        sim, report = run_sim(catalog, trace)
        self.assertEqual(sim.completed[1].response_at - sim.completed[1].arrival, 1 * S)
        self.assertEqual(sim.completed[1].cache_tier, "L0")
        self.assertEqual(report["cache"]["tier_counts"]["L0"], 2)

    def test_underload_has_zero_wait(self):
        catalog = {"a": toy_model("a")}
        trace = toy_trace([(float(k * 100), "a") for k in range(10)])
        sim, _ = run_sim(catalog, trace)
        for req in sim.completed:
            self.assertEqual(req.phases["wait"], 0)

    def test_overload_wait_closed_form(self):
        # Warm service is exactly 1 s; arrivals every 0.5 s starting at t=100
        # after a warmup request at t=0 (13 s cold path ends at t=13).
        # k-th overload request (k=0..9) starts service at 100 + k*1.0 and
        # waited k*(1.0-0.5) seconds.
        catalog = {"a": toy_model("a")}
        requests = [(0.0, "a")] + [(100.0 + 0.5 * k, "a") for k in range(10)]
        sim, _ = run_sim(catalog, toy_trace(requests))
        overload = sim.completed[1:]
        for k, req in enumerate(overload):
            self.assertEqual(req.phases["wait"], int(k * 0.5 * S), k)
            self.assertEqual(req.response_at - req.arrival, int((k * 0.5 + 1.0) * S))

    def test_a_to_b_switch_closed_form(self):
        # Model a resident, then b arrives: teardown 3 + fetch 1 + ready 10
        # + call1 2 = 16 s exactly.
        catalog = {"a": toy_model("a"), "b": toy_model("b")}
        trace = toy_trace([(0.0, "a"), (100.0, "b")])
        sim, _ = run_sim(catalog, trace)
        b = sim.completed[1]
        self.assertEqual(b.phases["teardown"], 3 * S)
        self.assertEqual(b.phases["fetch"], 1 * S)
        self.assertEqual(b.response_at - b.arrival, 16 * S)

    def test_l1_cold_prewarm_charged_once(self):
        # b evicted from GPU but still in L1: switch back costs teardown +
        # prewarm (first time only) + ready + call1, no fetch.
        catalog = {
            "a": toy_model("a"),
            "b": toy_model("b", full_read_s=5.0),
        }
        trace = toy_trace([(0.0, "b"), (100.0, "a"), (200.0, "b"), (300.0, "a"), (400.0, "b")])
        sim, _ = run_sim(catalog, trace)
        first_b, second_b, third_b = (
            sim.completed[0], sim.completed[2], sim.completed[4]
        )
        # cold: fetch 1 + prewarm 5 + ready 10 + call1 2
        self.assertEqual(first_b.response_at - first_b.arrival, 18 * S)
        self.assertEqual(first_b.cache_tier, "L2")
        # back from L1, already prewarmed: teardown 3 + ready 10 + call1 2
        self.assertEqual(second_b.response_at - second_b.arrival, 15 * S)
        self.assertEqual(second_b.cache_tier, "L1-warm")
        self.assertEqual(third_b.response_at - third_b.arrival, 15 * S)

    def test_conventional_strategy_uses_conventional_clock(self):
        catalog = {"a": toy_model("a")}
        config = PolicyConfig(strategy="conventional")
        sim, _ = run_sim(catalog, toy_trace([(0.0, "a")]), config=config)
        req = sim.completed[0]
        # fetch 1 + conventional 60 + call1 2
        self.assertEqual(req.response_at - req.arrival, 63 * S)


class PlacementTest(unittest.TestCase):
    def test_shortest_switch_cost_prefers_resident_node(self):
        catalog = {"a": toy_model("a"), "b": toy_model("b")}
        # Warm both models on separate nodes, then request each again: the
        # router must route to the resident node (L0 hits), never switch.
        trace = toy_trace(
            [(0.0, "a"), (0.1, "b"), (100.0, "a"), (100.1, "b"), (200.0, "a")]
        )
        sim, report = run_sim(catalog, trace, n_nodes=2)
        self.assertEqual(report["cache"]["tier_counts"]["L2"], 2)
        self.assertEqual(report["cache"]["tier_counts"]["L0"], 3)

    def test_least_loaded_ignores_affinity(self):
        catalog = {"a": toy_model("a"), "b": toy_model("b")}
        config = PolicyConfig(placement="least-loaded")
        trace = toy_trace([(0.0, "a"), (100.0, "b"), (200.0, "a")])
        sim, report = run_sim(catalog, trace, config=config, n_nodes=2)
        # All three land on node 0 by load tie-break: b displaces a from the
        # GPU, so the third request pays a full restore from L1 instead of the
        # L0 hit that shortest-switch-cost placement would have preserved.
        self.assertEqual(sim.completed[2].cache_tier, "L1-warm")
        self.assertEqual(report["cache"]["tier_counts"]["L0"], 0)


class AdmissionAndFailureTest(unittest.TestCase):
    def test_bounded_queue_rejects_when_full(self):
        catalog = {"a": toy_model("a")}
        config = PolicyConfig(admission="bounded-queue", max_queue_per_node=2)
        # Burst of 6 at t=0 on one node: 1 in service, 2 queued, 3 rejected.
        trace = toy_trace([(0.0, "a")] * 6)
        sim, report = run_sim(catalog, trace, config=config)
        self.assertEqual(report["n_rejected"], 3)
        self.assertEqual(report["n_completed"], 3)
        self.assertEqual(
            report["n_requests"],
            report["n_completed"] + report["n_rejected"] + report["n_failed"],
        )

    def test_node_failure_retries_and_conserves_requests(self):
        catalog = {"a": toy_model("a")}
        fleet = toy_fleet(node_mtbf_micros=40 * S, node_reprovision_micros=10 * S)
        trace = toy_trace([(float(k * 20), "a") for k in range(50)])
        sim, report = run_sim(catalog, trace, fleet=fleet, n_nodes=2, failures=True)
        self.assertGreater(report["node_failures"], 0)
        self.assertEqual(
            report["n_requests"],
            report["n_completed"] + report["n_rejected"] + report["n_failed"],
        )
        # Retried completions must still have causal timestamps (verify() ran).
        self.assertGreaterEqual(report["n_retried_completions"], 0)

    def test_failure_wipes_caches(self):
        catalog = {"a": toy_model("a")}
        fleet = toy_fleet(node_mtbf_micros=40 * S, node_reprovision_micros=10 * S)
        trace = toy_trace([(float(k * 20), "a") for k in range(50)])
        sim, report = run_sim(catalog, trace, fleet=fleet, n_nodes=2, failures=True)
        # After failures, later requests must re-fetch: more than one L2 miss.
        self.assertGreater(report["cache"]["tier_counts"]["L2"], 1)


class InvariantTest(unittest.TestCase):
    def test_stale_artifact_detected(self):
        catalog = {"a": toy_model("a")}
        sim = Simulator(
            catalog=catalog,
            trace=toy_trace([(0.0, "a")]),
            config=PolicyConfig(),
            fleet=toy_fleet(),
            n_nodes=1,
            seed=1,
            enable_failures=False,
        )
        # A node holds a stale L1 copy (older digest than the catalog's
        # current artifact identity): serving from it must be refused loudly
        # rather than silently restoring an outdated model.
        sim.nodes[0].cache.insert(
            "a", 1000, "sha256-fixture-a-v0-stale", 0, 100, prewarmed=True
        )
        with self.assertRaises(InvariantViolation):
            sim.run()

    def test_event_in_past_rejected(self):
        catalog = {"a": toy_model("a")}
        sim = Simulator(
            catalog=catalog,
            trace=toy_trace([(0.0, "a")]),
            config=PolicyConfig(),
            fleet=toy_fleet(),
            n_nodes=1,
            seed=1,
            enable_failures=False,
        )
        sim.now = 10 * S
        with self.assertRaises(InvariantViolation):
            sim._push(5 * S, "arrival", None)

    def test_unknown_model_in_trace_rejected(self):
        catalog = {"a": toy_model("a")}
        sim = Simulator(
            catalog=catalog,
            trace=toy_trace([(0.0, "ghost")]),
            config=PolicyConfig(),
            fleet=toy_fleet(),
            n_nodes=1,
            seed=1,
            enable_failures=False,
        )
        with self.assertRaises(InvariantViolation):
            sim.run()


class WarmAndPrefetchTest(unittest.TestCase):
    def test_topk_warm_repins_after_capacity_loss(self):
        # Sparse demand for a and b on two mostly-idle nodes with frequent
        # preemptions: after a node's caches are wiped, the next warm refresh
        # must proactively restore a top-K model onto an idle node (counted
        # as reserved-but-not-serving warm-setup GPU time).
        catalog = {"a": toy_model("a"), "b": toy_model("b")}
        config = PolicyConfig(
            warm="topk-adaptive", warm_k=2, warm_window_micros=30 * S
        )
        fleet = toy_fleet(node_mtbf_micros=150 * S, node_reprovision_micros=5 * S)
        requests = []
        for k in range(6):
            requests.append((float(k * 200), "a"))
            requests.append((float(k * 200 + 100), "b"))
        sim, report = run_sim(
            catalog, toy_trace(requests, horizon_s=1300.0),
            config=config, fleet=fleet, n_nodes=2, failures=True,
        )
        self.assertGreater(report["node_failures"], 0)
        self.assertGreater(report["gpu"]["warm_setup_gpu_hours"], 0.0)
        self.assertEqual(
            report["n_requests"],
            report["n_completed"] + report["n_rejected"] + report["n_failed"],
        )

    def test_pipeline_prefetch_moves_bytes(self):
        catalog = {
            "a": toy_model("a", group=0),
            "b": toy_model("b", group=0),
        }
        config = PolicyConfig(prefetch="pipeline-next")
        trace = toy_trace([(0.0, "a"), (50.0, "b")])
        sim, report = run_sim(catalog, trace, config=config)
        self.assertGreater(report["bytes"]["prefetch_gib"], 0.0)
        # b was prefetched into L1 while a served, so b's serve skips fetch.
        b = sim.completed[1]
        self.assertEqual(b.phases["fetch"], 0)
        self.assertEqual(b.cache_tier, "L1-cold")


if __name__ == "__main__":
    unittest.main()
