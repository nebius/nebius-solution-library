from __future__ import annotations

import importlib.util
import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "live" / "internal_scout_server_v6.py"
SPEC = importlib.util.spec_from_file_location("internal_scout_server_v6", MODULE_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


def line(value):
    return b"data: " + json.dumps(value).encode() + b"\n"


class InternalScoutServerV6Tests(unittest.TestCase):
    def setUp(self):
        self.keys = tempfile.TemporaryDirectory()
        self.private_key = Path(self.keys.name) / "private.pem"
        self.public_key = Path(self.keys.name) / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(self.private_key)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private_key), "-pubout", "-out", str(self.public_key)],
            check=True,
            capture_output=True,
        )

    def tearDown(self):
        self.keys.cleanup()

    def verifier_context(self):
        return mock.patch.multiple(
            server,
            GATE_VERIFIER_PUBLIC_KEY_PATH=self.public_key,
            GATE_VERIFIER_PUBLIC_KEY_SHA256=hashlib.sha256(self.public_key.read_bytes()).hexdigest(),
        )

    def runtime_gate(self, signing_key=None, *, issued_at="2026-08-19T16:30:00Z"):
        signing_key = signing_key or self.private_key
        payload = {
            "schema": "catalog-switch-internal-runtime-gate/v6",
            "authorization_id": "internal-qwen3-h100-scout-v6-20260819",
            "authorization_sha256": "1" * 64,
            "broker_receipt_sha256": "6" * 64,
            "clearance_expires_at": "2099-08-19T17:00:00Z",
            "health_proof_sha256": "2" * 64,
            "instance_id": "computeinstance-task-owned",
            "isolation_proof_sha256": "3" * 64,
            "listener_proof_sha256": "7" * 64,
            "issued_at_utc": issued_at,
            "lease_id": server.LEASE_ID,
            "lease_plan_sha256": "4" * 64,
            "lease_state": "ACTIVE",
            "observed_gpu": {
                "count": 1,
                "name": "NVIDIA H100 80GB HBM3",
                "uuid_sha256": "5" * 64,
            },
            "network_binding": {
                "instance_id": "computeinstance-task-owned",
                "security_group_id": "securitygroup-task-owned",
                "subnet_id": "subnet-task-owned",
            },
            "profile": {
                "platform": "gpu-h100-sxm",
                "preset": "1gpu-16vcpu-200gb",
            },
            "runtime_egress_rule_count": 0,
        }
        return {
            **payload,
            "gate_signature_ed25519_base64": self.sign_payload(payload, signing_key),
        }

    def sign_payload(self, payload, signing_key=None):
        signing_key = signing_key or self.private_key
        with tempfile.NamedTemporaryFile() as message, tempfile.NamedTemporaryFile() as signature:
            message.write(server.canonical(payload))
            message.flush()
            subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(signing_key), "-in", message.name, "-out", signature.name],
                check=True,
                capture_output=True,
            )
            signature.seek(0)
            encoded = base64.b64encode(signature.read()).decode()
        return encoded

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
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "GROUP_STATE_DIR", Path(directory)
        ), mock.patch.object(server, "completed_runtime_groups", return_value=[]):
            server.validate_transition(None, "qwen-smoke-01", "attempt-1", 1)

    def test_second_request_requires_same_runtime_group_and_distinct_attempt(self):
        active = {
            "runtime_group_id": "qwen-smoke-01",
            "requests": [{"attempt_id": "attempt-1"}],
        }
        active["container_id"] = "a" * 64
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "GROUP_STATE_DIR", Path(directory)
        ):
            server.GROUP_STATE_DIR.mkdir(parents=True, exist_ok=True)
            server.claim_runtime_ordinal("qwen-smoke-01", "attempt-1", 1)
            server.update_group_state(
                "qwen-smoke-01",
                state="AWAITING_ORDINAL2",
                container_id="a" * 64,
            )
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
            with mock.patch.object(server, "TOKEN_PATH", token_path), self.verifier_context(), mock.patch.object(
                server,
                "current_utc",
                return_value=server.datetime(2026, 8, 19, 16, 30, tzinfo=server.UTC),
            ):
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
                        if item_key != "gate_signature_ed25519_base64"
                    }
                    changed["gate_signature_ed25519_base64"] = self.sign_payload(payload)
                    with self.assertRaisesRegex(ValueError, "fresh exact ACTIVE"):
                        server.validate_runtime_gate(changed)
                forged = dict(gate)
                forged["gate_signature_ed25519_base64"] = base64.b64encode(b"0" * 64).decode()
                with self.assertRaisesRegex(ValueError, "signature"):
                    server.validate_runtime_gate(forged)

                client_forgery = dict(gate)
                payload = {
                    key: value
                    for key, value in client_forgery.items()
                    if key != "gate_signature_ed25519_base64"
                }
                attacker_private = Path(directory) / "attacker.pem"
                subprocess.run(
                    ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(attacker_private)],
                    check=True,
                    capture_output=True,
                )
                client_forgery["gate_signature_ed25519_base64"] = self.sign_payload(
                    payload, attacker_private
                )
                with self.assertRaisesRegex(ValueError, "signature"):
                    server.validate_runtime_gate(client_forgery)

                stale = self.runtime_gate(issued_at="1970-01-01T00:00:00Z")
                with self.assertRaisesRegex(ValueError, "fresh exact ACTIVE"):
                    server.validate_runtime_gate(stale)

    def test_vm_public_verifier_cannot_self_mint_a_gate(self):
        with tempfile.NamedTemporaryFile() as message, tempfile.NamedTemporaryFile() as signature:
            message.write(b"forged-gate")
            message.flush()
            result = subprocess.run(
                ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(self.public_key), "-in", message.name, "-out", signature.name],
                check=False,
                capture_output=True,
            )
        self.assertNotEqual(0, result.returncode)

    def test_server_ready_marker_binds_fresh_boot_identity(self):
        boot = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n"
        with mock.patch.object(Path, "read_text", return_value=boot), mock.patch.object(
            server, "utc_now", return_value="2026-08-19T18:00:00.000000Z"
        ):
            marker = server.server_ready_marker()
        encoded = marker.split("=", 1)[1]
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        self.assertEqual(server.LEASE_ID, payload["lease_id"])
        self.assertEqual(boot.strip(), payload["boot_id"])

    def test_runtime_group_ordinal_is_atomically_consumed_before_runtime_start(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "GROUP_STATE_DIR", Path(directory)
        ):
            server.GROUP_STATE_DIR.mkdir(parents=True, exist_ok=True)
            first = server.claim_runtime_ordinal(
                "qwen-smoke-01", "attempt-first", 1
            )
            self.assertEqual("ORDINAL1_IN_PROGRESS", first["state"])
            with self.assertRaisesRegex(ValueError, "already consumed"):
                server.claim_runtime_ordinal(
                    "qwen-smoke-01", "attempt-race", 1
                )
            server.update_group_state(
                "qwen-smoke-01",
                state="AWAITING_ORDINAL2",
                container_id="a" * 64,
            )
            active = {
                "runtime_group_id": "qwen-smoke-01",
                "container_id": "a" * 64,
                "requests": [{"attempt_id": "attempt-first"}],
            }
            second = server.claim_runtime_ordinal(
                "qwen-smoke-01", "attempt-second", 2
            )
            self.assertEqual("ORDINAL2_IN_PROGRESS", second["state"])
            with self.assertRaisesRegex(ValueError, "not exactly claimable"):
                server.claim_runtime_ordinal(
                    "qwen-smoke-01", "attempt-second-retry", 2
                )

    def test_crash_recovery_is_terminal_and_retry_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            server, "GROUP_STATE_DIR", Path(directory)
        ), mock.patch.object(
            server, "remove_runtime", return_value={"status": "removed"}
        ) as remove:
            server.GROUP_STATE_DIR.mkdir(parents=True, exist_ok=True)
            state = server.claim_runtime_ordinal(
                "qwen-smoke-01", "attempt-crashed", 1
            )
            server.recover_runtime_groups()
            recovered = server.load_group_state("qwen-smoke-01")
            self.assertEqual("FAILED_CRASH_RECOVERED", recovered["state"])
            remove.assert_called_once_with("catswitch-vllm-qwen-smoke-01")
            with self.assertRaisesRegex(ValueError, "already consumed"):
                server.claim_runtime_ordinal(
                    "qwen-smoke-01", "attempt-retry", 1
                )

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
