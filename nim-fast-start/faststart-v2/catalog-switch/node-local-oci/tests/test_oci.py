"""Concrete OCI adapter tests: real subprocesses, real PIDs, hostile output.

The happy paths spawn genuine processes through the pinned stub ``ctr`` so
PID/liveness observations exercise the real /proc logic.  The hostile paths
pin deliberately broken binaries (the controller signs *whatever* binary the
policy names — the adapter must still refuse garbage output rather than
treating it as evidence)."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from . import helpers
from node_local_oci.errors import Refusal
from node_local_oci.execute import PinnedBinaries
from node_local_oci.oci import CtrAdapter


def pinned(bin_dir: Path, names=("ctr",)) -> PinnedBinaries:
    return PinnedBinaries({"binaries": {
        name: {"path": str(bin_dir / name),
               "sha256": helpers.sha256_file(bin_dir / name)}
        for name in names}})


def write_hostile_ctr(base: Path, body: str) -> Path:
    bin_dir = base / "hostile-bin"
    bin_dir.mkdir()
    path = bin_dir / "ctr"
    path.write_text("#!/usr/bin/env python3\nimport sys\n" + body,
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return bin_dir


class BinaryPinning(unittest.TestCase):
    def test_on_disk_drift_refuses_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = helpers.make_stub_bins(Path(tmp))
            binaries = pinned(bin_dir)
            (bin_dir / "ctr").write_text("#!/bin/sh\nexit 0\n")
            with self.assertRaises(Refusal) as caught:
                binaries.run("ctr", ["-n", "ns", "images", "ls", "-q"],
                             timeout_s=10)
            self.assertEqual(caught.exception.code, "execute.binary-drift")

    def test_unpinned_binary_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = helpers.make_stub_bins(Path(tmp))
            with self.assertRaises(Refusal) as caught:
                pinned(bin_dir).run("nerdctl", [], timeout_s=10)
            self.assertEqual(caught.exception.code, "execute.unpinned-binary")


class LifecycleAgainstRealProcesses(unittest.TestCase):
    def _adapter(self, tmp: Path) -> tuple[CtrAdapter, Path]:
        bin_dir = helpers.make_stub_bins(tmp)
        helpers.seed_image(bin_dir, helpers.STUB_IMAGE)
        adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                             launch_class="offline-validation")
        return adapter, bin_dir

    def test_launch_inspect_stop_remove_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, _ = self._adapter(Path(tmp))
            inspect = adapter.launch(
                helpers.STUB_IMAGE, "nlo-t1-b", [],
                [sys.executable, "-c", "import time; time.sleep(120)"])
            self.assertEqual(inspect["image"], helpers.STUB_IMAGE)
            self.assertEqual(inspect["runtime"], "io.containerd.runc.v2")
            self.assertTrue(Path(f"/proc/{inspect['pid']}").is_dir())
            stop = adapter.stop("nlo-t1-b", inspect["pid"],
                                term_wait_s=5.0, kill_wait_s=5.0)
            self.assertFalse(Path(f"/proc/{inspect['pid']}").is_dir())
            self.assertFalse(stop["escalated_sigkill"])
            absence = adapter.remove("nlo-t1-b")
            self.assertIs(absence["absent"], True)

    def test_sigterm_ignorer_is_escalated_to_sigkill(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, _ = self._adapter(Path(tmp))
            stubborn = ("import signal, time\n"
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        "time.sleep(120)\n")
            inspect = adapter.launch(helpers.STUB_IMAGE, "nlo-t2-b", [],
                                     [sys.executable, "-c", stubborn])
            import time as time_module
            time_module.sleep(0.3)  # let the handler install
            stop = adapter.stop("nlo-t2-b", inspect["pid"],
                                term_wait_s=1.0, kill_wait_s=5.0)
            self.assertTrue(stop["escalated_sigkill"])
            self.assertFalse(Path(f"/proc/{inspect['pid']}").is_dir())
            adapter.remove("nlo-t2-b")

    def test_foreign_prefix_launch_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, _ = self._adapter(Path(tmp))
            with self.assertRaises(Refusal) as caught:
                adapter.launch(helpers.STUB_IMAGE, "someone-elses-container", [],
                               ["true"])
            self.assertEqual(caught.exception.code, "oci.container-prefix")

    def test_image_identity_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, bin_dir = self._adapter(Path(tmp))
            other = "registry.local/other@sha256:" + "cd" * 32
            helpers.seed_image(bin_dir, other)
            adapter.launch(other, "nlo-t3-b", [],
                           [sys.executable, "-c", "import time; time.sleep(60)"])
            try:
                with self.assertRaises(Refusal) as caught:
                    adapter.inspect_running("nlo-t3-b", helpers.STUB_IMAGE)
                self.assertEqual(caught.exception.code, "oci.image-identity")
            finally:
                row = adapter.task_row("nlo-t3-b")
                adapter.stop("nlo-t3-b", row["pid"], term_wait_s=5, kill_wait_s=5)
                adapter.remove("nlo-t3-b")

    def test_dead_pid_reported_running_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter, bin_dir = self._adapter(Path(tmp))
            # Fabricate a container whose recorded pid does not exist.
            state = bin_dir / "ctr-state"
            containers = {"nlo-ghost": {"image": helpers.STUB_IMAGE,
                                        "pid": 2 ** 22 - 3}}
            (state / "containers.json").write_text(json.dumps(containers))
            with self.assertRaises(Refusal) as caught:
                adapter.inspect_running("nlo-ghost", helpers.STUB_IMAGE)
            self.assertIn(caught.exception.code,
                          ("oci.task-status", "oci.pid-missing"))


class HostileInventory(unittest.TestCase):
    def test_malformed_task_inventory_is_never_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = write_hostile_ctr(Path(tmp), textwrap.dedent("""\
                if sys.argv[3:5] == ["tasks", "ls"]:
                    print("{}")
                    sys.exit(0)
                sys.exit(0)
                """))
            adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                                 launch_class="offline-validation")
            with self.assertRaises(Refusal) as caught:
                adapter.task_row("nlo-x")
            self.assertEqual(caught.exception.code, "oci.tasks-header")

    def test_empty_task_inventory_is_never_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = write_hostile_ctr(Path(tmp), "sys.exit(0)\n")
            adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                                 launch_class="offline-validation")
            with self.assertRaises(Refusal) as caught:
                adapter.task_row("nlo-x")
            self.assertEqual(caught.exception.code, "oci.tasks-empty")

    def test_error_without_notfound_is_not_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = write_hostile_ctr(Path(tmp), textwrap.dedent("""\
                print("connection error: permission denied", file=sys.stderr)
                sys.exit(1)
                """))
            adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                                 launch_class="offline-validation")
            with self.assertRaises(Refusal) as caught:
                adapter.assert_container_absent("nlo-x")
            self.assertEqual(caught.exception.code, "oci.absence-ambiguous")

    def test_live_class_requires_cgroup_identity(self):
        """In live-h100 class, a process whose cgroup does not contain the
        container id is refused even when containerd reports it RUNNING."""
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = helpers.make_stub_bins(Path(tmp))
            helpers.seed_image(bin_dir, helpers.STUB_IMAGE)
            adapter = CtrAdapter(pinned(bin_dir), "nlo-test",
                                 launch_class="live-h100")
            with self.assertRaises(Refusal) as caught:
                adapter.launch(helpers.STUB_IMAGE, "nlo-t4-b", [],
                               [sys.executable, "-c",
                                "import time; time.sleep(60)"])
            self.assertEqual(caught.exception.code, "oci.cgroup-identity")
            # fail-closed: tear the spawned process down via stub state
            state = json.loads((bin_dir / "ctr-state" /
                                "containers.json").read_text())
            os.kill(state["nlo-t4-b"]["pid"], 9)


if __name__ == "__main__":
    unittest.main()
