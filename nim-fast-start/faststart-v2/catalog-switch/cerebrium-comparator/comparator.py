#!/usr/bin/env python3
"""Fail-closed external-client comparator for pinned Cerebrium/Nebius arms.

The supplemental receipt preserves streaming landmarks. Product-SLO traces and
ledgers are emitted through the reviewed performance.request_slo contract.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
FASTSTART_ROOT = ROOT.parents[1]
if str(FASTSTART_ROOT) not in sys.path:
    sys.path.insert(0, str(FASTSTART_ROOT))

from performance.request_slo import harness as slo  # noqa: E402


SCHEMA = "catalog-switch-cerebrium-attempt/v3"
CAMPAIGN = ROOT / "contracts" / "campaign.json"
MODELS = ROOT / "contracts" / "models.json"
PROMPTS = ROOT / "contracts" / "prompts.json"
SOURCES = ROOT / "contracts" / "sources.json"
PROFILES = FASTSTART_ROOT / "resource-broker" / "profiles.json"
BROKER = FASTSTART_ROOT / "resource-broker" / "broker.py"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
ATTEMPT_KEYS = {
    "accounting",
    "arm_id",
    "attempt_id",
    "backend",
    "cold_state",
    "cohort_family",
    "cohort_id",
    "completed_at_utc",
    "model",
    "outcome",
    "request",
    "response",
    "response_identity",
    "schema",
    "started_at_utc",
    "timing_ns",
}
TIMING_KEYS = {"t0", "first_response_byte", "ttft", "ttfo", "complete"}
COLD_KEYS = {
    "classification",
    "min_replicas_zero",
    "no_live_replica_before_demand",
    "unique_runtime_identity",
    "startup_path",
    "image_state",
    "artifact_state",
    "cache_state",
    "capacity_state",
    "proof_sha256",
}
BACKEND_KEYS = {
    "backend_id",
    "provider",
    "project_id",
    "region",
    "gpu_type",
    "gpu_count",
    "node_id",
    "container_id",
    "runtime_id",
    "image_digest",
    "config_sha256",
    "code_revision",
    "auth_enabled",
    "min_replicas",
    "replica_concurrency",
    "checkpointing",
    "placement_verified",
    "resource_prefix",
    "resources",
    "broker_evidence",
}
BROKER_EVIDENCE_KEYS = {
    "authorization_sha256",
    "broker_receipt_sha256",
    "clearance_expires_at",
    "health_proof_sha256",
    "instance_id",
    "isolation_proof_sha256",
    "listener_proof_sha256",
    "lease_id",
    "lease_plan_sha256",
    "lease_state",
    "network_binding",
    "observed_gpu",
    "runtime_egress_rule_count",
    "runtime_gate_sha256",
}
OBSERVED_GPU_KEYS = {"count", "name", "uuid_sha256"}
RESPONSE_IDENTITY_KEYS = {
    "attempt_id",
    "container_id",
    "lease_id",
    "qualification_ordinal",
    "runtime_gate_sha256",
    "runtime_group_id",
}
QWEN_V6_LEASE_ID = "catswitch-qwen3-h100-scout-v6-20260819"
QWEN_V6_RUNTIME_GROUP_SEQUENCE = (
    "qwen-smoke-01",
    "qwen-scout-01",
    "qwen-scout-02",
    "qwen-scout-03",
)
QWEN_V6_RUNTIME_GROUPS = set(QWEN_V6_RUNTIME_GROUP_SEQUENCE)
MODEL_KEYS = {"contract_id", "model_id", "revision", "artifact_identity_sha256"}
REQUEST_KEYS = {"prompt_id", "payload_sha256", "payload_bytes"}
OUTCOME_KEYS = {
    "status",
    "semantically_valid",
    "failure_class",
    "reason",
    "response_sha256",
    "response_bytes",
}
RESPONSE_KEYS = {"model_id", "content", "reasoning_content", "tool_calls"}
ACCOUNTING_KEYS = {
    "bytes_sent",
    "bytes_received",
    "generated_tokens",
    "billed_seconds",
    "cost_usd",
}
CLASSIFICATIONS = {
    "process-cold-artifact-hit",
    "fresh-node-artifact-miss",
    "capacity-miss",
    "warm-control",
    "steady-state-exploration",
}


class ComparatorError(ValueError):
    """Evidence cannot be admitted to the frozen comparator contract."""


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComparatorError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ComparatorError("value is not canonicalizable JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ComparatorError(f"input is not a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparatorError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ComparatorError(f"expected JSON object: {path}")
    return value


def expect_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise ComparatorError(
            f"{label} keys differ; missing={sorted(keys - actual)}, extra={sorted(actual - keys)}"
        )
    return value


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _model_map() -> dict[str, dict[str, Any]]:
    contract = load_json(MODELS)
    if contract.get("schema") != "catalog-switch-cerebrium-model-contract/v1":
        raise ComparatorError("unsupported model contract")
    models = contract.get("models")
    if not isinstance(models, list):
        raise ComparatorError("models must be a list")
    mapped = {item.get("contract_id"): item for item in models if isinstance(item, dict)}
    if len(mapped) != len(models) or None in mapped:
        raise ComparatorError("model contract IDs are missing or duplicated")
    return mapped


def _prompt_map() -> dict[str, dict[str, Any]]:
    contract = load_json(PROMPTS)
    if contract.get("schema") != "catalog-switch-cerebrium-prompt-corpus/v1":
        raise ComparatorError("unsupported prompt corpus")
    prompts = contract.get("prompts")
    if not isinstance(prompts, list):
        raise ComparatorError("prompts must be a list")
    if contract.get("corpus_sha256") != digest(prompts):
        raise ComparatorError("prompt corpus checksum is not frozen or differs")
    mapped = {item.get("prompt_id"): item for item in prompts if isinstance(item, dict)}
    if len(mapped) != len(prompts) or None in mapped:
        raise ComparatorError("prompt IDs are missing or duplicated")
    return mapped


def _arm_map() -> dict[str, dict[str, Any]]:
    contract = load_json(CAMPAIGN)
    if contract.get("schema") != "catalog-switch-cerebrium-campaign/v1":
        raise ComparatorError("unsupported campaign contract")
    arms = contract.get("arms")
    if not isinstance(arms, list):
        raise ComparatorError("campaign arms must be a list")
    mapped = {item.get("arm_id"): item for item in arms if isinstance(item, dict)}
    if len(mapped) != len(arms) or None in mapped:
        raise ComparatorError("arm IDs are missing or duplicated")
    return mapped


def _load_broker() -> Any:
    spec = importlib.util.spec_from_file_location("catalog_switch_resource_broker", BROKER)
    if spec is None or spec.loader is None:
        raise ComparatorError("cannot load reviewed resource broker")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bind_internal_backend(backend: dict[str, Any], lease_path: Path) -> dict[str, Any]:
    """Build receipt identity from the exact ACTIVE broker ledger, never declarations."""
    lease = load_json(lease_path)
    health = lease.get("health_proof")
    isolation = lease.get("isolation_proof")
    listener = lease.get("runtime_listener_proof")
    gate = lease.get("runtime_gate")
    broker = _load_broker()
    expected_receipt_sha256 = (
        broker.sha256_json(broker.runtime_receipt_payload(lease))
        if isinstance(gate, dict)
        else None
    )
    if (
        lease.get("state") != "ACTIVE"
        or not isinstance(health, dict)
        or not isinstance(isolation, dict)
        or not isinstance(listener, dict)
        or not isinstance(gate, dict)
        or gate.get("schema") != "catalog-switch-internal-runtime-gate/v6"
        or gate.get("lease_id") != lease.get("lease_id")
        or gate.get("lease_state") != "ACTIVE"
        or gate.get("runtime_egress_rule_count") != 0
        or gate.get("health_proof_sha256") != digest(health)
        or gate.get("isolation_proof_sha256") != digest(isolation)
        or gate.get("listener_proof_sha256") != digest(listener)
        or gate.get("instance_id") != health.get("instance_id")
        or gate.get("observed_gpu") != health.get("observed_gpu")
        or gate.get("broker_receipt_sha256") != expected_receipt_sha256
        or gate.get("network_binding", {}).get("instance_id")
        != health.get("instance_id")
    ):
        raise ComparatorError("broker ledger cannot produce ACTIVE zero-egress receipt evidence")
    resources = [
        {
            "kind": item["kind"],
            "id": item["id"],
            "project_id": item["project_id"],
            "region": item["region"],
            "dedicated": True,
        }
        for item in lease.get("resources", [])
        if not item.get("deleted_at") and item.get("deletion_mode") != "PROVIDER_CASCADE"
    ]
    if len([item for item in resources if item["kind"] == "instance"]) != 1:
        raise ComparatorError("broker ledger must contain exactly one live instance")
    result = json.loads(canonical(backend))
    result.update(
        {
            "node_id": health["instance_id"],
            "resource_prefix": lease["prefix"],
            "resources": resources,
            "broker_evidence": {
                "authorization_sha256": gate["authorization_sha256"],
                "broker_receipt_sha256": gate["broker_receipt_sha256"],
                "clearance_expires_at": gate["clearance_expires_at"],
                "health_proof_sha256": gate["health_proof_sha256"],
                "instance_id": gate["instance_id"],
                "isolation_proof_sha256": gate["isolation_proof_sha256"],
                "listener_proof_sha256": gate["listener_proof_sha256"],
                "lease_id": gate["lease_id"],
                "lease_plan_sha256": gate["lease_plan_sha256"],
                "lease_state": gate["lease_state"],
                "network_binding": gate["network_binding"],
                "observed_gpu": gate["observed_gpu"],
                "runtime_egress_rule_count": gate["runtime_egress_rule_count"],
                "runtime_gate_sha256": digest(gate),
            },
        }
    )
    return result


def validate_contracts() -> dict[str, Any]:
    models_contract = load_json(MODELS)
    models = _model_map()
    prompts_contract = load_json(PROMPTS)
    prompts = _prompt_map()
    campaign = load_json(CAMPAIGN)
    arms = _arm_map()
    sources = load_json(SOURCES)

    allowed_backends = {"cerebrium", "internal-nebius", "availability-audit"}
    observed_backends = {arm.get("backend") for arm in arms.values()}
    if not observed_backends <= allowed_backends:
        raise ComparatorError("campaign contains an unauthorized measured backend")

    if sources.get("qwen3_claim_status") != "UNVERIFIED":
        raise ComparatorError("Qwen3 claim must remain UNVERIFIED without a stronger primary source")
    if arms["cerebrium-qwen-public-claim-native"]["enabled"] is not False:
        raise ComparatorError("unverified claim-native arm cannot be enabled")
    if arms["cerebrium-qwen-public-claim-native"]["cohort_family"] == arms[
        "cerebrium-qwen3-new-target-matched"
    ]["cohort_family"]:
        raise ComparatorError("claim-native and matched Qwen cohorts must remain separate")

    required_models = {
        "qwen3-8b-bf16-b968826": (
            "Qwen/Qwen3-8B",
            "b968826d9c46dd6066d109eabc6255188de91218",
            1,
        ),
        "glm-5.2-fp8-ba978f7": (
            "zai-org/GLM-5.2-FP8",
            "ba978f7d347eaf65d22f1a86833408afdb953541",
            8,
        ),
        "glm-5.2-bf16-b4734de-availability-only": (
            "zai-org/GLM-5.2",
            "b4734de4facf877f85769a911abafc5283eab3d9",
            None,
        ),
    }
    for contract_id, expected in required_models.items():
        model = models.get(contract_id)
        if model is None or (model.get("model_id"), model.get("revision"), model.get("tensor_parallel_size")) != expected:
            raise ComparatorError(f"canonical model identity differs: {contract_id}")
        if not SHA256_RE.fullmatch(str(model.get("artifact_identity_sha256", ""))):
            raise ComparatorError(f"model artifact identity is not SHA-256: {contract_id}")

    fp8 = models["glm-5.2-fp8-ba978f7"]
    bf16 = models["glm-5.2-bf16-b4734de-availability-only"]
    if fp8["repository_bytes"] != 761025363709 or fp8["quantization"] != "official-fp8-checkpoint":
        raise ComparatorError("GLM-5.2-FP8 size/variant label differs")
    if bf16["repository_bytes"] != 1506689458421 or "availability" not in bf16["role"]:
        raise ComparatorError("GLM-5.2 BF16 must remain an unmatched availability result")
    if fp8["tokenizer"]["sha256"] != "19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d":
        raise ComparatorError("GLM tokenizer checksum differs")
    if fp8["chat_template"]["sha256"] != "172dc74a35e1752df75ecfb2b2cf9326d2852bb1379868ebeec9571654489679":
        raise ComparatorError("GLM chat template checksum differs")

    runtime = models_contract.get("runtime", {})
    if runtime.get("checkpointing") is not False or runtime.get("required_vllm_minimum") != "0.23.0":
        raise ComparatorError("matched runtime/checkpoint contract differs")
    if not IMAGE_RE.fullmatch(str(runtime.get("image_amd64_digest", ""))):
        raise ComparatorError("runtime amd64 image is not digest-pinned")

    glm_primary = campaign.get("glm_primary", {})
    expected_glm = {
        "checkpointing": False,
        "gpu_count": 8,
        "gpu_type": "H200",
        "max_model_len": 131072,
        "mtp": False,
        "node_count": 1,
        "prefix_cache": False,
        "prompt_id": "glm52-nonthinking-exact",
        "tensor_parallel_size": 8,
    }
    if glm_primary != expected_glm:
        raise ComparatorError("primary GLM hardware/runtime contract differs")
    required_smokes = {
        "glm52-nonthinking-exact",
        "glm52-thinking-high",
        "glm52-thinking-default",
        "glm52-tool-glm47",
    }
    if set(campaign["parity_smokes"]["required_prompt_ids"]) != required_smokes:
        raise ComparatorError("GLM parity-smoke set differs")
    if campaign["parity_smokes"]["structured_json_in_product_scope"] is not False:
        raise ComparatorError("structured JSON scope changed without a contract revision")
    if campaign.get("prompt_corpus_sha256") != prompts_contract["corpus_sha256"]:
        raise ComparatorError("campaign does not pin the prompt corpus")
    if campaign["statistics"] != {
        "cold_claim_minimum_n": 30,
        "cold_scout_minimum_n": 3,
        "percentile_estimator": slo.PERCENTILE_ESTIMATOR,
        "promoted_steady_state_minimum_n": 1000,
        "warm_exploration_minimum_n": 100,
    }:
        raise ComparatorError("statistics contract differs")
    for prompt in prompts.values():
        if prompt.get("model_contract_id") not in models:
            raise ComparatorError(f"prompt references unknown model: {prompt.get('prompt_id')}")
        generation = prompt.get("generation", {})
        if generation.get("stream") is not True or generation.get("temperature") != 0:
            raise ComparatorError(f"prompt is not deterministic streaming: {prompt.get('prompt_id')}")

    profiles = load_json(PROFILES)["profiles"]
    h200 = profiles.get("h200-tp8")
    if h200 is None or (
        h200.get("platform"), h200.get("preset"), h200.get("gpu_count"), h200.get("boot_disk_gib")
    ) != ("gpu-h200-sxm", "8gpu-128vcpu-1600gb", 8, 1600):
        raise ComparatorError("reviewed broker lacks the exact frozen H200 TP8 profile")
    if h200["local_nvme"]["request"] is not False:
        raise ComparatorError("matched H200 primary cannot silently enable local NVMe")

    for path in sorted((ROOT / "resource-requests").glob("*.request.json")):
        broker = _load_broker()
        broker.validate_request(load_json(path), broker.load_profiles(PROFILES))

    qwen_toml = ROOT / "deploy" / "qwen3" / "cerebrium.toml"
    if qwen_toml.exists():
        with qwen_toml.open("rb") as handle:
            config = tomllib.load(handle)
        deployment = config["cerebrium"]["deployment"]
        hardware = config["cerebrium"]["hardware"]
        scaling = config["cerebrium"]["scaling"]
        if deployment.get("disable_auth") is not False:
            raise ComparatorError("Cerebrium authentication must remain enabled")
        if (hardware.get("provider"), hardware.get("region"), hardware.get("compute"), hardware.get("gpu_count")) != (
            "nebius",
            "eu-north1-rsd",
            "HOPPER_H100",
            1,
        ):
            raise ComparatorError("Qwen Cerebrium placement differs")
        if (scaling.get("min_replicas"), scaling.get("replica_concurrency")) != (0, 1):
            raise ComparatorError("Cerebrium cold-state scaling differs")

    return {
        "status": "PASS",
        "schema": campaign["schema"],
        "campaign_id": campaign["campaign_id"],
        "models": len(models),
        "prompts": len(prompts),
        "arms": len(arms),
        "qwen3_claim": "UNVERIFIED",
        "measured_external_backends": ["cerebrium"],
        "live_mutation_authorized": False,
        "prompt_corpus_sha256": prompts_contract["corpus_sha256"],
    }


def build_payload(prompt: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    generation = json.loads(json.dumps(prompt["generation"]))
    payload: dict[str, Any] = {"model": model["model_id"], "messages": prompt["messages"]}
    payload.update(generation)
    return payload


def _tool_calls(raw: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {"index": index, "name": item["name"], "arguments": item["arguments"]}
        for index, item in sorted(raw.items())
    ]


def semantic_validate(prompt: dict[str, Any], response: dict[str, Any]) -> tuple[bool, str]:
    oracle = prompt["oracle"]
    content = response["content"]
    reasoning = response["reasoning_content"]
    if oracle["type"] == "exact-content":
        valid = content.strip() == oracle["expected"]
        return valid, "exact content matched" if valid else "exact content mismatch"
    if oracle["type"] == "reasoning-content":
        valid = bool(reasoning.strip()) and oracle["content_contains"] in content
        if oracle.get("separate_reasoning_and_content") and reasoning.strip() == content.strip():
            valid = False
        return valid, "reasoning/content separation matched" if valid else "reasoning/content oracle failed"
    if oracle["type"] == "exact-tool-call":
        calls = response["tool_calls"]
        if len(calls) != 1 or calls[0]["name"] != oracle["name"]:
            return False, "tool name/count mismatch"
        try:
            arguments = json.loads(calls[0]["arguments"], object_pairs_hook=_duplicates)
        except (json.JSONDecodeError, ComparatorError):
            return False, "tool arguments are not unique-key JSON"
        valid = arguments == oracle["arguments"]
        return valid, "exact tool call matched" if valid else "tool arguments mismatch"
    raise ComparatorError(f"unsupported semantic oracle: {oracle['type']}")


def stream_request(
    endpoint: str,
    payload: dict[str, Any],
    token: str,
    *,
    opener: Any = urllib.request.urlopen,
    timeout_seconds: int = 1800,
    admission: dict[str, Any] | None = None,
    attempt_id: str | None = None,
    runtime_group_id: str | None = None,
    qualification_ordinal: int | None = None,
) -> dict[str, Any]:
    encoded = canonical(payload).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if attempt_id is not None:
        if not ID_RE.fullmatch(attempt_id):
            raise ComparatorError("attempt header is not canonical")
        headers["X-Catswitch-Attempt-ID"] = attempt_id
    if runtime_group_id is not None or qualification_ordinal is not None:
        if (
            runtime_group_id is None
            or not ID_RE.fullmatch(runtime_group_id)
            or qualification_ordinal not in {1, 2}
        ):
            raise ComparatorError("qualification runtime-group headers are incomplete")
        headers["X-Catswitch-Runtime-Group-ID"] = runtime_group_id
        headers["X-Catswitch-Qualification-Ordinal"] = str(qualification_ordinal)
    request = urllib.request.Request(
        endpoint,
        data=encoded,
        headers=headers,
        method="POST",
    )
    started_at = utc_now()
    t0 = time.monotonic_ns()
    if admission is not None:
        admission.update({"started_at_utc": started_at, "t0": t0, "bytes_sent": len(encoded)})
    first_byte: int | None = None
    ttft: int | None = None
    ttfo: int | None = None
    received = 0
    content = ""
    reasoning = ""
    calls: dict[int, dict[str, str]] = {}
    observed_model: str | None = None
    generated_tokens: int | None = None
    response_identity: dict[str, Any] | None = None
    with opener(request, timeout=timeout_seconds) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise ComparatorError(f"unexpected HTTP status {status}")
        if runtime_group_id is not None:
            response_headers = getattr(response, "headers", {})

            def header(name: str) -> str | None:
                getter = getattr(response_headers, "get", None)
                if callable(getter):
                    return getter(name)
                getheader = getattr(response, "getheader", None)
                return getheader(name) if callable(getheader) else None

            response_identity = {
                "attempt_id": header("X-Catswitch-Attempt-ID"),
                "container_id": header("X-Catswitch-Container-ID"),
                "lease_id": header("X-Catswitch-Lease-ID"),
                "qualification_ordinal": header("X-Catswitch-Qualification-Ordinal"),
                "runtime_gate_sha256": header("X-Catswitch-Runtime-Gate-SHA256"),
                "runtime_group_id": header("X-Catswitch-Runtime-Group-ID"),
            }
            if (
                response_identity["attempt_id"] != attempt_id
                or response_identity["runtime_group_id"] != runtime_group_id
                or response_identity["lease_id"] != QWEN_V6_LEASE_ID
                or response_identity["qualification_ordinal"]
                != str(qualification_ordinal)
                or not re.fullmatch(
                    r"[0-9a-f]{64}", str(response_identity["container_id"] or "")
                )
                or not SHA256_RE.fullmatch(
                    str(response_identity["runtime_gate_sha256"] or "")
                )
            ):
                raise ComparatorError("response identity headers differ from the request/broker gate")
            response_identity["qualification_ordinal"] = qualification_ordinal
        first_fragment = response.read(1)
        if first_fragment:
            first_byte = time.monotonic_ns()
        while True:
            raw = first_fragment + response.readline()
            first_fragment = b""
            observed = time.monotonic_ns()
            if not raw:
                break
            received += len(raw)
            line = raw.strip()
            if not line or line.startswith(b":"):
                continue
            if not line.startswith(b"data:"):
                raise ComparatorError("stream contains a non-SSE data line")
            data = line[5:].strip()
            if data == b"[DONE]":
                break
            try:
                chunk = json.loads(data, object_pairs_hook=_duplicates)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ComparatorError("stream contains invalid JSON") from exc
            chunk_model = chunk.get("model")
            if chunk_model is not None:
                if observed_model is not None and chunk_model != observed_model:
                    raise ComparatorError("stream changes model identity")
                observed_model = chunk_model
            usage = chunk.get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
                generated_tokens = usage["completion_tokens"]
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta", {})
            if not isinstance(delta, dict):
                raise ComparatorError("stream delta is not an object")
            reasoning_piece = delta.get("reasoning_content") or ""
            content_piece = delta.get("content") or ""
            tool_piece = delta.get("tool_calls") or []
            if not isinstance(reasoning_piece, str) or not isinstance(content_piece, str):
                raise ComparatorError("stream content fields are not strings")
            has_token = bool(reasoning_piece or content_piece or tool_piece)
            if has_token and ttft is None:
                ttft = observed
            if content_piece and ttfo is None:
                ttfo = observed
            reasoning += reasoning_piece
            content += content_piece
            if not isinstance(tool_piece, list):
                raise ComparatorError("stream tool_calls is not a list")
            for item in tool_piece:
                if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                    raise ComparatorError("stream tool call lacks an integer index")
                entry = calls.setdefault(item["index"], {"name": "", "arguments": ""})
                function = item.get("function") or {}
                if function.get("name"):
                    entry["name"] += str(function["name"])
                if function.get("arguments"):
                    entry["arguments"] += str(function["arguments"])
    complete = time.monotonic_ns()
    return {
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "timing_ns": {
            "t0": t0,
            "first_response_byte": first_byte,
            "ttft": ttft,
            "ttfo": ttfo,
            "complete": complete,
        },
        "response": {
            "model_id": observed_model,
            "content": content,
            "reasoning_content": reasoning,
            "tool_calls": _tool_calls(calls),
        },
        "bytes_sent": len(encoded),
        "bytes_received": received,
        "generated_tokens": generated_tokens,
        "response_identity": response_identity,
    }


def _failure_class(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError) and exc.code in {408, 429, 500, 502, 503, 504}:
        return "capacity" if exc.code in {429, 503} else "backend"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ComparatorError):
        return "validation"
    return "backend"


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return f"{type(exc).__name__}: {str(exc)[:400]}"


def validate_backend(arm: dict[str, Any], backend: dict[str, Any], campaign: dict[str, Any]) -> None:
    expect_keys(backend, BACKEND_KEYS, "backend proof")
    if backend["placement_verified"] is not True:
        raise ComparatorError("backend placement is not independently verified")
    if not IMAGE_RE.fullmatch(str(backend["image_digest"])):
        raise ComparatorError("backend image must be digest-pinned")
    if not SHA256_RE.fullmatch(str(backend["config_sha256"])) or not re.fullmatch(
        r"[0-9a-f]{40}", str(backend["code_revision"])
    ):
        raise ComparatorError("backend config/code revision is not pinned")
    resources = backend["resources"]
    if not isinstance(resources, list) or not resources:
        raise ComparatorError("backend proof must identify dedicated resources")
    for resource in resources:
        if set(resource) != {"kind", "id", "project_id", "region", "dedicated"} or resource["dedicated"] is not True:
            raise ComparatorError("backend resource is not exact and task-dedicated")
    broker_evidence = backend["broker_evidence"]
    if arm["backend"] == "internal-nebius":
        expect_keys(broker_evidence, BROKER_EVIDENCE_KEYS, "backend broker evidence")
        observed_gpu = expect_keys(
            broker_evidence["observed_gpu"], OBSERVED_GPU_KEYS, "observed GPU proof"
        )
        network_binding = expect_keys(
            broker_evidence["network_binding"],
            {"instance_id", "security_group_id", "subnet_id"},
            "network binding proof",
        )
        if (
            broker_evidence["lease_state"] != "ACTIVE"
            or broker_evidence["runtime_egress_rule_count"] != 0
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                str(broker_evidence["clearance_expires_at"]),
            )
            or broker_evidence["instance_id"] != backend["node_id"]
            or network_binding["instance_id"] != backend["node_id"]
            or observed_gpu["count"] != 1
            or not re.fullmatch(r"NVIDIA H100(?: |$).*", str(observed_gpu["name"]))
            or not all(
                SHA256_RE.fullmatch(str(broker_evidence[key]))
                for key in (
                    "authorization_sha256",
                    "broker_receipt_sha256",
                    "health_proof_sha256",
                    "isolation_proof_sha256",
                    "listener_proof_sha256",
                    "lease_plan_sha256",
                    "runtime_gate_sha256",
                )
            )
            or not SHA256_RE.fullmatch(str(observed_gpu["uuid_sha256"]))
        ):
            raise ComparatorError(
                "internal receipt lacks ACTIVE zero-egress broker/health/H100 proof"
            )
        if arm["arm_id"] == "internal-qwen3-new-target-matched" and broker_evidence[
            "lease_id"
        ] != QWEN_V6_LEASE_ID:
            raise ComparatorError("internal Qwen receipt is not bound to the v6 lease")
        instance_resources = [item for item in resources if item["kind"] == "instance"]
        if len(instance_resources) != 1 or instance_resources[0]["id"] != backend["node_id"]:
            raise ComparatorError("broker instance proof differs from backend resources")
        for kind, binding_key in (
            ("subnet", "subnet_id"),
            ("security_group", "security_group_id"),
        ):
            matching = [item for item in resources if item["kind"] == kind]
            if len(matching) != 1 or matching[0]["id"] != network_binding[binding_key]:
                raise ComparatorError(
                    f"broker {kind} proof differs from the signed network binding"
                )
    elif broker_evidence is not None:
        raise ComparatorError("non-internal backend cannot claim broker evidence")
    placement_key = {
        "cerebrium-qwen3-new-target-matched": "cerebrium_qwen",
        "internal-qwen3-new-target-matched": "internal_qwen",
        "cerebrium-glm52-fp8-matched": "cerebrium_glm",
        "internal-glm52-fp8-matched": "internal_glm",
    }.get(arm["arm_id"])
    if placement_key is None:
        raise ComparatorError("arm has no executable placement contract")
    expected = campaign["placement"][placement_key]
    for key in ("provider", "project_id", "region", "gpu_type", "gpu_count"):
        if key in expected and backend[key] != expected[key]:
            raise ComparatorError(f"backend placement fallback detected: {key}")
    if arm["backend"] == "cerebrium":
        if backend["auth_enabled"] is not True or backend["min_replicas"] != 0 or backend["replica_concurrency"] != 1:
            raise ComparatorError("Cerebrium auth/min_replicas/concurrency gate failed")
        if backend["checkpointing"] is not False:
            raise ComparatorError("matched Cerebrium arm cannot enable checkpointing")


def validate_cold_state(value: dict[str, Any]) -> None:
    expect_keys(value, COLD_KEYS, "cold-state proof")
    if value["classification"] not in CLASSIFICATIONS:
        raise ComparatorError("cold-state classification is not frozen")
    if not SHA256_RE.fullmatch(str(value["proof_sha256"])):
        raise ComparatorError("cold-state proof is not hash-pinned")
    if value["classification"] in {"process-cold-artifact-hit", "fresh-node-artifact-miss"}:
        for key in ("min_replicas_zero", "no_live_replica_before_demand", "unique_runtime_identity"):
            if value[key] is not True:
                raise ComparatorError(f"cold-state proof failed: {key}")
    if value["startup_path"] not in {"conventional", "restored", "not-placed", "warm"}:
        raise ComparatorError("startup path is not explicit")


def run_attempt(
    *,
    arm_id: str,
    cohort_id: str,
    prompt_id: str,
    endpoint: str,
    token: str,
    backend: dict[str, Any],
    cold_state: dict[str, Any],
    attempt_id: str,
    opener: Any = urllib.request.urlopen,
    runtime_group_id: str | None = None,
    qualification_ordinal: int | None = None,
) -> dict[str, Any]:
    validate_contracts()
    campaign = load_json(CAMPAIGN)
    arms = _arm_map()
    models = _model_map()
    prompts = _prompt_map()
    arm = arms.get(arm_id)
    prompt = prompts.get(prompt_id)
    if arm is None or prompt is None:
        raise ComparatorError("unknown arm or prompt")
    pair_exception = (
        arm_id == "internal-qwen3-new-target-matched"
        and prompt_id == "qwen3-nonthinking-exact"
        and backend.get("broker_evidence", {}).get("lease_id") == QWEN_V6_LEASE_ID
        and SHA256_RE.fullmatch(
            str(backend.get("broker_evidence", {}).get("runtime_gate_sha256", ""))
        )
        and runtime_group_id is not None
        and qualification_ordinal in {1, 2}
    )
    if arm["enabled"] is not True and not pair_exception:
        raise ComparatorError(f"live arm is not enabled in the frozen campaign: {arm['status']}")
    if arm["model_contract_id"] != prompt["model_contract_id"]:
        raise ComparatorError("arm/prompt model identity differs")
    model = models[arm["model_contract_id"]]
    validate_backend(arm, backend, campaign)
    validate_cold_state(cold_state)
    payload = build_payload(prompt, model)
    started = utc_now()
    fallback_t0 = time.monotonic_ns()
    admission: dict[str, Any] = {}
    raw: dict[str, Any] | None = None
    caught: Exception | None = None
    try:
        # stream_request captures the authoritative T0 immediately before dispatch.
        raw = stream_request(
            endpoint,
            payload,
            token,
            opener=opener,
            admission=admission,
            attempt_id=attempt_id,
            runtime_group_id=runtime_group_id,
            qualification_ordinal=qualification_ordinal,
        )
    except Exception as exc:  # every admitted request remains in the denominator
        caught = exc
    complete = time.monotonic_ns()
    if raw is not None:
        response = raw["response"]
        valid, reason = semantic_validate(prompt, response)
        if response["model_id"] != model["model_id"]:
            valid = False
            reason = "response model identity mismatch"
        response_bytes = len(canonical(response).encode())
        outcome = {
            "status": "success" if valid else "failed",
            "semantically_valid": valid,
            "failure_class": None if valid else "validation",
            "reason": reason,
            "response_sha256": hashlib.sha256(canonical(response).encode()).hexdigest(),
            "response_bytes": response_bytes,
        }
        timing = raw["timing_ns"]
        started_at = raw["started_at_utc"]
        completed_at = raw["completed_at_utc"]
        accounting = {
            "bytes_sent": raw["bytes_sent"],
            "bytes_received": raw["bytes_received"],
            "generated_tokens": raw["generated_tokens"],
            "billed_seconds": None,
            "cost_usd": None,
        }
    else:
        response = {"model_id": None, "content": "", "reasoning_content": "", "tool_calls": []}
        reason = _failure_reason(caught or RuntimeError("unknown failure"))
        outcome = {
            "status": "failed",
            "semantically_valid": False,
            "failure_class": _failure_class(caught or RuntimeError("unknown failure")),
            "reason": reason,
            "response_sha256": None,
            "response_bytes": 0,
        }
        timing = {"t0": admission.get("t0", fallback_t0), "first_response_byte": None, "ttft": None, "ttfo": None, "complete": complete}
        started_at = admission.get("started_at_utc", started)
        completed_at = utc_now()
        accounting = {
            "bytes_sent": len(canonical(payload).encode()),
            "bytes_received": 0,
            "generated_tokens": None,
            "billed_seconds": None,
            "cost_usd": None,
        }
    receipt_backend = json.loads(canonical(backend))
    if raw is not None and raw["response_identity"] is not None:
        receipt_backend["container_id"] = raw["response_identity"]["container_id"]
    receipt = {
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "arm_id": arm_id,
        "cohort_id": cohort_id,
        "cohort_family": arm["cohort_family"],
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "model": {
            "contract_id": model["contract_id"],
            "model_id": model["model_id"],
            "revision": model["revision"],
            "artifact_identity_sha256": model["artifact_identity_sha256"],
        },
        "request": {
            "prompt_id": prompt_id,
            "payload_sha256": hashlib.sha256(canonical(payload).encode()).hexdigest(),
            "payload_bytes": len(canonical(payload).encode()),
        },
        "backend": receipt_backend,
        "cold_state": cold_state,
        "timing_ns": timing,
        "response": response,
        "response_identity": raw["response_identity"] if raw is not None else None,
        "outcome": outcome,
        "accounting": accounting,
    }
    validate_receipt(receipt)
    return receipt


def run_qwen_qualification_pair(
    *,
    endpoint: str,
    token: str,
    backend: dict[str, Any],
    cold_state: dict[str, Any],
    warm_state: dict[str, Any],
    runtime_group_id: str,
    cold_attempt_id: str,
    companion_attempt_id: str,
    cohort_id: str,
    runtime_gate: dict[str, Any],
    opener: Any = urllib.request.urlopen,
    receipt_sink: Any | None = None,
) -> dict[str, Any]:
    """Run and independently validate the required two-request cold-runtime pair."""
    if not endpoint.endswith("/v1/chat/completions"):
        raise ComparatorError("qualification endpoint must be the exact chat-completions path")
    if cold_attempt_id == companion_attempt_id:
        raise ComparatorError("qualification attempt IDs must be distinct")
    runtime_gate_sha256 = digest(runtime_gate)
    if (
        runtime_group_id not in QWEN_V6_RUNTIME_GROUPS
        or backend.get("broker_evidence", {}).get("runtime_gate_sha256")
        != runtime_gate_sha256
    ):
        raise ComparatorError("qualification is not bound to the exact broker runtime gate")
    activation_endpoint = endpoint.removesuffix("/v1/chat/completions") + "/broker/activate"
    activation_payload = canonical(runtime_gate).encode()
    activation_request = urllib.request.Request(
        activation_endpoint,
        data=activation_payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with opener(activation_request, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise ComparatorError("broker runtime-gate activation did not return HTTP 200")
        try:
            activation = json.loads(response.read(), object_pairs_hook=_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComparatorError("runtime-gate activation response is invalid") from exc
    if activation != {
        "schema": "catalog-switch-runtime-gate-activation/v6",
        "runtime_gate_sha256": runtime_gate_sha256,
    }:
        raise ComparatorError("runtime-gate activation identity differs")
    cold_receipt = run_attempt(
        arm_id="internal-qwen3-new-target-matched",
        cohort_id=cohort_id,
        prompt_id="qwen3-nonthinking-exact",
        endpoint=endpoint,
        token=token,
        backend=backend,
        cold_state=cold_state,
        attempt_id=cold_attempt_id,
        opener=opener,
        runtime_group_id=runtime_group_id,
        qualification_ordinal=1,
    )
    if receipt_sink is not None:
        receipt_sink(cold_receipt)
    companion_receipt = run_attempt(
        arm_id="internal-qwen3-new-target-matched",
        cohort_id=f"{cohort_id}-runtime-companion",
        prompt_id="qwen3-nonthinking-exact",
        endpoint=endpoint,
        token=token,
        backend=backend,
        cold_state=warm_state,
        attempt_id=companion_attempt_id,
        opener=opener,
        runtime_group_id=runtime_group_id,
        qualification_ordinal=2,
    )
    if receipt_sink is not None:
        receipt_sink(companion_receipt)
    evidence_endpoint = (
        endpoint.removesuffix("/v1/chat/completions")
        + "/qualification/"
        + urllib.parse.quote(runtime_group_id, safe="")
    )
    request = urllib.request.Request(
        evidence_endpoint,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with opener(request, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise ComparatorError("qualification evidence endpoint did not return HTTP 200")
        try:
            backend_evidence = json.loads(response.read(), object_pairs_hook=_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComparatorError("qualification evidence is not unique-key JSON") from exc
    replay = validate_qualification_pair(
        [cold_receipt, companion_receipt], backend_evidence
    )
    return {
        "receipts": [cold_receipt, companion_receipt],
        "backend_evidence": backend_evidence,
        "replay": replay,
    }


def run_qwen_qualification_campaign(
    *,
    endpoint: str,
    token: str,
    backend_template: dict[str, Any],
    lease_path: Path,
    cold_state: dict[str, Any],
    warm_state: dict[str, Any],
    opener: Any = urllib.request.urlopen,
    receipt_sink: Any | None = None,
) -> dict[str, Any]:
    """Execute the sole sealed four-runtime/eight-request internal-Qwen workflow."""
    lease = load_json(lease_path)
    gate = lease.get("runtime_gate")
    if (
        lease.get("lease_id") != QWEN_V6_LEASE_ID
        or lease.get("state") != "ACTIVE"
        or not isinstance(gate, dict)
        or gate.get("schema") != "catalog-switch-internal-runtime-gate/v6"
        or gate.get("lease_id") != QWEN_V6_LEASE_ID
    ):
        raise ComparatorError("sealed Qwen campaign requires the exact ACTIVE v6 lease/gate")
    backend = bind_internal_backend(backend_template, lease_path)
    pairs = []
    for runtime_group_id in QWEN_V6_RUNTIME_GROUP_SEQUENCE:
        pairs.append(
            run_qwen_qualification_pair(
                endpoint=endpoint,
                token=token,
                backend=backend,
                cold_state=cold_state,
                warm_state=warm_state,
                runtime_group_id=runtime_group_id,
                cold_attempt_id=f"{runtime_group_id}-cold",
                companion_attempt_id=f"{runtime_group_id}-companion",
                cohort_id="internal-qwen3-v6-scout",
                runtime_gate=gate,
                opener=opener,
                receipt_sink=receipt_sink,
            )
        )
    campaign_endpoint = endpoint.removesuffix("/v1/chat/completions") + "/campaign"
    request = urllib.request.Request(
        campaign_endpoint,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with opener(request, timeout=60) as response:
        if getattr(response, "status", 200) != 200:
            raise ComparatorError("server campaign endpoint did not return HTTP 200")
        try:
            server_campaign = json.loads(response.read(), object_pairs_hook=_duplicates)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComparatorError("server campaign evidence is invalid") from exc
    replay = validate_qualification_campaign(pairs, server_campaign)
    return {
        "schema": "catalog-switch-qwen-sealed-campaign/v6",
        "lease_id": QWEN_V6_LEASE_ID,
        "runtime_gate_sha256": digest(gate),
        "pairs": pairs,
        "server_campaign": server_campaign,
        "replay": replay,
    }


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    expect_keys(receipt, ATTEMPT_KEYS, "attempt")
    if receipt["schema"] != SCHEMA:
        raise ComparatorError("unsupported attempt schema")
    for key in ("attempt_id", "arm_id", "cohort_id", "cohort_family"):
        if not isinstance(receipt[key], str) or not ID_RE.fullmatch(receipt[key]):
            raise ComparatorError(f"attempt {key} is not canonical")
    expect_keys(receipt["model"], MODEL_KEYS, "attempt.model")
    expect_keys(receipt["request"], REQUEST_KEYS, "attempt.request")
    expect_keys(receipt["timing_ns"], TIMING_KEYS, "attempt.timing_ns")
    expect_keys(receipt["response"], RESPONSE_KEYS, "attempt.response")
    expect_keys(receipt["outcome"], OUTCOME_KEYS, "attempt.outcome")
    expect_keys(receipt["accounting"], ACCOUNTING_KEYS, "attempt.accounting")
    validate_cold_state(receipt["cold_state"])
    campaign = load_json(CAMPAIGN)
    arm = _arm_map().get(receipt["arm_id"])
    model = _model_map().get(receipt["model"]["contract_id"])
    prompt = _prompt_map().get(receipt["request"]["prompt_id"])
    if arm is None or model is None or prompt is None:
        raise ComparatorError("receipt references an unknown frozen contract")
    if receipt["cohort_family"] != arm["cohort_family"] or arm["model_contract_id"] != model["contract_id"]:
        raise ComparatorError("receipt arm/cohort/model differs")
    expected_model = {key: model[key] for key in MODEL_KEYS}
    if receipt["model"] != expected_model or prompt["model_contract_id"] != model["contract_id"]:
        raise ComparatorError("receipt model substitution detected")
    payload = build_payload(prompt, model)
    payload_bytes = canonical(payload).encode()
    if receipt["request"]["payload_sha256"] != hashlib.sha256(payload_bytes).hexdigest() or receipt["request"]["payload_bytes"] != len(payload_bytes):
        raise ComparatorError("receipt request payload differs from the frozen prompt/model")
    validate_backend(arm, receipt["backend"], campaign)
    identity = receipt["response_identity"]
    if identity is not None:
        expect_keys(identity, RESPONSE_IDENTITY_KEYS, "attempt.response_identity")
        if (
            identity["attempt_id"] != receipt["attempt_id"]
            or not ID_RE.fullmatch(str(identity["runtime_group_id"]))
            or identity["runtime_group_id"] not in QWEN_V6_RUNTIME_GROUPS
            or identity["lease_id"] != QWEN_V6_LEASE_ID
            or identity["qualification_ordinal"] not in {1, 2}
            or not re.fullmatch(r"[0-9a-f]{64}", str(identity["container_id"]))
            or identity["container_id"] != receipt["backend"]["container_id"]
            or identity["runtime_gate_sha256"]
            != receipt["backend"]["broker_evidence"]["runtime_gate_sha256"]
        ):
            raise ComparatorError("response identity does not bind request, runtime, and broker gate")
    timing = receipt["timing_ns"]
    if not isinstance(timing["t0"], int) or not isinstance(timing["complete"], int) or timing["complete"] <= timing["t0"]:
        raise ComparatorError("complete boundary does not follow external T0")
    landmarks = [value for value in (timing["first_response_byte"], timing["ttft"], timing["ttfo"]) if value is not None]
    if any(not isinstance(value, int) or value < timing["t0"] or value > timing["complete"] for value in landmarks):
        raise ComparatorError("streaming landmark is outside request boundaries")
    if timing["first_response_byte"] is not None and timing["ttft"] is not None and timing["first_response_byte"] > timing["ttft"]:
        raise ComparatorError("TTFT precedes the first response byte")
    if timing["ttft"] is not None and timing["ttfo"] is not None and timing["ttft"] > timing["ttfo"]:
        raise ComparatorError("TTFO precedes TTFT")
    success = receipt["outcome"]["status"] == "success"
    if success != (receipt["outcome"]["semantically_valid"] is True):
        raise ComparatorError("success and semantic validity differ")
    if success:
        if receipt["outcome"]["failure_class"] is not None or receipt["outcome"]["response_bytes"] < 1:
            raise ComparatorError("successful receipt lacks a valid response")
        if timing["first_response_byte"] is None or timing["ttft"] is None:
            raise ComparatorError("successful receipt lacks streaming landmarks")
        valid, _ = semantic_validate(prompt, receipt["response"])
        if not valid or receipt["response"]["model_id"] != model["model_id"]:
            raise ComparatorError("successful receipt fails replayed semantic/model validation")
        response_bytes = canonical(receipt["response"]).encode()
        if receipt["outcome"]["response_sha256"] != hashlib.sha256(response_bytes).hexdigest() or receipt["outcome"]["response_bytes"] != len(response_bytes):
            raise ComparatorError("successful response hash/size differs on replay")
    elif receipt["outcome"]["failure_class"] not in slo.FAILURE_CLASSES:
        raise ComparatorError("failed receipt has a noncanonical failure class")
    return receipt


def validate_qualification_pair(
    receipts: list[dict[str, Any]], backend_evidence: dict[str, Any]
) -> dict[str, Any]:
    """Prove two independent semantic results after one conventional cold start."""
    if len(receipts) != 2:
        raise ComparatorError("qualification requires exactly two external-client receipts")
    for receipt in receipts:
        validate_receipt(receipt)
        if receipt["outcome"]["status"] != "success" or not receipt["outcome"][
            "semantically_valid"
        ]:
            raise ComparatorError("each qualification receipt must independently pass its oracle")
    if len({item["attempt_id"] for item in receipts}) != 2:
        raise ComparatorError("qualification attempts must be distinct")
    identities = [item["response_identity"] for item in receipts]
    if any(identity is None for identity in identities):
        raise ComparatorError("qualification requires validated response identity headers")
    if (
        identities[0]["runtime_group_id"] != identities[1]["runtime_group_id"]
        or identities[0]["container_id"] != identities[1]["container_id"]
        or [identity["qualification_ordinal"] for identity in identities] != [1, 2]
    ):
        raise ComparatorError("qualification response identities do not prove one runtime")
    if receipts[0]["cold_state"]["classification"] != "process-cold-artifact-hit":
        raise ComparatorError("qualification ordinal 1 must be the conventional cold request")
    if receipts[1]["cold_state"]["classification"] != "warm-control":
        raise ComparatorError("qualification ordinal 2 must reuse the same cold-started runtime")
    expected_keys = {
        "cold_start_count",
        "completed_at_utc",
        "container_id",
        "requests",
        "runtime_group_id",
        "schema",
        "status",
        "teardown",
    }
    expect_keys(backend_evidence, expected_keys, "qualification backend evidence")
    if backend_evidence["schema"] != "catalog-switch-qwen-runtime-qualification/v6":
        raise ComparatorError("unsupported qualification evidence schema")
    if backend_evidence["status"] != "QUALIFIED" or backend_evidence["cold_start_count"] != 1:
        raise ComparatorError("backend did not prove one cold start with two valid requests")
    if backend_evidence["runtime_group_id"] not in QWEN_V6_RUNTIME_GROUPS:
        raise ComparatorError("qualification runtime-group ID is not canonical")
    if not re.fullmatch(r"[0-9a-f]{64}", str(backend_evidence["container_id"])):
        raise ComparatorError("qualification container identity is not canonical")
    if backend_evidence["container_id"] != identities[0]["container_id"]:
        raise ComparatorError("backend container ID differs from response identity headers")
    requests = backend_evidence["requests"]
    if not isinstance(requests, list) or len(requests) != 2:
        raise ComparatorError("backend evidence does not contain two request results")
    expected_request_keys = {
        "attempt_id",
        "model_id",
        "ordinal",
        "oracle_reason",
        "response_sha256",
        "semantically_valid",
        "stream_complete",
    }
    for ordinal, (receipt, result) in enumerate(zip(receipts, requests), 1):
        expect_keys(result, expected_request_keys, f"qualification request {ordinal}")
        if (
            result["ordinal"] != ordinal
            or result["attempt_id"] != receipt["attempt_id"]
            or result["model_id"] != receipt["model"]["model_id"]
            or result["response_sha256"] != receipt["outcome"]["response_sha256"]
            or result["semantically_valid"] is not True
            or result["stream_complete"] is not True
            or result["oracle_reason"] != "exact content matched"
        ):
            raise ComparatorError(
                "backend semantic verdict does not match the independently validated receipt"
            )
    teardown = expect_keys(
        backend_evidence["teardown"],
        {"container_absent", "verified_at_utc"},
        "qualification teardown",
    )
    if teardown["container_absent"] is not True:
        raise ComparatorError("qualification runtime teardown is not proven")
    result = {
        "schema": "catalog-switch-qwen-runtime-qualification-replay/v1",
        "runtime_group_id": backend_evidence["runtime_group_id"],
        "attempt_ids": [item["attempt_id"] for item in receipts],
        "container_id": backend_evidence["container_id"],
        "independent_recorder_oracles": 2,
        "server_oracle_verdicts": 2,
        "cold_start_count": 1,
        "teardown_verified": True,
        "backend_evidence_sha256": digest(backend_evidence),
    }
    result["replay_sha256"] = digest(result)
    return result


def validate_qualification_campaign(
    pairs: list[dict[str, Any]], server_campaign: dict[str, Any]
) -> dict[str, Any]:
    """Admit only one smoke plus three scouts: exactly four runtime groups."""
    if len(pairs) != 4:
        raise ComparatorError("qualification campaign requires exactly four runtime groups")
    groups: list[str] = []
    attempts: list[str] = []
    for pair in pairs:
        if set(pair) != {"backend_evidence", "receipts", "replay"}:
            raise ComparatorError("qualification pair bundle fields differ")
        replay = validate_qualification_pair(pair["receipts"], pair["backend_evidence"])
        if replay != pair["replay"]:
            raise ComparatorError("qualification pair replay differs")
        groups.append(replay["runtime_group_id"])
        attempts.extend(replay["attempt_ids"])
    if set(groups) != QWEN_V6_RUNTIME_GROUPS or len(set(groups)) != 4:
        raise ComparatorError("qualification campaign runtime groups differ from the exact four")
    if len(set(attempts)) != 8:
        raise ComparatorError("qualification campaign requires eight distinct attempts")
    expect_keys(
        server_campaign,
        {
            "complete",
            "completed_runtime_groups",
            "required_runtime_groups",
            "schema",
        },
        "server qualification campaign",
    )
    if (
        server_campaign["schema"] != "catalog-switch-qwen-runtime-campaign/v6"
        or server_campaign["complete"] is not True
        or set(server_campaign["required_runtime_groups"]) != QWEN_V6_RUNTIME_GROUPS
        or set(server_campaign["completed_runtime_groups"]) != QWEN_V6_RUNTIME_GROUPS
        or len(server_campaign["completed_runtime_groups"]) != 4
    ):
        raise ComparatorError("server did not prove exactly four completed runtime groups")
    result = {
        "schema": "catalog-switch-qwen-runtime-campaign-replay/v1",
        "runtime_group_ids": sorted(groups),
        "attempt_ids": sorted(attempts),
        "runtime_group_count": 4,
        "request_count": 8,
        "server_campaign_sha256": digest(server_campaign),
    }
    result["replay_sha256"] = digest(result)
    return result


def append_receipt(path: Path, receipt: dict[str, Any]) -> None:
    validate_receipt(receipt)
    if path.exists() and path.is_symlink():
        raise ComparatorError("receipt output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "r+", encoding="utf-8", closefd=False) as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            existing = stream.read()
            if existing and not existing.endswith("\n"):
                raise ComparatorError("receipt file is not newline terminated")
            for number, line in enumerate(existing.splitlines(), 1):
                parsed = json.loads(line, object_pairs_hook=_duplicates)
                if line != canonical(parsed):
                    raise ComparatorError(f"receipt line {number} is not canonical")
                validate_receipt(parsed)
                if parsed["attempt_id"] == receipt["attempt_id"]:
                    raise ComparatorError("attempt ID is already recorded")
            stream.seek(0, os.SEEK_END)
            stream.write(canonical(receipt) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def load_receipts(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ComparatorError("receipt input must be a regular non-symlink file")
    raw = path.read_text()
    if not raw or not raw.endswith("\n"):
        raise ComparatorError("receipt input must be nonempty and newline terminated")
    receipts = []
    ids = set()
    for number, line in enumerate(raw.splitlines(), 1):
        value = json.loads(line, object_pairs_hook=_duplicates)
        if line != canonical(value):
            raise ComparatorError(f"receipt line {number} is not canonical")
        validate_receipt(value)
        if value["attempt_id"] in ids:
            raise ComparatorError("duplicate attempt ID in receipt file")
        ids.add(value["attempt_id"])
        receipts.append(value)
    return receipts


def _nearest(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _distribution(values: list[float], *, p95_allowed: bool) -> dict[str, Any]:
    return {
        "n": len(values),
        "min_ms": min(values) if values else None,
        "p50_ms": _nearest(values, 0.50) if len(values) >= 2 else None,
        "p95_ms": _nearest(values, 0.95) if p95_allowed else None,
        "max_ms": max(values) if values else None,
    }


def aggregate(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    if not receipts:
        raise ComparatorError("cannot aggregate an empty cohort")
    for receipt in receipts:
        validate_receipt(receipt)
    homogeneous_keys = ("arm_id", "cohort_id", "cohort_family")
    for key in homogeneous_keys:
        if len({receipt[key] for receipt in receipts}) != 1:
            raise ComparatorError(f"mixed {key} cannot be aggregated")
    for key in ("contract_id", "model_id", "revision"):
        if len({receipt["model"][key] for receipt in receipts}) != 1:
            raise ComparatorError(f"mixed model {key} cannot be aggregated")
    if len({receipt["cold_state"]["classification"] for receipt in receipts}) != 1:
        raise ComparatorError("cold-state classifications must remain separate cohorts")
    if len({canonical(receipt["backend"]) for receipt in receipts}) != 1:
        raise ComparatorError("backend placement/runtime proofs differ within the cohort")
    successful = [receipt for receipt in receipts if receipt["outcome"]["status"] == "success"]
    n = len(receipts)
    p95_allowed = n >= 30

    def duration(receipt: dict[str, Any], key: str) -> float | None:
        end = receipt["timing_ns"][key]
        return None if end is None else (end - receipt["timing_ns"]["t0"]) / 1_000_000

    metrics = {}
    for key in ("first_response_byte", "ttft", "ttfo", "complete"):
        values = [value for receipt in successful if (value := duration(receipt, key)) is not None]
        metrics[key] = _distribution(values, p95_allowed=p95_allowed and len(values) >= 30)
    result = {
        "schema": "catalog-switch-cerebrium-aggregate/v1",
        "arm_id": receipts[0]["arm_id"],
        "cohort_id": receipts[0]["cohort_id"],
        "cohort_family": receipts[0]["cohort_family"],
        "model": receipts[0]["model"],
        "cold_state_classification": receipts[0]["cold_state"]["classification"],
        "attempts": n,
        "successes": len(successful),
        "failures": n - len(successful),
        "failure_rate": (n - len(successful)) / n,
        "p95_admissible": p95_allowed,
        "percentile_estimator": slo.PERCENTILE_ESTIMATOR,
        "metrics": metrics,
        "attempt_ids": [receipt["attempt_id"] for receipt in receipts],
        "receipts_sha256": digest(receipts),
    }
    result["aggregate_sha256"] = digest(result)
    return result


def _scenario(receipt: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    classification = receipt["cold_state"]["classification"]
    target = receipt["model"]
    cache = {
        "image": "local_verified",
        "artifact": "node_local_hit",
        "checkpoint": "not_applicable",
        "storage": "ready",
    }
    occupant = None
    capacity = "allocated"
    if classification in {"warm-control", "steady-state-exploration"}:
        scenario = "same_model_hot"
        occupant = {"model_id": target["model_id"], "model_version": target["revision"]}
        cache["artifact"] = "memory_hit"
    elif classification == "process-cold-artifact-hit":
        scenario = "idle_local"
    elif classification == "capacity-miss":
        scenario = "capacity_miss"
        capacity = "unavailable"
        cache = {
            "image": "unavailable",
            "artifact": "unavailable",
            "checkpoint": "missing",
            "storage": "unavailable",
        }
    elif classification == "fresh-node-artifact-miss":
        raise ComparatorError(
            "reviewed shared SLO v1 has no idle remote-artifact scenario; retain the raw receipt instead of inventing an A-to-B occupant"
        )
    else:
        raise ComparatorError("classification cannot map to the reviewed SLO v1")
    return scenario, {
        "current_node_occupant": occupant,
        "cache": cache,
        "capacity": capacity,
        "queue_depth": 0,
    }


def export_shared(receipts: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not receipts:
        raise ComparatorError("cannot export an empty receipt set")
    receipts = sorted(receipts, key=lambda item: item["timing_ns"]["t0"])
    for previous, current in zip(receipts, receipts[1:]):
        if current["timing_ns"]["t0"] <= previous["timing_ns"]["complete"]:
            raise ComparatorError("cold shared-ledger export requires non-overlapping attempts")
    first_t0 = receipts[0]["timing_ns"]["t0"]
    requests = []
    for index, receipt in enumerate(receipts):
        scenario, precondition = _scenario(receipt)
        requests.append(
            {
                "sequence": index,
                "request_id": f"request-{receipt['attempt_id']}",
                "attempt_id": receipt["attempt_id"],
                "offered_at_offset_ms": round((receipt["timing_ns"]["t0"] - first_t0) / 1_000_000),
                "scenario": scenario,
                "target": {
                    "model_id": receipt["model"]["model_id"],
                    "model_version": receipt["model"]["revision"],
                    "artifact_id": receipt["model"]["contract_id"],
                    "artifact_version": receipt["model"]["revision"],
                    "artifact_sha256": receipt["model"]["artifact_identity_sha256"],
                },
                "input": {
                    "workload_id": receipt["request"]["prompt_id"],
                    "input_id": receipt["request"]["prompt_id"],
                    "payload_sha256": receipt["request"]["payload_sha256"],
                    "input_bytes": receipt["request"]["payload_bytes"],
                },
                "precondition": precondition,
            }
        )
    trace = {
        "schema": slo.TRACE_SCHEMA,
        "trace_id": f"trace-{receipts[0]['cohort_id']}",
        "distribution": "adversarial",
        "seed": 240752,
        "catalog_sha256": digest([receipt["model"] for receipt in receipts]),
        "request_count": len(requests),
        "scenario_labels": list(slo.SCENARIOS),
        "requests": requests,
    }
    trace["trace_sha256"] = slo.canonical_sha256(trace)
    slo.validate_trace(trace)

    ledger_id = f"ledger-{receipts[0]['cohort_id']}"
    recorder = {
        "recorder_id": "cerebrium-comparator-v1",
        "clock_id": f"receipt-clock:{receipts[0]['backend']['runtime_id']}",
        "boot_id": receipts[0]["backend"]["runtime_id"],
        "utc_sync_source": "host-chrony-or-timesyncd",
        "max_error_ms": 100.0,
    }
    events: list[dict[str, Any]] = []
    attempt_sequences: dict[str, int] = {}
    first_utc = datetime.strptime(receipts[0]["started_at_utc"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)

    def add(receipt: dict[str, Any], event_type: str, data: dict[str, Any], mono: int) -> None:
        attempt_id = receipt["attempt_id"]
        sequence = attempt_sequences.get(attempt_id, 0)
        attempt_sequences[attempt_id] = sequence + 1
        observed = first_utc + timedelta(microseconds=(mono - first_t0) // 1000)
        events.append(
            {
                "schema": slo.EVENT_SCHEMA,
                "ledger_id": ledger_id,
                "ledger_sequence": len(events),
                "trace_id": trace["trace_id"],
                "request_id": f"request-{attempt_id}",
                "attempt_id": attempt_id,
                "attempt_sequence": sequence,
                "event_id": f"{attempt_id}:{sequence:06d}",
                "observed_at_utc": observed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "observed_monotonic_ns": mono,
                "recorder": recorder,
                "event_type": event_type,
                "data": data,
            }
        )

    for receipt, request in zip(receipts, requests, strict=True):
        t0 = receipt["timing_ns"]["t0"]
        complete = receipt["timing_ns"]["complete"]
        success = receipt["outcome"]["status"] == "success"
        resources = [
            {key: resource[key] for key in ("kind", "id", "project_id", "region")}
            for resource in receipt["backend"]["resources"]
        ]
        add(
            receipt,
            "request.accepted",
            {
                "boundary": slo.T0_BOUNDARY,
                "trace_request_sha256": slo.canonical_sha256(request),
                "scenario": request["scenario"],
                "target": request["target"],
                "input": request["input"],
                "precondition": request["precondition"],
                "environment": {
                    "backend": receipt["backend"]["backend_id"],
                    "backend_version": "v1",
                    "provider": receipt["backend"]["provider"],
                    "project_id": receipt["backend"]["project_id"],
                    "region": receipt["backend"]["region"],
                    "node_id": receipt["backend"]["node_id"],
                    "gpu_type": receipt["backend"]["gpu_type"],
                    "gpu_count": receipt["backend"]["gpu_count"],
                    "image_digest": receipt["backend"]["image_digest"],
                    "code_revision": receipt["backend"]["code_revision"],
                    "config_sha256": receipt["backend"]["config_sha256"],
                    "experiment_id": receipt["cohort_id"],
                },
                "ownership": {
                    "owner_task_id": "catalog-switch-cerebrium-qwen3-glm52-benchmark",
                    "resource_prefix": receipt["backend"]["resource_prefix"],
                    "dedicated": True,
                    "cleanup_required": bool(resources),
                    "resources": resources,
                },
            },
            t0,
        )
        cursor = t0
        failed_phase = "placement" if request["scenario"] == "capacity_miss" else "inference"
        for phase in slo.PHASES:
            cursor += 1
            if phase == failed_phase and not success:
                add(receipt, "phase.started", {"phase": phase, "occurrence": 0}, cursor)
                cursor += 1
                add(receipt, "phase.finished", {"phase": phase, "occurrence": 0, "outcome": "failed", "reason": receipt["outcome"]["reason"], "bytes_moved": 0}, cursor)
            elif (not success and slo.PHASES.index(phase) > slo.PHASES.index(failed_phase)):
                add(receipt, "phase.finished", {"phase": phase, "occurrence": 0, "outcome": "skipped", "reason": "causal prerequisite failed", "bytes_moved": 0}, cursor)
            elif phase == "inference":
                add(receipt, "phase.started", {"phase": phase, "occurrence": 0}, cursor)
                finish = max(cursor + 1, complete - 1)
                add(receipt, "phase.finished", {"phase": phase, "occurrence": 0, "outcome": "completed", "reason": "external dispatch envelope; raw receipt retains TTFRB/TTFT/TTFO", "bytes_moved": 0}, finish)
                cursor = finish
            else:
                add(receipt, "phase.finished", {"phase": phase, "occurrence": 0, "outcome": "skipped", "reason": "provider phase unavailable to external recorder", "bytes_moved": 0}, cursor)
        terminal_mono = max(cursor + 1, complete)
        if success:
            add(
                receipt,
                "response.validated",
                {
                    "boundary": slo.TERMINAL_BOUNDARY,
                    "validator_id": f"semantic-{receipt['request']['prompt_id']}",
                    "validator_sha256": digest(_prompt_map()[receipt["request"]["prompt_id"]]["oracle"]),
                    "response_sha256": receipt["outcome"]["response_sha256"],
                    "response_bytes": receipt["outcome"]["response_bytes"],
                    "complete_body": True,
                    "semantically_valid": True,
                    "model_id": receipt["model"]["model_id"],
                    "model_version": receipt["model"]["revision"],
                },
                terminal_mono,
            )
        else:
            failure_class = receipt["outcome"]["failure_class"]
            if request["scenario"] == "capacity_miss":
                failure_class = "capacity"
            add(receipt, "attempt.failed", {"failure_class": failure_class, "reason": receipt["outcome"]["reason"], "retryable": failure_class in {"capacity", "backend", "preempted", "timeout"}}, terminal_mono)
        add(receipt, "accounting.recorded", {"currency": "USD", "cost_usd": receipt["accounting"]["cost_usd"] or 0.0, "gpu_active_seconds": 0.0, "gpu_idle_seconds": 0.0, "billed_seconds": receipt["accounting"]["billed_seconds"] or 0.0, "bytes_moved_total": 0}, terminal_mono + 1)
        retained = [resource["id"] for resource in resources]
        add(receipt, "cleanup.finished", {"required": bool(resources), "status": "retained" if resources else "not_required", "resources_deleted": [], "resources_retained": retained, "receipt_sha256": None, "reason": "Cerebrium app deletion requires explicit approval; internal cleanup receipt must replace retained state after teardown" if resources else "no owned resources"}, terminal_mono + 2)
    slo.validate_ledger(events, trace)
    return trace, events


def _write_json(path: Path, value: Any) -> None:
    if path.exists() and path.is_symlink():
        raise ComparatorError("output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    run = sub.add_parser("run")
    run.add_argument("--arm", required=True)
    run.add_argument("--cohort", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--attempt", required=True)
    run.add_argument("--endpoint", required=True)
    run.add_argument("--token-env", default="CEREBRIUM_API_KEY")
    run.add_argument("--backend-proof", required=True, type=Path)
    run.add_argument("--cold-state-proof", required=True, type=Path)
    run.add_argument("--output", required=True, type=Path)
    campaign = sub.add_parser("run-internal-qwen-v6-campaign")
    campaign.add_argument("--lease", required=True, type=Path)
    campaign.add_argument("--endpoint", required=True)
    campaign.add_argument("--token-env", default="CATSWITCH_INTERNAL_BEARER")
    campaign.add_argument("--backend-proof", required=True, type=Path)
    campaign.add_argument("--cold-state-proof", required=True, type=Path)
    campaign.add_argument("--warm-state-proof", required=True, type=Path)
    campaign.add_argument("--output-dir", required=True, type=Path)
    aggregate_parser = sub.add_parser("aggregate")
    aggregate_parser.add_argument("--receipts", required=True, type=Path)
    aggregate_parser.add_argument("--output", required=True, type=Path)
    shared = sub.add_parser("export-shared")
    shared.add_argument("--receipts", required=True, type=Path)
    shared.add_argument("--trace", required=True, type=Path)
    shared.add_argument("--ledger", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "validate":
            result = validate_contracts()
        elif args.command == "run":
            token = os.environ.get(args.token_env)
            if not token:
                raise ComparatorError(f"missing token environment variable: {args.token_env}")
            receipt = run_attempt(
                arm_id=args.arm,
                cohort_id=args.cohort,
                prompt_id=args.prompt,
                endpoint=args.endpoint,
                token=token,
                backend=load_json(args.backend_proof),
                cold_state=load_json(args.cold_state_proof),
                attempt_id=args.attempt,
            )
            append_receipt(args.output, receipt)
            result = {"status": "RECORDED", "attempt_id": receipt["attempt_id"], "outcome": receipt["outcome"]["status"]}
        elif args.command == "run-internal-qwen-v6-campaign":
            token = os.environ.get(args.token_env)
            if not token:
                raise ComparatorError(f"missing token environment variable: {args.token_env}")
            if args.output_dir.exists():
                raise ComparatorError("sealed campaign output directory must not already exist")
            args.output_dir.mkdir(parents=True)
            receipts_path = args.output_dir / "attempts.ndjson"
            bundle = run_qwen_qualification_campaign(
                endpoint=args.endpoint,
                token=token,
                backend_template=load_json(args.backend_proof),
                lease_path=args.lease,
                cold_state=load_json(args.cold_state_proof),
                warm_state=load_json(args.warm_state_proof),
                receipt_sink=lambda receipt: append_receipt(receipts_path, receipt),
            )
            _write_json(args.output_dir / "campaign.json", bundle)
            result = {
                "status": "QUALIFIED",
                "lease_id": bundle["lease_id"],
                "runtime_groups": 4,
                "requests": 8,
                "replay_sha256": bundle["replay"]["replay_sha256"],
            }
        elif args.command == "aggregate":
            result = aggregate(load_receipts(args.receipts))
            _write_json(args.output, result)
        elif args.command == "export-shared":
            trace, events = export_shared(load_receipts(args.receipts))
            slo.write_canonical_json(args.trace, trace)
            slo.write_ledger(args.ledger, events)
            result = {"status": "PASS", "trace_sha256": trace["trace_sha256"], "ledger_sha256": slo.file_sha256(args.ledger), "attempts": len(trace["requests"])}
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ComparatorError as exc:
        print(f"COMPARATOR ERROR: {exc}", file=sys.stderr)
        return 2
    except slo.HarnessError as exc:
        print(f"SHARED SLO ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
