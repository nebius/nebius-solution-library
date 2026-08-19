#!/usr/bin/env python3
"""Evidence adapters for direct/node-local and Kubernetes runtimes.

Adapters are deliberately split into observation and mutation interfaces.  A
backend cannot claim successful termination merely because its delete command
returned zero; exact identity disappearance and GPU release are collected
independently and passed to the state machine as receipts.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Sequence

from state_machine import (
    ABSENCE_SCHEMA,
    GPU_RELEASE_SCHEMA,
    GpuReleaseProof,
    NvmlObservation,
    ProofRejected,
    RuntimeAbsenceProof,
    RuntimeIdentity,
    ScrubReceipt,
    canonical_sha256,
)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str]) -> CommandResult: ...


class SubprocessRunner:
    """No-shell command runner used by the concrete observation adapters."""

    def run(self, argv: Sequence[str]) -> CommandResult:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
        )
        return CommandResult(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class BackendActions(Protocol):
    """Mutation contract implemented by Kubernetes and node-local prototypes."""

    def stop_admission(self, runtime: RuntimeIdentity, switch_id: str) -> None: ...

    def cancel_request(self, runtime: RuntimeIdentity, lease_id: str) -> None: ...

    def terminate_exact(self, runtime: RuntimeIdentity, switch_id: str) -> None: ...

    def launch_reserved(
        self, model_id: str, runtime_generation: int, switch_id: str
    ) -> RuntimeIdentity: ...


@dataclass(frozen=True)
class CleanupAttestation:
    """Host-agent evidence that cannot be inferred from PID/NVML polling."""

    switch_id: str
    runtime_identity_sha256: str
    observer_id: str
    mounts_absent: bool
    namespaces_absent: bool
    credentials_revoked: bool
    kernel_residue_safe: bool
    raw_evidence_sha256: str

    def validate_for(self, switch_id: str, runtime: RuntimeIdentity) -> None:
        if self.switch_id != switch_id or self.runtime_identity_sha256 != runtime.digest:
            raise ProofRejected("cleanup attestation targets a different switch/runtime")
        if not self.observer_id:
            raise ProofRejected("cleanup attestation lacks an observer")
        if any(
            value is not True
            for value in (
                self.mounts_absent,
                self.namespaces_absent,
                self.credentials_revoked,
                self.kernel_residue_safe,
            )
        ):
            raise ProofRejected("cleanup attestation is not fully successful")
        if len(self.raw_evidence_sha256) != 64:
            raise ProofRejected("cleanup evidence digest is invalid")


class NvidiaSmiNvmlProbe:
    """Collect exact-UUID observations through NVIDIA's NVML-backed CLI."""

    MIB = 1024 * 1024

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        clock_ns=time.monotonic_ns,
    ):
        self.runner = runner or SubprocessRunner()
        self.clock_ns = clock_ns

    @staticmethod
    def _rows(output: str) -> list[list[str]]:
        return [
            [part.strip() for part in line.split(",")]
            for line in output.splitlines()
            if line.strip()
        ]

    def observe(self, gpu_uuid: str) -> NvmlObservation:
        memory = self.runner.run(
            (
                "nvidia-smi",
                "--query-gpu=uuid,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            )
        )
        if memory.returncode != 0:
            raise ProofRejected("NVML GPU query failed closed")
        matches = [row for row in self._rows(memory.stdout) if row and row[0] == gpu_uuid]
        if len(matches) != 1 or len(matches[0]) != 3:
            raise ProofRejected("NVML did not return exactly one requested GPU UUID")
        try:
            used_mib, total_mib = (int(matches[0][1]), int(matches[0][2]))
        except ValueError as exc:
            raise ProofRejected("NVML memory fields are not integers") from exc

        processes = self.runner.run(
            (
                "nvidia-smi",
                "--query-compute-apps=gpu_uuid,pid",
                "--format=csv,noheader,nounits",
            )
        )
        if processes.returncode != 0:
            # An empty process list still returns zero; any error is unknown,
            # never evidence that the GPU is free.
            raise ProofRejected("NVML compute-process query failed closed")
        pids: list[int] = []
        for row in self._rows(processes.stdout):
            if len(row) != 2:
                raise ProofRejected("NVML process row has an unexpected shape")
            if row[0] == gpu_uuid:
                try:
                    pids.append(int(row[1]))
                except ValueError as exc:
                    raise ProofRejected("NVML process PID is not an integer") from exc
        observation = NvmlObservation(
            observed_at_ns=self.clock_ns(),
            gpu_uuid=gpu_uuid,
            compute_pids=tuple(sorted(pids)),
            # H100 inference nodes are headless. A backend with a graphics
            # stack must supply a native NVML probe that populates this field.
            graphics_pids=(),
            memory_used_bytes=used_mib * self.MIB,
            memory_total_bytes=total_mib * self.MIB,
        )
        observation.validate(gpu_uuid)
        return observation


class NodeLocalEvidenceAdapter:
    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        proc_root: Path = Path("/proc"),
        cgroup_root: Path = Path("/sys/fs/cgroup"),
        container_cli: str | None = None,
        clock_ns=time.monotonic_ns,
        nvml_probe: NvidiaSmiNvmlProbe | None = None,
    ):
        self.runner = runner or SubprocessRunner()
        self.proc_root = proc_root
        self.cgroup_root = cgroup_root
        self.container_cli = container_cli
        self.clock_ns = clock_ns
        self.nvml_probe = nvml_probe or NvidiaSmiNvmlProbe(
            self.runner, clock_ns=clock_ns
        )

    def _exact_process_absent(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        stat_path = self.proc_root / str(runtime.host_pid) / "stat"
        try:
            stat = stat_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return True, "pid-not-present"
        except OSError as exc:
            raise ProofRejected(f"cannot inspect exact host PID: {type(exc).__name__}") from exc
        close = stat.rfind(")")
        fields = stat[close + 2 :].split() if close >= 0 else []
        if len(fields) <= 19:
            raise ProofRejected("/proc PID stat is malformed")
        try:
            observed_start_ticks = int(fields[19])
        except ValueError as exc:
            raise ProofRejected("/proc PID start time is malformed") from exc
        if observed_start_ticks == runtime.process_start_ticks:
            return False, "exact-pid-generation-still-present"
        return True, "pid-reused-old-generation-absent"

    def _cgroup_empty(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        relative = Path(runtime.cgroup_path.lstrip("/"))
        if ".." in relative.parts:
            raise ProofRejected("runtime cgroup path attempts traversal")
        procs = self.cgroup_root / relative / "cgroup.procs"
        try:
            values = [line.strip() for line in procs.read_text().splitlines() if line.strip()]
        except FileNotFoundError:
            return True, "exact-cgroup-absent"
        except OSError as exc:
            raise ProofRejected(f"cannot inspect exact cgroup: {type(exc).__name__}") from exc
        if any(not value.isdigit() for value in values):
            raise ProofRejected("cgroup.procs contains malformed data")
        return not values, "cgroup-empty" if not values else f"cgroup-pids={','.join(values)}"

    def _container_absent(self, runtime: RuntimeIdentity) -> tuple[bool, str]:
        if runtime.container_id is None:
            return True, "no-container-identity-for-node-process"
        if self.container_cli is None:
            raise ProofRejected("container identity exists but no runtime CLI was configured")
        result = self.runner.run((self.container_cli, "inspect", runtime.container_id))
        if result.returncode == 0:
            return False, "exact-container-still-present"
        text = f"{result.stdout}\n{result.stderr}".lower()
        if not any(marker in text for marker in ("not found", "no such", "does not exist")):
            raise ProofRejected("container inspect failed ambiguously")
        return True, "exact-container-not-found"

    def collect_runtime_absence(
        self,
        *,
        switch_id: str,
        runtime: RuntimeIdentity,
        cleanup: CleanupAttestation,
    ) -> RuntimeAbsenceProof:
        runtime.validate()
        if runtime.backend != "node-local":
            raise ProofRejected("node-local adapter received a Kubernetes runtime")
        cleanup.validate_for(switch_id, runtime)
        process_absent, process_detail = self._exact_process_absent(runtime)
        cgroup_empty, cgroup_detail = self._cgroup_empty(runtime)
        container_absent, container_detail = self._container_absent(runtime)
        raw = {
            "runtime": asdict(runtime),
            "process": process_detail,
            "cgroup": cgroup_detail,
            "container": container_detail,
            "cleanup_evidence": cleanup.raw_evidence_sha256,
        }
        return RuntimeAbsenceProof(
            schema=ABSENCE_SCHEMA,
            switch_id=switch_id,
            runtime_identity_sha256=runtime.digest,
            runtime_uid=runtime.runtime_uid,
            runtime_generation=runtime.runtime_generation,
            observer_id=cleanup.observer_id,
            observed_at_ns=self.clock_ns(),
            process_absent=process_absent,
            cgroup_empty=cgroup_empty,
            container_absent=container_absent,
            pod_absent=None,
            mounts_absent=cleanup.mounts_absent,
            namespaces_absent=cleanup.namespaces_absent,
            credentials_revoked=cleanup.credentials_revoked,
            kernel_residue_safe=cleanup.kernel_residue_safe,
            evidence_sha256=canonical_sha256(raw),
        )

    def collect_gpu_release(
        self,
        *,
        switch_id: str,
        runtime: RuntimeIdentity,
        scrub: ScrubReceipt,
        observer_id: str,
        idle_baseline_bytes: int,
        sample_count: int = 2,
        sample_interval_seconds: float = 0.05,
        sleeper=time.sleep,
    ) -> GpuReleaseProof:
        if sample_count < 2:
            raise ValueError("at least two NVML samples are required")
        scrub.validate_for(switch_id, runtime)
        observations: list[NvmlObservation] = []
        for index in range(sample_count):
            if index and sample_interval_seconds:
                sleeper(sample_interval_seconds)
            observations.append(self.nvml_probe.observe(runtime.gpu_uuid))
        raw = {
            "runtime_identity_sha256": runtime.digest,
            "scrub": asdict(scrub),
            "idle_baseline_bytes": idle_baseline_bytes,
            "observations": [asdict(item) for item in observations],
        }
        return GpuReleaseProof(
            schema=GPU_RELEASE_SCHEMA,
            switch_id=switch_id,
            runtime_identity_sha256=runtime.digest,
            gpu_uuid=runtime.gpu_uuid,
            observer_id=observer_id,
            idle_baseline_bytes=idle_baseline_bytes,
            observations=tuple(observations),
            scrub=scrub,
            evidence_sha256=canonical_sha256(raw),
        )


class KubernetesEvidenceAdapter:
    """Combine exact Pod UID absence with node-local process/GPU evidence."""

    def __init__(
        self,
        node_adapter: NodeLocalEvidenceAdapter,
        *,
        runner: CommandRunner | None = None,
        kubectl: str = "kubectl",
    ):
        self.node_adapter = node_adapter
        self.runner = runner or SubprocessRunner()
        self.kubectl = kubectl

    def collect_runtime_absence(
        self,
        *,
        switch_id: str,
        runtime: RuntimeIdentity,
        cleanup: CleanupAttestation,
    ) -> RuntimeAbsenceProof:
        runtime.validate()
        if runtime.backend != "kubernetes":
            raise ProofRejected("Kubernetes adapter received a node-local runtime")
        cleanup.validate_for(switch_id, runtime)
        result = self.runner.run(
            (
                self.kubectl,
                "get",
                "pods",
                "--namespace",
                str(runtime.pod_namespace),
                "--output",
                "json",
            )
        )
        if result.returncode != 0:
            raise ProofRejected("Kubernetes Pod UID inventory failed closed")
        try:
            payload = json.loads(result.stdout)
            items = payload["items"]
            pod_uids = [item["metadata"]["uid"] for item in items]
        except (ValueError, TypeError, KeyError) as exc:
            raise ProofRejected("Kubernetes Pod inventory is malformed") from exc
        pod_absent = runtime.pod_uid not in pod_uids

        process_absent, process_detail = self.node_adapter._exact_process_absent(runtime)
        cgroup_empty, cgroup_detail = self.node_adapter._cgroup_empty(runtime)
        container_absent, container_detail = self.node_adapter._container_absent(runtime)
        observed_at_ns = self.node_adapter.clock_ns()
        raw = {
            "pod_uids_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "pod_uid": runtime.pod_uid,
            "process": process_detail,
            "cgroup": cgroup_detail,
            "container": container_detail,
            "cleanup_evidence": cleanup.raw_evidence_sha256,
        }
        return RuntimeAbsenceProof(
            schema=ABSENCE_SCHEMA,
            switch_id=switch_id,
            runtime_identity_sha256=runtime.digest,
            runtime_uid=runtime.runtime_uid,
            runtime_generation=runtime.runtime_generation,
            observer_id=cleanup.observer_id,
            observed_at_ns=observed_at_ns,
            process_absent=process_absent,
            cgroup_empty=cgroup_empty,
            container_absent=container_absent,
            pod_absent=pod_absent,
            mounts_absent=cleanup.mounts_absent,
            namespaces_absent=cleanup.namespaces_absent,
            credentials_revoked=cleanup.credentials_revoked,
            kernel_residue_safe=cleanup.kernel_residue_safe,
            evidence_sha256=canonical_sha256(raw),
        )

    def collect_gpu_release(self, **kwargs) -> GpuReleaseProof:
        return self.node_adapter.collect_gpu_release(**kwargs)


__all__ = [
    "BackendActions",
    "CleanupAttestation",
    "CommandResult",
    "CommandRunner",
    "KubernetesEvidenceAdapter",
    "NvidiaSmiNvmlProbe",
    "NodeLocalEvidenceAdapter",
    "SubprocessRunner",
]
