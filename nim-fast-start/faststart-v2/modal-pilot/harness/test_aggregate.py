#!/usr/bin/env python3
"""Offline tests for fail-closed Modal pilot cohort aggregation."""

from __future__ import annotations

import unittest

from .aggregate import (
    PROMOTION_MIN_N,
    AggregationError,
    aggregate_cohort,
    conservative_percentile,
)
from .test_event_schema import make_event


def cohort(n_valid, n_failed=0, mode="cold", base_latency=100.0):
    events = []
    for index in range(n_valid):
        events.append(
            make_event(
                run_id=f"r{index}",
                mode=mode,
                t0_monotonic_s=0.0,
                t_first_valid_response_monotonic_s=base_latency + index,
            )
        )
    for index in range(n_failed):
        events.append(
            make_event(
                run_id=f"f{index}",
                mode=mode,
                outcome="timeout",
                failure_reason="startup_timeout",
            )
        )
    return events


class ConservativePercentileTest(unittest.TestCase):
    def test_nearest_rank_is_an_observed_sample(self):
        samples = [float(v) for v in range(1, 21)]  # 1..20
        self.assertEqual(conservative_percentile(samples, 50), 10.0)
        self.assertEqual(conservative_percentile(samples, 95), 19.0)
        self.assertEqual(conservative_percentile(samples, 100), 20.0)

    def test_rejects_empty_and_bad_percentile(self):
        with self.assertRaises(AggregationError):
            conservative_percentile([], 50)
        with self.assertRaises(AggregationError):
            conservative_percentile([1.0], 0)


class AggregateCohortTest(unittest.TestCase):
    def test_percentile_gates_fail_closed(self):
        summary = aggregate_cohort(cohort(4))
        self.assertIsNone(summary["latency_s"]["p50"])
        summary = aggregate_cohort(cohort(19))
        self.assertIsNotNone(summary["latency_s"]["p50"])
        self.assertIsNone(summary["latency_s"]["p95"])
        summary = aggregate_cohort(cohort(99))
        self.assertIsNotNone(summary["latency_s"]["p95"])
        self.assertIsNone(summary["latency_s"]["p99"])
        summary = aggregate_cohort(cohort(100))
        self.assertIsNotNone(summary["latency_s"]["p99"])

    def test_promoted_cold_requires_30_valid(self):
        with self.assertRaises(AggregationError):
            aggregate_cohort(cohort(PROMOTION_MIN_N - 1), promoted=True)
        summary = aggregate_cohort(cohort(PROMOTION_MIN_N), promoted=True)
        self.assertEqual(summary["n_valid"], PROMOTION_MIN_N)

    def test_failures_are_reported_not_dropped(self):
        summary = aggregate_cohort(cohort(30, n_failed=5))
        self.assertEqual(summary["n_total"], 35)
        self.assertEqual(summary["n_failures"], 5)
        self.assertEqual(summary["failure_reasons"], ["startup_timeout"])

    def test_rejects_mixed_cohorts_and_empty(self):
        mixed = cohort(2) + cohort(2, mode="switch")
        with self.assertRaises(AggregationError):
            aggregate_cohort(mixed)
        with self.assertRaises(AggregationError):
            aggregate_cohort([])


if __name__ == "__main__":
    unittest.main()
