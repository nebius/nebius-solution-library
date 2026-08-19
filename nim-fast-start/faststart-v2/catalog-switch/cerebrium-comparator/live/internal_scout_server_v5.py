#!/usr/bin/env python3
"""Authenticated, broker-gated v5 qualification server for the Qwen3 H100 scout.

Ordinal 1 starts one conventional vLLM runtime after request acceptance. Ordinal
2 must use that same container. Both streamed responses receive independent
server-side oracle verdicts; only then is the runtime removed and absence
recorded. The external comparator separately validates both responses.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MODEL_ID = "Qwen/Qwen3-8B"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
EXPECTED_ANSWER = "QWEN3_CATALOG_SWITCH_OK"
LEASE_ID = "catswitch-qwen3-h100-scout-v5-20260819"
RUNTIME_GROUP_IDS = (
    "qwen-smoke-01",
    "qwen-scout-01",
    "qwen-scout-02",
    "qwen-scout-03",
)
IMAGE = (
    "vllm/vllm-openai@"
    "sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d"
)
IMAGE_DIGEST = "sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d"
EXPECTED_PAYLOAD = {
    "chat_template_kwargs": {"enable_thinking": False},
    "max_tokens": 32,
    "messages": [
        {
            "content": "Return exactly QWEN3_CATALOG_SWITCH_OK and no other text.",
            "role": "user",
        }
    ],
    "model": MODEL_ID,
    "stream": True,
    "temperature": 0,
}
PAYLOAD_SHA256 = "c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d"
MODEL_DIR = Path("/var/lib/catswitch/model")
EVIDENCE_DIR = Path("/var/lib/catswitch/evidence")
ACTIVE_SESSION = Path("/var/lib/catswitch/active-session.json")
BOOTSTRAP_PROOF = Path("/var/lib/catswitch/bootstrap-proof.json")
RUNTIME_GATE = Path("/var/lib/catswitch/runtime-gate.json")
CAMPAIGN_EVIDENCE = Path("/var/lib/catswitch/campaign-evidence.json")
GROUP_STATE_DIR = Path("/var/lib/catswitch/runtime-groups")
TOKEN_PATH = Path("/run/catswitch/bearer-token")
GATE_VERIFIER_KEY_PATH = Path("/run/catswitch/gate-verifier-key")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
CONTAINER_RE = re.compile(r"[0-9a-f]{64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
LOCK = threading.Lock()


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def run(
    args: list[str], *, timeout: int = 60, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args, text=True, capture_output=True, timeout=timeout, check=False
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[:800]
        raise RuntimeError(
            f"command failed rc={result.returncode}: {args[0]} {args[1]}: {detail}"
        )
    return result


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def create_json_exclusive(path: Path, value: Any) -> None:
    """Create a durable claim exactly once; never replace an existing claim."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        # A partial/in-doubt claim deliberately remains fail-closed. Startup
        # recovery will never permit a second ordinal-1 from the same group.
        raise


def group_state_path(runtime_group_id: str) -> Path:
    if runtime_group_id not in RUNTIME_GROUP_IDS:
        raise ValueError("runtime group is outside the exact four-group campaign")
    return GROUP_STATE_DIR / f"{runtime_group_id}.json"


def ordinal_claim_path(runtime_group_id: str, ordinal: int) -> Path:
    if runtime_group_id not in RUNTIME_GROUP_IDS or ordinal not in {1, 2}:
        raise ValueError("runtime group/ordinal is outside the exact campaign")
    return GROUP_STATE_DIR / f"{runtime_group_id}.ordinal-{ordinal}.claim.json"


def load_group_state(runtime_group_id: str) -> dict[str, Any] | None:
    path = group_state_path(runtime_group_id)
    if not path.is_file():
        return None
    value = json.loads(path.read_text(), object_pairs_hook=unique_object)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "catalog-switch-runtime-group-state/v5"
        or value.get("runtime_group_id") != runtime_group_id
    ):
        raise RuntimeError("runtime-group state is invalid")
    return value


