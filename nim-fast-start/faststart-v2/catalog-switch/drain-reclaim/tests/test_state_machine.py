from __future__ import annotations

import copy
import json
import random
import tempfile
import threading
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from support import *  # noqa: F403
from state_machine import (  # noqa: E402
    DrainReclaimStateMachine,
    FenceRejected,
    InMemoryStateStore,
    InvalidTransition,
    JsonFileStateStore,
    LedgerGateReceipt,
    LedgerStage,
    MachineSnapshot,
    PlacementRevocationProof,
    ProofRejected,
    ResponseTimedOut,
    SwitchState,
    canonical_sha256,
    sign_payload,
)


class MachineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = node_authority()  # noqa: F405
        self.clock = FakeClock()  # noqa: F405
        self.machine = DrainReclaimStateMachine(
            InMemoryStateStore(MachineSnapshot.initial(self.authority, GPU_UUID)),  # noqa: F405
            evidence_trust=trust_store(authority=self.authority),  # noqa: F405
            clock_ns=self.clock,
        )
        self.fence = self.machine.claim_controller("controller-1")
        self.runtime_a = runtime(  # noqa: F405
            MODEL_A, 1, operation_id="bootstrap-a", suffix="a", authority=self.authority  # noqa: F405
        )
        self.machine.install_serving_a(self.fence, self.runtime_a)

    def begin_switch(self, *, timeout: int = 1_000) -> None:
        self.machine.begin_switch(
            self.fence,
            switch_id="switch-1",
            trace_id="switch-trace-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            target=MODEL_B,  # noqa: F405
            validator=VALIDATOR_B,  # noqa: F405
            accepted_t0_ns=self.clock.value,
            drain_timeout_ns=timeout,
        )

    def reach_gpu_free(self) -> None:
        ready, _ = self.machine.advance_drain(self.fence, switch_id="switch-1")
        self.assertTrue(ready)
        reclaim_started = self.machine.snapshot().transitions[-1].at_ns
        stop, absence, gpu = reclaim_bundle(  # noqa: F405
            switch_id="switch-1",
            target=self.runtime_a,
            fence=self.fence,
            reclaim_started=reclaim_started,
        )
        self.clock.advance(100)
        self.machine.record_reclaim(
            self.fence,
            switch_id="switch-1",
            stop_receipt=stop,
            absence=absence,
            gpu_release=gpu,
        )


class DrainAndFenceTests(MachineFixture):
    def test_active_a_completes_during_drain_before_reclaim(self) -> None:
        lease = self.machine.admit_request(
            self.fence,
            lease_id="lease-active-a",
            request_id="request-active-a",
            attempt_id="attempt-active-a",
            model=MODEL_A,  # noqa: F405
            deadline_ns=self.clock.value + 10_000,
        )
        self.begin_switch(timeout=1_000)
        completed = self.machine.complete_response(
            self.fence,
            lease_id=lease.lease_id,
            runtime_generation=self.runtime_a.runtime_generation,
            model=MODEL_A,  # noqa: F405
        )
        self.assertEqual(completed.status.value, "COMPLETED")
        ready, timed_out = self.machine.advance_drain(
            self.fence, switch_id="switch-1"
        )
        self.assertTrue(ready)
        self.assertEqual(timed_out, ())

    def test_hung_a_is_timed_out_and_late_a_response_rejected(self) -> None:
        lease = self.machine.admit_request(
            self.fence,
            lease_id="lease-a",
            request_id="request-a",
            attempt_id="attempt-a",
            model=MODEL_A,  # noqa: F405
            deadline_ns=self.clock.value + 10_000,
        )
        self.begin_switch(timeout=500)
        ready, _ = self.machine.advance_drain(self.fence, switch_id="switch-1")
        self.assertFalse(ready)
        self.clock.advance(1_000)
        ready, timed_out = self.machine.advance_drain(self.fence, switch_id="switch-1")
        self.assertTrue(ready)
        self.assertEqual(timed_out, (lease.lease_id,))
        with self.assertRaises(FenceRejected):
            self.machine.complete_response(
                self.fence,
                lease_id=lease.lease_id,
                runtime_generation=1,
                model=MODEL_A,  # noqa: F405
            )

    def test_late_response_timeout_is_persisted_before_exception(self) -> None:
        lease = self.machine.admit_request(
            self.fence,
            lease_id="deadline-lease",
            request_id="deadline-request",
            attempt_id="deadline-attempt",
            model=MODEL_A,  # noqa: F405
            deadline_ns=self.clock.value + 150,
        )
        self.clock.advance(1_000)
        before = self.machine.snapshot().revision
        with self.assertRaisesRegex(ResponseTimedOut, "persisted"):
            self.machine.complete_response(
                self.fence,
                lease_id=lease.lease_id,
                runtime_generation=1,
                model=MODEL_A,  # noqa: F405
            )
        snapshot = self.machine.snapshot()
        self.assertGreater(snapshot.revision, before)
        self.assertEqual(snapshot.request_leases[lease.lease_id].status.value, "TIMED_OUT")

    def test_stale_generation_and_stale_controller_commands_reject(self) -> None:
        lease = self.machine.admit_request(
            self.fence,
            lease_id="lease-1",
            request_id="request-1",
            attempt_id="attempt-1",
            model=MODEL_A,  # noqa: F405
            deadline_ns=self.clock.value + 10_000,
        )
        new_fence = self.machine.claim_controller("controller-2")
        with self.assertRaisesRegex(FenceRejected, "controller generation"):
            self.machine.cancel_request(self.fence, lease_id=lease.lease_id, reason="stale")
        with self.assertRaises(FenceRejected):
            self.machine.complete_response(
                new_fence,
                lease_id=lease.lease_id,
                runtime_generation=2,
                model=MODEL_A,  # noqa: F405
            )


