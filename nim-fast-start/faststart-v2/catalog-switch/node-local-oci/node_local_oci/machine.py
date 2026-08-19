"""The reviewed switch state machine (threat model 9cfbc1b1, section 6).

States and transitions are implemented verbatim from
``catalog-switch/security-reliability/threat_model.json``
(``reliability.state_machines.switch``).  Every transition requires a named
receipt kind, is appended to the durable hash-chained journal before it takes
effect in memory, and terminal states are absorbing.  ``QUARANTINED``
additionally persists a durable quarantine marker that blocks any future run
on this state directory until the node is recycled (INV-03: absence of
evidence is failure, quarantined nodes are never silently reused).
"""

from __future__ import annotations

from pathlib import Path

from .errors import Refusal, require
from .journal import ReceiptJournal, canonical_json, write_durable

SERVING_A = "SERVING_A"
DRAINING_A = "DRAINING_A"
SCRUBBING = "SCRUBBING"
VERIFIED_CLEAN = "VERIFIED_CLEAN"
PREPARING_B = "PREPARING_B"
LAUNCHING_B = "LAUNCHING_B"
VALIDATING_B = "VALIDATING_B"
ACCEPTED_B = "ACCEPTED_B"
QUARANTINED = "QUARANTINED"
FAILED_INCOMPLETE = "FAILED_INCOMPLETE"

STATES = (SERVING_A, DRAINING_A, SCRUBBING, VERIFIED_CLEAN, PREPARING_B,
          LAUNCHING_B, VALIDATING_B, ACCEPTED_B, QUARANTINED, FAILED_INCOMPLETE)
TERMINAL_STATES = (ACCEPTED_B, QUARANTINED, FAILED_INCOMPLETE)

# (from, to) -> receipt kind that must witness the transition
TRANSITIONS: dict[tuple[str, str], str] = {
    (SERVING_A, DRAINING_A): "drain-command",
    (DRAINING_A, SCRUBBING): "drain-complete",
    (SCRUBBING, VERIFIED_CLEAN): "scrub-verified",
    (SCRUBBING, QUARANTINED): "scrub-unverifiable",
    (VERIFIED_CLEAN, PREPARING_B): "artifact-verified",
    (VERIFIED_CLEAN, FAILED_INCOMPLETE): "ladder-exhausted",
    (PREPARING_B, LAUNCHING_B): "launch-started",
    (LAUNCHING_B, SCRUBBING): "launch-failed",
    (LAUNCHING_B, VALIDATING_B): "readiness-observed",
    (VALIDATING_B, SCRUBBING): "semantic-fail",
    (VALIDATING_B, ACCEPTED_B): "semantic-pass-durable",
}
# ANY -> FAILED_INCOMPLETE on lease expiry / node loss (CTL-12)
ANY_FAILURE_RECEIPT = "attempt-failed"

QUARANTINE_MARKER = "quarantined.json"


def assert_not_quarantined(state_dir: Path) -> None:
    marker = Path(state_dir) / QUARANTINE_MARKER
    require(not marker.exists(), "machine.quarantined",
            f"node state dir carries a quarantine marker ({marker}); "
            "a quarantined node is never reused without recycling")


class SwitchMachine:
    def __init__(self, journal: ReceiptJournal, state_dir: Path, *,
                 switch_uid: str, initial_state: str) -> None:
        require(initial_state in (SERVING_A, VERIFIED_CLEAN), "machine.initial",
                f"initial state must be SERVING_A (occupied) or VERIFIED_CLEAN (idle "
                f"with fresh clean receipts), got {initial_state!r}")
        assert_not_quarantined(state_dir)
        self.journal = journal
        self.state_dir = Path(state_dir)
        self.switch_uid = switch_uid
        self.state = initial_state
        self.journal.append({"machine": "switch", "switch_uid": switch_uid,
                             "transition": "enter", "state": initial_state})

    def transition(self, to_state: str, receipt_kind: str, receipt_sha256: str) -> None:
        require(to_state in STATES, "machine.unknown-state", f"{to_state!r}")
        require(self.state not in TERMINAL_STATES, "machine.terminal",
                f"state {self.state} is terminal; no further transitions")
        require(isinstance(receipt_sha256, str) and len(receipt_sha256) == 64,
                "machine.receipt-hash", "transition requires a receipt sha256")
        if to_state == FAILED_INCOMPLETE:
            require(receipt_kind == ANY_FAILURE_RECEIPT
                    or (self.state, to_state) in TRANSITIONS
                    and TRANSITIONS[(self.state, to_state)] == receipt_kind,
                    "machine.failure-receipt",
                    f"FAILED_INCOMPLETE requires receipt kind {ANY_FAILURE_RECEIPT!r}")
        else:
            edge = (self.state, to_state)
            require(edge in TRANSITIONS, "machine.illegal-transition",
                    f"transition {self.state} -> {to_state} is not in the reviewed "
                    "state machine")
            require(TRANSITIONS[edge] == receipt_kind, "machine.wrong-receipt",
                    f"transition {self.state} -> {to_state} requires receipt kind "
                    f"{TRANSITIONS[edge]!r}, got {receipt_kind!r}")
        self.journal.append({"machine": "switch", "switch_uid": self.switch_uid,
                             "transition": f"{self.state}->{to_state}",
                             "state": to_state, "receipt_kind": receipt_kind,
                             "receipt_sha256": receipt_sha256})
        if to_state == QUARANTINED:
            marker = self.state_dir / QUARANTINE_MARKER
            write_durable(marker, (canonical_json({
                "schema": "catalog-switch/nlo-quarantine/v1",
                "switch_uid": self.switch_uid,
                "from_state": self.state,
                "receipt_sha256": receipt_sha256,
            }) + "\n").encode("utf-8"))
        self.state = to_state

    def require_state(self, *allowed: str) -> None:
        require(self.state in allowed, "machine.ordering",
                f"operation requires state in {allowed}, but machine is in {self.state}")