def claim_runtime_ordinal(
    runtime_group_id: str, attempt_id: str, ordinal: int
) -> dict[str, Any]:
    """Consume an ordinal durably before any runtime start or inference."""
    path = group_state_path(runtime_group_id)
    if ordinal == 1:
        value = {
            "schema": "catalog-switch-runtime-group-state/v5",
            "runtime_group_id": runtime_group_id,
            "state": "ORDINAL1_IN_PROGRESS",
            "container_name": f"catswitch-vllm-{runtime_group_id}",
            "container_id": None,
            "ordinal1_attempt_id": attempt_id,
            "ordinal2_attempt_id": None,
            "claimed_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "failure": None,
        }
        try:
            create_json_exclusive(path, value)
        except FileExistsError as exc:
            raise ValueError(
                "qualification ordinal 1 was already consumed; retry cannot start another runtime"
            ) from exc
        return value
    value = load_group_state(runtime_group_id)
    if (
        ordinal != 2
        or value is None
        or value.get("state") != "AWAITING_ORDINAL2"
        or value.get("ordinal1_attempt_id") == attempt_id
    ):
        raise ValueError("qualification ordinal 2 is not exactly claimable")
    ordinal2_claim = {
        "schema": "catalog-switch-runtime-ordinal-claim/v5",
        "runtime_group_id": runtime_group_id,
        "ordinal": 2,
        "attempt_id": attempt_id,
        "claimed_at_utc": utc_now(),
    }
    try:
        create_json_exclusive(ordinal_claim_path(runtime_group_id, 2), ordinal2_claim)
    except FileExistsError as exc:
        raise ValueError(
            "qualification ordinal 2 was already consumed; retry is fail-closed"
        ) from exc
    value = load_group_state(runtime_group_id)
    if value is None or value.get("state") != "AWAITING_ORDINAL2":
        raise ValueError("qualification ordinal 2 state changed after durable claim")
    value["state"] = "ORDINAL2_IN_PROGRESS"
    value["ordinal2_attempt_id"] = attempt_id
    value["updated_at_utc"] = utc_now()
    atomic_json(path, value)
    return value


def update_group_state(runtime_group_id: str, **updates: Any) -> dict[str, Any]:
    value = load_group_state(runtime_group_id)
    if value is None:
        raise RuntimeError("runtime-group claim is missing")
    value.update(updates)
    value["updated_at_utc"] = utc_now()
    atomic_json(group_state_path(runtime_group_id), value)
    return value


def token() -> str:
    value = TOKEN_PATH.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("runtime bearer token is unavailable")
    return value


def gate_verifier_key() -> str:
    value = GATE_VERIFIER_KEY_PATH.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("broker gate verifier key is unavailable")
    return value


def current_utc() -> datetime:
    return datetime.now(UTC)