class ReclaimTests(MachineFixture):
    def test_exact_total_absence_before_scrub_and_zero_nvml_are_required(self) -> None:
        self.begin_switch()
        self.machine.advance_drain(self.fence, switch_id="switch-1")
        reclaim_started = self.machine.snapshot().transitions[-1].at_ns
        stop, absence, good = reclaim_bundle(  # noqa: F405
            switch_id="switch-1", target=self.runtime_a, fence=self.fence, reclaim_started=reclaim_started
        )
        mismatched = signed_gpu_release(  # noqa: F405
            switch_id="switch-1",
            subject_sha256=self.runtime_a.digest,
            authority=self.authority,
            absence_at=absence.observed_at_ns,
            total_bytes=1,
            bytes_scrubbed=1,
        )
        observations = tuple(
            replace(item, memory_total_bytes=TOTAL_BYTES) for item in mismatched.observations  # noqa: F405
        )
        payload = asdict(replace(mismatched, observations=observations))
        payload.pop("signature_sha256")
        mismatched = replace(
            mismatched,
            observations=observations,
            signature_sha256=sign_payload(NODE_KEY, payload),  # noqa: F405
        )
        with self.assertRaisesRegex(ProofRejected, "total memory differs"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                stop_receipt=stop,
                absence=absence,
                gpu_release=mismatched,
            )
        early_scrub = replace(
            good,
            scrub=replace(
                good.scrub,
                started_at_ns=stop.finished_at_ns,
                finished_at_ns=stop.finished_at_ns + 1,
            ),
            observations=tuple(
                replace(item, observed_at_ns=stop.finished_at_ns + 2 + index)
                for index, item in enumerate(good.observations)
            ),
        )
        payload = asdict(early_scrub)
        payload.pop("signature_sha256")
        early_scrub = replace(early_scrub, signature_sha256=sign_payload(NODE_KEY, payload))  # noqa: F405
        with self.assertRaisesRegex(ProofRejected, "only after exact absence"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                stop_receipt=stop,
                absence=absence,
                gpu_release=early_scrub,
            )
        nonzero = signed_gpu_release(  # noqa: F405
            switch_id="switch-1",
            subject_sha256=self.runtime_a.digest,
            authority=self.authority,
            absence_at=absence.observed_at_ns,
            used_bytes=1,
        )
        with self.assertRaisesRegex(ProofRejected, "must equal zero"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                stop_receipt=stop,
                absence=absence,
                gpu_release=nonzero,
            )
        self.machine.record_reclaim(
            self.fence,
            switch_id="switch-1",
            stop_receipt=stop,
            absence=absence,
            gpu_release=good,
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.GPU_FREE)

    def test_graphics_process_rejects_gpu_release(self) -> None:
        self.begin_switch()
        self.machine.advance_drain(self.fence, switch_id="switch-1")
        started = self.machine.snapshot().transitions[-1].at_ns
        stop, absence, _ = reclaim_bundle(  # noqa: F405
            switch_id="switch-1", target=self.runtime_a, fence=self.fence, reclaim_started=started
        )
        gpu = signed_gpu_release(  # noqa: F405
            switch_id="switch-1",
            subject_sha256=self.runtime_a.digest,
            authority=self.authority,
            absence_at=absence.observed_at_ns,
            graphics_pids=(777,),
        )
        with self.assertRaisesRegex(ProofRejected, "compute/graphics"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                stop_receipt=stop,
                absence=absence,
                gpu_release=gpu,
            )


