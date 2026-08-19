from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from adapters import (  # noqa: E402
    CleanupAttestation,
    CommandResult,
    KubernetesEvidenceAdapter,
    NvidiaSmiNvmlProbe,
    NodeLocalEvidenceAdapter,
)
from state_machine import (  # noqa: E402
    SCRUB_SCHEMA,
    ModelRef,
    ProofRejected,
    RuntimeIdentity,
    ScrubReceipt,
)


GPU_UUID = "GPU-00000000-0000-0000-0000-000000000001"
MODEL = ModelRef("model-a", "1", "a" * 64)


class StepClock:
    def __init__(self, value: int = 10_000):
        self.value = value

    def __call__(self) -> int:
        self.value += 10
        return self.value


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], CommandResult]):
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv):
        key = tuple(argv)
        self.calls.append(key)
        if key not in self.responses:
            raise AssertionError(f"unexpected command: {key}")
        return self.responses[key]


def result(argv, code=0, stdout="", stderr=""):
    return CommandResult(tuple(argv), code, stdout, stderr)


def node_runtime(*, container_id=None) -> RuntimeIdentity:
    return RuntimeIdentity(
        runtime_uid="runtime-a-1",
        backend="node-local",
        runtime_generation=1,
        model=MODEL,
        gpu_uuid=GPU_UUID,
        host_pid=1234,
        process_start_ticks=999,
        cgroup_path="/catalog-switch/runtime-a-1",
        container_id=container_id,
    )


def cleanup(runtime: RuntimeIdentity) -> CleanupAttestation:
    return CleanupAttestation(
        switch_id="switch-1",
        runtime_identity_sha256=runtime.digest,
        observer_id="host-agent-1",
        mounts_absent=True,
        namespaces_absent=True,
        credentials_revoked=True,
        kernel_residue_safe=True,
        raw_evidence_sha256="f" * 64,
    )


class NodeAdapterTests(unittest.TestCase):
    def test_missing_pid_cgroup_and_container_produce_exact_absence(self) -> None:
        runtime = node_runtime(container_id="sha256:container-a")
        inspect = ("crictl", "inspect", "sha256:container-a")
        runner = FakeRunner(
            {inspect: result(inspect, code=1, stderr="container not found")}
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = NodeLocalEvidenceAdapter(
                runner=runner,
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                container_cli="crictl",
                clock_ns=StepClock(),
            )
            proof = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=runtime, cleanup=cleanup(runtime)
            )
        self.assertTrue(proof.process_absent)
        self.assertTrue(proof.cgroup_empty)
        self.assertTrue(proof.container_absent)
        self.assertIsNone(proof.pod_absent)
        proof.validate_for("switch-1", runtime)

    def test_exact_pid_generation_is_not_absent_but_reused_pid_is(self) -> None:
        runtime = node_runtime()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stat = root / "proc" / str(runtime.host_pid) / "stat"
            stat.parent.mkdir(parents=True)
            # fields[19] after the closing parenthesis is Linux stat field 22.
            fields = ["S"] + ["0"] * 18 + [str(runtime.process_start_ticks)] + ["0"] * 4
            stat.write_text(f"{runtime.host_pid} (model worker) " + " ".join(fields))
            cgroup = root / "cgroup" / "catalog-switch" / "runtime-a-1"
            cgroup.mkdir(parents=True)
            (cgroup / "cgroup.procs").write_text("")
            adapter = NodeLocalEvidenceAdapter(
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                clock_ns=StepClock(),
            )
            exact = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=runtime, cleanup=cleanup(runtime)
            )
            self.assertFalse(exact.process_absent)
            with self.assertRaisesRegex(ProofRejected, "process_absent"):
                exact.validate_for("switch-1", runtime)
            fields[19] = str(runtime.process_start_ticks + 1)
            stat.write_text(f"{runtime.host_pid} (model worker) " + " ".join(fields))
            reused = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=runtime, cleanup=cleanup(runtime)
            )
            self.assertTrue(reused.process_absent)

    def test_ambiguous_container_error_fails_closed(self) -> None:
        runtime = node_runtime(container_id="sha256:container-a")
        inspect = ("crictl", "inspect", "sha256:container-a")
        runner = FakeRunner({inspect: result(inspect, code=1, stderr="permission denied")})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = NodeLocalEvidenceAdapter(
                runner=runner,
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                container_cli="crictl",
            )
            with self.assertRaisesRegex(ProofRejected, "ambiguously"):
                adapter.collect_runtime_absence(
                    switch_id="switch-1", runtime=runtime, cleanup=cleanup(runtime)
                )


