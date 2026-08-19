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
            request_count=60,
            interval_ms=900_000,
            trace_id="arm-a-a2b-local-test",
            seed=2407,
        )
        self.assertEqual(len(validate_trace(trace)["requests"]), 60)
        self.assertEqual(
            {
                model: sum(
                    item["target"]["model_id"] == model for item in trace["requests"]
                )
                for model in ("boltz2", "openfold2")
            },
            {"boltz2": 30, "openfold2": 30},
        )
        for previous, current in zip(trace["requests"], trace["requests"][1:]):
            self.assertEqual(
                current["precondition"]["current_node_occupant"],
                {
                    "model_id": previous["target"]["model_id"],
                    "model_version": previous["target"]["model_version"],
                },
            )

    def test_promoted_trace_cannot_have_twenty_nine_attempts(self) -> None:
        with self.assertRaisesRegex(ValueError, "30 requests per target"):
            build_trace(
                self.catalog,
                scenario="a_to_b_local",
                request_count=59,
                interval_ms=900_000,
                trace_id="undersized",
                seed=2407,
            )

    def test_offered_interval_preserves_recorder_ceiling(self) -> None:
        with self.assertRaisesRegex(ValueError, "100 ms"):
            build_trace(
                self.catalog,
                scenario="a_to_b_local",
                request_count=60,
                interval_ms=99,
                trace_id="bad-interval",
                seed=2407,
            )

    def test_each_arm_a_scenario_has_a_coherent_next_precondition(self) -> None:
        for scenario in (
            "idle_local", "a_to_b_local", "a_to_b_remote",
            "checkpoint_fallback", "capacity_miss",
        ):
            with self.subTest(scenario=scenario):
                trace = build_trace(
                    self.catalog, scenario=scenario, request_count=60,
                    interval_ms=100, trace_id=f"coherent-{scenario}", seed=2407,
                )
                for previous, current in zip(trace["requests"], trace["requests"][1:]):
                    occupant = current["precondition"]["current_node_occupant"]
                    if scenario in {"a_to_b_local", "a_to_b_remote", "checkpoint_fallback"}:
                        self.assertEqual(
                            occupant,
                            {
                                "model_id": previous["target"]["model_id"],
                                "model_version": previous["target"]["model_version"],
                            },
                        )
                    else:
                        self.assertIsNone(occupant)

    def test_same_model_hot_uses_one_model_per_independent_cohort(self) -> None:
        one_model = {"schema": self.catalog["schema"], "models": [self.catalog["models"][0]]}
        trace = build_trace(
            one_model, scenario="same_model_hot", request_count=30, interval_ms=100,
            trace_id="hot-boltz2", seed=2407,
        )
        self.assertEqual(len(trace["requests"]), 30)
        for request in trace["requests"]:
            self.assertEqual(
                request["precondition"]["current_node_occupant"],
                {
                    "model_id": request["target"]["model_id"],
                    "model_version": request["target"]["model_version"],
                },
            )

    def test_arm_b_success_remains_fail_closed_on_shared_v1_trace_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot represent successful new-node demand"):
            build_trace(
                self.catalog, scenario="a_to_b_remote", request_count=60,
                interval_ms=100, trace_id="arm-b-planned", seed=2407,
                campaign_arm="B_new_preemptible_node",
            )


if __name__ == "__main__":
    unittest.main()
