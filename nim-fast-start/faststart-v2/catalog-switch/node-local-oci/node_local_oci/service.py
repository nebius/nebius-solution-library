"""HTTP readiness and inference client for the launched node-local runtime.

Only node-local ``http://127.0.0.1:...`` endpoints (enforced by the policy
contract) are ever contacted.  Raw response bytes are streamed to a file so
the semantic oracle and the shared ledger always see exactly what the model
produced — the agent never re-serializes or normalizes a response body.
"""

from __future__ import annotations

import http.client
import time
import urllib.parse
from pathlib import Path

from .errors import Refusal, require


def _split_endpoint(endpoint: str) -> tuple[str, int]:
    parsed = urllib.parse.urlsplit(endpoint)
    require(parsed.scheme == "http" and parsed.hostname == "127.0.0.1",
            "service.endpoint", f"endpoint must be http://127.0.0.1: {endpoint!r}")
    require(parsed.port is not None, "service.endpoint-port",
            f"endpoint carries no port: {endpoint!r}")
    return parsed.hostname, parsed.port


def wait_ready(endpoint: str, health_path: str, *, deadline_monotonic: float,
               poll_interval_s: float = 0.2) -> dict:
    host, port = _split_endpoint(endpoint)
    attempts = 0
    last_error = "never polled"
    while time.monotonic() < deadline_monotonic:
        attempts += 1
        connection = http.client.HTTPConnection(host, port, timeout=5.0)
        try:
            connection.request("GET", health_path)
            response = connection.getresponse()
            body = response.read()
            if response.status == 200:
                return {"attempts": attempts, "status": response.status,
                        "body_bytes": len(body)}
            last_error = f"status {response.status}"
        except OSError as error:
            last_error = str(error)
        finally:
            connection.close()
        time.sleep(poll_interval_s)
    raise Refusal("service.readiness-timeout",
                  f"{endpoint}{health_path} not ready before deadline "
                  f"({attempts} polls, last: {last_error})")


def post_inference(endpoint: str, infer_path: str, payload: bytes,
                   response_path: Path, *, timeout_s: float) -> dict:
    host, port = _split_endpoint(endpoint)
    connection = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        connection.request("POST", infer_path, body=payload,
                           headers={"Content-Type": "application/json",
                                    "Content-Length": str(len(payload))})
        response = connection.getresponse()
        body = response.read()
    except OSError as error:
        raise Refusal("service.inference-transport",
                      f"inference request failed: {error}") from error
    finally:
        connection.close()
    require(response.status == 200, "service.inference-status",
            f"inference returned HTTP {response.status}")
    require(len(body) > 0, "service.inference-empty", "inference response body is empty")
    require(not response_path.exists(), "service.response-exists",
            f"refusing to overwrite captured response {response_path}")
    response_path.write_bytes(body)
    return {"status": response.status, "response_bytes": len(body),
            "response_path": str(response_path)}