class LaunchReservationTests(MachineFixture):
    def test_duplicate_launch_reservation_is_idempotent_and_conflict_rejects(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        first = self.machine.begin_start_b(
            self.fence,
            switch_id="switch-1",
            operation_id="launch-b-op",
            idempotency_key="launch-b-idem",
        )
        second = self.machine.begin_start_b(
            self.fence,
            switch_id="switch-1",
            operation_id="launch-b-op",
            idempotency_key="launch-b-idem",
        )
        self.assertEqual(first, second)
        self.assertEqual(first.runtime_generation, 2)
        self.assertEqual(self.machine.snapshot().next_runtime_generation, 3)
        with self.assertRaises(InvalidTransition):
            self.machine.begin_start_b(
                self.fence,
                switch_id="switch-1",
                operation_id="different-op",
                idempotency_key="different-idem",
            )

    def test_ambiguous_launch_must_be_proved_absent_before_new_generation(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        reservation = self.machine.begin_start_b(
            self.fence,
            switch_id="switch-1",
            operation_id="launch-b-response-lost",
            idempotency_key="launch-b-response-lost-idem",
        )
        self.machine.fail_start(
            self.fence,
            switch_id="switch-1",
            reason="launch response lost before runtime bind",
        )
        self.assertEqual(self.machine.snapshot().state, SwitchState.RECLAIMING_B)
        with self.assertRaises(InvalidTransition):
            self.machine.begin_start_b(
                self.fence,
                switch_id="switch-1",
                operation_id="gen3",
                idempotency_key="gen3-idem",
            )
        entered = self.machine.snapshot().transitions[-1].at_ns
        cleanup = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="cleanup-launch-operation",
            subject_sha256=reservation.digest,
            authority=self.authority,
            fence=self.fence,
            started=entered + 1,
        )
        absence = signed_operation_absence(  # noqa: F405
            switch_id="switch-1",
            reservation=reservation,
            authority=self.authority,
            observed_at=entered + 3,
        )
        gpu = signed_gpu_release(  # noqa: F405
            switch_id="switch-1",
            subject_sha256=reservation.digest,
            authority=self.authority,
            absence_at=absence.observed_at_ns,
        )
        wrong = replace(absence, runtime_generation=reservation.runtime_generation + 1)
        wrong_payload = asdict(wrong)
        wrong_payload.pop("signature_sha256")
        wrong = replace(wrong, signature_sha256=sign_payload(NODE_KEY, wrong_payload))  # noqa: F405
        with self.assertRaisesRegex(ProofRejected, "identity differs"):
            self.machine.record_ambiguous_launch_cleanup(
                self.fence,
                switch_id="switch-1",
                cleanup_receipt=cleanup,
                absence=wrong,
                gpu_release=gpu,
            )
        self.machine.record_ambiguous_launch_cleanup(
            self.fence,
            switch_id="switch-1",
            cleanup_receipt=cleanup,
            absence=absence,
            gpu_release=gpu,
        )
        self.assertIsNone(self.machine.snapshot().launch_reservation)
        self.assertIn(2, self.machine.snapshot().retired_runtime_generations)

    def test_cancelled_bound_b_requires_exact_partial_cleanup(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        reservation = self.machine.begin_start_b(
            self.fence,
            switch_id="switch-1",
            operation_id="launch-partial-b",
            idempotency_key="launch-partial-b-idem",
        )
        target = runtime(  # noqa: F405
            MODEL_B,
            reservation.runtime_generation,
            operation_id=reservation.operation_id,
            suffix="partial-b",
            authority=self.authority,
        )
        launch = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="launch-runtime",
            subject_sha256=reservation.digest,
            authority=self.authority,
            fence=self.fence,
            started=reservation.reserved_at_ns + 1,
            idempotency_key=reservation.idempotency_key,
        )
        self.clock.advance(100)
        self.machine.bind_starting_runtime(
            self.fence,
            switch_id="switch-1",
            runtime=target,
            launch_receipt=launch,
        )
        self.machine.cancel_switch(
            self.fence, switch_id="switch-1", reason="cancel after B launch"
        )
        self.machine.fail_start(
            self.fence, switch_id="switch-1", reason="cancelled B must be reclaimed"
        )
        entered = self.machine.snapshot().transitions[-1].at_ns
        stop, absence, gpu = reclaim_bundle(  # noqa: F405
            switch_id="switch-1",
            target=target,
            fence=self.fence,
            reclaim_started=entered,
        )
        incomplete = replace(absence, process_absent=False)
        payload = asdict(incomplete)
        payload.pop("signature_sha256")
        incomplete = replace(
            incomplete, signature_sha256=sign_payload(NODE_KEY, payload)  # noqa: F405
        )
        with self.assertRaisesRegex(ProofRejected, "incomplete"):
            self.machine.record_reclaim(
                self.fence,
                switch_id="switch-1",
                stop_receipt=stop,
                absence=incomplete,
                gpu_release=gpu,
            )
        self.clock.advance(100)
        self.machine.record_reclaim(
            self.fence,
            switch_id="switch-1",
            stop_receipt=stop,
            absence=absence,
            gpu_release=gpu,
        )
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.state, SwitchState.GPU_FREE)
        self.assertIn(reservation.runtime_generation, snapshot.retired_runtime_generations)

    def test_exact_bridge_receipt_is_mandatory_for_admission(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        reservation = self.machine.begin_start_b(
            self.fence,
            switch_id="switch-1",
            operation_id="launch-b-op",
            idempotency_key="launch-b-idem",
        )
        target = runtime(  # noqa: F405
            MODEL_B, reservation.runtime_generation, operation_id=reservation.operation_id, suffix="b", authority=self.authority  # noqa: F405
        )
        launch_receipt = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="launch-runtime",
            subject_sha256=reservation.digest,
            authority=self.authority,
            fence=self.fence,
            started=reservation.reserved_at_ns + 1,
            idempotency_key=reservation.idempotency_key,
        )
        self.clock.advance(100)
        self.machine.bind_starting_runtime(
            self.fence,
            switch_id="switch-1",
            runtime=target,
            launch_receipt=launch_receipt,
        )
        payload = {
            "schema": "archvteams.nebius.ai/catalog-switch-ledger-gate/v2",
            "stage": LedgerStage.TARGET_QUALIFIED,
            "switch_id": "switch-1",
            "trace_id": "switch-trace-1",
            "request_id": "switch-request-1",
            "attempt_id": "switch-attempt-1",
            "accepted_t0_ns": self.machine.snapshot().active_switch.accepted_t0_ns,
            "runtime_generation": 2,
            "launch_operation_id": "launch-b-op",
            "launch_action_receipt_sha256": canonical_sha256(asdict(launch_receipt)),
            "model_id": "model-b",
            "model_version": "2",
            "artifact_sha256": "b" * 64,
            "validator_sha256": "2" * 64,
            "shared_ledger_sha256": "a" * 64,
            "audit_segment_sha256": "b" * 64,
            "audit_sequence_start": 0,
            "audit_sequence_end": 1,
            "audit_chain_head_sha256": "c" * 64,
            "offnode_durability_receipt_sha256": "d" * 64,
            "product_terminal_event_sha256": "e" * 64,
            "predecessor_receipt_sha256": None,
            "first_semantic_at_ns": 10,
            "second_semantic_at_ns": 11,
        }
        serializable = dict(payload)
        serializable["stage"] = LedgerStage.TARGET_QUALIFIED.value
        receipt = LedgerGateReceipt(**payload, receipt_sha256=canonical_sha256(serializable))
        with self.assertRaisesRegex(ProofRejected, "no canonical ledger verifier"):
            self.machine.accept_b(
                self.fence, switch_id="switch-1", ledger_receipt=receipt
            )
        self.assertFalse(self.machine.snapshot().admission_open)


