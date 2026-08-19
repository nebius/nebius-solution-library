from __future__ import annotations

import json
import random
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from state_machine import (  # noqa: E402
    ABSENCE_SCHEMA,
    GPU_RELEASE_SCHEMA,
    SCRUB_SCHEMA,
    SEMANTIC_PROBE_SCHEMA,
    ControllerFence,
    DrainReclaimStateMachine,
    FenceRejected,
    GpuReleaseProof,
    InMemoryStateStore,
    InvalidTransition,
    JsonFileStateStore,
    LeaseStatus,
    MachineSnapshot,
    ModelRef,
    NvmlObservation,
    ProofRejected,
    RuntimeAbsenceProof,
    RuntimeIdentity,
    ScrubReceipt,
    SemanticInferenceReceipt,
    SemanticProbeProof,
    SwitchState,
)


class FakeClock:
    def __init__(self, value: int = 1_000_000):
        self.value = value
        self._lock = threading.Lock()

    def __call__(self) -> int:
        with self._lock:
            self.value += 100
            return self.value

    def advance(self, amount: int) -> None:
        with self._lock:
            self.value += amount


MODEL_A = ModelRef("model-a", "1", "a" * 64)
MODEL_B = ModelRef("model-b", "2", "b" * 64)
GPU_UUID = "GPU-00000000-0000-0000-0000-000000000001"


def runtime(model: ModelRef, generation: int, *, suffix: str = "a") -> RuntimeIdentity:
    return RuntimeIdentity(
        runtime_uid=f"runtime-{suffix}-{generation}",
        backend="node-local",
        runtime_generation=generation,
        model=model,
        gpu_uuid=GPU_UUID,
        host_pid=1000 + generation,
        process_start_ticks=20_000 + generation,
        cgroup_path=f"/catalog-switch/runtime-{suffix}-{generation}",
    )


def reclaim_proofs(
    switch_id: str,
    exact_runtime: RuntimeIdentity,
    after_ns: int,
) -> tuple[RuntimeAbsenceProof, GpuReleaseProof]:
    absence = RuntimeAbsenceProof(
        schema=ABSENCE_SCHEMA,
        switch_id=switch_id,
        runtime_identity_sha256=exact_runtime.digest,
        runtime_uid=exact_runtime.runtime_uid,
        runtime_generation=exact_runtime.runtime_generation,
        observer_id="host-agent-1",
        observed_at_ns=after_ns + 20,
        process_absent=True,
        cgroup_empty=True,
        container_absent=True,
        pod_absent=None,
        mounts_absent=True,
        namespaces_absent=True,
        credentials_revoked=True,
        kernel_residue_safe=True,
        evidence_sha256="c" * 64,
    )
    scrub = ScrubReceipt(
        schema=SCRUB_SCHEMA,
        switch_id=switch_id,
        runtime_identity_sha256=exact_runtime.digest,
        gpu_uuid=GPU_UUID,
        method="full-vram-zero",
        bytes_scrubbed=80_000_000_000,
        total_memory_bytes=80_000_000_000,
        started_at_ns=after_ns + 10,
        finished_at_ns=after_ns + 30,
        succeeded=True,
        evidence_sha256="d" * 64,
    )
    observations = (
        NvmlObservation(after_ns + 40, GPU_UUID, (), (), 0, 80_000_000_000),
        NvmlObservation(after_ns + 50, GPU_UUID, (), (), 0, 80_000_000_000),
    )
    gpu = GpuReleaseProof(
        schema=GPU_RELEASE_SCHEMA,
        switch_id=switch_id,
        runtime_identity_sha256=exact_runtime.digest,
        gpu_uuid=GPU_UUID,
        observer_id="nvml-probe-1",
        idle_baseline_bytes=0,
        observations=observations,
        scrub=scrub,
        evidence_sha256="e" * 64,
    )
    return absence, gpu