def validate_runtime_gate(value: Any) -> dict[str, Any]:
    """Verify a fresh broker-only signature and its exact ledger join."""
    required = {
        "authorization_id",
        "authorization_sha256",
        "broker_receipt_sha256",
        "clearance_expires_at",
        "gate_hmac_sha256",
        "health_proof_sha256",
        "instance_id",
        "isolation_proof_sha256",
        "issued_at_utc",
        "lease_id",
        "lease_plan_sha256",
        "lease_state",
        "network_binding",
        "observed_gpu",
        "profile",
        "runtime_egress_rule_count",
        "schema",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("runtime gate fields differ")
    signature = value["gate_hmac_sha256"]
    payload = {
        key: item for key, item in value.items() if key != "gate_hmac_sha256"
    }
    expected = hmac.new(
        gate_verifier_key().encode(), canonical(payload), hashlib.sha256
    ).hexdigest()
    if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
        raise ValueError("runtime gate signature differs")
    gpu = value["observed_gpu"]
    try:
        issued_at = datetime.strptime(
            value["issued_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
        clearance_expires = datetime.strptime(
            value["clearance_expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=UTC)
    except (TypeError, ValueError) as exc:
        raise ValueError("runtime gate clearance expiry is invalid") from exc
    now = current_utc()
    binding = value["network_binding"]
    profile = value["profile"]
    if (
        value["schema"] != "catalog-switch-internal-runtime-gate/v5"
        or value["authorization_id"]
        != "internal-qwen3-h100-scout-v5-20260819"
        or value["lease_id"] != LEASE_ID
        or value["lease_state"] != "ACTIVE"
        or value["runtime_egress_rule_count"] != 0
        or issued_at > now + timedelta(seconds=5)
        or now - issued_at > timedelta(minutes=5)
        or now >= clearance_expires
        or not all(
            SHA256_RE.fullmatch(str(value[key]))
            for key in (
                "authorization_sha256",
                "broker_receipt_sha256",
                "health_proof_sha256",
                "isolation_proof_sha256",
                "lease_plan_sha256",
            )
        )
        or not isinstance(gpu, dict)
        or set(gpu) != {"count", "name", "uuid_sha256"}
        or gpu["count"] != 1
        or not re.fullmatch(r"NVIDIA H100(?: |$).*", str(gpu["name"]))
        or not SHA256_RE.fullmatch(str(gpu["uuid_sha256"]))
        or not isinstance(binding, dict)
        or set(binding) != {"instance_id", "security_group_id", "subnet_id"}
        or binding["instance_id"] != value["instance_id"]
        or not all(
            re.fullmatch(r"[a-z][a-z0-9-]{7,127}", str(binding[key]))
            for key in ("instance_id", "security_group_id", "subnet_id")
        )
        or profile
        != {"platform": "gpu-h100-sxm", "preset": "1gpu-16vcpu-200gb"}
    ):
        raise ValueError(
            "runtime gate is not a fresh exact ACTIVE/instance/H100/isolation join"
        )
    return value


def load_runtime_gate() -> dict[str, Any]:
    if not RUNTIME_GATE.is_file() or RUNTIME_GATE.is_symlink():
        raise RuntimeError("broker ACTIVE zero-egress gate is unavailable")
    return validate_runtime_gate(json.loads(RUNTIME_GATE.read_text()))


def completed_runtime_groups() -> list[str]:
    if not CAMPAIGN_EVIDENCE.is_file():
        return []
    value = json.loads(CAMPAIGN_EVIDENCE.read_text())
    groups = value.get("completed_runtime_groups")
    if not isinstance(groups, list) or any(group not in RUNTIME_GROUP_IDS for group in groups):
        raise RuntimeError("campaign runtime-group evidence is invalid")
    if len(groups) != len(set(groups)) or len(groups) > len(RUNTIME_GROUP_IDS):
        raise RuntimeError("campaign runtime-group evidence contains duplicates or overflow")
    return groups


def record_completed_runtime_group(runtime_group_id: str) -> dict[str, Any]:
    groups = completed_runtime_groups()
    if runtime_group_id in groups:
        raise RuntimeError("runtime group was already completed")
    groups.append(runtime_group_id)
    if len(groups) > 4:
        raise RuntimeError("campaign exceeds exactly four runtime groups")
    value = {
        "schema": "catalog-switch-qwen-runtime-campaign/v5",
        "required_runtime_groups": list(RUNTIME_GROUP_IDS),
        "completed_runtime_groups": groups,
        "complete": set(groups) == set(RUNTIME_GROUP_IDS) and len(groups) == 4,
        "updated_at_utc": utc_now(),
    }
    atomic_json(CAMPAIGN_EVIDENCE, value)
    return value


def live_containers() -> list[str]:
    result = run(
        [
            "docker",
            "ps",
            "--no-trunc",
            "--filter",
            "name=^/catswitch-vllm-",
            "--format",
            "{{.ID}}",
        ],
        timeout=30,
    )
    values = [line for line in result.stdout.splitlines() if line]
    if any(not CONTAINER_RE.fullmatch(value) for value in values):
        raise RuntimeError("docker ps returned a truncated or invalid container ID")
    return values


def exact_container_id(name: str) -> str | None:
    result = run(
        ["docker", "inspect", "--format", "{{.Id}} {{.State.Running}}", name],
        timeout=30,
        check=False,
    )
    if result.returncode:
        return None
    parts = result.stdout.strip().split()
    if len(parts) != 2 or parts[1] != "true" or not CONTAINER_RE.fullmatch(parts[0]):
        raise RuntimeError("docker inspect did not prove one exact running container ID")
    return parts[0]


def start_runtime(runtime_group_id: str) -> tuple[str, str]:
    container_name = f"catswitch-vllm-{runtime_group_id}"
    result = run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--gpus",
            "all",
            "--ipc",
            "host",
            "--network",
            "host",
            "-v",
            f"{MODEL_DIR}:/model:ro",
            IMAGE,
            "--model",
            "/model",
            "--served-model-name",
            MODEL_ID,
            "--dtype",
            "bfloat16",
            "--tensor-parallel-size",
            "1",
            "--max-model-len",
            "32768",
            "--reasoning-parser",
            "qwen3",
            "--disable-log-requests",
        ],
        timeout=120,
    )
    container_id = result.stdout.strip()
    if not CONTAINER_RE.fullmatch(container_id):
        raise RuntimeError("docker did not return a canonical container ID")
    return container_name, container_id


def wait_ready(deadline_seconds: int = 900) -> None:
    deadline = time.monotonic() + deadline_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
                if response.status == 200:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8000/v1/models", timeout=5
                    ) as models_response:
                        value = json.loads(models_response.read())
                    if [item.get("id") for item in value.get("data", [])] == [MODEL_ID]:
                        return
                    last_error = "served model identity differs"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        time.sleep(2)
    raise TimeoutError(f"vLLM readiness timed out: {last_error}")


def remove_runtime(container_name: str) -> dict[str, Any]:
    run(["docker", "rm", "-f", container_name], timeout=120, check=False)
    absent = exact_container_id(container_name) is None
    return {"container_absent": absent, "verified_at_utc": utc_now()}


class StreamOracle:
    """Incrementally reconstruct the OpenAI stream for a server-side verdict."""

    def __init__(self) -> None:
        self.content = ""
        self.reasoning = ""
        self.model_id: str | None = None
        self.tool_calls: dict[int, dict[str, str]] = {}
        self.done = False

    def feed(self, raw: bytes) -> None:
        line = raw.strip()
        if not line or line.startswith(b":"):
            return
        if not line.startswith(b"data:"):
            raise ValueError("stream contains non-SSE data")
        data = line[5:].strip()
        if data == b"[DONE]":
            self.done = True
            return
        chunk = json.loads(data, object_pairs_hook=unique_object)
        model = chunk.get("model")
        if model is not None:
            if self.model_id is not None and self.model_id != model:
                raise ValueError("stream changed model identity")
            self.model_id = model
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return
        delta = choices[0].get("delta", {})
        if not isinstance(delta, dict):
            raise ValueError("stream delta is not an object")
        content = delta.get("content") or ""
        reasoning = delta.get("reasoning_content") or ""
        if not isinstance(content, str) or not isinstance(reasoning, str):
            raise ValueError("stream text fields are not strings")
        self.content += content
        self.reasoning += reasoning
        calls = delta.get("tool_calls") or []
        if not isinstance(calls, list):
            raise ValueError("stream tool calls are not a list")
        for item in calls:
            index = item.get("index")
            if not isinstance(index, int):
                raise ValueError("stream tool call index is invalid")
            entry = self.tool_calls.setdefault(index, {"name": "", "arguments": ""})
            function = item.get("function") or {}
            entry["name"] += str(function.get("name") or "")
            entry["arguments"] += str(function.get("arguments") or "")

    def verdict(self) -> tuple[dict[str, Any], bool, str]:
        response = {
            "model_id": self.model_id,
            "content": self.content,
            "reasoning_content": self.reasoning,
            "tool_calls": [
                {"index": index, **value}
                for index, value in sorted(self.tool_calls.items())
            ],
        }
        valid = (
            self.done
            and self.model_id == MODEL_ID
            and self.content.strip() == EXPECTED_ANSWER
            and not self.reasoning.strip()
            and not self.tool_calls
        )
        return response, valid, "exact content matched" if valid else "exact content mismatch"


def validate_transition(
    active: dict[str, Any] | None,
    runtime_group_id: str,
    attempt_id: str,
    ordinal: int,
) -> None:
    if runtime_group_id not in RUNTIME_GROUP_IDS:
        raise ValueError("runtime group is outside the exact four-group campaign")
    if ordinal == 1:
        if active is not None:
            raise ValueError("another cold runtime is awaiting qualification ordinal 2")
        if runtime_group_id in completed_runtime_groups():
            raise ValueError("runtime group was already completed")
        if load_group_state(runtime_group_id) is not None:
            raise ValueError(
                "qualification ordinal 1 was already consumed; retry is fail-closed"
            )
        return
    if active is None:
        raise ValueError("qualification ordinal 2 has no cold-started runtime")
    if active.get("runtime_group_id") != runtime_group_id:
        raise ValueError("qualification ordinal 2 changed runtime group")
    requests = active.get("requests")
    if not isinstance(requests, list) or len(requests) != 1:
        raise ValueError("qualification ordinal 2 requires exactly one prior result")
    if requests[0].get("attempt_id") == attempt_id:
        raise ValueError("qualification requests must have distinct attempt IDs")
    group_state = load_group_state(runtime_group_id)
    if (
        group_state is None
        or group_state.get("state") != "AWAITING_ORDINAL2"
        or group_state.get("ordinal1_attempt_id") != requests[0].get("attempt_id")
        or group_state.get("container_id") != active.get("container_id")
    ):
        raise ValueError("qualification ordinal 2 durable state differs")


def load_active() -> dict[str, Any] | None:
    if not ACTIVE_SESSION.is_file():
        return None
    value = json.loads(ACTIVE_SESSION.read_text())
    name = value.get("container_name")
    if not isinstance(name, str) or exact_container_id(name) != value.get("container_id"):
        raise RuntimeError("persisted qualification runtime identity is not live")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "catalog-switch-qwen-scout/5"
    protocol_version = "HTTP/1.0"

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def authorized(self) -> bool:
        return hmac.compare_digest(
            self.headers.get("Authorization", ""), f"Bearer {token()}"
        )

    def json_response(self, status: int, value: Any) -> None:
        body = canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self.authorized():
            self.json_response(401, {"error": "unauthorized"})
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.json_response(
                200,
                {
                    "schema": "catalog-switch-internal-scout-health/v5",
                    "bootstrap_proof_sha256": hashlib.sha256(
                        BOOTSTRAP_PROOF.read_bytes()
                    ).hexdigest(),
                    "active_runtime_group": (
                        json.loads(ACTIVE_SESSION.read_text()).get("runtime_group_id")
                        if ACTIVE_SESSION.is_file()
                        else None
                    ),
                    "live_inference_containers": live_containers(),
                },
            )
            return
        if parsed.path == "/campaign":
            groups = completed_runtime_groups()
            self.json_response(
                200,
                {
                    "schema": "catalog-switch-qwen-runtime-campaign/v5",
                    "required_runtime_groups": list(RUNTIME_GROUP_IDS),
                    "completed_runtime_groups": groups,
                    "complete": len(groups) == 4 and set(groups) == set(RUNTIME_GROUP_IDS),
                },
            )
            return
        if parsed.path.startswith("/qualification/"):
            group = parsed.path.removeprefix("/qualification/")
            if not ID_RE.fullmatch(group):
                self.json_response(400, {"error": "invalid runtime-group ID"})
                return
            evidence = EVIDENCE_DIR / f"qualification-{group}.json"
            if not evidence.is_file():
                self.json_response(404, {"error": "qualification evidence not found"})
                return
            self.json_response(200, json.loads(evidence.read_text()))
            return
        self.json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.authorized():
            self.json_response(401, {"error": "unauthorized"})
            return
        if self.path == "/broker/activate":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 1 <= length <= 16_384:
                self.json_response(400, {"error": "invalid activation length"})
                return
            try:
                value = json.loads(
                    self.rfile.read(length), object_pairs_hook=unique_object
                )
                validated = validate_runtime_gate(value)
            except (ValueError, json.JSONDecodeError) as exc:
                self.json_response(400, {"error": f"invalid runtime gate: {exc}"})
                return
            atomic_json(RUNTIME_GATE, validated)
            self.json_response(
                200,
                {
                    "schema": "catalog-switch-runtime-gate-activation/v5",
                    "runtime_gate_sha256": hashlib.sha256(canonical(validated)).hexdigest(),
                },
            )
            return
        if self.path != "/v1/chat/completions":
            self.json_response(404, {"error": "not found"})
            return
        try:
            runtime_gate = load_runtime_gate()
        except (RuntimeError, ValueError, json.JSONDecodeError):
            self.json_response(503, {"error": "broker ACTIVE zero-egress gate required"})
            return
        attempt_id = self.headers.get("X-Catswitch-Attempt-ID", "")
        runtime_group_id = self.headers.get("X-Catswitch-Runtime-Group-ID", "")
        try:
            ordinal = int(self.headers.get("X-Catswitch-Qualification-Ordinal", "0"))
        except ValueError:
            ordinal = 0
        if not ID_RE.fullmatch(attempt_id) or not ID_RE.fullmatch(runtime_group_id):
            self.json_response(400, {"error": "missing or invalid qualification identity"})
            return
        if ordinal not in {1, 2}:
            self.json_response(400, {"error": "qualification ordinal must be 1 or 2"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 16_384:
            self.json_response(400, {"error": "invalid payload length"})
            return
        raw_payload = self.rfile.read(length)
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            self.json_response(400, {"error": "invalid JSON"})
            return
        if (
            hashlib.sha256(raw_payload).hexdigest() != PAYLOAD_SHA256
            or canonical(payload) != canonical(EXPECTED_PAYLOAD)
        ):
            self.json_response(400, {"error": "payload differs from frozen input"})
            return
        if not LOCK.acquire(blocking=False):
            self.json_response(409, {"error": "replica_concurrency=1"})
            return
        try:
            self.handle_qualification(
                runtime_group_id, attempt_id, ordinal, raw_payload, runtime_gate
            )
        finally:
            LOCK.release()

    def handle_qualification(
        self,
        runtime_group_id: str,
        attempt_id: str,
        ordinal: int,
        raw_payload: bytes,
        runtime_gate: dict[str, Any],
    ) -> None:
        active = load_active()
        response_started = False
        ordinal_claimed = False
        container_name = active.get("container_name") if active else None
        try:
            validate_transition(active, runtime_group_id, attempt_id, ordinal)
            group_state = claim_runtime_ordinal(
                runtime_group_id, attempt_id, ordinal
            )
            ordinal_claimed = True
            if ordinal == 1:
                if live_containers():
                    raise RuntimeError("live inference runtime existed before cold request")
                container_name, container_id = start_runtime(runtime_group_id)
                group_state = update_group_state(
                    runtime_group_id,
                    container_name=container_name,
                    container_id=container_id,
                )
                wait_ready()
                active = {
                    "runtime_group_id": runtime_group_id,
                    "container_name": container_name,
                    "container_id": container_id,
                    "cold_start_count": 1,
                    "requests": [],
                }
            else:
                assert active is not None and container_name is not None
                if exact_container_id(container_name) != active["container_id"]:
                    raise RuntimeError("qualification ordinal 2 is not using the same container")
            current_gate = load_runtime_gate()
            if current_gate != runtime_gate:
                raise RuntimeError("broker runtime gate changed before inference dispatch")
            request = urllib.request.Request(
                "http://127.0.0.1:8000/v1/chat/completions",
                data=raw_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            oracle = StreamOracle()
            with urllib.request.urlopen(request, timeout=300) as upstream:
                self.send_response(upstream.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Catswitch-Attempt-ID", attempt_id)
                self.send_header("X-Catswitch-Runtime-Group-ID", runtime_group_id)
                self.send_header("X-Catswitch-Container-ID", active["container_id"])
                self.send_header("X-Catswitch-Lease-ID", LEASE_ID)
                self.send_header("X-Catswitch-Qualification-Ordinal", str(ordinal))
                self.send_header(
                    "X-Catswitch-Runtime-Gate-SHA256",
                    hashlib.sha256(canonical(runtime_gate)).hexdigest(),
                )
                self.end_headers()
                response_started = True
                while True:
                    line = upstream.readline()
                    if not line:
                        break
                    oracle.feed(line)
                    self.wfile.write(line)
                    self.wfile.flush()
            response, valid, reason = oracle.verdict()
            result = {
                "attempt_id": attempt_id,
                "model_id": response["model_id"],
                "ordinal": ordinal,
                "oracle_reason": reason,
                "response_sha256": hashlib.sha256(canonical(response)).hexdigest(),
                "semantically_valid": valid,
                "stream_complete": oracle.done,
            }
            active["requests"].append(result)
            if ordinal == 1 and valid:
                update_group_state(
                    runtime_group_id,
                    state="AWAITING_ORDINAL2",
                    container_id=active["container_id"],
                    ordinal1_result=result,
                )
                atomic_json(ACTIVE_SESSION, active)
                return
            teardown = remove_runtime(container_name)
            if ACTIVE_SESSION.exists():
                ACTIVE_SESSION.unlink()
            evidence = {
                "schema": "catalog-switch-qwen-runtime-qualification/v5",
                "runtime_group_id": runtime_group_id,
                "container_id": active["container_id"],
                "cold_start_count": active["cold_start_count"],
                "requests": active["requests"],
                "teardown": teardown,
                "completed_at_utc": utc_now(),
                "status": (
                    "QUALIFIED"
                    if len(active["requests"]) == 2
                    and all(item["semantically_valid"] for item in active["requests"])
                    and teardown["container_absent"]
                    else "FAILED"
                ),
            }
            atomic_json(EVIDENCE_DIR / f"qualification-{runtime_group_id}.json", evidence)
            if evidence["status"] == "QUALIFIED":
                update_group_state(
                    runtime_group_id,
                    state="QUALIFIED",
                    ordinal2_result=result,
                    teardown=teardown,
                )
                record_completed_runtime_group(runtime_group_id)
            else:
                update_group_state(
                    runtime_group_id,
                    state="FAILED",
                    ordinal2_result=result if ordinal == 2 else None,
                    teardown=teardown,
                    failure="semantic-or-teardown-failure",
                )
            if not valid:
                raise RuntimeError("server-side semantic oracle rejected the streamed response")
        except Exception as exc:
            teardown = None
            if container_name:
                teardown = remove_runtime(container_name)
            if ACTIVE_SESSION.exists():
                ACTIVE_SESSION.unlink()
            try:
                if ordinal_claimed and load_group_state(runtime_group_id) is not None:
                    update_group_state(
                        runtime_group_id,
                        state="FAILED",
                        teardown=teardown,
                        failure=f"{type(exc).__name__}:{str(exc)[:240]}",
                    )
            except Exception:
                pass
            if not response_started:
                self.json_response(
                    500,
                    {"error": f"qualification failed: {type(exc).__name__}"},
                )


def recover_runtime_groups() -> None:
    """Convert every crash-in-doubt ordinal into a terminal failed group."""
    for runtime_group_id in RUNTIME_GROUP_IDS:
        state = load_group_state(runtime_group_id)
        if state is None:
            continue
        if state.get("state") in {"ORDINAL1_IN_PROGRESS", "ORDINAL2_IN_PROGRESS"}:
            teardown = remove_runtime(state["container_name"])
            update_group_state(
                runtime_group_id,
                state="FAILED_CRASH_RECOVERED",
                teardown=teardown,
                failure="server-restarted-with-ordinal-in-progress; retry-forbidden",
            )
            if ACTIVE_SESSION.is_file():
                active = json.loads(ACTIVE_SESSION.read_text())
                if active.get("runtime_group_id") == runtime_group_id:
                    ACTIVE_SESSION.unlink()
        elif state.get("state") == "AWAITING_ORDINAL2":
            ordinal2_in_doubt = ordinal_claim_path(runtime_group_id, 2).is_file()
            runtime_lost = (
                exact_container_id(state["container_name"])
                != state.get("container_id")
            )
            if ordinal2_in_doubt or runtime_lost:
                teardown = remove_runtime(state["container_name"])
                update_group_state(
                    runtime_group_id,
                    state=(
                        "FAILED_CRASH_RECOVERED"
                        if ordinal2_in_doubt
                        else "FAILED_RUNTIME_LOST"
                    ),
                    teardown=teardown,
                    failure=(
                        "server-restarted-with-ordinal-2-claim-in-doubt; retry-forbidden"
                        if ordinal2_in_doubt
                        else "ordinal-1 runtime was not live after restart; retry-forbidden"
                    ),
                )
                if ACTIVE_SESSION.is_file():
                    active = json.loads(ACTIVE_SESSION.read_text())
                    if active.get("runtime_group_id") == runtime_group_id:
                        ACTIVE_SESSION.unlink()


def main() -> None:
    if (
        not BOOTSTRAP_PROOF.is_file()
        or not TOKEN_PATH.is_file()
        or not GATE_VERIFIER_KEY_PATH.is_file()
    ):
        raise SystemExit("bootstrap proof, bearer, or gate verifier key is missing")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    GROUP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    recover_runtime_groups()
    load_active()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
