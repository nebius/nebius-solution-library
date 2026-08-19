"""Concrete containerd (``ctr``) adapter: launch, inspect, stop, remove.

This is the only execution backend in the package.  Every operation is a real
subprocess against the controller-pinned ``ctr`` binary, and every claim the
adapter makes is derived from authoritative runtime observations:

- launch identity comes from ``ctr containers info`` (image ref, runtime name)
  joined with ``ctr tasks ls`` (PID, RUNNING) and the kernel's ``/proc``
  (process exists; in live-h100 class the cgroup path must contain the exact
  container id);
- absence is proven per-id via ``ctr containers/tasks info`` returning a
  NotFound error for the exact id — a successful-but-empty listing is never
  accepted as absence, and unparseable inventory refuses instead of proving
  anything (the malformed-``{}``-inventory failure class);
- stop follows the CTL-13 escalation: SIGTERM, bounded wait, SIGKILL, and the
  PID observed at launch must be gone from ``/proc`` before the task is
  considered stopped.

Container ids created here are always ``nlo-<switch_uid>-<role>`` so cleanup
can be prefix-scoped and can never name foreign state.
"""

from __future__ import annotations

import time
from pathlib import Path

from .errors import Refusal, require
from .execute import PinnedBinaries

RUNTIME_NAME = "io.containerd.runc.v2"


def _find_not_found(stderr: str) -> bool:
    return "not found" in stderr.lower()


