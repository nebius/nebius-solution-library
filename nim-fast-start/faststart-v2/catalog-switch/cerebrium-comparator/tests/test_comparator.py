from __future__ import annotations

import hashlib
import inspect
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "comparator.py"
SPEC = importlib.util.spec_from_file_location("cerebrium_comparator", MODULE_PATH)
assert SPEC and SPEC.loader
comparator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparator)


class FakeResponse:
    def __init__(self, lines, *, headers=None, status=200):
        self.status = status
        self.headers = headers or {}
        self.stream = io.BytesIO(b"".join(lines))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def readline(self):
        return self.stream.readline()

    def read(self, size=-1):
        return self.stream.read(size)


def sse(*chunks):
    return [b"data: " + json.dumps(chunk).encode() + b"\n" for chunk in chunks] + [
        b"data: [DONE]\n"
    ]


def backend(*, gpu_type="H100", gpu_count=1):
    return {
        "backend_id": "internal-nebius",
        "provider": "nebius",
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "gpu_type": gpu_type,
        "gpu_count": gpu_count,
        "node_id": "computeinstance-task-owned",
        "container_id": "container-task-owned",
        "runtime_id": "runtime-task-owned",
        "image_digest": "sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d",
        "config_sha256": "a" * 64,
        "code_revision": "b" * 40,
        "auth_enabled": True,
        "min_replicas": 0,
        "replica_concurrency": 1,
        "checkpointing": False,
        "placement_verified": True,
        "resource_prefix": "mlsp-csw-test-owned",
        "resources": [
            {
                "kind": "instance",
                "id": "computeinstance-task-owned",
                "project_id": "project-e00z6b02t8ddk96c49",
                "region": "eu-north1",
                "dedicated": True,
            },
            {
                "kind": "subnet",
                "id": "subnet-task-owned",
                "project_id": "project-e00z6b02t8ddk96c49",
                "region": "eu-north1",
                "dedicated": True,
            },
            {
                "kind": "security_group",
                "id": "securitygroup-task-owned",
                "project_id": "project-e00z6b02t8ddk96c49",
                "region": "eu-north1",
                "dedicated": True,
            },
        ],
        "broker_evidence": {
            "authorization_sha256": "1" * 64,
            "broker_receipt_sha256": "7" * 64,
            "clearance_expires_at": "2026-08-19T17:00:00Z",
            "health_proof_sha256": "2" * 64,
            "instance_id": "computeinstance-task-owned",
            "isolation_proof_sha256": "3" * 64,
            "listener_proof_sha256": "8" * 64,
            "lease_id": comparator.QWEN_V6_LEASE_ID,
            "lease_plan_sha256": "4" * 64,
            "lease_state": "ACTIVE",
            "network_binding": {
                "instance_id": "computeinstance-task-owned",
                "security_group_id": "securitygroup-task-owned",
                "subnet_id": "subnet-task-owned",
            },
            "observed_gpu": {
                "count": 1,
                "name": "NVIDIA H100 80GB HBM3",
                "uuid_sha256": "5" * 64,
            },
            "runtime_egress_rule_count": 0,
            "runtime_gate_sha256": "6" * 64,
        },
    }


def cold(classification="process-cold-artifact-hit"):
    return {
        "classification": classification,
        "min_replicas_zero": True,
        "no_live_replica_before_demand": True,
        "unique_runtime_identity": True,
        "startup_path": "not-placed" if classification == "capacity-miss" else "conventional",
        "image_state": "local-verified",
        "artifact_state": "node-local-hit",
        "cache_state": "cold",
        "capacity_state": "unavailable" if classification == "capacity-miss" else "allocated",
        "proof_sha256": "c" * 64,
    }