class QuarantineAndDurabilityTests(MachineFixture):
    def test_quarantine_revoke_recycle_new_boot_and_requalify(self) -> None:
        self.begin_switch()
        self.machine.advance_drain(self.fence, switch_id="switch-1")
        self.machine.reject_reclaim_proof(
            self.fence, switch_id="switch-1", reason="injected NVML receipt loss"
        )
        self.machine.begin_quarantine_recovery(self.fence, switch_id="switch-1")
        entered = self.machine.snapshot().transitions[-1].at_ns
        revoke = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="revoke-placement-lease",
            subject_sha256=self.authority.placement_subject_sha256,
            authority=self.authority,
            fence=self.fence,
            started=entered + 1,
        )
        revocation_payload = {
            "schema": "archvteams.nebius.ai/catalog-switch-placement-revocation/v1",
            "switch_id": "switch-1",
            "authority_sha256": self.authority.digest,
            "placement_lease_id": self.authority.placement_lease_id,
            "backend": self.authority.backend,
            "source_id": "resource-broker",
            "source_key_sha256": key_sha256(BROKER_KEY),  # noqa: F405
            "revoked_at_ns": entered + 5,
            "placement_refusal_observed_at_ns": entered + 6,
            "lease_absent": True,
            "new_placement_refused": True,
            "raw_evidence_sha256": "8" * 64,
        }
        revocation = PlacementRevocationProof(
            **revocation_payload,
            signature_sha256=sign_payload(BROKER_KEY, revocation_payload),  # noqa: F405
        )
        unsafe_payload = dict(revocation_payload)
        unsafe_payload["new_placement_refused"] = False
        unsafe_revocation = PlacementRevocationProof(
            **unsafe_payload,
            signature_sha256=sign_payload(BROKER_KEY, unsafe_payload),  # noqa: F405
        )
        with self.assertRaisesRegex(ProofRejected, "remains eligible"):
            self.machine.record_quarantine_revocation(
                self.fence,
                switch_id="switch-1",
                receipt=revoke,
                proof=unsafe_revocation,
            )
        self.machine.record_quarantine_revocation(
            self.fence,
            switch_id="switch-1",
            receipt=revoke,
            proof=revocation,
        )
        new_authority = node_authority(  # noqa: F405
            boot="fresh-boot-2",
            key=NEW_NODE_KEY,
            node_id="node-2",
            node_uid="node-uid-2",
        )
        recycle_payload = {
            "schema": "archvteams.nebius.ai/catalog-switch-node-recycle/v1",
            "switch_id": "switch-1",
            "old_authority_sha256": self.authority.digest,
            "new_authority": asdict(new_authority),
            "old_resource_id": self.authority.node_id,
            "new_resource_id": new_authority.node_id,
            "old_resource_absent": True,
            "new_resource_created": True,
            "old_gpu_uuid": GPU_UUID,  # noqa: F405
            "new_gpu_uuid": "GPU-00000000-0000-0000-0000-000000000002",
            "source_id": "resource-broker",
            "source_key_sha256": key_sha256(BROKER_KEY),  # noqa: F405
            "completed_at_ns": entered + 10,
            "raw_evidence_sha256": "9" * 64,
        }
        recycle = NodeRecycleProof(  # noqa: F405
            schema=recycle_payload["schema"],
            switch_id=recycle_payload["switch_id"],
            old_authority_sha256=recycle_payload["old_authority_sha256"],
            new_authority=new_authority,
            old_resource_id=recycle_payload["old_resource_id"],
            new_resource_id=recycle_payload["new_resource_id"],
            old_resource_absent=recycle_payload["old_resource_absent"],
            new_resource_created=recycle_payload["new_resource_created"],
            old_gpu_uuid=recycle_payload["old_gpu_uuid"],
            new_gpu_uuid=recycle_payload["new_gpu_uuid"],
            source_id=recycle_payload["source_id"],
            source_key_sha256=recycle_payload["source_key_sha256"],
            completed_at_ns=recycle_payload["completed_at_ns"],
            raw_evidence_sha256=recycle_payload["raw_evidence_sha256"],
            signature_sha256=sign_payload(BROKER_KEY, recycle_payload),  # noqa: F405
        )
        with self.assertRaisesRegex(
            ProofRejected, "old-absence/new-creation proof"
        ):
            self.machine.record_node_recycle(
                self.fence,
                switch_id="switch-1",
                proof=replace(recycle, old_resource_absent=False),
            )
        with self.assertRaisesRegex(ProofRejected, "resource IDs differ"):
            self.machine.record_node_recycle(
                self.fence,
                switch_id="switch-1",
                proof=replace(recycle, new_resource_id="unbound-resource"),
            )
        self.machine.record_node_recycle(
            self.fence, switch_id="switch-1", proof=recycle
        )
        observations = (
            NvmlObservation(entered + 20, recycle.new_gpu_uuid, (), (), True, 0, TOTAL_BYTES),  # noqa: F405
            NvmlObservation(entered + 21, recycle.new_gpu_uuid, (), (), True, 0, TOTAL_BYTES),  # noqa: F405
        )
        requal_payload = {
            "schema": "archvteams.nebius.ai/catalog-switch-requalification/v1",
            "switch_id": "switch-1",
            "authority_sha256": new_authority.digest,
            "gpu_uuid": recycle.new_gpu_uuid,
            "source_id": new_authority.node_agent_id,
            "source_key_sha256": key_sha256(NEW_NODE_KEY),  # noqa: F405
            "observed_at_ns": entered + 22,
            "sentinel_vram_absent": True,
            "host_residue_absent": True,
            "exclusive_occupancy_enforced": True,
            "direct_launch_refused": True,
            "audit_offnode_continuity": True,
            "command_replay_refused": True,
            "observations": [asdict(item) for item in observations],
            "raw_evidence_sha256": "a" * 64,
        }
        requal = RequalificationProof(  # noqa: F405
            schema=requal_payload["schema"],
            switch_id=requal_payload["switch_id"],
            authority_sha256=requal_payload["authority_sha256"],
            gpu_uuid=requal_payload["gpu_uuid"],
            source_id=requal_payload["source_id"],
            source_key_sha256=requal_payload["source_key_sha256"],
            observed_at_ns=requal_payload["observed_at_ns"],
            sentinel_vram_absent=True,
            host_residue_absent=True,
            exclusive_occupancy_enforced=True,
            direct_launch_refused=True,
            audit_offnode_continuity=True,
            command_replay_refused=True,
            observations=observations,
            raw_evidence_sha256=requal_payload["raw_evidence_sha256"],
            signature_sha256=sign_payload(NEW_NODE_KEY, requal_payload),  # noqa: F405
        )
        self.machine.record_requalification(
            self.fence, switch_id="switch-1", proof=requal
        )
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.state, SwitchState.GPU_FREE)
        self.assertEqual(snapshot.authority.node_boot_id, "fresh-boot-2")
        self.assertEqual(snapshot.gpu_uuid, recycle.new_gpu_uuid)
        self.assertIsNone(snapshot.quarantine_reason)
        self.assertIsNotNone(snapshot.quarantine_revocation_proof_sha256)
        self.assertIsNotNone(snapshot.node_recycle_proof_sha256)
        self.assertIsNotNone(snapshot.requalification_proof_sha256)

    def test_transition_chain_binds_every_state_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = JsonFileStateStore(path, MachineSnapshot.initial(self.authority, GPU_UUID))  # noqa: F405
            machine = DrainReclaimStateMachine(
                store,
                evidence_trust=trust_store(authority=self.authority),  # noqa: F405
                clock_ns=self.clock,
            )
            fence = machine.claim_controller("controller-file")
            machine.install_serving_a(
                fence,
                runtime(MODEL_A, 1, operation_id="bootstrap-file", suffix="file", authority=self.authority),  # noqa: F405
            )
            value = json.loads(path.read_text())
            value["next_runtime_generation"] = 99
            path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
            with self.assertRaisesRegex(Exception, "current snapshot differs"):
                machine.snapshot()

    def test_restart_preserves_state_and_fences_the_old_controller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            first = DrainReclaimStateMachine(
                JsonFileStateStore(
                    path, MachineSnapshot.initial(self.authority, GPU_UUID)  # noqa: F405
                ),
                evidence_trust=trust_store(authority=self.authority),  # noqa: F405
                clock_ns=self.clock,
            )
            old_fence = first.claim_controller("controller-old")
            first.install_serving_a(
                old_fence,
                runtime(  # noqa: F405
                    MODEL_A,
                    1,
                    operation_id="bootstrap-restart",
                    suffix="restart-a",
                    authority=self.authority,
                ),
            )
            restarted = DrainReclaimStateMachine(
                JsonFileStateStore(path),
                evidence_trust=trust_store(authority=self.authority),  # noqa: F405
                clock_ns=self.clock,
            )
            new_fence = restarted.claim_controller("controller-new")
            with self.assertRaisesRegex(FenceRejected, "controller generation"):
                first.admit_request(
                    old_fence,
                    lease_id="stale-after-restart",
                    request_id="stale-request",
                    attempt_id="stale-attempt",
                    model=MODEL_A,  # noqa: F405
                    deadline_ns=self.clock.value + 1_000,
                )
            self.assertGreater(new_fence.generation, old_fence.generation)
            self.assertEqual(restarted.snapshot().state, SwitchState.SERVING_A)


