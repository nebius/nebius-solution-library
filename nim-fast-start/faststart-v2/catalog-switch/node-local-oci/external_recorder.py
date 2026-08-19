"""External recorder for the node-local OCI switch adapter.

This tool embodies the *recorder* authority: it owns the shared request-SLO
ledger (appending through the pinned harness only), signs acceptance
authorizations with the recorder private key, and mirrors the agent's signed
receipt stream into shared ledger events.  It runs in a separate process
from the agent and never holds the agent, controller, or oracle keys.

The node agent can only *read* the ledger and *verify* authorizations, so it
cannot mint T0.  Conversely this recorder performs no OCI/GPU action: every
runtime claim it mirrors originates from an agent receipt whose signature is
verifiable under the agent public key.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

LANE_DIR = Path(__file__).resolve().parent
FASTSTART_ROOT = LANE_DIR.parent.parent
for entry in (str(FASTSTART_ROOT), str(LANE_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from performance.request_slo import harness  # noqa: E402
from node_local_oci import contracts  # noqa: E402
from node_local_oci.journal import canonical_json  # noqa: E402
from node_local_oci.keys import load_private, sign  # noqa: E402



def build_trace(*, trace_id: str, catalog: dict, requests: list[dict],
                distribution: str = "adversarial", seed: int = 0) -> dict:
    """Build and validate a canonical trace around real request payloads."""
    trace = {
        "schema": harness.TRACE_SCHEMA,
        "trace_id": trace_id,
        "catalog_sha256": harness.canonical_sha256(catalog),
        "distribution": distribution,
        "seed": seed,
        "request_count": len(requests),
        "scenario_labels": list(harness.SCENARIOS),
        "requests": requests,
    }
    trace["trace_sha256"] = harness.canonical_sha256(
        {key: value for key, value in trace.items() if key != "trace_sha256"})
    return harness.validate_trace(trace)


class ExternalRecorder:
    def __init__(self, *, recorder_key_path: Path, ledger_path: Path, ledger_id: str,
                 trace: dict, exchange_dir: Path, recorder_id: str,
                 max_error_ms: float = 50.0) -> None:
        self.private = load_private(Path(recorder_key_path))
        self.ledger_path = Path(ledger_path)
        self.ledger_id = ledger_id
        self.trace = trace
        self.exchange_dir = Path(exchange_dir)
        self.exchange_dir.mkdir(parents=True, exist_ok=True)
        self.recorder_id = recorder_id
        self.recorder = harness.default_recorder(recorder_id, max_error_ms=max_error_ms)
        self._bytes_moved: dict[str, int] = {}
        self._terminal_seen: set[str] = set()
        self._processed_receipts = 0

    # -- T0 ---------------------------------------------------------------

    def accept(self, trace_request: dict, *, payload: bytes, environment: dict,
               ownership: dict) -> dict:
        """Append request.accepted, then sign and publish the authorization."""
        digest = hashlib.sha256(payload).hexdigest()
        if digest != trace_request["input"]["payload_sha256"]:
            raise SystemExit("payload bytes do not match the trace pin")
        data = {
            "boundary": harness.T0_BOUNDARY,
            "trace_request_sha256": harness.canonical_sha256(trace_request),
            "scenario": trace_request["scenario"],
            "target": trace_request["target"],
            "input": trace_request["input"],
            "precondition": trace_request["precondition"],
            "environment": environment,
            "ownership": ownership,
        }
        event = harness.append_event(
            self.ledger_path,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=trace_request["request_id"],
            attempt_id=trace_request["attempt_id"],
            recorder=self.recorder,
            event_type="request.accepted",
            data=data,
        )
        lines = self.ledger_path.read_bytes().split(b"\n")[:-1]
        line_number = len(lines)
        line_sha256 = hashlib.sha256(lines[-1] + b"\n").hexdigest()
        body = {
            "schema": contracts.AUTHORIZATION_SCHEMA,
            "attempt_id": trace_request["attempt_id"],
            "request_id": trace_request["request_id"],
            "trace_id": self.trace["trace_id"],
            "ledger_id": self.ledger_id,
            "ledger_line_number": line_number,
            "line_sha256": line_sha256,
            "accepted_monotonic_ns": event["observed_monotonic_ns"],
            "recorder_id": self.recorder_id,
        }
        envelope = dict(body)
        envelope["signature"] = sign(self.private, "recorder",
                                     contracts.AUTHORIZATION_SCHEMA, body)
        payload_path = self.exchange_dir / f"payload-{trace_request['attempt_id']}.bin"
        if not payload_path.exists():
            payload_path.write_bytes(payload)
        auth_path = self.exchange_dir / f"authorization-{trace_request['attempt_id']}.json"
        auth_path.write_text(canonical_json(envelope) + "\n", encoding="utf-8")
        return event

    # -- receipt mirroring ---------------------------------------------------

    def _append(self, attempt_id: str, event_type: str, data: dict) -> dict:
        matching = [request for request in self.trace["requests"]
                    if request["attempt_id"] == attempt_id]
        if len(matching) != 1:
            raise SystemExit(f"receipt names unknown attempt {attempt_id!r}")
        return harness.append_event(
            self.ledger_path,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=matching[0]["request_id"],
            attempt_id=attempt_id,
            recorder=self.recorder,
            event_type=event_type,
            data=data,
        )

    def mirror_new_receipts(self, receipts_path: Path, *, model_binding: dict) -> int:
        """Mirror agent receipts observed since the last call. Returns count."""
        if not receipts_path.is_file():
            return 0
        text = receipts_path.read_text(encoding="utf-8")
        complete = text[:text.rfind("\n") + 1] if "\n" in text else ""
        lines = complete.splitlines()
        mirrored = 0
        for line in lines[self._processed_receipts:]:
            self._processed_receipts += 1
            receipt = json.loads(line)["entry"]
            kind = receipt.get("kind")
            attempt_id = receipt.get("attempt_id")
            data = receipt.get("data", {})
            if kind == "phase-started" and attempt_id:
                self._append(attempt_id, "phase.started",
                             {"phase": data["phase"], "occurrence": data["occurrence"]})
                mirrored += 1
            elif kind == "phase-finished" and attempt_id:
                self._append(attempt_id, "phase.finished",
                             {"phase": data["phase"], "occurrence": data["occurrence"],
                              "outcome": data["outcome"], "reason": data["reason"],
                              "bytes_moved": data["bytes_moved"]})
                self._bytes_moved[attempt_id] = (self._bytes_moved.get(attempt_id, 0)
                                                 + data["bytes_moved"])
                mirrored += 1
            elif kind == "verdict-verified" and attempt_id:
                self._append(attempt_id, "response.validated", {
                    "boundary": harness.TERMINAL_BOUNDARY,
                    "validator_id": data["validator_id"],
                    "validator_sha256": data["validator_sha256"],
                    "response_sha256": data["response_sha256"],
                    "response_bytes": data["response_bytes"],
                    "complete_body": data["complete_body"],
                    "semantically_valid": data["semantically_valid"],
                    "model_id": model_binding["model_id"],
                    "model_version": model_binding["model_version"],
                })
                self._terminal_seen.add(attempt_id)
                mirrored += 1
            elif kind == "attempt-failed" and attempt_id \
                    and attempt_id not in self._terminal_seen:
                self._append(attempt_id, "attempt.failed",
                             {"failure_class": data.get("failure_class", "backend"),
                              "reason": data.get("detail", data.get("error_code",
                                                                    "unknown")),
                              "retryable": False})
                self._terminal_seen.add(attempt_id)
                mirrored += 1
        return mirrored

    def fail_unprocessed_attempt(self, attempt_id: str, reason: str) -> None:
        """Honest bookkeeping for an accepted request the agent never processed:
        catalog_selection fails, every other phase is skipped, terminal failure,
        zero accounting, cleanup not required.  The attempt stays in the
        denominator."""
        self._append(attempt_id, "phase.started",
                     {"phase": "catalog_selection", "occurrence": 0})
        self._append(attempt_id, "phase.finished",
                     {"phase": "catalog_selection", "occurrence": 0,
                      "outcome": "failed", "reason": reason, "bytes_moved": 0})
        for phase in harness.PHASES[1:]:
            self._append(attempt_id, "phase.finished",
                         {"phase": phase, "occurrence": 0, "outcome": "skipped",
                          "reason": f"not reached: {reason}", "bytes_moved": 0})
        self._append(attempt_id, "attempt.failed",
                     {"failure_class": "backend", "reason": reason,
                      "retryable": False})
        self._terminal_seen.add(attempt_id)

    def finalize_attempt(self, attempt_id: str, *, cost_usd: float,
                         gpu_active_seconds: float, gpu_idle_seconds: float,
                         billed_seconds: float, cleanup: dict) -> None:
        self._append(attempt_id, "accounting.recorded", {
            "currency": "USD",
            "cost_usd": cost_usd,
            "gpu_active_seconds": gpu_active_seconds,
            "gpu_idle_seconds": gpu_idle_seconds,
            "billed_seconds": billed_seconds,
            "bytes_moved_total": self._bytes_moved.get(attempt_id, 0),
        })
        self._append(attempt_id, "cleanup.finished", cleanup)
