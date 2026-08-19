from __future__ import annotations

import hashlib
import base64
import json
import tempfile
import unittest
from pathlib import Path

from support import *  # noqa: F403
from adapters import (  # noqa: E402
    ActionJournal,
    CommandAdmissionPolicy,
    CommandResult,
    ControllerCommandSigner,
    DEFAULT_K8S_AGENT_EXECUTABLE,
    DEFAULT_NODE_AGENT_EXECUTABLE,
    FencedActionExecutor,
    GpuScrubAdapter,
    GpuEvidenceAdapter,
    KubernetesActions,
    KubernetesEvidenceAdapter,
    LocalSignedNodeAgent,
    NodeLocalActions,
    NodeLocalEvidenceAdapter,
    NvidiaSmiNvmlProbe,
)
from state_machine import ControllerFence, ProofRejected  # noqa: E402


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], CommandResult] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv):
        key = tuple(argv)
        self.calls.append(key)
        if key not in self.responses:
            raise AssertionError(f"unexpected command: {key}")
        return self.responses[key]


def result(argv, code=0, stdout="", stderr=""):
    return CommandResult(tuple(argv), code, stdout, stderr)


class NodeEvidenceTests(unittest.TestCase):
    def test_node_agent_attestation_binds_exact_node_and_boot(self) -> None:
        authority = node_authority()  # noqa: F405
        target = runtime(MODEL_A, 1, operation_id="bootstrap-a", suffix="a", authority=authority)  # noqa: F405
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = LocalSignedNodeAgent(
                authority=authority,
                key=NODE_KEY,  # noqa: F405
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                cleanup_assertions=clean_host_assertions,  # noqa: F405
                operation_assertions=clean_operation_assertions,  # noqa: F405
            )
            adapter = NodeLocalEvidenceAdapter(
                authority=authority,
                node_agent=agent,
                node_agent_verification_key=NODE_KEY,  # noqa: F405
            )
            proof = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=target
            )
            proof.validate_for("switch-1", target, trust_store(authority=authority))  # noqa: F405
            wrong_authority = node_authority(boot="other-boot")  # noqa: F405
            wrong_runtime = runtime(
                MODEL_A, 1, operation_id="bootstrap-a", suffix="wrong", authority=wrong_authority  # noqa: F405
            )
            with self.assertRaisesRegex(ProofRejected, "authority differs"):
                adapter.collect_runtime_absence(
                    switch_id="switch-1", runtime=wrong_runtime
                )

    def test_kubernetes_adapter_pins_kubeconfig_context_cluster_ca_namespace_node(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kubeconfig = root / "fresh.kubeconfig"
            kubeconfig.write_bytes(b"fresh-cluster-kubeconfig")
            kubectl = root / "kubectl"
            kubectl.write_bytes(b"pinned-test-kubectl")
            kubectl.chmod(0o700)
            authority = k8s_authority(  # noqa: F405
                kubeconfig_sha256=hashlib.sha256(kubeconfig.read_bytes()).hexdigest(),
                kubectl_executable_sha256=hashlib.sha256(
                    kubectl.read_bytes()
                ).hexdigest(),
            )
            target = runtime(
                MODEL_A,
                1,
                operation_id="bootstrap-k8s",
                suffix="k8s-a",
                authority=authority,
            )  # noqa: F405
            base = (
                str(kubectl),
                "--kubeconfig",
                str(kubeconfig.resolve()),
                "--context",
                str(authority.kube_context),
            )
            config_cmd = (*base, "config", "view", "--minify", "--raw", "--output", "json")
            uid_cmd = (*base, "get", "namespace", "kube-system", "--output", "json")
            node_cmd = (*base, "get", "node", authority.node_id, "--output", "json")
            pods_cmd = (*base, "get", "pods", "--namespace", str(authority.namespace), "--output", "json")
            inspect = ("crictl", "inspect", str(target.container_id))
            config = {"clusters": [{"cluster": {"server": authority.api_server_url, "certificate-authority-data": base64.b64encode(b"test-ca").decode("ascii")}}]}
            runner = FakeRunner(
                {
                    config_cmd: result(config_cmd, stdout=json.dumps(config)),
                    uid_cmd: result(uid_cmd, stdout=json.dumps({"metadata": {"uid": authority.cluster_uid}})),
                    node_cmd: result(
                        node_cmd,
                        stdout=json.dumps(
                            {
                                "metadata": {"uid": authority.node_uid},
                                "status": {"nodeInfo": {"bootID": authority.node_boot_id}},
                            }
                        ),
                    ),
                    pods_cmd: result(pods_cmd, stdout=json.dumps({"items": []})),
                    inspect: result(inspect, code=1, stderr="not found"),
                }
            )
            agent = LocalSignedNodeAgent(
                authority=authority,
                key=NODE_KEY,  # noqa: F405
                proc_root=root / "proc",
                cgroup_root=root / "cgroup",
                container_cli="crictl",
                runner=runner,
                cleanup_assertions=clean_host_assertions,  # noqa: F405
                operation_assertions=clean_operation_assertions,  # noqa: F405
            )
            adapter = KubernetesEvidenceAdapter(
                authority=authority,
                kubeconfig=kubeconfig,
                kubectl_executable=kubectl,
                runner=runner,
                node_agent=agent,
                node_agent_verification_key=NODE_KEY,  # noqa: F405
            )
            proof = adapter.collect_runtime_absence(
                switch_id="switch-1", runtime=target
            )
            self.assertTrue(proof.pod_absent)
            proof.validate_for("switch-1", target, trust_store(authority=authority))  # noqa: F405
            runner.responses[uid_cmd] = result(
                uid_cmd, stdout=json.dumps({"metadata": {"uid": "wrong-cluster-uid"}})
            )
            with self.assertRaisesRegex(ProofRejected, "cluster UID"):
                adapter.collect_runtime_absence(
                    switch_id="switch-1", runtime=target
                )
            runner.responses[uid_cmd] = result(
                uid_cmd,
                stdout=json.dumps({"metadata": {"uid": authority.cluster_uid}}),
            )
            runner.responses[node_cmd] = result(
                node_cmd,
                stdout=json.dumps(
                    {
                        "metadata": {"uid": "wrong-node-uid"},
                        "status": {
                            "nodeInfo": {"bootID": authority.node_boot_id}
                        },
                    }
                ),
            )
            with self.assertRaisesRegex(ProofRejected, "node UID/boot"):
                adapter.collect_runtime_absence(
                    switch_id="switch-1", runtime=target
                )
            kubectl.write_bytes(b"changed-kubectl-after-authority-bind")
            with self.assertRaisesRegex(ProofRejected, "executable bytes differ"):
                adapter.collect_runtime_absence(
                    switch_id="switch-1", runtime=target
                )


class NvmlTests(unittest.TestCase):
    def test_nvml_observes_compute_and_graphics_contexts(self) -> None:
        memory = (
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        )
        pmon = ("nvidia-smi", "pmon", "-c", "1", "-s", "m")
        runner = FakeRunner(
            {
                memory: result(memory, stdout=f"0, {GPU_UUID}, 0, 81920\n"),  # noqa: F405
                pmon: result(
                    pmon,
                    stdout="# gpu pid type sm mem enc dec command\n0 77 C 0 0 0 0 worker\n0 88 G 0 0 0 0 graphics\n",
                ),
            }
        )
        observation = NvidiaSmiNvmlProbe(runner).observe(GPU_UUID)  # noqa: F405
        self.assertEqual(observation.compute_pids, (77,))
        self.assertEqual(observation.graphics_pids, (88,))
        self.assertTrue(observation.graphics_query_supported)

    def test_graphics_query_failure_is_not_hard_coded_empty(self) -> None:
        memory = (
            "nvidia-smi",
            "--query-gpu=index,uuid,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        )
        pmon = ("nvidia-smi", "pmon", "-c", "1", "-s", "m")
        runner = FakeRunner(
            {
                memory: result(memory, stdout=f"0, {GPU_UUID}, 0, 81920\n"),  # noqa: F405
                pmon: result(pmon, code=1, stderr="unsupported"),
            }
        )
        with self.assertRaisesRegex(ProofRejected, "graphics query failed closed"):
            NvidiaSmiNvmlProbe(runner).observe(GPU_UUID)  # noqa: F405


class FencedActionTests(unittest.TestCase):
    @staticmethod
    def _policy() -> CommandAdmissionPolicy:
        return CommandAdmissionPolicy(
            operation_executables={
                "stop-runtime": (DEFAULT_NODE_AGENT_EXECUTABLE,),
                "noop": (DEFAULT_NODE_AGENT_EXECUTABLE,),
                "launch-runtime": (
                    DEFAULT_NODE_AGENT_EXECUTABLE,
                    DEFAULT_K8S_AGENT_EXECUTABLE,
                ),
                "cleanup-launch-operation": (
                    DEFAULT_NODE_AGENT_EXECUTABLE,
                    DEFAULT_K8S_AGENT_EXECUTABLE,
                ),
                "scrub-gpu": (DEFAULT_NODE_AGENT_EXECUTABLE,),
                "revoke-placement-lease": (
                    DEFAULT_NODE_AGENT_EXECUTABLE,
                    DEFAULT_K8S_AGENT_EXECUTABLE,
                ),
            },
            allowed_artifact_sha256s=(MODEL_B.artifact_sha256,),  # noqa: F405
        )

    def _executor(self, root: Path, authority, runner, current):
        return FencedActionExecutor(
            authority=authority,
            controller_keys={"controller-signer": CONTROLLER_KEY},  # noqa: F405
            agent_key=NODE_KEY,  # noqa: F405
            current_fence=lambda: current[0],
            admission_policy=self._policy(),
            journal=ActionJournal(root / "journal.json"),
            runner=runner,
            clock_ns=FakeClock(10_000),  # noqa: F405
        )

    def _envelope(self, *, signer, authority, fence, argv, sequence, operation, subject, idem):
        return signer.create(
            command_id=f"command-{sequence}",
            idempotency_key=idem,
            command_sequence=sequence,
            switch_id="switch-1",
            operation=operation,
            subject_sha256=subject,
            fence=fence,
            authority=authority,
            argv=argv,
            admission_policy_sha256=self._policy().digest,
            issued_at_ns=1,
            expires_at_ns=1_000_000,
        )

    def test_stale_controller_and_captured_replay_cannot_issue_physical_side_effect(self) -> None:
        authority = node_authority()  # noqa: F405
        target = runtime(MODEL_A, 1, operation_id="bootstrap-a", suffix="a", authority=authority)  # noqa: F405
        argv = (
            DEFAULT_NODE_AGENT_EXECUTABLE,
            "stop",
            "--runtime-uid",
            target.runtime_uid,
            "--pid",
            str(target.host_pid),
            "--start-ticks",
            str(target.process_start_ticks),
        )
        runner = FakeRunner({argv: result(argv)})
        current = [ControllerFence("controller-1", 2)]
        signer = ControllerCommandSigner(signer_id="controller-signer", key=CONTROLLER_KEY)  # noqa: F405
        with tempfile.TemporaryDirectory() as directory:
            executor = self._executor(Path(directory), authority, runner, current)
            stale = self._envelope(
                signer=signer,
                authority=authority,
                fence=ControllerFence("controller-1", 1),
                argv=argv,
                sequence=1,
                operation="stop-runtime",
                subject=target.digest,
                idem="stop-stale",
            )
            with self.assertRaisesRegex(ProofRejected, "stale controller"):
                NodeLocalActions(executor).stop_runtime(stale, target)
            self.assertEqual(runner.calls, [])
            fresh = self._envelope(
                signer=signer,
                authority=authority,
                fence=current[0],
                argv=argv,
                sequence=2,
                operation="stop-runtime",
                subject=target.digest,
                idem="stop-fresh",
            )
            first = NodeLocalActions(executor).stop_runtime(fresh, target)
            self.assertEqual(first.outcome, "completed")
            newer_argv = (DEFAULT_NODE_AGENT_EXECUTABLE, "noop")
            runner.responses[newer_argv] = result(newer_argv)
            newer = self._envelope(
                signer=signer,
                authority=authority,
                fence=current[0],
                argv=newer_argv,
                sequence=3,
                operation="noop",
                subject=target.digest,
                idem="newer",
            )
            executor.execute(newer, newer_argv)
            with self.assertRaisesRegex(ProofRejected, "captured command replay"):
                NodeLocalActions(executor).stop_runtime(fresh, target)
            self.assertEqual(runner.calls.count(argv), 1)

    def test_node_local_and_kubernetes_action_adapters_refuse_second_occupancy(self) -> None:
        signer = ControllerCommandSigner(signer_id="controller-signer", key=CONTROLLER_KEY)  # noqa: F405
        fence = ControllerFence("controller-1", 1)
        current = [fence]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node_auth = node_authority()  # noqa: F405
            reservation = LaunchReservation(
                "switch-1", "launch-b", "launch-b-idem", 2, MODEL_B, GPU_UUID, node_auth.digest, "node-local", fence.controller_id, fence.generation, 100  # noqa: F405
            )
            node_argv = (
                DEFAULT_NODE_AGENT_EXECUTABLE,
                "launch",
                "--operation-id",
                reservation.operation_id,
                "--generation",
                str(reservation.runtime_generation),
                "--artifact-sha256",
                reservation.model.artifact_sha256,
            )
            node_runner = FakeRunner({node_argv: result(node_argv, code=1, stderr="exclusive occupancy")})
            node_executor = self._executor(root / "node", node_auth, node_runner, current)
            node_envelope = self._envelope(
                signer=signer,
                authority=node_auth,
                fence=fence,
                argv=node_argv,
                sequence=1,
                operation="launch-runtime",
                subject=reservation.digest,
                idem=reservation.idempotency_key,
            )
            with self.assertRaisesRegex(ProofRejected, "physical action failed"):
                NodeLocalActions(node_executor).launch(node_envelope, reservation)

            kubeconfig = root / "kubeconfig"
            kubeconfig.write_bytes(b"fresh")
            kubectl = root / "kubectl"
            kubectl.write_bytes(b"pinned-test-kubectl")
            kubectl.chmod(0o700)
            k8s_auth = k8s_authority(  # noqa: F405
                kubeconfig_sha256=hashlib.sha256(kubeconfig.read_bytes()).hexdigest(),
                kubectl_executable_sha256=hashlib.sha256(
                    kubectl.read_bytes()
                ).hexdigest(),
            )
            k8s_reservation = LaunchReservation(
                "switch-1", "launch-k8s-b", "launch-k8s-b-idem", 2, MODEL_B, GPU_UUID, k8s_auth.digest, "kubernetes", fence.controller_id, fence.generation, 100  # noqa: F405
            )
            k8s_argv = (
                DEFAULT_K8S_AGENT_EXECUTABLE,
                "launch",
                "--operation-id",
                k8s_reservation.operation_id,
                "--generation",
                str(k8s_reservation.runtime_generation),
                "--artifact-sha256",
                k8s_reservation.model.artifact_sha256,
                "--cluster-uid",
                str(k8s_auth.cluster_uid),
                "--namespace",
                str(k8s_auth.namespace),
            )
            k8s_base = (
                str(kubectl),
                "--kubeconfig",
                str(kubeconfig.resolve()),
                "--context",
                str(k8s_auth.kube_context),
            )
            config_cmd = (
                *k8s_base,
                "config",
                "view",
                "--minify",
                "--raw",
                "--output",
                "json",
            )
            uid_cmd = (
                *k8s_base,
                "get",
                "namespace",
                "kube-system",
                "--output",
                "json",
            )
            node_cmd = (
                *k8s_base,
                "get",
                "node",
                k8s_auth.node_id,
                "--output",
                "json",
            )
            k8s_runner = FakeRunner(
                {
                    config_cmd: result(
                        config_cmd,
                        stdout=json.dumps(
                            {
                                "clusters": [
                                    {
                                        "cluster": {
                                            "server": k8s_auth.api_server_url,
                                            "certificate-authority-data": base64.b64encode(
                                                b"test-ca"
                                            ).decode("ascii"),
                                        }
                                    }
                                ]
                            }
                        ),
                    ),
                    uid_cmd: result(
                        uid_cmd,
                        stdout=json.dumps(
                            {"metadata": {"uid": k8s_auth.cluster_uid}}
                        ),
                    ),
                    node_cmd: result(
                        node_cmd,
                        stdout=json.dumps(
                            {
                                "metadata": {"uid": k8s_auth.node_uid},
                                "status": {
                                    "nodeInfo": {"bootID": k8s_auth.node_boot_id}
                                },
                            }
                        ),
                    ),
                    k8s_argv: result(
                        k8s_argv, code=1, stderr="exclusive occupancy"
                    ),
                }
            )
            k8s_executor = self._executor(root / "k8s", k8s_auth, k8s_runner, current)
            k8s_envelope = self._envelope(
                signer=signer,
                authority=k8s_auth,
                fence=fence,
                argv=k8s_argv,
                sequence=1,
                operation="launch-runtime",
                subject=k8s_reservation.digest,
                idem=k8s_reservation.idempotency_key,
            )
            with self.assertRaisesRegex(ProofRejected, "physical action failed"):
                KubernetesActions(
                    k8s_executor,
                    kubeconfig=kubeconfig,
                    context=str(k8s_auth.kube_context),
                    kubectl_executable=kubectl,
                ).launch(k8s_envelope, k8s_reservation)

            # A validly signed command still cannot reach a physical action
            # when the pinned kubeconfig resolves to another cluster UID.
            k8s_reservation_2 = LaunchReservation(
                "switch-1",
                "launch-k8s-c",
                "launch-k8s-c-idem",
                3,
                MODEL_B,  # noqa: F405
                GPU_UUID,  # noqa: F405
                k8s_auth.digest,
                "kubernetes",
                fence.controller_id,
                fence.generation,
                101,
            )
            k8s_argv_2 = (
                DEFAULT_K8S_AGENT_EXECUTABLE,
                "launch",
                "--operation-id",
                k8s_reservation_2.operation_id,
                "--generation",
                str(k8s_reservation_2.runtime_generation),
                "--artifact-sha256",
                k8s_reservation_2.model.artifact_sha256,
                "--cluster-uid",
                str(k8s_auth.cluster_uid),
                "--namespace",
                str(k8s_auth.namespace),
            )
            k8s_runner.responses[k8s_argv_2] = result(k8s_argv_2)
            k8s_runner.responses[uid_cmd] = result(
                uid_cmd,
                stdout=json.dumps({"metadata": {"uid": "wrong-cluster-uid"}}),
            )
            wrong_cluster = self._envelope(
                signer=signer,
                authority=k8s_auth,
                fence=fence,
                argv=k8s_argv_2,
                sequence=2,
                operation="launch-runtime",
                subject=k8s_reservation_2.digest,
                idem=k8s_reservation_2.idempotency_key,
            )
            before = len(k8s_runner.calls)
            with self.assertRaisesRegex(ProofRejected, "cluster UID"):
                KubernetesActions(
                    k8s_executor,
                    kubeconfig=kubeconfig,
                    context=str(k8s_auth.kube_context),
                    kubectl_executable=kubectl,
                ).launch(wrong_cluster, k8s_reservation_2)
            self.assertNotIn(k8s_argv_2, k8s_runner.calls[before:])

    def test_action_crash_window_is_durable_and_never_replays(self) -> None:
        authority = node_authority()  # noqa: F405
        fence = ControllerFence("controller-1", 1)
        target = runtime(  # noqa: F405
            MODEL_A,
            1,
            operation_id="bootstrap-a",
            suffix="a",
            authority=authority,
        )
        argv = (
            DEFAULT_NODE_AGENT_EXECUTABLE,
            "stop",
            "--runtime-uid",
            target.runtime_uid,
            "--pid",
            str(target.host_pid),
            "--start-ticks",
            str(target.process_start_ticks),
        )

        class CrashAfterDispatch:
            def __init__(self):
                self.calls = []

            def run(self, command):
                self.calls.append(tuple(command))
                raise RuntimeError("simulated response loss")

        signer = ControllerCommandSigner(  # noqa: F405
            signer_id="controller-signer", key=CONTROLLER_KEY
        )
        envelope = self._envelope(
            signer=signer,
            authority=authority,
            fence=fence,
            argv=argv,
            sequence=1,
            operation="stop-runtime",
            subject=target.digest,
            idem="stop-response-loss",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crashing = CrashAfterDispatch()
            executor = self._executor(root, authority, crashing, [fence])
            with self.assertRaisesRegex(RuntimeError, "response loss"):
                NodeLocalActions(executor).stop_runtime(envelope, target)
            retry_runner = FakeRunner({argv: result(argv)})
            retry = self._executor(root, authority, retry_runner, [fence])
            with self.assertRaisesRegex(ProofRejected, "ambiguous"):
                NodeLocalActions(retry).stop_runtime(envelope, target)
            self.assertEqual(retry_runner.calls, [])

    def test_signed_out_of_policy_command_is_refused_before_side_effect(self) -> None:
        authority = node_authority()  # noqa: F405
        fence = ControllerFence("controller-1", 1)
        argv = (DEFAULT_NODE_AGENT_EXECUTABLE, "arbitrary-root-command")
        runner = FakeRunner({argv: result(argv)})
        signer = ControllerCommandSigner(  # noqa: F405
            signer_id="controller-signer", key=CONTROLLER_KEY
        )
        envelope = self._envelope(
            signer=signer,
            authority=authority,
            fence=fence,
            argv=argv,
            sequence=1,
            operation="arbitrary-root-command",
            subject="f" * 64,
            idem="out-of-policy",
        )
        with tempfile.TemporaryDirectory() as directory:
            executor = self._executor(Path(directory), authority, runner, [fence])
            with self.assertRaisesRegex(ProofRejected, "outside admission policy"):
                executor.execute(envelope, argv)
            self.assertEqual(runner.calls, [])
            disguised_argv = (
                DEFAULT_NODE_AGENT_EXECUTABLE,
                "delete-everything",
                "--runtime-uid",
                "runtime-a",
                "--pid",
                "1001",
                "--start-ticks",
                "9001",
            )
            runner.responses[disguised_argv] = result(disguised_argv)
            disguised = self._envelope(
                signer=signer,
                authority=authority,
                fence=fence,
                argv=disguised_argv,
                sequence=2,
                operation="stop-runtime",
                subject="e" * 64,
                idem="signed-but-wrong-subcommand",
            )
            with self.assertRaisesRegex(ProofRejected, "subcommand/argument grammar"):
                executor.execute(disguised, disguised_argv)
            self.assertEqual(runner.calls, [])

    def test_concrete_scrub_and_cleanup_receipt_producers(self) -> None:
        authority = node_authority()  # noqa: F405
        fence = ControllerFence("controller-1", 1)
        reservation = LaunchReservation(
            "switch-1",
            "launch-b",
            "launch-b-idem",
            2,
            MODEL_B,  # noqa: F405
            GPU_UUID,  # noqa: F405
            authority.digest,
            "node-local",
            fence.controller_id,
            fence.generation,
            100,
        )
        cleanup_argv = (
            DEFAULT_NODE_AGENT_EXECUTABLE,
            "cleanup-operation",
            "--operation-id",
            reservation.operation_id,
            "--generation",
            str(reservation.runtime_generation),
        )
        scrub_argv = (
            DEFAULT_NODE_AGENT_EXECUTABLE,
            "scrub-gpu",
            "--gpu-uuid",
            GPU_UUID,  # noqa: F405
            "--subject-sha256",
            reservation.digest,
            "--method",
            "full-vram-zero",
            "--total-memory-bytes",
            str(TOTAL_BYTES),  # noqa: F405
        )
        revoke_argv = (
            DEFAULT_NODE_AGENT_EXECUTABLE,
            "revoke-placement",
            "--placement-lease-id",
            authority.placement_lease_id,
            "--node-uid",
            authority.node_uid,
        )
        runner = FakeRunner(
            {
                cleanup_argv: result(cleanup_argv),
                scrub_argv: result(
                    scrub_argv,
                    stdout=json.dumps(
                        {
                            "schema": "archvteams.nebius.ai/catalog-switch-scrub-command-result/v1",
                            "gpu_uuid": GPU_UUID,  # noqa: F405
                            "method": "full-vram-zero",
                            "bytes_scrubbed": TOTAL_BYTES,  # noqa: F405
                            "total_memory_bytes": TOTAL_BYTES,  # noqa: F405
                            "completed": True,
                        }
                    ),
                ),
                revoke_argv: result(revoke_argv),
            }
        )
        signer = ControllerCommandSigner(
            signer_id="controller-signer", key=CONTROLLER_KEY  # noqa: F405
        )
        with tempfile.TemporaryDirectory() as directory:
            executor = self._executor(Path(directory), authority, runner, [fence])
            cleanup_envelope = self._envelope(
                signer=signer,
                authority=authority,
                fence=fence,
                argv=cleanup_argv,
                sequence=1,
                operation="cleanup-launch-operation",
                subject=reservation.digest,
                idem="cleanup-launch-b",
            )
            cleanup_receipt = NodeLocalActions(executor).cleanup_launch(
                cleanup_envelope, reservation
            )
            self.assertEqual(cleanup_receipt.operation, "cleanup-launch-operation")
            scrub_envelope = self._envelope(
                signer=signer,
                authority=authority,
                fence=fence,
                argv=scrub_argv,
                sequence=2,
                operation="scrub-gpu",
                subject=reservation.digest,
                idem="scrub-launch-b",
            )
            action, scrub = GpuScrubAdapter(executor).scrub(
                scrub_envelope,
                switch_id="switch-1",
                subject_sha256=reservation.digest,
                gpu_uuid=GPU_UUID,  # noqa: F405
                method="full-vram-zero",
                total_memory_bytes=TOTAL_BYTES,  # noqa: F405
            )
            self.assertEqual(action.operation, "scrub-gpu")
            self.assertEqual(scrub.bytes_scrubbed, scrub.total_memory_bytes)
            revoke_envelope = self._envelope(
                signer=signer,
                authority=authority,
                fence=fence,
                argv=revoke_argv,
                sequence=3,
                operation="revoke-placement-lease",
                subject=authority.placement_subject_sha256,
                idem="revoke-placement-node-1",
            )
            revoke = NodeLocalActions(executor).revoke_placement(revoke_envelope)
            self.assertEqual(revoke.operation, "revoke-placement-lease")


if __name__ == "__main__":
    unittest.main()