class ConcurrencyTests(MachineFixture):
    def test_concurrent_duplicate_switch_is_idempotent(self) -> None:
        outcomes: list[Exception] = []
        t0 = self.clock.value

        def worker() -> None:
            try:
                self.machine.begin_switch(
                    self.fence,
                    switch_id="switch-1",
                    trace_id="switch-trace-1",
                    request_id="switch-request-1",
                    attempt_id="switch-attempt-1",
                    target=MODEL_B,  # noqa: F405
                    validator=VALIDATOR_B,  # noqa: F405
                    accepted_t0_ns=t0,
                    drain_timeout_ns=1_000,
                )
            except Exception as exc:  # pragma: no cover
                outcomes.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes, [])
        self.assertEqual(self.machine.snapshot().state, SwitchState.DRAINING_A)

    def test_concurrent_duplicate_b_reserves_one_generation(self) -> None:
        self.begin_switch()
        self.reach_gpu_free()
        results = []
        failures: list[Exception] = []

        def worker() -> None:
            try:
                results.append(
                    self.machine.begin_start_b(
                        self.fence,
                        switch_id="switch-1",
                        operation_id="concurrent-launch-b",
                        idempotency_key="concurrent-launch-b-idem",
                    )
                )
            except Exception as exc:  # pragma: no cover
                failures.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 12)
        self.assertEqual({item.digest for item in results}, {results[0].digest})
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot.next_runtime_generation, 3)
        self.assertEqual(snapshot.launch_reservation.runtime_generation, 2)


