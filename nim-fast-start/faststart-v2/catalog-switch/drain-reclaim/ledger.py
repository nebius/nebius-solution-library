#!/usr/bin/env python3
"""Bridge from switch state transitions to the reviewed external-T0 ledger."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from performance.request_slo.harness import (
    PHASES,
    T0_BOUNDARY,
    HarnessError,
    append_event,
    canonical_sha256,
    load_ledger,
    validate_ledger,
    validate_trace,
)
from state_machine import RuntimeIdentity, SemanticProbeProof


class SwitchLedgerBridge:
    """Restart-safe writer for one attempt in the shared canonical ledger.

    The bridge never creates request.accepted: only the external client owns T0.
    Construction fails until that durable event is present. Replayed phase
    calls are idempotent only when their exact canonical data match.
    """

    def __init__(
        self,
        *,
        path: Path,
        trace: dict[str, Any],
        ledger_id: str,
        request_id: str,
        attempt_id: str,
        recorder: dict[str, Any],
    ):
        self.path = path
        self.trace = validate_trace(trace)
        self.ledger_id = ledger_id
        self.request_id = request_id
        self.attempt_id = attempt_id
        self.recorder = recorder
        matching = [
            request
            for request in self.trace["requests"]
            if request["request_id"] == request_id
            and request["attempt_id"] == attempt_id
        ]
        if len(matching) != 1:
            raise HarnessError("ledger bridge request/attempt is not unique in trace")
        self.trace_request = matching[0]
        accepted = self._accepted_event()
        if accepted["data"].get("boundary") != T0_BOUNDARY:
            raise HarnessError("ledger bridge does not follow the frozen external T0")
        if accepted["data"].get("trace_request_sha256") != canonical_sha256(
            self.trace_request
        ):
            raise HarnessError("ledger bridge acceptance differs from trace request")

    @property
    def accepted_t0_ns(self) -> int:
        return int(self._accepted_event()["observed_monotonic_ns"])

    def _attempt_events(self) -> list[dict[str, Any]]:
        events = load_ledger(self.path)
        if any(event["ledger_id"] != self.ledger_id for event in events):
            raise HarnessError("ledger bridge found a mixed ledger identity")
        if any(event["trace_id"] != self.trace["trace_id"] for event in events):
            raise HarnessError("ledger bridge found a mixed trace identity")
        if any(event["recorder"] != self.recorder for event in events):
            raise HarnessError("ledger bridge found a mixed external recorder")
        return [
            event
            for event in events
            if event["request_id"] == self.request_id
            and event["attempt_id"] == self.attempt_id
        ]

    def _accepted_event(self) -> dict[str, Any]:
        events = self._attempt_events()
        if not events or events[0]["event_type"] != "request.accepted":
            raise HarnessError("switch work cannot start before external request acceptance")
        accepted = [event for event in events if event["event_type"] == "request.accepted"]
        if len(accepted) != 1:
            raise HarnessError("attempt must contain exactly one request acceptance")
        return accepted[0]

    def _append(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        return append_event(
            self.path,
            ledger_id=self.ledger_id,
            trace_id=self.trace["trace_id"],
            request_id=self.request_id,
            attempt_id=self.attempt_id,
            recorder=self.recorder,
            event_type=event_type,
            data=data,
        )

    def start_phase(self, phase: str, *, occurrence: int = 0) -> dict[str, Any]:
        if phase not in PHASES:
            raise HarnessError("unknown canonical switch phase")
        data = {"phase": phase, "occurrence": occurrence}
        matching = [
            event
            for event in self._attempt_events()
            if event["event_type"] == "phase.started" and event["data"] == data
        ]
        if matching:
            if len(matching) != 1:
                raise HarnessError("phase start is duplicated")
            return matching[0]
        if any(
            event["event_type"] in {"response.validated", "attempt.failed"}
            for event in self._attempt_events()
        ):
            raise HarnessError("cannot start a phase after product terminal")
        return self._append("phase.started", data)

    def finish_phase(
        self,
        phase: str,
        *,
        outcome: str,
        reason: str,
        bytes_moved: int = 0,
        occurrence: int = 0,
    ) -> dict[str, Any]:
        data = {
            "phase": phase,
            "occurrence": occurrence,
            "outcome": outcome,
            "reason": reason,
            "bytes_moved": bytes_moved,
        }
        matching = [
            event
            for event in self._attempt_events()
            if event["event_type"] == "phase.finished"
            and event["data"].get("phase") == phase
            and event["data"].get("occurrence") == occurrence
        ]
        if matching:
            if len(matching) != 1 or matching[0]["data"] != data:
                raise HarnessError("phase finish replay differs from durable event")
            return matching[0]
        return self._append("phase.finished", data)

    def fail_attempt(
        self,
        *,
        failed_phase: str,
        failure_class: str,
        reason: str,
        retryable: bool,
        accounting: dict[str, Any],
        cleanup: dict[str, Any],
    ) -> None:
        """Close every phase and retain the failure in the SLO denominator."""

        if failed_phase not in PHASES:
            raise HarnessError("failure phase is not canonical")
        events = self._attempt_events()
        if any(
            event["event_type"] in {"response.validated", "attempt.failed"}
            for event in events
        ):
            raise HarnessError("attempt already has a product terminal")
        finished = {
            (event["data"]["phase"], event["data"]["occurrence"])
            for event in events
            if event["event_type"] == "phase.finished"
        }
        started = {
            (event["data"]["phase"], event["data"]["occurrence"])
            for event in events
            if event["event_type"] == "phase.started"
        }
        for phase in PHASES:
            key = (phase, 0)
            if key in finished:
                continue
            if phase == failed_phase:
                if key not in started:
                    self.start_phase(phase)
                self.finish_phase(
                    phase,
                    outcome="failed",
                    reason=reason,
                    bytes_moved=0,
                )
            else:
                if key in started:
                    raise HarnessError(
                        f"open phase {phase} must be explicitly closed before failure"
                    )
                self.finish_phase(
                    phase,
                    outcome="skipped",
                    reason=f"skipped after {failed_phase} failure: {reason}",
                    bytes_moved=0,
                )
        self._append(
            "attempt.failed",
            {
                "failure_class": failure_class,
                "reason": reason,
                "retryable": retryable,
            },
        )
        self._append("accounting.recorded", accounting)
        self._append("cleanup.finished", cleanup)

    def record_success(self, response: dict[str, Any]) -> dict[str, Any]:
        return self._append("response.validated", response)

    def record_accounting(self, accounting: dict[str, Any]) -> dict[str, Any]:
        return self._append("accounting.recorded", accounting)

    def record_cleanup(self, cleanup: dict[str, Any]) -> dict[str, Any]:
        return self._append("cleanup.finished", cleanup)

    def terminal_receipt_sha256(self) -> str:
        """Return a digest only after the entire shared ledger validates."""

        events = load_ledger(self.path)
        validate_ledger(events, self.trace)
        attempt = self._attempt_events()
        if len(attempt) < 3 or [event["event_type"] for event in attempt[-3:]] not in (
            ["response.validated", "accounting.recorded", "cleanup.finished"],
            ["attempt.failed", "accounting.recorded", "cleanup.finished"],
        ):
            raise HarnessError("attempt terminal/accounting/cleanup receipt is incomplete")
        return canonical_sha256(attempt[-3:])

    def validate_semantic_probe(
        self, proof: SemanticProbeProof, runtime: RuntimeIdentity
    ) -> str:
        """Bind inference 1 to the frozen product terminal without shifting it.

        Inference 2 is a switch-acceptance qualification stored in the durable
        state-machine proof. It intentionally does not create a post-terminal
        execution phase in the product ledger.
        """

        proof.validate_for(proof.switch_id, runtime)
        terminals = [
            event
            for event in self._attempt_events()
            if event["event_type"] == "response.validated"
        ]
        if len(terminals) != 1:
            raise HarnessError("semantic proof requires exactly one product terminal")
        terminal = terminals[0]
        first = proof.inferences[0]
        if terminal["observed_monotonic_ns"] != first.observed_at_ns:
            raise HarnessError("first semantic inference time differs from product terminal")
        if terminal["data"].get("response_sha256") != first.response_sha256:
            raise HarnessError("first semantic response digest differs from product terminal")
        if (
            terminal["data"].get("model_id"),
            terminal["data"].get("model_version"),
        ) != (proof.model_id, proof.model_version):
            raise HarnessError("semantic proof model differs from product terminal")
        terminal_digest = canonical_sha256(terminal)
        if proof.product_terminal_event_sha256 != terminal_digest:
            raise HarnessError("semantic proof terminal event digest differs")
        return canonical_sha256(
            {"product_terminal": terminal_digest, "semantic_probe": asdict(proof)}
        )


__all__ = ["SwitchLedgerBridge"]
