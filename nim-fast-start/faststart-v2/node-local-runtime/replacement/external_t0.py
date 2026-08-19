"""Durable external-client T0 ingestion for the replacement runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from performance.request_slo import harness

from node_runtime.audit import AuditChain


class ExternalT0Recorder:
    """Writes request.accepted before the runtime can perform request work."""

    def __init__(self, ledger: Path, audit: Path, trace: dict[str, Any]) -> None:
        self.ledger = ledger
        self.audit = AuditChain(audit)
        self.trace = harness.validate_trace(trace)
        self.ledger_id = f"{self.trace['trace_id']}-replacement-ledger"
        self.recorder = harness.default_recorder(
            "catalog-switch-replacement-external-recorder", max_error_ms=50.0
        )

    def accept(self, index: int, *, environment: dict[str, Any], ownership: dict[str, Any]) -> dict[str, Any]:
        request = self.trace["requests"][index]
        event = harness.append_event(
            self.ledger,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=request["request_id"],
            attempt_id=request["attempt_id"],
            recorder=self.recorder,
            event_type="request.accepted",
            data={
                "boundary": harness.T0_BOUNDARY,
                "trace_request_sha256": harness.canonical_sha256(request),
                "scenario": request["scenario"],
                "target": request["target"],
                "input": request["input"],
                "precondition": request["precondition"],
                "environment": environment,
                "ownership": ownership,
            },
        )
        self.audit.append(event)
        return event

    def accepted_attempts(self) -> set[str]:
        if not self.ledger.exists():
            return set()
        return {
            event["attempt_id"]
            for event in harness.load_ledger(self.ledger)
            if event["event_type"] == "request.accepted"
        }
