import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "costmodel"))
import lib  # noqa: E402


class NearestRankTest(unittest.TestCase):
    def test_percentiles(self):
        vals = [Decimal(i) for i in range(1, 21)]
        self.assertEqual(lib.nearest_rank(vals, 50), Decimal(10))
        self.assertEqual(lib.nearest_rank(vals, 95), Decimal(19))
        self.assertEqual(lib.nearest_rank(vals, 99), Decimal(20))
        self.assertEqual(lib.nearest_rank(vals, 100), Decimal(20))

    def test_empty_fails(self):
        with self.assertRaises(lib.InputError):
            lib.nearest_rank([], 50)

    def test_goodput(self):
        vals = [Decimal("1"), Decimal("2"), Decimal("30")]
        self.assertEqual(lib.goodput_within(vals, Decimal(20)),
                         Decimal("0.6667"))
        self.assertEqual(lib.goodput_within(vals, Decimal(30)),
                         Decimal("1.0000"))


class CostMathTest(unittest.TestCase):
    def test_gpu_seconds_cost_exact(self):
        # 3600 s at $3.85/h is exactly $3.85.
        self.assertEqual(lib.gpu_seconds_cost(Decimal(3600), Decimal("3.85")),
                         Decimal("3.850000"))
        # 30 s at $2.15/h = 2.15/120.
        self.assertEqual(lib.gpu_seconds_cost(Decimal(30), Decimal("2.15")),
                         Decimal("0.017917"))

    def test_retry_multiplier(self):
        self.assertEqual(lib.retry_multiplier(Decimal(0)), Decimal(1))
        self.assertEqual(lib.retry_multiplier(Decimal("0.5")), Decimal(2))
        for bad in (Decimal(1), Decimal("-0.1"), Decimal("1.5")):
            with self.assertRaises(lib.InputError):
                lib.retry_multiplier(bad)

    def test_preemption_breakeven_h100(self):
        be = lib.preemption_breakeven(Decimal("2.15"), Decimal("3.85"))
        self.assertEqual(be, Decimal("0.44155844"))
        # Sanity: expected preemptible cost at break-even equals on-demand.
        attempt = lib.gpu_seconds_cost(Decimal(3600), Decimal("2.15"))
        exp = lib.expected_cost_per_success(attempt, be)
        self.assertAlmostEqual(float(exp), 3.85, places=5)

    def test_warm_breakeven(self):
        self.assertEqual(
            lib.warm_breakeven_requests_per_month(Decimal("2810.5"),
                                                  Decimal("0.01")),
            Decimal("281050.00"))
        with self.assertRaises(lib.InputError):
            lib.warm_breakeven_requests_per_month(Decimal(1), Decimal(0))

    def test_storage_breakeven(self):
        be = lib.storage_breakeven_refetches_per_gib_month(
            Decimal("0.08"), Decimal("0.0147"), Decimal("0.015"))
        self.assertEqual(be, Decimal("4.3533"))


class RepriceTest(unittest.TestCase):
    REPORT = {
        "trace_family": "t", "policy": "p", "sensitivity": "base",
        "n_requests": 10, "n_completed": 10, "n_failed": 0,
        "latency_seconds": {"p50": 1.0, "p95": 2.0, "p99": 3.0},
        "slo_goodput": {"within_30s": 1.0},
        "cache": {"hot_hit_rate": 0.5},
        "gpu": {"reserved_gpu_hours": 2.0, "utilization": 0.5},
        "bytes": {"fetched_gib": 100.0},
    }

    def test_exact_repricing(self):
        out = lib.reprice_simulator_report(
            self.REPORT, {"on_demand": Decimal("3.85"),
                          "preemptible": Decimal("2.15")}, Decimal("0.015"))
        billed = out["cost_usd"]["preemptible/egress_billed"]
        self.assertEqual(billed["gpu"], "4.300000")
        self.assertEqual(billed["egress"], "1.500000")
        self.assertEqual(billed["total"], "5.800000")
        self.assertEqual(billed["per_1000_completed"], "580.000000")
        free = out["cost_usd"]["on_demand/egress_free"]
        self.assertEqual(free["total"], "7.700000")
        self.assertEqual(free["egress"], "0.000000")

    def test_zero_completed_fails(self):
        bad = dict(self.REPORT, n_completed=0)
        with self.assertRaises(lib.InputError):
            lib.reprice_simulator_report(bad, {"on_demand": Decimal(1)},
                                         Decimal(0))


if __name__ == "__main__":
    unittest.main()
