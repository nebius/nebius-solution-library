from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from timing_evidence import TimingEvidenceError, build_timing_evidence  # noqa: E402


def fixtures() -> tuple[dict, dict, dict]:
    run = {"demand_at": "2026-08-18T00:00:00Z"}
    semantic = {
        "status": "PASS",
        "ok": True,
        "request_count": 2,
        "base_url": "http://canary:8000",
        "started_at": "2026-08-18T00:00:01Z",
        "finished_at": "2026-08-18T00:00:05Z",
        "passed_case_count": 2,
        "failed_case_count": 0,
        "ready": {
            "status": "PASS",
            "endpoint": "http://canary:8000/v1/health/ready",
            "started_at": "2026-08-18T00:00:01Z",
            "finished_at": "2026-08-18T00:00:02Z",
        },
        "cases": [
            {"status": "PASS", "ok": True, "elapsed_seconds": 2.5},
            {"status": "PASS", "ok": True, "elapsed_seconds": 0.4},
        ],
    }
    target = {
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "True",
                    "lastTransitionTime": "2026-08-18T00:00:03Z",
                }
            ]
        }
    }
    return run, semantic, target


class TimingEvidenceTests(unittest.TestCase):
    def test_exposes_http_kubernetes_call_and_cross_check_timings(self) -> None:
        result = build_timing_evidence(*fixtures())
        self.assertEqual(result["demand_to_http_ready_seconds"], 2.0)
        self.assertEqual(result["demand_to_kubernetes_ready_seconds"], 3.0)
        self.assertEqual(result["semantic_request_1_seconds"], 2.5)
        self.assertEqual(result["semantic_request_2_seconds"], 0.4)
        self.assertEqual(result["demand_to_two_semantic_seconds"], 5.0)

    def test_http_readiness_and_worker_receipt_have_no_shared_order(self) -> None:
        run, semantic, target = fixtures()
        # No worker receipt is an input: semantic readiness is an independent timeline.
        result = build_timing_evidence(run, semantic, target)
        self.assertEqual(result["demand_to_http_ready_seconds"], 2.0)

    def test_rejects_failed_or_misbound_http_readiness(self) -> None:
        run, semantic, target = fixtures()
        for mutation in ("failed", "misbound"):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(semantic)
                if mutation == "failed":
                    changed["ready"]["status"] = "FAIL"
                else:
                    changed["ready"]["endpoint"] = "http://other:8000/v1/health/ready"
                with self.assertRaises(TimingEvidenceError):
                    build_timing_evidence(run, changed, target)

    def test_rejects_http_readiness_after_second_call(self) -> None:
        run, semantic, target = fixtures()
        semantic["ready"]["finished_at"] = "2026-08-18T00:00:06Z"
        with self.assertRaisesRegex(TimingEvidenceError, "monotonically ordered"):
            build_timing_evidence(run, semantic, target)

    def test_accepts_ready_wait_and_ready_at_encodings(self) -> None:
        run, semantic, target = fixtures()
        semantic["ready_wait"] = semantic.pop("ready")
        self.assertEqual(
            build_timing_evidence(run, semantic, target)[
                "demand_to_http_ready_seconds"
            ],
            2.0,
        )

        semantic.pop("ready_wait")
        semantic["ready_at"] = "2026-08-18T00:00:02Z"
        self.assertEqual(
            build_timing_evidence(run, semantic, target)[
                "demand_to_http_ready_seconds"
            ],
            2.0,
        )

    def test_normalizes_only_subsecond_kubernetes_timestamp_quantization(self) -> None:
        run, semantic, target = fixtures()
        run["demand_at"] = "2026-08-18T00:00:00.900000Z"
        target["status"]["conditions"][0]["lastTransitionTime"] = (
            "2026-08-18T00:00:00Z"
        )
        result = build_timing_evidence(run, semantic, target)
        self.assertEqual(result["demand_to_kubernetes_ready_seconds"], 0.0)
        self.assertEqual(
            result["timing_evidence"]["kubernetes_ready_at"],
            "2026-08-18T00:00:00Z",
        )

        target["status"]["conditions"][0]["lastTransitionTime"] = (
            "2026-08-17T23:59:59Z"
        )
        with self.assertRaisesRegex(TimingEvidenceError, "at least one second"):
            build_timing_evidence(run, semantic, target)


if __name__ == "__main__":
    unittest.main()
