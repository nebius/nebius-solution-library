"""Reviewed switch state machine ordering + fail-closed cleanup adversaries."""

from __future__ import annotations

import json
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from . import helpers
from node_local_oci.cleanup import CleanupFailed, CleanupManager
from node_local_oci.errors import Refusal
from node_local_oci.execute import PinnedBinaries
from node_local_oci.journal import IntentJournal, ReceiptJournal
from node_local_oci.machine import (ACCEPTED_B, DRAINING_A, FAILED_INCOMPLETE,
                                    LAUNCHING_B, PREPARING_B, QUARANTINED,
                                    SCRUBBING, SERVING_A, SwitchMachine,
                                    VALIDATING_B, VERIFIED_CLEAN,
                                    assert_not_quarantined)
from node_local_oci.oci import CtrAdapter

SHA = "5" * 64


class MachineOrdering(unittest.TestCase):
    def _machine(self, tmp: Path, initial=SERVING_A) -> SwitchMachine:
        journal = ReceiptJournal(tmp / "journal.jsonl")
        return SwitchMachine(journal, tmp, switch_uid="nlo-sw-1",
                             initial_state=initial)

    def test_full_reviewed_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            for state, receipt in [(DRAINING_A, "drain-command"),
                                   (SCRUBBING, "drain-complete"),
                                   (VERIFIED_CLEAN, "scrub-verified"),
                                   (PREPARING_B, "artifact-verified"),
                                   (LAUNCHING_B, "launch-started"),
                                   (VALIDATING_B, "readiness-observed"),
                                   (ACCEPTED_B, "semantic-pass-durable")]:
                machine.transition(state, receipt, SHA)
            self.assertEqual(machine.state, ACCEPTED_B)
            with self.assertRaises(Refusal) as caught:
                machine.transition(SCRUBBING, "semantic-fail", SHA)
            self.assertEqual(caught.exception.code, "machine.terminal")

    def test_launch_cannot_skip_scrub(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            machine.transition(DRAINING_A, "drain-command", SHA)
            with self.assertRaises(Refusal) as caught:
                machine.transition(LAUNCHING_B, "launch-started", SHA)
            self.assertEqual(caught.exception.code, "machine.illegal-transition")

    def test_wrong_receipt_kind_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            with self.assertRaises(Refusal) as caught:
                machine.transition(DRAINING_A, "scrub-verified", SHA)
            self.assertEqual(caught.exception.code, "machine.wrong-receipt")

    def test_failed_launch_returns_to_scrubbing(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            machine.transition(DRAINING_A, "drain-command", SHA)
            machine.transition(SCRUBBING, "drain-complete", SHA)
            machine.transition(VERIFIED_CLEAN, "scrub-verified", SHA)
            machine.transition(PREPARING_B, "artifact-verified", SHA)
            machine.transition(LAUNCHING_B, "launch-started", SHA)
            machine.transition(SCRUBBING, "launch-failed", SHA)
            self.assertEqual(machine.state, SCRUBBING)

    def test_quarantine_persists_and_blocks_future_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            machine.transition(DRAINING_A, "drain-command", SHA)
            machine.transition(SCRUBBING, "drain-complete", SHA)
            machine.transition(QUARANTINED, "scrub-unverifiable", SHA)
            with self.assertRaises(Refusal) as caught:
                assert_not_quarantined(Path(tmp))
            self.assertEqual(caught.exception.code, "machine.quarantined")
            journal2 = ReceiptJournal(Path(tmp) / "journal2.jsonl")
            with self.assertRaises(Refusal):
                SwitchMachine(journal2, Path(tmp), switch_uid="nlo-sw-2",
                              initial_state=SERVING_A)

    def test_any_state_can_fail_incomplete_with_failure_receipt_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            machine = self._machine(Path(tmp))
            machine.transition(DRAINING_A, "drain-command", SHA)
            with self.assertRaises(Refusal):
                machine.transition(FAILED_INCOMPLETE, "drain-complete", SHA)
            machine.transition(FAILED_INCOMPLETE, "attempt-failed", SHA)
            self.assertEqual(machine.state, FAILED_INCOMPLETE)


def pinned(bin_dir: Path) -> PinnedBinaries:
    return PinnedBinaries({"binaries": {
        "ctr": {"path": str(bin_dir / "ctr"),
                "sha256": helpers.sha256_file(bin_dir / "ctr")}}})


class CleanupRules(unittest.TestCase):
    def _manager(self, tmp: Path) -> tuple[CleanupManager, CtrAdapter, Path]:
        bin_dir = helpers.make_stub_bins(tmp)
        helpers.seed_image(bin_dir, helpers.STUB_IMAGE)
        adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                             launch_class="offline-validation")
        intents = IntentJournal(tmp / "intents.jsonl")
        return CleanupManager(intents, adapter, "nlo"), adapter, bin_dir

    def test_foreign_and_empty_ids_are_refused_not_proven_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager, _, _ = self._manager(Path(tmp))
            with self.assertRaises(Refusal) as caught:
                manager.register("container", "prod-vm-of-another-tenant", {})
            self.assertEqual(caught.exception.code, "cleanup.prefix")
            # Nothing registered: cleanup has nothing to act on and cannot
            # fabricate absence for ids it never owned.
            report = manager.cleanup_all()
            self.assertEqual(report["outcomes"], [])
            self.assertTrue(report["complete"])

    def test_created_container_is_stopped_removed_and_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager, adapter, _ = self._manager(Path(tmp))
            manager.register("container", "nlo-c1-b", {"term_wait_s": 5.0,
                                                       "kill_wait_s": 5.0})
            adapter.launch(helpers.STUB_IMAGE, "nlo-c1-b", [],
                           [sys.executable, "-c", "import time; time.sleep(60)"])
            report = manager.cleanup_all()
            self.assertTrue(report["complete"])
            self.assertEqual(report["outcomes"][0]["outcome"], "deleted-verified")
            self.assertIs(report["outcomes"][0]["proof"]["absent"], True)

    def test_crash_window_recovery_replays_open_intents(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager, adapter, _ = self._manager(Path(tmp))
            manager.register("container", "nlo-c2-b", {})
            adapter.launch(helpers.STUB_IMAGE, "nlo-c2-b", [],
                           [sys.executable, "-c", "import time; time.sleep(60)"])
            # Simulate a crash: a fresh manager over the same durable intents.
            fresh_intents = IntentJournal(Path(tmp) / "intents.jsonl")
            self.assertEqual([e["resource_id"] for e in
                              fresh_intents.open_resources()], ["nlo-c2-b"])
            fresh = CleanupManager(fresh_intents, adapter, "nlo")
            report = fresh.cleanup_all()
            self.assertTrue(report["complete"])
            self.assertEqual([], fresh_intents.open_resources())

    def test_cleanup_failure_is_persisted_and_raised_never_swallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bin_dir = base / "broken-bin"
            bin_dir.mkdir()
            ctr = bin_dir / "ctr"
            ctr.write_text(textwrap.dedent("""\
                #!/usr/bin/env python3
                import sys
                if sys.argv[3:5] == ["tasks", "ls"]:
                    print("TASK    PID    STATUS")
                    sys.exit(0)
                print("ctr: I/O failure, cannot delete", file=sys.stderr)
                sys.exit(1)
                """), encoding="utf-8")
            ctr.chmod(ctr.stat().st_mode | stat.S_IXUSR)
            adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                                 launch_class="offline-validation")
            intents = IntentJournal(base / "intents.jsonl")
            manager = CleanupManager(intents, adapter, "nlo")
            manager.register("container", "nlo-c3-b", {})
            with self.assertRaises(CleanupFailed) as caught:
                manager.cleanup_all()
            self.assertEqual(len(caught.exception.report["failures"]), 1)
            # Failure persisted durably: the resource is still open for recovery.
            replay = IntentJournal(base / "intents.jsonl")
            self.assertEqual([e["resource_id"] for e in replay.open_resources()],
                             ["nlo-c3-b"])

    def test_unknown_resource_kind_fails_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager, _, _ = self._manager(Path(tmp))
            manager.register("mystery-kind", "nlo-c4", {})
            with self.assertRaises(CleanupFailed):
                manager.cleanup_all()

    def test_journaled_foreign_prefix_is_refused_at_cleanup_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager, _, _ = self._manager(Path(tmp))
            # Bypass register() to simulate a tampered/foreign journal entry.
            manager.intents.record_intent("container", "foreign-thing", {})
            with self.assertRaises(Refusal) as caught:
                manager.cleanup_all()
            self.assertEqual(caught.exception.code, "cleanup.journal-prefix")


if __name__ == "__main__":
    unittest.main()