class CtrAdapter:
    def __init__(self, binaries: PinnedBinaries, namespace: str, *,
                 launch_class: str, proc_root: Path = Path("/proc")) -> None:
        require(isinstance(namespace, str) and len(namespace) > 0,
                "oci.namespace", "containerd namespace empty")
        self.binaries = binaries
        self.namespace = namespace
        self.launch_class = launch_class
        self.proc_root = Path(proc_root)
        self.executions: list[dict] = []

    def _ctr(self, args: list[str], *, timeout_s: float = 120.0):
        execution = self.binaries.run("ctr", ["-n", self.namespace, *args],
                                      timeout_s=timeout_s)
        self.executions.append(execution.receipt_data())
        return execution

    # -- image -------------------------------------------------------------

    def image_present(self, image_ref: str) -> bool:
        execution = self._ctr(["images", "ls", "-q"])
        require(execution.returncode == 0, "oci.image-ls",
                f"image listing failed: {execution.stderr.strip()!r}")
        refs = [line.strip() for line in execution.stdout.splitlines() if line.strip()]
        return image_ref in refs

    def image_pull(self, image_ref: str, *, timeout_s: float) -> dict:
        execution = self._ctr(["images", "pull", image_ref], timeout_s=timeout_s)
        require(execution.returncode == 0, "oci.image-pull",
                f"pull of {image_ref} failed: {execution.stderr.strip()!r}")
        require(self.image_present(image_ref), "oci.image-pull-absent",
                f"pull reported success but {image_ref} is not in the image store")
        return execution.receipt_data()

    # -- launch ------------------------------------------------------------

    def launch(self, image_ref: str, container_id: str, run_args: list[str],
               command: list[str], *, timeout_s: float = 300.0) -> dict:
        require(container_id.startswith("nlo-"), "oci.container-prefix",
                f"container id {container_id!r} is outside the task-owned nlo- prefix")
        require(self.image_present(image_ref), "oci.launch-image-missing",
                f"image {image_ref} is not present at launch time")
        execution = self._ctr(["run", "-d", *run_args, image_ref, container_id, *command],
                              timeout_s=timeout_s)
        require(execution.returncode == 0, "oci.launch",
                f"ctr run failed for {container_id}: {execution.stderr.strip()!r}")
        return self.inspect_running(container_id, image_ref)

    # -- inspect -----------------------------------------------------------

    def container_info(self, container_id: str) -> dict:
        import json

        execution = self._ctr(["containers", "info", container_id])
        require(execution.returncode == 0, "oci.info",
                f"containers info {container_id} failed: {execution.stderr.strip()!r}")
        try:
            info = json.loads(execution.stdout)
        except json.JSONDecodeError as error:
            raise Refusal("oci.info-parse",
                          f"containers info output unparseable: {error}") from error
        require(isinstance(info, dict), "oci.info-shape", "containers info is not an object")
        return info

    def task_row(self, container_id: str) -> dict:
        execution = self._ctr(["tasks", "ls"])
        require(execution.returncode == 0, "oci.tasks-ls",
                f"tasks ls failed: {execution.stderr.strip()!r}")
        lines = [line for line in execution.stdout.splitlines() if line.strip()]
        require(len(lines) >= 1, "oci.tasks-empty",
                "tasks ls produced no output at all; unparseable inventory is not evidence")
        header = lines[0].split()
        require(header[:3] == ["TASK", "PID", "STATUS"], "oci.tasks-header",
                f"tasks ls header unrecognized: {lines[0]!r}")
        for line in lines[1:]:
            fields = line.split()
            require(len(fields) >= 3, "oci.tasks-parse", f"unparseable task row: {line!r}")
            if fields[0] == container_id:
                require(fields[1].isdigit(), "oci.tasks-pid",
                        f"non-numeric pid for {container_id}: {line!r}")
                return {"container_id": fields[0], "pid": int(fields[1]),
                        "status": fields[2]}
        raise Refusal("oci.task-missing", f"no task row for {container_id}")

    def inspect_running(self, container_id: str, expected_image_ref: str) -> dict:
        info = self.container_info(container_id)
        image = info.get("Image")
        require(image == expected_image_ref, "oci.image-identity",
                f"{container_id}: runtime image {image!r} != admitted {expected_image_ref!r}")
        runtime = (info.get("Runtime") or {}).get("Name")
        require(runtime == RUNTIME_NAME, "oci.runtime-identity",
                f"{container_id}: runtime {runtime!r} != {RUNTIME_NAME!r}")
        task = self.task_row(container_id)
        require(task["status"] == "RUNNING", "oci.task-status",
                f"{container_id}: task status {task['status']!r}")
        pid = task["pid"]
        proc_dir = self.proc_root / str(pid)
        require(proc_dir.is_dir(), "oci.pid-missing",
                f"{container_id}: containerd reports pid {pid} but /proc/{pid} is absent")
        cgroup_path = proc_dir / "cgroup"
        try:
            cgroup = cgroup_path.read_text(encoding="utf-8")
        except OSError as error:
            raise Refusal("oci.cgroup-unreadable", f"/proc/{pid}/cgroup: {error}") from error
        if self.launch_class == "live-h100":
            require(container_id in cgroup, "oci.cgroup-identity",
                    f"{container_id}: /proc/{pid}/cgroup does not contain the container id; "
                    "the observed process is not the launched container")
        return {
            "container_id": container_id,
            "image": image,
            "runtime": runtime,
            "pid": pid,
            "status": task["status"],
            "cgroup": cgroup,
        }

    # -- absence -----------------------------------------------------------

    def assert_container_absent(self, container_id: str) -> dict:
        """Positive per-id absence proof; listings are never used for absence."""
        import json as _json

        execution = self._ctr(["containers", "info", container_id])
        if execution.returncode == 0:
            raise Refusal("oci.still-present",
                          f"container {container_id} still exists")
        require(_find_not_found(execution.stderr), "oci.absence-ambiguous",
                f"containers info {container_id} failed without NotFound; "
                f"this is an error, not absence: {execution.stderr.strip()!r}")
        task_execution = self._ctr(["tasks", "ls"])
        require(task_execution.returncode == 0, "oci.absence-tasks",
                f"tasks ls failed during absence check: {task_execution.stderr.strip()!r}")
        lines = [line for line in task_execution.stdout.splitlines() if line.strip()]
        require(len(lines) >= 1 and lines[0].split()[:3] == ["TASK", "PID", "STATUS"],
                "oci.absence-tasks-header",
                "tasks ls output unrecognizable during absence check")
        for line in lines[1:]:
            require(line.split()[0] != container_id, "oci.absence-task-alive",
                    f"task row for {container_id} still present")
        return {"container_id": container_id, "absent": True,
                "stderr_marker": execution.stderr.strip(),
                "info_returncode": execution.returncode}

    # -- stop / remove -----------------------------------------------------

    def stop(self, container_id: str, launch_pid: int, *,
             term_wait_s: float, kill_wait_s: float) -> dict:
        term = self._ctr(["tasks", "kill", "-s", "SIGTERM", container_id])
        escalated = False
        deadline = time.monotonic() + term_wait_s
        while time.monotonic() < deadline:
            if not (self.proc_root / str(launch_pid)).is_dir():
                break
            time.sleep(0.05)
        if (self.proc_root / str(launch_pid)).is_dir():
            escalated = True
            kill = self._ctr(["tasks", "kill", "-s", "SIGKILL", container_id])
            require(kill.returncode == 0 or _find_not_found(kill.stderr),
                    "oci.sigkill", f"SIGKILL failed: {kill.stderr.strip()!r}")
            deadline = time.monotonic() + kill_wait_s
            while time.monotonic() < deadline:
                if not (self.proc_root / str(launch_pid)).is_dir():
                    break
                time.sleep(0.05)
        require(not (self.proc_root / str(launch_pid)).is_dir(), "oci.stop-pid-alive",
                f"pid {launch_pid} still alive after SIGTERM/SIGKILL escalation")
        delete_task = self._ctr(["tasks", "delete", container_id])
        require(delete_task.returncode == 0 or _find_not_found(delete_task.stderr),
                "oci.task-delete",
                f"task delete failed: {delete_task.stderr.strip()!r}")
        return {"container_id": container_id, "sigterm_rc": term.returncode,
                "escalated_sigkill": escalated, "launch_pid": launch_pid}

    def remove(self, container_id: str) -> dict:
        delete = self._ctr(["containers", "delete", container_id])
        require(delete.returncode == 0 or _find_not_found(delete.stderr),
                "oci.container-delete",
                f"container delete failed: {delete.stderr.strip()!r}")
        return self.assert_container_absent(container_id)
