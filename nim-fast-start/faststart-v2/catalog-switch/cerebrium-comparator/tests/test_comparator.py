from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "comparator.py"
SPEC = importlib.util.spec_from_file_location("cerebrium_comparator", MODULE_PATH)
assert SPEC and SPEC.loader
comparator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparator)


class FakeResponse:
    status = 200

    def __init__(self, lines):
        self.lines = iter(lines)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def readline(self):
        return next(self.lines, b"")


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
            }
        ],
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


if __name__ == "__main__":
    unittest.main()