class PropertyScheduleTests(unittest.TestCase):
    def test_many_seed_drain_cancel_failure_and_cleanup_preserve_invariants(self) -> None:
        for seed in range(50):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                authority = node_authority(  # noqa: F405
                    boot=f"boot-{seed}",
                    node_id=f"node-{seed}",
                    node_uid=f"node-uid-{seed}",
                )
                clock = FakeClock(1_000_000 + seed * 100_000)  # noqa: F405
                machine = DrainReclaimStateMachine(
                    InMemoryStateStore(
                        MachineSnapshot.initial(authority, GPU_UUID)  # noqa: F405
                    ),
                    evidence_trust=trust_store(authority=authority),  # noqa: F405
                    clock_ns=clock,
                )
                fence = machine.claim_controller(f"controller-{seed}")
                active_a = runtime(  # noqa: F405
                    MODEL_A,
                    1,
                    operation_id=f"bootstrap-{seed}",
                    suffix=f"a-{seed}",
                    authority=authority,
                )
                machine.install_serving_a(fence, active_a)
                leases = [
                    machine.admit_request(
                        fence,
                        lease_id=f"lease-{seed}-{index}",
                        request_id=f"request-{seed}-{index}",
                        attempt_id=f"attempt-{seed}-{index}",
                        model=MODEL_A,  # noqa: F405
                        deadline_ns=clock.value + 50_000,
                    )
                    for index in range(rng.randrange(5))
                ]
                switch_id = f"switch-{seed}"
                machine.begin_switch(
                    fence,
                    switch_id=switch_id,
                    trace_id=f"trace-{seed}",
                    request_id=f"switch-request-{seed}",
                    attempt_id=f"switch-attempt-{seed}",
                    target=MODEL_B,  # noqa: F405
                    validator=VALIDATOR_B,  # noqa: F405
                    accepted_t0_ns=clock.value,
                    drain_timeout_ns=500,
                )
                for lease in leases:
                    disposition = rng.randrange(3)
                    if disposition == 0:
                        machine.complete_response(
                            fence,
                            lease_id=lease.lease_id,
                            runtime_generation=1,
                            model=MODEL_A,  # noqa: F405
                        )
                    elif disposition == 1:
                        machine.cancel_request(
                            fence,
                            lease_id=lease.lease_id,
                            reason="seeded request cancellation",
                        )
                ready, _ = machine.advance_drain(fence, switch_id=switch_id)
                if not ready:
                    clock.advance(1_000)
                    ready, _ = machine.advance_drain(fence, switch_id=switch_id)
                self.assertTrue(ready)
                reclaim_started = machine.snapshot().transitions[-1].at_ns
                stop, absence, gpu = reclaim_bundle(  # noqa: F405
                    switch_id=switch_id,
                    target=active_a,
                    fence=fence,
                    reclaim_started=reclaim_started,
                )
                clock.advance(100)
                machine.record_reclaim(
                    fence,
                    switch_id=switch_id,
                    stop_receipt=stop,
                    absence=absence,
                    gpu_release=gpu,
                )
                reservation = machine.begin_start_b(
                    fence,
                    switch_id=switch_id,
                    operation_id=f"launch-b-{seed}",
                    idempotency_key=f"launch-b-{seed}-idem",
                )
                if rng.choice((False, True)):
                    target = runtime(  # noqa: F405
                        MODEL_B,
                        reservation.runtime_generation,
                        operation_id=reservation.operation_id,
                        suffix=f"b-{seed}",
                        authority=authority,
                    )
                    launch = signed_action(  # noqa: F405
                        switch_id=switch_id,
                        operation="launch-runtime",
                        subject_sha256=reservation.digest,
                        authority=authority,
                        fence=fence,
                        started=reservation.reserved_at_ns + 1,
                        idempotency_key=reservation.idempotency_key,
                    )
                    clock.advance(100)
                    machine.bind_starting_runtime(
                        fence,
                        switch_id=switch_id,
                        runtime=target,
                        launch_receipt=launch,
                    )
                    if rng.choice((False, True)):
                        machine.cancel_switch(
                            fence,
                            switch_id=switch_id,
                            reason="seeded cancellation after B launch",
                        )
                    machine.fail_start(
                        fence, switch_id=switch_id, reason="seeded bound B failure"
                    )
                    reclaim_started = machine.snapshot().transitions[-1].at_ns
                    stop, absence, gpu = reclaim_bundle(  # noqa: F405
                        switch_id=switch_id,
                        target=target,
                        fence=fence,
                        reclaim_started=reclaim_started,
                    )
                    clock.advance(100)
                    machine.record_reclaim(
                        fence,
                        switch_id=switch_id,
                        stop_receipt=stop,
                        absence=absence,
                        gpu_release=gpu,
                    )
                else:
                    machine.fail_start(
                        fence,
                        switch_id=switch_id,
                        reason="seeded ambiguous B launch",
                    )
                    reclaim_started = machine.snapshot().transitions[-1].at_ns
                    cleanup = signed_action(  # noqa: F405
                        switch_id=switch_id,
                        operation="cleanup-launch-operation",
                        subject_sha256=reservation.digest,
                        authority=authority,
                        fence=fence,
                        started=reclaim_started + 1,
                    )
                    absence = signed_operation_absence(  # noqa: F405
                        switch_id=switch_id,
                        reservation=reservation,
                        authority=authority,
                        observed_at=reclaim_started + 3,
                    )
                    gpu = signed_gpu_release(  # noqa: F405
                        switch_id=switch_id,
                        subject_sha256=reservation.digest,
                        authority=authority,
                        absence_at=absence.observed_at_ns,
                    )
                    clock.advance(100)
                    machine.record_ambiguous_launch_cleanup(
                        fence,
                        switch_id=switch_id,
                        cleanup_receipt=cleanup,
                        absence=absence,
                        gpu_release=gpu,
                    )
                snapshot = machine.snapshot()
                self.assertEqual(snapshot.state, SwitchState.GPU_FREE)
                self.assertFalse(snapshot.admission_open)
                self.assertIsNone(snapshot.active_runtime)
                self.assertIsNone(snapshot.launch_reservation)
                self.assertFalse(
                    any(
                        lease.status.value == "ACTIVE"
                        for lease in snapshot.request_leases.values()
                    )
                )


if __name__ == "__main__":
    unittest.main()
