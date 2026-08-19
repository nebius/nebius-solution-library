from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.catalog import build_catalog  # noqa: E402
from catalog_sim.report import nearest_rank  # noqa: E402
from catalog_sim.schema import SchemaError  # noqa: E402
from catalog_sim.traces import (  # noqa: E402
    TRACE_FAMILIES,
    generate_all,
    generate_trace,
)

SIM_DIR = Path(__file__).resolve().parents[1]


class TraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog, _ = build_catalog(200, "base")
        cls.model_ids = sorted(catalog)

    def test_all_five_families_exist(self):
        self.assertEqual(
            set(TRACE_FAMILIES),
            {"uniform", "zipf", "bursty", "correlated", "adversarial"},
        )

    def test_traces_deterministic_and_checksummed(self):
        for family in TRACE_FAMILIES:
            t1 = generate_trace(family, self.model_ids, horizon_seconds=600.0)
            t2 = generate_trace(family, self.model_ids, horizon_seconds=600.0)
            self.assertEqual(t1.checksum(), t2.checksum(), family)
            self.assertEqual(len(t1.checksum()), 64, family)

    def test_arrivals_sorted_and_in_horizon(self):
        for family in TRACE_FAMILIES:
            trace = generate_trace(family, self.model_ids, horizon_seconds=600.0)
            self.assertGreater(len(trace.requests), 0, family)
            arrivals = [t for t, _ in trace.requests]
            self.assertEqual(arrivals, sorted(arrivals), family)
            self.assertLessEqual(arrivals[-1], trace.horizon_micros, family)
            for _, model_id in trace.requests:
                self.assertIn(model_id, self.model_ids)

    def test_zipf_is_skewed_uniform_is_not(self):
        zipf = generate_trace("zipf", self.model_ids, horizon_seconds=3600.0)
        uniform = generate_trace("uniform", self.model_ids, horizon_seconds=3600.0)

        def top_share(trace, k=10):
            counts = {}
            for _, m in trace.requests:
                counts[m] = counts.get(m, 0) + 1
            top = sorted(counts.values(), reverse=True)[:k]
            return sum(top) / len(trace.requests)

        self.assertGreater(top_share(zipf), top_share(uniform) + 0.10)

    def test_adversarial_alternates_working_sets(self):
        trace = generate_trace("adversarial", self.model_ids, horizon_seconds=1200.0)
        half = len(self.model_ids) // 2
        set_a = set(self.model_ids[:half])
        for t, model_id in trace.requests:
            phase = int((t / 1_000_000) // 240.0) % 2
            self.assertEqual(model_id in set_a, phase == 0, (t, model_id))

    def test_unknown_family_rejected(self):
        with self.assertRaises(SchemaError):
            generate_trace("chaos", self.model_ids)

    def test_pinned_checksums_match_regeneration(self):
        checksum_path = SIM_DIR / "traces" / "CHECKSUMS.json"
        if not checksum_path.exists():
            self.skipTest("traces/CHECKSUMS.json not generated yet")
        pinned = json.loads(checksum_path.read_text())
        traces = generate_all(
            self.model_ids,
            horizon_seconds=pinned["horizon_seconds"],
            mean_rate_per_s=pinned["mean_rate_per_s"],
            seed=pinned["trace_seed"],
        )
        for family, trace in traces.items():
            self.assertEqual(
                trace.checksum(), pinned["sha256"][family], family
            )


class NearestRankReportTest(unittest.TestCase):
    def test_matches_repo_convention(self):
        ordered = sorted([3_000_000, 1_000_000, 2_000_000, 4_000_000])
        self.assertEqual(nearest_rank(ordered, 0, 50), 2.0)
        self.assertEqual(nearest_rank(ordered, 0, 95), 4.0)

    def test_failed_requests_sort_after_successes(self):
        ordered = [1_000_000] * 18
        # 18 successes + 2 unbounded failures: p95 rank 19 lands on a failure.
        self.assertIsNone(nearest_rank(ordered, 2, 95))
        self.assertEqual(nearest_rank(ordered, 2, 50), 1.0)

    def test_empty_is_none(self):
        self.assertIsNone(nearest_rank([], 0, 50))


if __name__ == "__main__":
    unittest.main()