def semantic_probe(
    switch_id: str, exact_runtime: RuntimeIdentity, after_ns: int
) -> SemanticProbeProof:
    return SemanticProbeProof(
        schema=SEMANTIC_PROBE_SCHEMA,
        switch_id=switch_id,
        runtime_identity_sha256=exact_runtime.digest,
        runtime_generation=exact_runtime.runtime_generation,
        model_id=exact_runtime.model.model_id,
        model_version=exact_runtime.model.model_version,
        validator_sha256="6" * 64,
        product_terminal_event_sha256="c" * 64,
        inferences=(
            SemanticInferenceReceipt(
                sequence=1,
                request_sha256="7" * 64,
                response_sha256="8" * 64,
                complete_body=True,
                semantically_valid=True,
                observed_at_ns=after_ns + 10,
            ),
            SemanticInferenceReceipt(
                sequence=2,
                request_sha256="a" * 64,
                response_sha256="b" * 64,
                complete_body=True,
                semantically_valid=True,
                observed_at_ns=after_ns + 20,
            ),
        ),
    )


class MachineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.store = InMemoryStateStore(MachineSnapshot.initial("node-1", GPU_UUID))
        self.machine = DrainReclaimStateMachine(self.store, clock_ns=self.clock)
        self.fence = self.machine.claim_controller("controller-1")
        self.runtime_a = runtime(MODEL_A, 1)
        self.machine.install_serving_a(self.fence, self.runtime_a)

    def begin_switch(self, *, timeout: int = 5_000) -> None:
        self.machine.begin_switch(
            self.fence,
            switch_id="switch-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            target=MODEL_B,
            accepted_t0_ns=self.clock.value,
            drain_timeout_ns=timeout,
        )

    def reach_gpu_free(self) -> str:
        ready, timed_out = self.machine.advance_drain(
            self.fence, switch_id="switch-1"
        )
        self.assertTrue(ready)
        self.assertEqual(timed_out, ())
        reclaim_started = self.machine.snapshot().transitions[-1].at_ns
        absence, gpu = reclaim_proofs("switch-1", self.runtime_a, reclaim_started)
        return self.machine.record_reclaim(
            self.fence,
            switch_id="switch-1",
            absence=absence,
            gpu_release=gpu,
        )


class HappyPathTests(MachineFixture):
    def test_happy_path_requires_gpu_free_before_b_and_fences_models(self) -> None:
        self.begin_switch()
        with self.assertRaises(InvalidTransition):
            self.machine.begin_start_b(self.fence, switch_id="switch-1")
        self.reach_gpu_free()
        generation = self.machine.begin_start_b(self.fence, switch_id="switch-1")
        self.assertEqual(generation, 2)
        runtime_b = runtime(MODEL_B, generation, suffix="b")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=runtime_b
        )
        self.machine.accept_b(
            self.fence,
            switch_id="switch-1",
            semantic_probe=semantic_probe(
                "switch-1", runtime_b, self.machine.snapshot().transitions[-1].at_ns
            ),
        )
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.state, SwitchState.SERVING_B)
        self.assertTrue(snapshot.admission_open)
        lease = self.machine.admit_request(
            self.fence,
            lease_id="b-lease",
            request_id="b-request",
            attempt_id="b-attempt",
            model=MODEL_B,
            deadline_ns=self.clock.value + 5_000,
        )
        with self.assertRaises(FenceRejected):
            self.machine.complete_response(
                self.fence,
                lease_id=lease.lease_id,
                runtime_generation=generation,
                model=MODEL_A,
            )
        completed = self.machine.complete_response(
            self.fence,
            lease_id=lease.lease_id,
            runtime_generation=generation,
            model=MODEL_B,
        )
        self.assertEqual(completed.status, LeaseStatus.COMPLETED)
        self.machine.seal_switch(
            self.fence,
            switch_id="switch-1",
            terminal_ledger_sha256="9" * 64,
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.SERVING_A)

    def test_wrong_generation_semantic_probe_cannot_open_b_admission(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        generation = self.machine.begin_start_b(self.fence, switch_id="switch-1")
        runtime_b = runtime(MODEL_B, generation, suffix="b")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=runtime_b
        )
        proof = semantic_probe(
            "switch-1", runtime_b, self.machine.snapshot().transitions[-1].at_ns
        )
        with self.assertRaisesRegex(ProofRejected, "runtime generation differs"):
            self.machine.accept_b(
                self.fence,
                switch_id="switch-1",
                semantic_probe=replace(proof, runtime_generation=generation + 1),
            )
        self.assertFalse(self.machine.snapshot().admission_open)

    def test_b_requires_two_distinct_ordered_semantic_inferences(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        generation = self.machine.begin_start_b(self.fence, switch_id="switch-1")
        runtime_b = runtime(MODEL_B, generation, suffix="b")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=runtime_b
        )
        proof = semantic_probe(
            "switch-1", runtime_b, self.machine.snapshot().transitions[-1].at_ns
        )
        with self.assertRaisesRegex(ProofRejected, "exactly two"):
            self.machine.accept_b(
                self.fence,
                switch_id="switch-1",
                semantic_probe=replace(proof, inferences=proof.inferences[:1]),
            )
        duplicate = replace(
            proof.inferences[1], request_sha256=proof.inferences[0].request_sha256
        )
        with self.assertRaisesRegex(ProofRejected, "must be distinct"):
            self.machine.accept_b(
                self.fence,
                switch_id="switch-1",
                semantic_probe=replace(
                    proof, inferences=(proof.inferences[0], duplicate)
                ),
            )
        self.assertFalse(self.machine.snapshot().admission_open)

    def test_active_a_completes_during_drain_but_late_a_is_rejected(self) -> None:
        first = self.machine.admit_request(
            self.fence,
            lease_id="a-first",
            request_id="a-request-first",
            attempt_id="a-attempt-first",
            model=MODEL_A,
            deadline_ns=self.clock.value + 20_000,
        )
        second = self.machine.admit_request(
            self.fence,
            lease_id="a-hung",
            request_id="a-request-hung",
            attempt_id="a-attempt-hung",
            model=MODEL_A,
            deadline_ns=self.clock.value + 20_000,
        )
        self.begin_switch(timeout=1_000)
        completed = self.machine.complete_response(
            self.fence,
            lease_id=first.lease_id,
            runtime_generation=1,
            model=MODEL_A,
        )
        self.assertEqual(completed.status, LeaseStatus.COMPLETED)
        ready, _ = self.machine.advance_drain(self.fence, switch_id="switch-1")
        self.assertFalse(ready)
        self.clock.advance(2_000)
        ready, timed_out = self.machine.advance_drain(
            self.fence, switch_id="switch-1"
        )
        self.assertTrue(ready)
        self.assertEqual(timed_out, (second.lease_id,))
        with self.assertRaises(FenceRejected):
            self.machine.complete_response(
                self.fence,
                lease_id=second.lease_id,
                runtime_generation=1,
                model=MODEL_A,
            )
        snapshot = self.machine.snapshot()
        self.assertIn(1, snapshot.retired_runtime_generations)