class NvmlAdapterTests(unittest.TestCase):
    def test_two_empty_nvml_samples_after_full_scrub_form_release_proof(self) -> None:
        memory = (
            "nvidia-smi",
            "--query-gpu=uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        )
        processes = (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid",
            "--format=csv,noheader,nounits",
        )
        clock = StepClock(1_000)
        runner = FakeRunner(
            {
                memory: result(memory, stdout=f"{GPU_UUID}, 0, 81920\n"),
                processes: result(processes, stdout=""),
            }
        )
        nvml = NvidiaSmiNvmlProbe(runner, clock_ns=clock)
        runtime = node_runtime()
        adapter = NodeLocalEvidenceAdapter(
            runner=runner, clock_ns=clock, nvml_probe=nvml
        )
        scrub = ScrubReceipt(
            schema=SCRUB_SCHEMA,
            switch_id="switch-1",
            runtime_identity_sha256=runtime.digest,
            gpu_uuid=GPU_UUID,
            method="full-vram-zero",
            bytes_scrubbed=81920 * 1024 * 1024,
            total_memory_bytes=81920 * 1024 * 1024,
            started_at_ns=900,
            finished_at_ns=1_000,
            succeeded=True,
            evidence_sha256="1" * 64,
        )
        proof = adapter.collect_gpu_release(
            switch_id="switch-1",
            runtime=runtime,
            scrub=scrub,
            observer_id="nvml-probe-1",
            idle_baseline_bytes=0,
            sample_interval_seconds=0,
        )
        self.assertEqual(len(proof.observations), 2)
        proof.validate_for("switch-1", runtime)

    def test_nvml_query_error_is_not_interpreted_as_empty(self) -> None:
        memory = (
            "nvidia-smi",
            "--query-gpu=uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        )
        runner = FakeRunner({memory: result(memory, code=1, stderr="driver error")})
        with self.assertRaisesRegex(ProofRejected, "failed closed"):
            NvidiaSmiNvmlProbe(runner).observe(GPU_UUID)

    def test_memory_above_pinned_idle_baseline_rejects_release(self) -> None:
        runtime = node_runtime()
        scrub = ScrubReceipt(
            schema=SCRUB_SCHEMA,
            switch_id="switch-1",
            runtime_identity_sha256=runtime.digest,
            gpu_uuid=GPU_UUID,
            method="gpu-reset",
            bytes_scrubbed=0,
            total_memory_bytes=81920 * 1024 * 1024,
            started_at_ns=100,
            finished_at_ns=200,
            succeeded=True,
            evidence_sha256="2" * 64,
        )
        from state_machine import GPU_RELEASE_SCHEMA, GpuReleaseProof, NvmlObservation

        proof = GpuReleaseProof(
            schema=GPU_RELEASE_SCHEMA,
            switch_id="switch-1",
            runtime_identity_sha256=runtime.digest,
            gpu_uuid=GPU_UUID,
            observer_id="nvml-probe-1",
            idle_baseline_bytes=64 * 1024 * 1024,
            observations=(
                NvmlObservation(300, GPU_UUID, (), (), 65 * 1024 * 1024, 81920 * 1024 * 1024),
                NvmlObservation(400, GPU_UUID, (), (), 64 * 1024 * 1024, 81920 * 1024 * 1024),
            ),
            scrub=scrub,
            evidence_sha256="3" * 64,
        )
        with self.assertRaisesRegex(ProofRejected, "above the pinned idle baseline"):
            proof.validate_for("switch-1", runtime, expected_idle_baseline_bytes=64 * 1024 * 1024)


class KubernetesAdapterTests(unittest.TestCase):
    def test_pod_uid_not_name_is_the_absence_identity(self) -> None:
        runtime = RuntimeIdentity(
            runtime_uid="runtime-k8s-1",
            backend="kubernetes",
            runtime_generation=1,
            model=MODEL,
            gpu_uuid=GPU_UUID,
            host_pid=1234,
            process_start_ticks=999,
            cgroup_path="/kubepods/pod-old/container-old",
            container_id="containerd://sha256:old",
            pod_uid="pod-uid-old",
            pod_namespace="catalog-switch-test",
            pod_name="model-a",
        )
        kubectl = (
            "kubectl",
            "get",
            "pods",
            "--namespace",
            "catalog-switch-test",
            "--output",
            "json",
        )
        inspect = ("crictl", "inspect", "containerd://sha256:old")
        # A same-name replacement is harmless to old-UID absence; placement's
        # exclusive-occupancy check is a separate launch gate.
        payload = {"items": [{"metadata": {"name": "model-a", "uid": "pod-uid-new"}}]}
        runner = FakeRunner(
            {
                kubectl: result(kubectl, stdout=json.dumps(payload)),
                inspect: result(inspect, code=1, stderr="not found"),
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = NodeLocalEvidenceAdapter(
                runner=runner,
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                container_cli="crictl",
                clock_ns=StepClock(),
            )
            adapter = KubernetesEvidenceAdapter(node, runner=runner)
            proof = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=runtime, cleanup=cleanup(runtime)
            )
        self.assertTrue(proof.pod_absent)
        proof.validate_for("switch-1", runtime)


if __name__ == "__main__":
    unittest.main()
