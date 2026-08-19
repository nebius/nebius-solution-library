from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "live" / "internal_scout_server_v3.py"
SPEC = importlib.util.spec_from_file_location("internal_scout_server_v3", MODULE_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def line(value):
    return b"data: " + json.dumps(value).encode() + b"\n"


class InternalScoutServerV3Tests(unittest.TestCase):
    def test_stream_oracle_records_complete_exact_semantic_verdict(self):
        oracle = server.StreamOracle()
        oracle.feed(
            line(
                {
                    "model": server.MODEL_ID,
                    "choices": [{"delta": {"content": server.EXPECTED_ANSWER}}],
                }
            )
        )
        oracle.feed(b"data: [DONE]\n")
        response, valid, reason = oracle.verdict()
        self.assertTrue(valid)
        self.assertEqual("exact content matched", reason)
        self.assertEqual(server.MODEL_ID, response["model_id"])

    def test_stream_complete_without_semantic_match_is_rejected(self):
        oracle = server.StreamOracle()
        oracle.feed(
            line(
                {
                    "model": server.MODEL_ID,
                    "choices": [{"delta": {"content": "wrong"}}],
                }
            )
        )
        oracle.feed(b"data: [DONE]\n")
        _response, valid, reason = oracle.verdict()
        self.assertFalse(valid)
        self.assertEqual("exact content mismatch", reason)

    def test_first_request_does_not_require_an_active_runtime(self):
        server.validate_transition(None, "runtime-1", "attempt-1", 1)

    def test_second_request_requires_same_runtime_group_and_distinct_attempt(self):
        active = {
            "runtime_group_id": "runtime-1",
            "requests": [{"attempt_id": "attempt-1"}],
        }
        server.validate_transition(active, "runtime-1", "attempt-2", 2)
        with self.assertRaisesRegex(ValueError, "changed runtime group"):
            server.validate_transition(active, "runtime-2", "attempt-2", 2)
        with self.assertRaisesRegex(ValueError, "distinct attempt"):
            server.validate_transition(active, "runtime-1", "attempt-1", 2)

    def test_single_request_cannot_claim_pair_qualification(self):
        active = {"runtime_group_id": "runtime-1", "requests": []}
        with self.assertRaisesRegex(ValueError, "one prior result"):
            server.validate_transition(active, "runtime-1", "attempt-2", 2)

    def test_reasoning_content_is_not_silently_accepted_in_nonthinking_arm(self):
        oracle = server.StreamOracle()
        oracle.feed(
            line(
                {
                    "model": server.MODEL_ID,
                    "choices": [
                        {
                            "delta": {
                                "reasoning_content": "hidden reasoning",
                                "content": server.EXPECTED_ANSWER,
                            }
                        }
                    ],
                }
            )
        )
        oracle.feed(b"data: [DONE]\n")
        self.assertFalse(oracle.verdict()[1])


if __name__ == "__main__":
    unittest.main()
