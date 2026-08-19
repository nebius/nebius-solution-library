#!/usr/bin/env python3
"""Authenticated, single-flight process-cold Qwen3 scout proxy.

This service is deliberately small and standard-library-only.  It accepts the
frozen OpenAI request, launches a new digest-pinned vLLM container after the
request is accepted, forwards the streaming response, records backend phase
diagnostics, and removes the container before admitting another attempt.
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
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MODEL_ID = "Qwen/Qwen3-8B"
MODEL_REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
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
EVIDENCE_DIR = Path("/var/lib/catswitch/evidence")
BOOTSTRAP_PROOF = Path("/var/lib/catswitch/bootstrap-proof.json")
MODEL_DIR = Path("/var/lib/catswitch/model")
TOKEN_PATH = Path("/run/catswitch/bearer-token")
ATTEMPT_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}")
LOCK = threading.Lock()


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


def run(args: list[str], *, timeout: int = 60, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()[:800]
        raise RuntimeError(f"command failed rc={result.returncode}: {args[0]} {args[1]}: {detail}")
    return result


def token() -> str:
    value = TOKEN_PATH.read_text().strip()
    if len(value) < 32:
        raise RuntimeError("runtime bearer token is unavailable")
    return value


def live_containers() -> list[str]:
    result = run(
        ["docker", "ps", "--filter", "name=^/catswitch-vllm-", "--format", "{{.ID}}"],
        timeout=30,
    )
    return [line for line in result.stdout.splitlines() if line]


def docker_image_id() -> str:
    result = run(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], timeout=30)
    return result.stdout.strip()


def artifact_bytes() -> int:
    total = 0
    for path in MODEL_DIR.rglob("*"):
        if path.is_file() and ".cache" not in path.parts:
            total += path.stat().st_size
    return total


def gpu_snapshot() -> list[dict[str, str]]:
    result = run(
        [
            "nvidia-smi",
            "--query-gpu=uuid,name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=30,
    )
    values = []
    for line in result.stdout.splitlines():
        fields = [item.strip() for item in line.split(",")]
        if len(fields) == 4:
            values.append(
                {
                    "uuid": fields[0],
                    "name": fields[1],
                    "memory_total_mib": fields[2],
                    "driver_version": fields[3],
                }
            )
    return values


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    os.replace(temporary, path)


def wait_ready(deadline_seconds: int = 900) -> dict[str, Any]:
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
                    ids = [item.get("id") for item in value.get("data", [])]
                    if ids == [MODEL_ID]:
                        return {"health_status": 200, "model_ids": ids}
                    last_error = f"unexpected model IDs: {ids}"
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        time.sleep(2)
    raise TimeoutError(f"vLLM readiness timed out: {last_error}")


def start_runtime(attempt_id: str) -> tuple[str, str, list[str]]:
    container_name = f"catswitch-vllm-{attempt_id}"
    command = [
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
    ]
    result = run(command, timeout=120)
    container_id = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        raise RuntimeError("docker did not return a canonical container ID")
    return container_name, container_id, command


def remove_runtime(container_name: str) -> dict[str, Any]:
    result = run(["docker", "rm", "-f", container_name], timeout=120, check=False)
    absent = run(
        ["docker", "ps", "-a", "--filter", f"name=^/{container_name}$", "--format", "{{.ID}}"],
        timeout=30,
    ).stdout.strip() == ""
    return {
        "command_returncode": result.returncode,
        "container_absent": absent,
        "stderr": result.stderr.strip()[:400],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "catalog-switch-qwen-scout/1"
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {token()}"
        return hmac.compare_digest(supplied, expected)

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
        if self.path == "/health":
            proof = json.loads(BOOTSTRAP_PROOF.read_text())
            self.json_response(
                200,
                {
                    "schema": "catalog-switch-internal-scout-health/v1",
                    "observed_at": utc_now(),
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "image_digest": IMAGE_DIGEST,
                    "image_id": docker_image_id(),
                    "artifact_bytes": artifact_bytes(),
                    "gpu": gpu_snapshot(),
                    "live_inference_containers": live_containers(),
                    "bootstrap_proof_sha256": hashlib.sha256(canonical(proof)).hexdigest(),
                },
            )
            return
        if self.path.startswith("/evidence/"):
            attempt_id = self.path.removeprefix("/evidence/")
            if not ATTEMPT_RE.fullmatch(attempt_id):
                self.json_response(400, {"error": "invalid attempt ID"})
                return
            path = EVIDENCE_DIR / f"{attempt_id}.json"
            if not path.is_file():
                self.json_response(404, {"error": "evidence not found"})
                return
            self.json_response(200, json.loads(path.read_text()))
            return
        self.json_response(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.authorized():
            self.json_response(401, {"error": "unauthorized"})
            return
        if self.path != "/v1/chat/completions":
            self.json_response(404, {"error": "not found"})
            return
        attempt_id = self.headers.get("X-Catswitch-Attempt-ID", "")
        if not ATTEMPT_RE.fullmatch(attempt_id):
            self.json_response(400, {"error": "missing or invalid attempt ID"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 16_384:
            self.json_response(400, {"error": "invalid payload length"})
            return
        raw_payload = self.rfile.read(length)
        if hashlib.sha256(raw_payload).hexdigest() != PAYLOAD_SHA256:
            self.json_response(400, {"error": "payload digest differs from frozen input"})
            return
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            self.json_response(400, {"error": "invalid JSON"})
            return
        if canonical(payload) != canonical(EXPECTED_PAYLOAD):
            self.json_response(400, {"error": "payload differs from frozen input"})
            return
        if not LOCK.acquire(blocking=False):
            self.json_response(409, {"error": "replica_concurrency=1"})
            return
        try:
            self._cold_attempt(attempt_id, raw_payload)
        finally:
            LOCK.release()

    def _cold_attempt(self, attempt_id: str, raw_payload: bytes) -> None:
        evidence: dict[str, Any] = {
            "schema": "catalog-switch-internal-qwen-backend-evidence/v1",
            "attempt_id": attempt_id,
            "accepted_at_utc": utc_now(),
            "server_accept_monotonic_ns": time.monotonic_ns(),
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "image_digest": IMAGE_DIGEST,
            "request_sha256": hashlib.sha256(raw_payload).hexdigest(),
            "cold_classification": "process-cold-artifact-hit",
            "startup_path": "conventional",
            "checkpointing": False,
            "prefix_cache": False,
            "before": {},
            "runtime": {},
            "timing_ns": {},
            "cleanup": {},
            "outcome": "failed",
            "error": None,
        }
        container_name = f"catswitch-vllm-{attempt_id}"
        response_started = False
        try:
            before_live = live_containers()
            evidence["before"] = {
                "live_inference_containers": before_live,
                "no_live_replica_before_demand": before_live == [],
                "image_id": docker_image_id(),
                "image_state": "local-verified",
                "artifact_state": "node-local-hit",
                "artifact_bytes": artifact_bytes(),
                "gpu": gpu_snapshot(),
            }
            if before_live:
                raise RuntimeError("a live inference container existed before the admitted request")
            launch_start = time.monotonic_ns()
            container_name, container_id, command = start_runtime(attempt_id)
            evidence["timing_ns"]["runtime_launch_start"] = launch_start
            evidence["runtime"] = {
                "container_name": container_name,
                "container_id": container_id,
                "command": command,
                "unique_runtime_identity": True,
            }
            ready = wait_ready()
            ready_at = time.monotonic_ns()
            evidence["timing_ns"]["service_ready"] = ready_at
            evidence["runtime"]["readiness"] = ready
            request = urllib.request.Request(
                "http://127.0.0.1:8000/v1/chat/completions",
                data=raw_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            inference_dispatch = time.monotonic_ns()
            evidence["timing_ns"]["inference_dispatch"] = inference_dispatch
            with urllib.request.urlopen(request, timeout=300) as upstream:
                self.send_response(upstream.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Catswitch-Attempt-ID", attempt_id)
                self.end_headers()
                response_started = True
                first_upstream_byte = None
                response_bytes = 0
                while True:
                    line = upstream.readline()
                    if not line:
                        break
                    observed = time.monotonic_ns()
                    if first_upstream_byte is None:
                        first_upstream_byte = observed
                    response_bytes += len(line)
                    self.wfile.write(line)
                    self.wfile.flush()
                evidence["timing_ns"]["first_upstream_byte"] = first_upstream_byte
                evidence["timing_ns"]["upstream_complete"] = time.monotonic_ns()
                evidence["runtime"]["stream_bytes"] = response_bytes
            evidence["outcome"] = "stream-complete"
        except Exception as exc:
            evidence["error"] = f"{type(exc).__name__}: {str(exc)[:800]}"
            if not response_started:
                self.json_response(500, {"error": "internal conventional-start attempt failed"})
        finally:
            evidence["cleanup"] = remove_runtime(container_name)
            evidence["cleanup"]["verified_at_utc"] = utc_now()
            evidence["completed_at_utc"] = utc_now()
            evidence["evidence_sha256"] = hashlib.sha256(canonical(evidence)).hexdigest()
            atomic_json(EVIDENCE_DIR / f"{attempt_id}.json", evidence)


def main() -> None:
    if not BOOTSTRAP_PROOF.is_file() or not TOKEN_PATH.is_file():
        raise SystemExit("bootstrap proof or bearer token is missing")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