def receipt(
    sequence=0,
    *,
    classification="process-cold-artifact-hit",
    success=True,
    arm_id="internal-qwen3-new-target-matched",
    cohort_id="qwen3-process-cold-scout",
):
    models = comparator._model_map()
    prompts = comparator._prompt_map()
    model = models["qwen3-8b-bf16-b968826"]
    prompt = prompts["qwen3-nonthinking-exact"]
    payload = comparator.build_payload(prompt, model)
    payload_bytes = comparator.canonical(payload).encode()
    response = {
        "model_id": model["model_id"] if success else None,
        "content": "QWEN3_CATALOG_SWITCH_OK" if success else "",
        "reasoning_content": "",
        "tool_calls": [],
    }
    response_bytes = comparator.canonical(response).encode()
    t0 = 1_000_000_000_000 + sequence * 2_000_000_000
    return {
        "schema": comparator.SCHEMA,
        "attempt_id": f"attempt-{sequence:04d}",
        "arm_id": arm_id,
        "cohort_id": cohort_id,
        "cohort_family": "qwen3-new-target-matched",
        "started_at_utc": f"2026-08-19T00:00:{sequence % 60:02d}.000000Z",
        "completed_at_utc": f"2026-08-19T00:00:{sequence % 60:02d}.900000Z",
        "model": {key: model[key] for key in comparator.MODEL_KEYS},
        "request": {
            "prompt_id": prompt["prompt_id"],
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "payload_bytes": len(payload_bytes),
        },
        "backend": backend(),
        "cold_state": cold(classification),
        "timing_ns": {
            "t0": t0,
            "first_response_byte": t0 + 100_000_000 if success else None,
            "ttft": t0 + 200_000_000 if success else None,
            "ttfo": t0 + 200_000_000 if success else None,
            "complete": t0 + 900_000_000,
        },
        "response": response,
        "response_identity": None,
        "outcome": {
            "status": "success" if success else "failed",
            "semantically_valid": success,
            "failure_class": None if success else ("capacity" if classification == "capacity-miss" else "backend"),
            "reason": "exact content matched" if success else "capacity unavailable",
            "response_sha256": hashlib.sha256(response_bytes).hexdigest() if success else None,
            "response_bytes": len(response_bytes) if success else 0,
        },
        "accounting": {
            "bytes_sent": len(payload_bytes),
            "bytes_received": len(response_bytes) if success else 0,
            "generated_tokens": 1 if success else None,
            "billed_seconds": None,
            "cost_usd": None,
        },
    }


