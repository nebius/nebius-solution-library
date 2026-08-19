from __future__ import annotations

import importlib.util
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "live" / "internal_scout_server_v4.py"
SPEC = importlib.util.spec_from_file_location("internal_scout_server_v4", MODULE_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def line(value):
    return b"data: " + json.dumps(value).encode() + b"\n"


class InternalScoutServerV4Tests(unittest.TestCase):
    def runtime_gate(self, token_value="a" * 64):
        payload = {
            "schema": "catalog-switch-internal-runtime-gate/v4",
            "authorization_sha256": "1" * 64,
            "clearance_expires_at": "2099-08-19T17:00:00Z",
            "health_proof_sha256": "2" * 64,
            "instance_id": "computeinstance-task-owned",
            "isolation_proof_sha256": "3" * 64,
            "issued_at_utc": "2026-08-19T16:00:00Z",
            "lease_id": server.LEASE_ID,
            "lease_plan_sha256": "4" * 64,
            "lease_state": "ACTIVE",
            "observed_gpu": {
                "count": 1,
                "name": "NVIDIA H100 80GB HBM3",
                "uuid_sha256": "5" * 64,
            },
            "runtime_egress_rule_count": 0,
        }
        signature = hmac.new(
            token_value.encode(), server.canonical(payload), hashlib.sha256
        ).hexdigest()
        return {**payload, "hmac_sha256": signature}

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
        with mock.patch.object(server, "completed_runtime_groups", return_value=[]):
            server.validate_transition(None, "qwen-smoke-01", "attempt-1", 1)

    def test_second_request_requires_same_runtime_group_and_distinct_attempt(self):
        active = {
            "runtime_group_id": "qwen-smoke-01",
            "requests": [{"attempt_id": "attempt-1"}],
        }
        server.validate_transition(active, "qwen-smoke-01", "attempt-2", 2)
        with self.assertRaisesRegex(ValueError, "changed runtime group"):
            server.validate_transition(active, "qwen-scout-01", "attempt-2", 2)
        with self.assertRaisesRegex(ValueError, "distinct attempt"):
            server.validate_transition(active, "qwen-smoke-01", "attempt-1", 2)

    def test_single_request_cannot_claim_pair_qualification(self):
        active = {"runtime_group_id": "qwen-smoke-01", "requests": []}
        with self.assertRaisesRegex(ValueError, "one prior result"):
            server.validate_transition(active, "qwen-smoke-01", "attempt-2", 2)

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

    def test_inference_gate_requires_authenticated_active_zero_egress_h100(self):
        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory) / "token"
            token_path.write_text("a" * 64 + "\n")
            with mock.patch.object(server, "TOKEN_PATH", token_path):
                gate = self.runtime_gate()
                self.assertEqual("ACTIVE", server.validate_runtime_gate(gate)["lease_state"])
                for key, value in (
                    ("lease_state", "CREATING"),
                    ("runtime_egress_rule_count", 1),
                    ("clearance_expires_at", "2000-01-01T00:00:00Z"),
                ):
                    changed = dict(gate)
                    changed[key] = value
                    payload = {
                        item_key: item_value
                        for item_key, item_value in changed.items()
                        if item_key != "hmac_sha256"
                    }
                    changed["hmac_sha256"] = hmac.new(
                        ("a" * 64).encode(), server.canonical(payload), hashlib.sha256
                    ).hexdigest()
                    with self.assertRaisesRegex(ValueError, "ACTIVE"):
                        server.validate_runtime_gate(changed)
                forged = dict(gate)
                forged["hmac_sha256"] = "0" * 64
                with self.assertRaisesRegex(ValueError, "signature"):
                    server.validate_runtime_gate(forged)

    def test_container_identity_uses_no_trunc_and_exact_running_inspect_id(self):
        calls = []

        def fake_run(args, **_kwargs):
            calls.append(args)
            if args[1] == "ps":
                return type("Result", (), {"stdout": "a" * 64 + "\n", "returncode": 0})()
            return type("Result", (), {"stdout": "b" * 64 + " true\n", "returncode": 0})()

        with mock.patch.object(server, "run", side_effect=fake_run):
            self.assertEqual(["a" * 64], server.live_containers())
            self.assertEqual("b" * 64, server.exact_container_id("catswitch-vllm-qwen-smoke-01"))
        self.assertIn("--no-trunc", calls[0])
        self.assertEqual("inspect", calls[1][1])

        with mock.patch.object(
            server,
            "run",
            return_value=type("Result", (), {"stdout": "c" * 12 + " true\n", "returncode": 0})(),
        ):
            with self.assertRaisesRegex(RuntimeError, "exact running container ID"):
                server.exact_container_id("catswitch-vllm-qwen-smoke-01")

    def test_campaign_accepts_exactly_four_runtime_groups_once(self):
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory) / "campaign.json"
            with mock.patch.object(server, "CAMPAIGN_EVIDENCE", campaign):
                for group in server.RUNTIME_GROUP_IDS:
                    result = server.record_completed_runtime_group(group)
                self.assertTrue(result["complete"])
                self.assertEqual(4, len(result["completed_runtime_groups"]))
                with self.assertRaisesRegex(RuntimeError, "already completed"):
                    server.record_completed_runtime_group(server.RUNTIME_GROUP_IDS[0])
                with self.assertRaisesRegex(ValueError, "exact four-group"):
                    server.validate_transition(None, "qwen-scout-04", "attempt-9", 1)


if __name__ == "__main__":
    unittest.main()