class FailureAndRollbackTests(MachineFixture):
    def test_partial_b_failure_must_reclaim_b_before_rollback(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        generation = self.machine.begin_start_b(self.fence, switch_id="switch-1")
        runtime_b = runtime(MODEL_B, generation, suffix="partial-b")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=runtime_b
        )
        self.machine.fail_start(
            self.fence, switch_id="switch-1", reason="semantic probe failed"
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.RECLAIMING_B)
        with self.assertRaises(InvalidTransition):
            self.machine.begin_rollback(self.fence, switch_id="switch-1")
        reclaim_started = self.machine.snapshot().transitions[-1].at_ns
        absence, gpu = reclaim_proofs("switch-1", runtime_b, reclaim_started)
        self.machine.record_reclaim(
            self.fence,
            switch_id="switch-1",
            absence=absence,
            gpu_release=gpu,
        )
        self.machine.mark_failed(
            self.fence, switch_id="switch-1", reason="B validation failed"
        )
        rollback_generation = self.machine.begin_rollback(
            self.fence, switch_id="switch-1"
        )
        rollback_runtime = runtime(MODEL_A, rollback_generation, suffix="rollback-a")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=rollback_runtime
        )
        self.machine.accept_rollback(
            self.fence,
            switch_id="switch-1",
            semantic_probe=semantic_probe(
                "switch-1",
                rollback_runtime,
                self.machine.snapshot().transitions[-1].at_ns,
            ),
        )
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.state, SwitchState.ROLLBACK_SERVING)
        self.assertEqual(snapshot.serving_model, MODEL_A)

    def test_cancelled_switch_still_reclaims_then_can_rollback(self) -> None:
        self.begin_switch()
        self.machine.cancel_switch(
            self.fence, switch_id="switch-1", reason="caller cancelled B"
        )
        self.reach_gpu_free()
        with self.assertRaises(InvalidTransition):
            self.machine.begin_start_b(self.fence, switch_id="switch-1")
        generation = self.machine.begin_rollback(self.fence, switch_id="switch-1")
        self.assertEqual(generation, 2)

    def test_cancellation_after_b_process_exists_blocks_semantic_admission(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        generation = self.machine.begin_start_b(self.fence, switch_id="switch-1")
        runtime_b = runtime(MODEL_B, generation, suffix="cancelled-b")
        self.machine.bind_starting_runtime(
            self.fence, switch_id="switch-1", runtime=runtime_b
        )
        self.machine.cancel_switch(
            self.fence, switch_id="switch-1", reason="caller cancelled after launch"
        )
        with self.assertRaisesRegex(InvalidTransition, "cannot be admitted"):
            self.machine.accept_b(
                self.fence,
                switch_id="switch-1",
                semantic_probe=semantic_probe(
                    "switch-1",
                    runtime_b,
                    self.machine.snapshot().transitions[-1].at_ns,
                ),
            )
        self.machine.fail_start(
            self.fence, switch_id="switch-1", reason="cancelled launch cleanup"
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.RECLAIMING_B)

    def test_unverifiable_release_quarantines_and_never_admits_b(self) -> None:
        self.begin_switch()
        self.machine.advance_drain(self.fence, switch_id="switch-1")
        reclaim_started = self.machine.snapshot().transitions[-1].at_ns
        absence, gpu = reclaim_proofs("switch-1", self.runtime_a, reclaim_started)
        occupied = replace(
            gpu.observations[0], compute_pids=(self.runtime_a.host_pid,)
        )
        bad_gpu = replace(gpu, observations=(occupied, gpu.observations[1]))
        with self.assertRaisesRegex(ProofRejected, "still reports GPU processes"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                absence=absence,
                gpu_release=bad_gpu,
            )
        self.machine.reject_reclaim_proof(
            self.fence,
            switch_id="switch-1",
            reason="NVML process list nonempty",
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.QUARANTINED)
        with self.assertRaises(InvalidTransition):
            self.machine.begin_start_b(self.fence, switch_id="switch-1")


class ConcurrencyAndRestartTests(MachineFixture):
    def test_concurrent_duplicate_b_is_idempotent_without_double_generation(self) -> None:
        errors: list[Exception] = []
        accepted_t0_ns = self.clock.value

        def worker() -> None:
            try:
                self.machine.begin_switch(
                    self.fence,
                    switch_id="switch-1",
                    request_id="switch-request-1",
                    attempt_id="switch-attempt-1",
                    target=MODEL_B,
                    accepted_t0_ns=accepted_t0_ns,
                    drain_timeout_ns=5_000,
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.active_switch.switch_id, "switch-1")
        self.assertEqual(snapshot.next_runtime_generation, 2)
        self.assertEqual(snapshot.state, SwitchState.DRAINING_A)

    def test_competing_switches_admit_exactly_one(self) -> None:
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def worker(switch_id: str, target: ModelRef) -> None:
            barrier.wait()
            try:
                self.machine.begin_switch(
                    self.fence,
                    switch_id=switch_id,
                    request_id=f"request-{switch_id}",
                    attempt_id=f"attempt-{switch_id}",
                    target=target,
                    accepted_t0_ns=self.clock.value,
                    drain_timeout_ns=1_000,
                )
                outcomes.append("accepted")
            except InvalidTransition:
                outcomes.append("rejected")

        model_c = ModelRef("model-c", "1", "f" * 64)
        threads = [
            threading.Thread(target=worker, args=("switch-b", MODEL_B)),
            threading.Thread(target=worker, args=("switch-c", model_c)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(outcomes), ["accepted", "rejected"])

    def test_restart_fences_old_controller_and_preserves_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            clock = FakeClock()
            store = JsonFileStateStore(path, MachineSnapshot.initial("node-1", GPU_UUID))
            first = DrainReclaimStateMachine(store, clock_ns=clock)
            old_fence = first.claim_controller("controller-old")
            first.install_serving_a(old_fence, runtime(MODEL_A, 1))
            restarted = DrainReclaimStateMachine(JsonFileStateStore(path), clock_ns=clock)
            new_fence = restarted.claim_controller("controller-new")
            self.assertGreater(new_fence.generation, old_fence.generation)
            with self.assertRaises(FenceRejected):
                first.begin_switch(
                    old_fence,
                    switch_id="stale-switch",
                    request_id="stale-request",
                    attempt_id="stale-attempt",
                    target=MODEL_B,
                    accepted_t0_ns=clock.value,
                    drain_timeout_ns=1_000,
                )
            restarted.begin_switch(
                new_fence,
                switch_id="fresh-switch",
                request_id="fresh-request",
                attempt_id="fresh-attempt",
                target=MODEL_B,
                accepted_t0_ns=clock.value,
                drain_timeout_ns=1_000,
            )
            raw = path.read_text()
            self.assertEqual(raw, json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")) + "\n")

    def test_transition_chain_tamper_is_detected_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            clock = FakeClock()
            store = JsonFileStateStore(path, MachineSnapshot.initial("node-1", GPU_UUID))
            machine = DrainReclaimStateMachine(store, clock_ns=clock)
            fence = machine.claim_controller("controller-1")
            machine.install_serving_a(fence, runtime(MODEL_A, 1))
            value = json.loads(path.read_text())
            value["transitions"][0]["operation"] = "forged-operation"
            path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
            with self.assertRaisesRegex(Exception, "record hash differs"):
                DrainReclaimStateMachine(JsonFileStateStore(path), clock_ns=clock).snapshot()


class PropertyTests(unittest.TestCase):
    def test_many_seed_concurrent_and_failure_sequences_preserve_invariants(self) -> None:
        for seed in range(100):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                clock = FakeClock(seed * 100_000 + 1_000_000)
                machine = DrainReclaimStateMachine(
                    InMemoryStateStore(MachineSnapshot.initial(f"node-{seed}", GPU_UUID)),
                    clock_ns=clock,
                )
                fence = machine.claim_controller(f"controller-{seed}")
                a = runtime(MODEL_A, 1, suffix=f"a-{seed}")
                machine.install_serving_a(fence, a)
                lease_ids: list[str] = []
                for index in range(rng.randrange(0, 8)):
                    lease = machine.admit_request(
                        fence,
                        lease_id=f"lease-{seed}-{index}",
                        request_id=f"request-{seed}-{index}",
                        attempt_id=f"attempt-{seed}-{index}",
                        model=MODEL_A,
                        deadline_ns=clock.value + 10_000,
                    )
                    lease_ids.append(lease.lease_id)
                machine.begin_switch(
                    fence,
                    switch_id=f"switch-{seed}",
                    request_id=f"switch-request-{seed}",
                    attempt_id=f"switch-attempt-{seed}",
                    target=MODEL_B,
                    accepted_t0_ns=clock.value,
                    drain_timeout_ns=1_000,
                )
                for lease_id in lease_ids:
                    if rng.choice((True, False)):
                        machine.complete_response(
                            fence,
                            lease_id=lease_id,
                            runtime_generation=1,
                            model=MODEL_A,
                        )
                clock.advance(2_000)
                ready, _ = machine.advance_drain(
                    fence, switch_id=f"switch-{seed}"
                )
                self.assertTrue(ready)
                reclaim_started = machine.snapshot().transitions[-1].at_ns
                absence, gpu = reclaim_proofs(f"switch-{seed}", a, reclaim_started)
                machine.record_reclaim(
                    fence,
                    switch_id=f"switch-{seed}",
                    absence=absence,
                    gpu_release=gpu,
                )
                self.assertEqual(machine.snapshot().state, SwitchState.GPU_FREE)
                if rng.choice((True, False)):
                    generation = machine.begin_start_b(
                        fence, switch_id=f"switch-{seed}"
                    )
                    b = runtime(MODEL_B, generation, suffix=f"b-{seed}")
                    machine.bind_starting_runtime(
                        fence, switch_id=f"switch-{seed}", runtime=b
                    )
                    if rng.choice((True, False)):
                        machine.accept_b(
                            fence,
                            switch_id=f"switch-{seed}",
                            semantic_probe=semantic_probe(
                                f"switch-{seed}",
                                b,
                                machine.snapshot().transitions[-1].at_ns,
                            ),
                        )
                        self.assertEqual(machine.snapshot().serving_model, MODEL_B)
                    else:
                        machine.fail_start(
                            fence,
                            switch_id=f"switch-{seed}",
                            reason="seeded B failure",
                        )
                        self.assertEqual(
                            machine.snapshot().state, SwitchState.RECLAIMING_B
                        )


if __name__ == "__main__":
    unittest.main()