class ComparatorTests(unittest.TestCase):
    def test_sealed_internal_qwen_campaign_cli_is_executable_without_boolean_exception(self):
        self.assertNotIn(
            "authorized_internal_qwen_pair",
            inspect.signature(comparator.run_attempt).parameters,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("backend.json", "cold.json", "warm.json"):
                (root / name).write_text("{}\n")
            bundle = {
                "schema": "catalog-switch-qwen-sealed-campaign/v6",
                "lease_id": comparator.QWEN_V6_LEASE_ID,
                "runtime_gate_sha256": "a" * 64,
                "pairs": [],
                "server_campaign": {},
                "replay": {"replay_sha256": "b" * 64},
            }
            with mock.patch.dict(os.environ, {"TEST_QWEN_TOKEN": "secret"}), mock.patch.object(
                comparator, "run_qwen_qualification_campaign", return_value=bundle
            ) as run_campaign:
                rc = comparator.main(
                    [
                        "run-internal-qwen-v6-campaign",
                        "--lease", str(root / "lease.json"),
                        "--endpoint", "https://recorder.example/v1/chat/completions",
                        "--token-env", "TEST_QWEN_TOKEN",
                        "--backend-proof", str(root / "backend.json"),
                        "--cold-state-proof", str(root / "cold.json"),
                        "--warm-state-proof", str(root / "warm.json"),
                        "--output-dir", str(root / "output"),
                    ]
                )
            self.assertEqual(0, rc)
            run_campaign.assert_called_once()
            self.assertEqual(
                root / "lease.json", run_campaign.call_args.kwargs["lease_path"]
            )
            self.assertTrue(callable(run_campaign.call_args.kwargs["receipt_sink"]))

            with mock.patch.dict(os.environ, {"TEST_QWEN_TOKEN": "secret"}), mock.patch.object(
                comparator, "run_qwen_qualification_campaign", return_value=bundle
            ) as blocked:
                rc = comparator.main(
                    [
                        "run-internal-qwen-v6-campaign",
                        "--lease", str(root / "lease.json"),
                        "--endpoint", "https://recorder.example/v1/chat/completions",
                        "--token-env", "TEST_QWEN_TOKEN",
                        "--backend-proof", str(root / "backend.json"),
                        "--cold-state-proof", str(root / "cold.json"),
                        "--warm-state-proof", str(root / "warm.json"),
                        "--output-dir", str(root / "output"),
                    ]
                )
            self.assertEqual(2, rc)
            blocked.assert_not_called()

    def test_frozen_contracts_validate(self):
        result = comparator.validate_contracts()
        self.assertEqual("PASS", result["status"])
        self.assertEqual("UNVERIFIED", result["qwen3_claim"])
        self.assertEqual(["cerebrium"], result["measured_external_backends"])
        self.assertFalse(result["live_mutation_authorized"])

    def test_qwen_is_new_target_and_glm_variants_cannot_collapse(self):
        arms = comparator._arm_map()
        models = comparator._model_map()
        self.assertFalse(arms["cerebrium-qwen-public-claim-native"]["enabled"])
        self.assertNotEqual(
            arms["cerebrium-qwen-public-claim-native"]["cohort_family"],
            arms["cerebrium-qwen3-new-target-matched"]["cohort_family"],
        )
        self.assertEqual("official-fp8-checkpoint", models["glm-5.2-fp8-ba978f7"]["quantization"])
        self.assertIn("availability", models["glm-5.2-bf16-b4734de-availability-only"]["role"])

    def test_streaming_landmarks_separate_ttft_and_ttfo(self):
        lines = sse(
            {"model": "zai-org/GLM-5.2-FP8", "choices": [{"delta": {"reasoning_content": "thinking"}}]},
            {"model": "zai-org/GLM-5.2-FP8", "choices": [{"delta": {"content": "answer"}}]},
        )
        result = comparator.stream_request(
            "https://example.invalid/v1/chat/completions",
            {"model": "zai-org/GLM-5.2-FP8", "messages": [], "stream": True},
            "secret-not-printed",
            opener=lambda *_args, **_kwargs: FakeResponse(lines),
        )
        self.assertLessEqual(result["timing_ns"]["ttft"], result["timing_ns"]["ttfo"])
        self.assertEqual("thinking", result["response"]["reasoning_content"])
        self.assertEqual("answer", result["response"]["content"])

    def test_stream_request_sends_server_compatible_attempt_and_pair_headers(self):
        captured = {}

        def opener(request, **_kwargs):
            captured["headers"] = dict(request.header_items())
            return FakeResponse(
                sse(
                    {
                        "model": "Qwen/Qwen3-8B",
                        "choices": [{"delta": {"content": "QWEN3_CATALOG_SWITCH_OK"}}],
                    }
                ),
                headers={
                    "X-Catswitch-Attempt-ID": "attempt-pair-1",
                    "X-Catswitch-Runtime-Group-ID": "qwen-smoke-01",
                    "X-Catswitch-Qualification-Ordinal": "1",
                    "X-Catswitch-Container-ID": "a" * 64,
                    "X-Catswitch-Lease-ID": comparator.QWEN_V6_LEASE_ID,
                    "X-Catswitch-Runtime-Gate-SHA256": "6" * 64,
                },
            )

        comparator.stream_request(
            "https://example.invalid/v1/chat/completions",
            {"model": "Qwen/Qwen3-8B", "messages": [], "stream": True},
            "secret-not-printed",
            opener=opener,
            attempt_id="attempt-pair-1",
            runtime_group_id="qwen-smoke-01",
            qualification_ordinal=1,
        )
        lowered = {key.lower(): value for key, value in captured["headers"].items()}
        self.assertEqual("attempt-pair-1", lowered["x-catswitch-attempt-id"])
        self.assertEqual("qwen-smoke-01", lowered["x-catswitch-runtime-group-id"])
        self.assertEqual("1", lowered["x-catswitch-qualification-ordinal"])

    def test_response_identity_headers_are_required_and_first_byte_is_body_read(self):
        lines = sse(
            {
                "model": "Qwen/Qwen3-8B",
                "choices": [{"delta": {"content": "QWEN3_CATALOG_SWITCH_OK"}}],
            }
        )
        headers = {
            "X-Catswitch-Attempt-ID": "attempt-identity-1",
            "X-Catswitch-Runtime-Group-ID": "qwen-smoke-01",
            "X-Catswitch-Qualification-Ordinal": "1",
            "X-Catswitch-Container-ID": "a" * 64,
            "X-Catswitch-Lease-ID": comparator.QWEN_V6_LEASE_ID,
            "X-Catswitch-Runtime-Gate-SHA256": "6" * 64,
        }
        result = comparator.stream_request(
            "https://example.invalid/v1/chat/completions",
            {"model": "Qwen/Qwen3-8B", "messages": [], "stream": True},
            "secret-not-printed",
            opener=lambda *_args, **_kwargs: FakeResponse(lines, headers=headers),
            attempt_id="attempt-identity-1",
            runtime_group_id="qwen-smoke-01",
            qualification_ordinal=1,
        )
        self.assertIsNotNone(result["timing_ns"]["first_response_byte"])
        self.assertEqual("a" * 64, result["response_identity"]["container_id"])
        bad = dict(headers)
        bad["X-Catswitch-Attempt-ID"] = "different-attempt"
        with self.assertRaisesRegex(comparator.ComparatorError, "response identity"):
            comparator.stream_request(
                "https://example.invalid/v1/chat/completions",
                {"model": "Qwen/Qwen3-8B", "messages": [], "stream": True},
                "secret-not-printed",
                opener=lambda *_args, **_kwargs: FakeResponse(lines, headers=bad),
                attempt_id="attempt-identity-1",
                runtime_group_id="qwen-smoke-01",
                qualification_ordinal=1,
            )

    def test_reasoning_and_tool_oracles_require_exact_parity(self):
        prompts = comparator._prompt_map()
        valid, _ = comparator.semantic_validate(
            prompts["glm52-thinking-high"],
            {"content": "GLM52_REASONING_OK_42", "reasoning_content": "17+25=42", "tool_calls": [], "model_id": "zai-org/GLM-5.2-FP8"},
        )
        self.assertTrue(valid)
        valid, _ = comparator.semantic_validate(
            prompts["glm52-thinking-high"],
            {"content": "GLM52_REASONING_OK_42", "reasoning_content": "", "tool_calls": [], "model_id": "zai-org/GLM-5.2-FP8"},
        )
        self.assertFalse(valid)
        valid, _ = comparator.semantic_validate(
            prompts["glm52-tool-glm47"],
            {"content": "", "reasoning_content": "", "tool_calls": [{"index": 0, "name": "catalog_switch_echo", "arguments": '{"value":"glm52-tool-ok"}'}], "model_id": "zai-org/GLM-5.2-FP8"},
        )
        self.assertTrue(valid)

    def test_model_fallback_and_empty_http_200_are_rejected(self):
        value = receipt()
        value["response"]["model_id"] = "Qwen/Qwen3-4B"
        with self.assertRaisesRegex(comparator.ComparatorError, "model"):
            comparator.validate_receipt(value)
        value = receipt()
        value["response"]["content"] = ""
        with self.assertRaisesRegex(comparator.ComparatorError, "semantic"):
            comparator.validate_receipt(value)

    def test_internal_receipt_binds_active_lease_health_h100_and_zero_egress(self):
        for path, replacement in (
            (("lease_state",), "CREATING"),
            (("runtime_egress_rule_count",), 1),
            (("lease_id",), "foreign-lease"),
            (("observed_gpu", "name"), "NVIDIA H200"),
            (("health_proof_sha256",), "not-a-digest"),
        ):
            value = receipt()
            target = value["backend"]["broker_evidence"]
            if len(path) == 1:
                target[path[0]] = replacement
            else:
                target[path[0]][path[1]] = replacement
            with self.subTest(path=path), self.assertRaises(comparator.ComparatorError):
                comparator.validate_receipt(value)

    def test_backend_evidence_is_derived_from_exact_active_broker_ledger(self):
        health = {
            "instance_id": "computeinstance-task-owned",
            "observed_gpu": {
                "count": 1,
                "name": "NVIDIA H100 80GB HBM3",
                "uuid_sha256": "5" * 64,
            },
        }
        isolation = {"security_group": {"rules": []}}
        listener = {"serial_log_marker_observed": True}
        gate = {
            "schema": "catalog-switch-internal-runtime-gate/v6",
            "authorization_id": "internal-qwen3-h100-scout-v6-20260819",
            "authorization_sha256": "1" * 64,
            "broker_receipt_sha256": "placeholder",
            "clearance_expires_at": "2026-08-19T17:00:00Z",
            "health_proof_sha256": comparator.digest(health),
            "gate_signature_ed25519_base64": "dGVzdC1vbmx5LXNpZ25hdHVyZS1ieXRlcy10ZXN0LW9ubHktc2lnbmF0dXJlLWJ5dGVzLXRlc3Qtb25seS0xMjM0NTY3ODkwMTI=",
            "instance_id": "computeinstance-task-owned",
            "isolation_proof_sha256": comparator.digest(isolation),
            "listener_proof_sha256": comparator.digest(listener),
            "issued_at_utc": "2026-08-19T16:30:00Z",
            "lease_id": comparator.QWEN_V6_LEASE_ID,
            "lease_plan_sha256": "4" * 64,
            "lease_state": "ACTIVE",
            "network_binding": {
                "instance_id": "computeinstance-task-owned",
                "security_group_id": "securitygroup-task-owned",
                "subnet_id": "subnet-task-owned",
            },
            "observed_gpu": health["observed_gpu"],
            "profile": {
                "platform": "gpu-h100-sxm",
                "preset": "1gpu-16vcpu-200gb",
            },
            "runtime_egress_rule_count": 0,
        }
        lease = {
            "state": "ACTIVE",
            "lease_id": comparator.QWEN_V6_LEASE_ID,
            "prefix": "mlsp-csw-task-owned",
            "profile_snapshot": {
                "platform": "gpu-h100-sxm",
                "preset": "1gpu-16vcpu-200gb",
            },
            "health_proof": health,
            "isolation_proof": isolation,
            "runtime_listener_proof": listener,
            "live_authorization": {
                "authorization_sha256": "1" * 64,
                "clearance": {"expires_at": "2026-08-19T17:00:00Z"},
                "frozen": {"lease_plan_sha256": "4" * 64},
            },
            "runtime_gate": gate,
            "resources": [
                {
                    "kind": "instance",
                    "id": "computeinstance-task-owned",
                    "name": "task-instance",
                    "project_id": "project-e00z6b02t8ddk96c49",
                    "region": "eu-north1",
                    "deleted_at": None,
                },
                {
                    "kind": "subnet",
                    "id": "subnet-task-owned",
                    "name": "task-subnet",
                    "project_id": "project-e00z6b02t8ddk96c49",
                    "region": "eu-north1",
                    "deleted_at": None,
                },
                {
                    "kind": "security_group",
                    "id": "securitygroup-task-owned",
                    "name": "task-security-group",
                    "project_id": "project-e00z6b02t8ddk96c49",
                    "region": "eu-north1",
                    "deleted_at": None,
                },
            ],
        }
        broker = comparator._load_broker()
        gate["broker_receipt_sha256"] = broker.sha256_json(
            broker.runtime_receipt_payload(lease)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lease.json"
            path.write_text(json.dumps(lease))
            bound = comparator.bind_internal_backend(backend(), path)
            self.assertEqual(
                comparator.digest(gate),
                bound["broker_evidence"]["runtime_gate_sha256"],
            )
            lease["runtime_gate"]["runtime_egress_rule_count"] = 1
            path.write_text(json.dumps(lease))
            with self.assertRaisesRegex(comparator.ComparatorError, "zero-egress"):
                comparator.bind_internal_backend(backend(), path)

    def test_attempt_and_runtime_ids_use_one_lowercase_grammar(self):
        value = receipt()
        value["attempt_id"] = "Attempt/Upper"
        with self.assertRaisesRegex(comparator.ComparatorError, "canonical"):
            comparator.validate_receipt(value)
        self.assertEqual(
            r"^[a-z0-9][a-z0-9._-]{0,95}$", comparator.ID_RE.pattern
        )

    def test_all_failures_remain_in_denominator_and_p95_waits_for_30(self):
        values = [receipt(index, success=index != 28) for index in range(29)]
        result = comparator.aggregate(values)
        self.assertEqual(29, result["attempts"])
        self.assertEqual(1, result["failures"])
        self.assertFalse(result["p95_admissible"])
        self.assertIsNone(result["metrics"]["complete"]["p95_ms"])
        values.append(receipt(29))
        result = comparator.aggregate(values)
        self.assertTrue(result["p95_admissible"])
        self.assertIsNone(result["metrics"]["complete"]["p95_ms"])
        values.append(receipt(30))
        result = comparator.aggregate(values)
        self.assertIsNotNone(result["metrics"]["complete"]["p95_ms"])

    def test_mixed_cold_classifications_and_arms_cannot_aggregate(self):
        with self.assertRaisesRegex(comparator.ComparatorError, "cold-state"):
            comparator.aggregate([receipt(0), receipt(1, classification="capacity-miss")])
        other = receipt(1)
        other["arm_id"] = "cerebrium-qwen3-new-target-matched"
        other["backend"].update(
            {
                "backend_id": "cerebrium",
                "project_id": "p-12ff482a",
                "region": "eu-north1-rsd",
                "broker_evidence": None,
            }
        )
        other["backend"]["resources"][0].update(
            {"id": "cerebrium-app-task-owned", "project_id": "p-12ff482a", "region": "eu-north1-rsd"}
        )
        with self.assertRaisesRegex(comparator.ComparatorError, "arm_id"):
            comparator.aggregate([receipt(0), other])

    def test_canonical_ndjson_rejects_duplicates_and_replays_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipts.ndjson"
            comparator.append_receipt(path, receipt(0))
            with self.assertRaisesRegex(comparator.ComparatorError, "already recorded"):
                comparator.append_receipt(path, receipt(0))
            loaded = comparator.load_receipts(path)
            self.assertEqual(1, len(loaded))
            path.write_text(path.read_text().replace('"arm_id":', '"arm_id":"x","arm_id":', 1))
            with self.assertRaises(comparator.ComparatorError):
                comparator.load_receipts(path)

    def test_shared_external_t0_export_validates_with_reviewed_harness(self):
        value = receipt(0)
        trace, events = comparator.export_shared([value])
        attempts = comparator.slo.validate_ledger(events, trace)
        self.assertEqual(1, len(attempts))
        self.assertTrue(attempts[0]["success"])
        self.assertEqual(0.9, attempts[0]["terminal_seconds"])

    def test_capacity_miss_exports_as_failed_placement(self):
        value = receipt(0, classification="capacity-miss", success=False, cohort_id="qwen-capacity-miss")
        trace, events = comparator.export_shared([value])
        attempts = comparator.slo.validate_ledger(events, trace)
        self.assertFalse(attempts[0]["success"])
        self.assertEqual("capacity", attempts[0]["failure_class"])

    def test_fresh_node_remote_miss_is_not_falsely_mapped_to_a_to_b(self):
        value = receipt(0, classification="fresh-node-artifact-miss", cohort_id="qwen-fresh-node")
        with self.assertRaisesRegex(comparator.ComparatorError, "no idle remote-artifact scenario"):
            comparator.export_shared([value])

    def test_two_independent_semantic_receipts_and_server_verdicts_are_required(self):
        first = receipt(1)
        second = receipt(2, classification="warm-control", cohort_id="qwen3-runtime-companion")
        for ordinal, value in enumerate((first, second), 1):
            value["backend"]["container_id"] = "a" * 64
            value["response_identity"] = {
                "attempt_id": value["attempt_id"],
                "container_id": "a" * 64,
                "lease_id": comparator.QWEN_V6_LEASE_ID,
                "qualification_ordinal": ordinal,
                "runtime_gate_sha256": "6" * 64,
                "runtime_group_id": "qwen-smoke-01",
            }
        evidence = {
            "schema": "catalog-switch-qwen-runtime-qualification/v6",
            "runtime_group_id": "qwen-smoke-01",
            "container_id": "a" * 64,
            "cold_start_count": 1,
            "requests": [
                {
                    "attempt_id": first["attempt_id"],
                    "model_id": first["model"]["model_id"],
                    "ordinal": 1,
                    "oracle_reason": "exact content matched",
                    "response_sha256": first["outcome"]["response_sha256"],
                    "semantically_valid": True,
                    "stream_complete": True,
                },
                {
                    "attempt_id": second["attempt_id"],
                    "model_id": second["model"]["model_id"],
                    "ordinal": 2,
                    "oracle_reason": "exact content matched",
                    "response_sha256": second["outcome"]["response_sha256"],
                    "semantically_valid": True,
                    "stream_complete": True,
                },
            ],
            "teardown": {"container_absent": True, "verified_at_utc": "2026-08-19T00:00:03Z"},
            "completed_at_utc": "2026-08-19T00:00:03Z",
            "status": "QUALIFIED",
        }
        replay = comparator.validate_qualification_pair([first, second], evidence)
        self.assertEqual(2, replay["independent_recorder_oracles"])
        with self.assertRaisesRegex(comparator.ComparatorError, "exactly two"):
            comparator.validate_qualification_pair([first], evidence)
        evidence["requests"][1]["semantically_valid"] = False
        with self.assertRaisesRegex(comparator.ComparatorError, "backend semantic verdict"):
            comparator.validate_qualification_pair([first, second], evidence)

    def test_campaign_requires_exactly_four_runtime_groups(self):
        pairs = []
        for index, group in enumerate(sorted(comparator.QWEN_V6_RUNTIME_GROUPS)):
            first = receipt(10 + index * 2)
            second = receipt(
                11 + index * 2,
                classification="warm-control",
                cohort_id=f"qwen3-runtime-companion-{index}",
            )
            container_id = f"{index + 1:064x}"
            for ordinal, value in enumerate((first, second), 1):
                value["backend"]["container_id"] = container_id
                value["response_identity"] = {
                    "attempt_id": value["attempt_id"],
                    "container_id": container_id,
                    "lease_id": comparator.QWEN_V6_LEASE_ID,
                    "qualification_ordinal": ordinal,
                    "runtime_gate_sha256": "6" * 64,
                    "runtime_group_id": group,
                }
            evidence = {
                "schema": "catalog-switch-qwen-runtime-qualification/v6",
                "runtime_group_id": group,
                "container_id": container_id,
                "cold_start_count": 1,
                "requests": [
                    {
                        "attempt_id": value["attempt_id"],
                        "model_id": value["model"]["model_id"],
                        "ordinal": ordinal,
                        "oracle_reason": "exact content matched",
                        "response_sha256": value["outcome"]["response_sha256"],
                        "semantically_valid": True,
                        "stream_complete": True,
                    }
                    for ordinal, value in enumerate((first, second), 1)
                ],
                "teardown": {
                    "container_absent": True,
                    "verified_at_utc": "2026-08-19T00:00:03Z",
                },
                "completed_at_utc": "2026-08-19T00:00:03Z",
                "status": "QUALIFIED",
            }
            replay = comparator.validate_qualification_pair([first, second], evidence)
            pairs.append(
                {"receipts": [first, second], "backend_evidence": evidence, "replay": replay}
            )
        campaign = {
            "schema": "catalog-switch-qwen-runtime-campaign/v6",
            "required_runtime_groups": sorted(comparator.QWEN_V6_RUNTIME_GROUPS),
            "completed_runtime_groups": sorted(comparator.QWEN_V6_RUNTIME_GROUPS),
            "complete": True,
        }
        replay = comparator.validate_qualification_campaign(pairs, campaign)
        self.assertEqual(4, replay["runtime_group_count"])
        with self.assertRaisesRegex(comparator.ComparatorError, "exactly four"):
            comparator.validate_qualification_campaign(pairs[:3], campaign)


if __name__ == "__main__":
    unittest.main()
