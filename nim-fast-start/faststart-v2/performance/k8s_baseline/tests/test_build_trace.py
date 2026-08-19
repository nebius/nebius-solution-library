from __future__ import annotations

import json
import unittest
from pathlib import Path

from performance.k8s_baseline.build_trace import build_trace
from performance.request_slo.harness import validate_trace


ROOT = Path(__file__).resolve().parents[1]


class BuildTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads((ROOT / "experiment-catalog.json").read_text())

    def test_promoted_a_to_b_trace_alternates_natural_occupants(self) -> None:
        trace = build_trace(
            self.catalog,
            scenario="a_to_b_local",
            request_count=30,
            interval_ms=900_000,
            trace_id="arm-a-a2b-local-test",
            seed=2407,
        )
        self.assertEqual(len(validate_trace(trace)["requests"]), 30)
        for previous, current in zip(trace["requests"], trace["requests"][1:]):
            self.assertEqual(
                current["precondition"]["current_node_occupant"],
                {
                    "model_id": previous["target"]["model_id"],
                    "model_version": previous["target"]["model_version"],
                },
            )

    def test_promoted_trace_cannot_have_twenty_nine_attempts(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 30"):
            build_trace(
                self.catalog,
                scenario="a_to_b_local",
                request_count=29,
                interval_ms=900_000,
                trace_id="undersized",
                seed=2407,
            )

    def test_offered_interval_preserves_recorder_ceiling(self) -> None:
        with self.assertRaisesRegex(ValueError, "100 ms"):
            build_trace(
                self.catalog,
                scenario="a_to_b_local",
                request_count=30,
                interval_ms=99,
                trace_id="bad-interval",
                seed=2407,
            )


if __name__ == "__main__":
    unittest.main()
