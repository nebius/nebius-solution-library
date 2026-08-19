from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from support import *  # noqa: F403
from ledger import (  # noqa: E402
    AuditChainStore,
    ExactLedgerReceiptVerifier,
    FileOffNodeSink,
    ImmutableObjectStoreSink,
    SwitchLedgerBridge,
    ValidatorRuntime,
)
from performance.request_slo.harness import HarnessError, aggregate_ledger, load_ledger  # noqa: E402
from state_machine import (  # noqa: E402
    DrainReclaimStateMachine,
    InMemoryStateStore,
    InvalidTransition,
    LedgerExpectation,
    LedgerStage,
    MachineSnapshot,
    ProofRejected,
    SwitchState,
)


RAW_B_REQUEST_1 = b'{"call":1,"input":"B-one"}\n'
RAW_B_REQUEST_2 = b'{"call":2,"input":"B-two"}\n'
RAW_B_RESPONSE_1 = b'{"model_id":"model-b","model_version":"2","valid":true,"value":1}\n'
RAW_B_RESPONSE_2 = b'{"model_id":"model-b","model_version":"2","valid":true,"value":2}\n'
RAW_A_REQUEST_1 = b'{"call":1,"input":"A-one"}\n'
RAW_A_REQUEST_2 = b'{"call":2,"input":"A-two"}\n'
RAW_A_RESPONSE_1 = b'{"model_id":"model-a","model_version":"1","valid":true,"value":1}\n'
RAW_A_RESPONSE_2 = b'{"model_id":"model-a","model_version":"1","valid":true,"value":2}\n'


def fixed_inference(response: bytes):
    return lambda _request, _idempotency_key: response


class LedgerFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger_path = self.root / "shared.jsonl"
        self.audit_path = self.root / "switch-chain.jsonl"
        self.evidence_root = self.root / "evidence"
        self.trace = make_trace(RAW_B_REQUEST_1)  # noqa: F405
        write_acceptance(self.ledger_path, self.trace)  # noqa: F405
        self.authority = node_authority()  # noqa: F405
        self.validator_b = ValidatorRuntime(  # noqa: F405
            VALIDATOR_B, validator_replay(MODEL_B), VALIDATOR_B_SOURCE
        )
        self.sink = FileOffNodeSink(
            self.root / "offnode",
            sink_id="offnode-test-sink",
            key=SINK_KEY,  # noqa: F405
        )
        self.bridge = self.make_bridge()
        self.fence = ControllerFence("controller-1", 1)  # noqa: F405
        self.reservation = LaunchReservation(  # noqa: F405
            "switch-1",
            "launch-b-op",
            "launch-b-idem",
            2,
            MODEL_B,  # noqa: F405
            GPU_UUID,  # noqa: F405
            self.authority.digest,
            "node-local",
            self.fence.controller_id,
            self.fence.generation,
            1_100_000,
        )
        self.runtime_b = runtime(  # noqa: F405
            MODEL_B,
            2,
            operation_id="launch-b-op",
            suffix="b",
            authority=self.authority,
        )
        self.launch_receipt = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="launch-runtime",
            subject_sha256=self.reservation.digest,
            authority=self.authority,
            fence=self.fence,
            started=self.reservation.reserved_at_ns + 1,
            idempotency_key=self.reservation.idempotency_key,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_bridge(self) -> SwitchLedgerBridge:
        return SwitchLedgerBridge(
            path=self.ledger_path,
            audit_path=self.audit_path,
            evidence_root=self.evidence_root,
            trace=self.trace,
            ledger_id="drain-reclaim-ledger-1",
            switch_id="switch-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            recorder=recorder(),  # noqa: F405
            validator_runtime=self.validator_b,
            offnode_sink=self.sink,
        )

    def complete_phases(self, bridge: SwitchLedgerBridge | None = None) -> None:
        writer = bridge or self.bridge
        for phase in (
            "catalog_selection",
            "queue",
            "drain",
            "gpu_release",
            "placement",
            "image_readiness",
            "artifact_readiness",
            "storage_readiness",
            "cache_readiness",
            "runtime_launch",
            "service_readiness",
            "inference",
        ):
            writer.start_phase(phase)
            writer.finish_phase(
                phase,
                outcome="completed",
                reason="state-machine/v2 exact causal evidence",
            )

    def complete_success(self) -> tuple[object, ExactLedgerReceiptVerifier]:
        self.bridge.record_launch_reservation(self.reservation)
        self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
        self.complete_phases()
        self.bridge.execute_semantic_call(
            sequence=1,
            raw_request=RAW_B_REQUEST_1,
            inference=fixed_inference(RAW_B_RESPONSE_1),
        )
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        self.bridge.close_success(
            accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
        )
        receipt = self.bridge.qualification_receipt()
        verifier = self.verifier()
        verifier.verify(
            receipt,
            LedgerExpectation(
                LedgerStage.TARGET_QUALIFIED,
                "switch-1",
                "switch-trace-1",
                "switch-request-1",
                "switch-attempt-1",
                self.bridge.accepted_t0_ns,
                self.runtime_b,
                VALIDATOR_B,  # noqa: F405
                canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
            ),
        )
        return receipt, verifier

    def verifier(self, *, validators=None, recovery_ledgers=None) -> ExactLedgerReceiptVerifier:
        return ExactLedgerReceiptVerifier(
            ledger_path=self.ledger_path,
            audit_path=self.audit_path,
            evidence_root=self.evidence_root,
            trace=self.trace,
            validator_runtimes=validators or {VALIDATOR_B.source_sha256: self.validator_b},  # noqa: F405
            durability_keys={"offnode-test-sink": SINK_KEY},  # noqa: F405
            recovery_ledgers=recovery_ledgers,
            allow_isolated_test_sink=True,
        )


class LedgerGateTests(LedgerFixture):
    def test_bridge_refuses_work_before_external_t0(self) -> None:
        missing = self.root / "missing.jsonl"
        with self.assertRaises(Exception):
            SwitchLedgerBridge(
                path=missing,
                audit_path=self.root / "missing-audit.jsonl",
                evidence_root=self.root / "missing-evidence",
                trace=self.trace,
                ledger_id="drain-reclaim-ledger-1",
                switch_id="switch-1",
                request_id="switch-request-1",
                attempt_id="switch-attempt-1",
                recorder=recorder(),  # noqa: F405
                validator_runtime=self.validator_b,
                offnode_sink=self.sink,
            )

    def test_success_receipt_verifies_actual_shared_chain_raw_blobs_and_offnode_object(self) -> None:
        receipt, _ = self.complete_success()
        events = AuditChainStore(self.audit_path).load()
        self.assertEqual(events[-1]["event_type"], "qualification.terminal")
        self.assertEqual(receipt.audit_chain_head_sha256, events[-1]["record_sha256"])
        self.assertEqual(receipt.accepted_t0_ns, self.bridge.accepted_t0_ns)
        result = aggregate_ledger(load_ledger(self.ledger_path), self.trace)
        self.assertEqual(result["attempts"]["offered"], 1)
        self.assertEqual(result["attempts"]["valid_responses"], 1)

    def test_immutable_offnode_sink_requires_versioned_external_authority(self) -> None:
        self.bridge.record_launch_reservation(self.reservation)
        events = AuditChainStore(self.audit_path).load()

        class Client:
            def __init__(self):
                self.calls = []
                self.objects = {}

            def put_if_absent(self, *, object_key, content, content_sha256):
                self.calls.append((object_key, content, content_sha256))
                uri = f"s3://mlspec-audit/{object_key}"
                version = f"generation-{len(self.calls)}"
                self.objects[(uri, version)] = content
                return uri, version

            def get_exact(self, *, object_uri, object_version):
                return self.objects[(object_uri, object_version)]

        client = Client()
        receipt = ImmutableObjectStoreSink(
            client=client,
            object_prefix="catalog-switch/drain-reclaim",
            sink_id="immutable-sink-1",
            receipt_signing_key=SINK_KEY,  # noqa: F405
        ).persist(switch_id="switch-1", events=events)
        self.assertEqual(receipt.sink_class, "immutable-object-store")
        self.assertEqual(receipt.object_version, "generation-1")
        self.assertEqual(len(client.calls), 1)
        self.bridge.offnode_sink = ImmutableObjectStoreSink(
            client=client,
            object_prefix="catalog-switch/drain-reclaim",
            sink_id="immutable-sink-1",
            receipt_signing_key=SINK_KEY,  # noqa: F405
        )
        self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
        self.complete_phases()
        self.bridge.execute_semantic_call(
            sequence=1,
            raw_request=RAW_B_REQUEST_1,
            inference=fixed_inference(RAW_B_RESPONSE_1),
        )
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        self.bridge.close_success(
            accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
        )
        gate = self.bridge.qualification_receipt()
        expectation = LedgerExpectation(
            LedgerStage.TARGET_QUALIFIED,
            "switch-1",
            "switch-trace-1",
            "switch-request-1",
            "switch-attempt-1",
            self.bridge.accepted_t0_ns,
            self.runtime_b,
            VALIDATOR_B,  # noqa: F405
            canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
        )
        verifier_args = {
            "ledger_path": self.ledger_path,
            "audit_path": self.audit_path,
            "evidence_root": self.evidence_root,
            "trace": self.trace,
            "validator_runtimes": {VALIDATOR_B.source_sha256: self.validator_b},  # noqa: F405
            "durability_keys": {"immutable-sink-1": SINK_KEY},  # noqa: F405
        }
        with self.assertRaisesRegex(ProofRejected, "cannot be independently read"):
            ExactLedgerReceiptVerifier(**verifier_args).verify(gate, expectation)
        ExactLedgerReceiptVerifier(
            **verifier_args, immutable_object_reader=client
        ).verify(gate, expectation)

    def test_fabricated_hashes_or_missing_canonical_files_never_admit(self) -> None:
        receipt, verifier = self.complete_success()
        forged = replace(receipt, shared_ledger_sha256="f" * 64)
        payload = forged.payload()
        forged = replace(forged, receipt_sha256=canonical_sha256(payload))  # noqa: F405
        with self.assertRaisesRegex(ProofRejected, "shared ledger bytes"):
            verifier.verify(
                forged,
                LedgerExpectation(
                    LedgerStage.TARGET_QUALIFIED,
                    "switch-1",
                    "switch-trace-1",
                    "switch-request-1",
                    "switch-attempt-1",
                    self.bridge.accepted_t0_ns,
                    self.runtime_b,
                    VALIDATOR_B,  # noqa: F405
                    canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
                ),
            )
        self.ledger_path.rename(self.root / "ledger-removed")
        with self.assertRaises(Exception):
            verifier.verify(
                receipt,
                LedgerExpectation(
                    LedgerStage.TARGET_QUALIFIED,
                    "switch-1",
                    "switch-trace-1",
                    "switch-request-1",
                    "switch-attempt-1",
                    self.bridge.accepted_t0_ns,
                    self.runtime_b,
                    VALIDATOR_B,  # noqa: F405
                    canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
                ),
            )

    def test_semantic_mismatch_missing_duplicate_reordered_and_prior_calls_reject(self) -> None:
        with self.subTest("missing-call2"):
            self.bridge.record_launch_reservation(self.reservation)
            self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
            self.complete_phases()
            self.bridge.execute_semantic_call(
                sequence=1,
                raw_request=RAW_B_REQUEST_1,
                inference=fixed_inference(RAW_B_RESPONSE_1),
            )
            with self.assertRaisesRegex(HarnessError, "calls 1 and 2"):
                self.bridge.close_success(
                    accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
                )

        for case in ("duplicate-body", "reordered"):
            with self.subTest(case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                ledger_path = root / "shared.jsonl"
                trace = make_trace(RAW_B_REQUEST_1)  # noqa: F405
                write_acceptance(ledger_path, trace)  # noqa: F405
                bridge = SwitchLedgerBridge(
                    path=ledger_path,
                    audit_path=root / "audit.jsonl",
                    evidence_root=root / "evidence",
                    trace=trace,
                    ledger_id="drain-reclaim-ledger-1",
                    switch_id="switch-1",
                    request_id="switch-request-1",
                    attempt_id="switch-attempt-1",
                    recorder=recorder(),  # noqa: F405
                    validator_runtime=self.validator_b,
                    offnode_sink=FileOffNodeSink(root / "offnode", sink_id="sink", key=SINK_KEY),  # noqa: F405
                )
                bridge.record_launch_reservation(self.reservation)
                bridge.bind_runtime(self.runtime_b, self.launch_receipt)
                self.complete_phases(bridge)
                if case == "reordered":
                    with self.assertRaisesRegex(HarnessError, "cannot precede"):
                        bridge.execute_semantic_call(
                            sequence=2,
                            raw_request=RAW_B_REQUEST_2,
                            inference=fixed_inference(RAW_B_RESPONSE_2),
                        )
                else:
                    bridge.execute_semantic_call(
                        sequence=1,
                        raw_request=RAW_B_REQUEST_1,
                        inference=fixed_inference(RAW_B_RESPONSE_1),
                    )
                    bridge.execute_semantic_call(
                        sequence=2,
                        raw_request=RAW_B_REQUEST_2,
                        inference=fixed_inference(RAW_B_RESPONSE_1),
                    )
                    bridge.close_success(
                        accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
                    )
                    with self.assertRaisesRegex(ProofRejected, "response bodies"):
                        bridge.qualification_receipt()

        with self.subTest("validator-mismatch"):
            with self.assertRaisesRegex(ValueError, "executable source differs"):
                ValidatorRuntime(
                    VALIDATOR_B,  # noqa: F405
                    validator_replay(MODEL_B),  # noqa: F405
                    VALIDATOR_A_SOURCE,  # noqa: F405
                )

    def test_validator_source_authority_tamper_rejects(self) -> None:
        receipt, verifier = self.complete_success()
        calls = [
            event
            for event in AuditChainStore(self.audit_path).load()
            if event["event_type"] == "semantic.call"
        ]
        source_uri = calls[0]["payload"]["validator_source_authority"]["authority"]
        Path(source_uri.removeprefix("file://")).write_bytes(b"changed-validator-source\n")
        with self.assertRaisesRegex(ProofRejected, "byte count/digest"):
            verifier.verify(
                receipt,
                LedgerExpectation(
                    LedgerStage.TARGET_QUALIFIED,
                    "switch-1",
                    "switch-trace-1",
                    "switch-request-1",
                    "switch-attempt-1",
                    self.bridge.accepted_t0_ns,
                    self.runtime_b,
                    VALIDATOR_B,  # noqa: F405
                    canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
                ),
            )

    def test_prior_call_or_restart_is_rejected_by_exact_verifier(self) -> None:
        self.bridge.record_launch_reservation(self.reservation)
        self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
        self.complete_phases()
        self.bridge.audit.append(
            event_id="injected-restart",
            event_type="runtime.restart",
            switch_id="switch-1",
            trace_id="switch-trace-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            payload={"runtime_generation": 2},
        )
        self.bridge.execute_semantic_call(
            sequence=1,
            raw_request=RAW_B_REQUEST_1,
            inference=fixed_inference(RAW_B_RESPONSE_1),
        )
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        self.bridge.close_success(accounting=complete_accounting(), cleanup=no_cleanup())  # noqa: F405
        receipt = self.bridge.qualification_receipt()
        with self.assertRaisesRegex(ProofRejected, "prior semantic call or runtime restart"):
            self.verifier().verify(
                receipt,
                LedgerExpectation(
                    LedgerStage.TARGET_QUALIFIED,
                    "switch-1",
                    "switch-trace-1",
                    "switch-request-1",
                    "switch-attempt-1",
                    self.bridge.accepted_t0_ns,
                    self.runtime_b,
                    VALIDATOR_B,  # noqa: F405
                    canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
                ),
            )

    def test_validator_hash_is_joined_to_terminal_and_exact_replay(self) -> None:
        receipt, verifier = self.complete_success()
        wrong = replace(receipt, validator_sha256=VALIDATOR_A.source_sha256)  # noqa: F405
        wrong = replace(wrong, receipt_sha256=canonical_sha256(wrong.payload()))  # noqa: F405
        with self.assertRaisesRegex(ProofRejected, "binding differs"):
            verifier.verify(
                wrong,
                LedgerExpectation(
                    LedgerStage.TARGET_QUALIFIED,
                    "switch-1",
                    "switch-trace-1",
                    "switch-request-1",
                    "switch-attempt-1",
                    self.bridge.accepted_t0_ns,
                    self.runtime_b,
                    VALIDATOR_B,  # noqa: F405
                    canonical_sha256(asdict(self.launch_receipt)),  # noqa: F405
                ),
            )

    def test_admission_and_seal_each_require_fresh_complete_durable_segment(self) -> None:
        # Build state first so the bridge and state consume the exact same
        # durable reservation and signed launch receipt.
        clock = FakeClock(self.bridge.accepted_t0_ns + 1_000)  # noqa: F405
        machine = DrainReclaimStateMachine(
            InMemoryStateStore(MachineSnapshot.initial(self.authority, GPU_UUID)),  # noqa: F405
            evidence_trust=trust_store(authority=self.authority),  # noqa: F405
            clock_ns=clock,
        )
        fence = machine.claim_controller("controller-1")
        runtime_a = runtime(MODEL_A, 1, operation_id="bootstrap-a", suffix="a", authority=self.authority)  # noqa: F405
        machine.install_serving_a(fence, runtime_a)
        machine.begin_switch(
            fence,
            switch_id="switch-1",
            trace_id="switch-trace-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            target=MODEL_B,  # noqa: F405
            validator=VALIDATOR_B,  # noqa: F405
            accepted_t0_ns=self.bridge.accepted_t0_ns,
            drain_timeout_ns=1_000,
        )
        machine.advance_drain(fence, switch_id="switch-1")
        started = machine.snapshot().transitions[-1].at_ns
        stop, absence, gpu = reclaim_bundle(switch_id="switch-1", target=runtime_a, fence=fence, reclaim_started=started)  # noqa: F405
        machine.record_reclaim(fence, switch_id="switch-1", stop_receipt=stop, absence=absence, gpu_release=gpu)
        state_reservation = machine.begin_start_b(
            fence,
            switch_id="switch-1",
            operation_id="launch-b-op",
            idempotency_key="launch-b-idem",
        )
        # The canonical bridge reservation carries the same generation/op/model;
        # its earlier controller timestamp is audit evidence, not state identity.
        target = runtime(MODEL_B, state_reservation.runtime_generation, operation_id=state_reservation.operation_id, suffix="b", authority=self.authority)  # noqa: F405
        launch_receipt = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="launch-runtime",
            subject_sha256=state_reservation.digest,
            authority=self.authority,
            fence=fence,
            started=state_reservation.reserved_at_ns + 1,
            idempotency_key=state_reservation.idempotency_key,
        )
        clock.advance(100)
        machine.bind_starting_runtime(
            fence,
            switch_id="switch-1",
            runtime=target,
            launch_receipt=launch_receipt,
        )
        self.bridge.record_launch_reservation(state_reservation)
        self.bridge.bind_runtime(target, launch_receipt)
        self.complete_phases()
        self.bridge.execute_semantic_call(
            sequence=1,
            raw_request=RAW_B_REQUEST_1,
            inference=fixed_inference(RAW_B_RESPONSE_1),
        )
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        self.bridge.close_success(accounting=complete_accounting(), cleanup=no_cleanup())  # noqa: F405
        receipt = self.bridge.qualification_receipt()
        verifier = self.verifier()
        machine.ledger_verifier = verifier
        machine.accept_b(fence, switch_id="switch-1", ledger_receipt=receipt)
        self.assertEqual(machine.snapshot().state, SwitchState.SERVING_B)
        with self.assertRaises(ProofRejected):
            machine.seal_switch(fence, switch_id="switch-1", ledger_receipt=receipt)
        sealed = self.bridge.seal_receipt(qualified_receipt=receipt)
        machine.seal_switch(fence, switch_id="switch-1", ledger_receipt=sealed)
        self.assertEqual(machine.snapshot().state, SwitchState.SERVING_A)


class CrashAndFailureTests(LedgerFixture):
    def test_semantic_response_loss_reuses_durable_intent_and_idempotency_key(self) -> None:
        self.bridge.record_launch_reservation(self.reservation)
        self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
        self.complete_phases()
        keys: list[str] = []

        def response_loss_then_recover(_request: bytes, idempotency_key: str) -> bytes:
            keys.append(idempotency_key)
            if len(keys) == 1:
                raise TimeoutError("simulated response loss after dispatch")
            return RAW_B_RESPONSE_1

        with self.assertRaisesRegex(TimeoutError, "response loss"):
            self.bridge.execute_semantic_call(
                sequence=1,
                raw_request=RAW_B_REQUEST_1,
                inference=response_loss_then_recover,
            )
        first_intent = self.bridge._semantic_intents("switch-attempt-1")[0]
        completed = self.bridge.execute_semantic_call(
            sequence=1,
            raw_request=RAW_B_REQUEST_1,
            inference=response_loss_then_recover,
        )
        self.assertEqual(keys, ["switch-attempt-1.semantic-1"] * 2)
        self.assertEqual(
            completed["payload"]["request_started_at_ns"],
            first_intent["payload"]["request_started_at_ns"],
        )
        self.assertEqual(len(self.bridge._semantic_intents("switch-attempt-1")), 1)
        self.assertEqual(len(self.bridge._semantic_calls("switch-attempt-1")), 1)
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        self.bridge.close_success(
            accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
        )
        self.bridge.qualification_receipt()

    def test_failure_recovery_is_idempotent_and_retained_in_denominator(self) -> None:
        self.bridge.record_launch_reservation(self.reservation)
        for phase in ("catalog_selection", "queue", "drain", "gpu_release"):
            self.bridge.start_phase(phase)
            self.bridge.finish_phase(
                phase, outcome="completed", reason="measured before injected failure"
            )
        original = self.bridge._record_accounting
        with patch.object(
            self.bridge,
            "_record_accounting",
            side_effect=RuntimeError("crash-after-terminal"),
        ):
            with self.assertRaisesRegex(RuntimeError, "crash-after-terminal"):
                self.bridge.fail_attempt(
                    failed_phase="runtime_launch",
                    failure_class="backend",
                    reason="ambiguous launch response loss",
                    retryable=True,
                    accounting=complete_accounting(),  # noqa: F405
                    cleanup=no_cleanup(),  # noqa: F405
                )
        self.assertEqual(
            [event["event_type"] for event in load_ledger(self.ledger_path)].count(
                "attempt.failed"
            ),
            1,
        )
        self.bridge._record_accounting = original
        for _ in range(2):
            self.bridge.fail_attempt(
                failed_phase="runtime_launch",
                failure_class="backend",
                reason="ambiguous launch response loss",
                retryable=True,
                accounting=complete_accounting(),  # noqa: F405
                cleanup=no_cleanup(),  # noqa: F405
            )
        types = [event["event_type"] for event in load_ledger(self.ledger_path)]
        self.assertEqual(types.count("attempt.failed"), 1)
        self.assertEqual(types.count("accounting.recorded"), 1)
        self.assertEqual(types.count("cleanup.finished"), 1)
        aggregate = aggregate_ledger(load_ledger(self.ledger_path), self.trace)
        self.assertEqual(aggregate["attempts"]["offered"], 1)
        self.assertEqual(aggregate["attempts"]["failures"], 1)
        receipt = self.bridge.failure_receipt()
        self.verifier().verify(
            receipt,
            LedgerExpectation(
                LedgerStage.TARGET_FAILED,
                "switch-1",
                "switch-trace-1",
                "switch-request-1",
                "switch-attempt-1",
                self.bridge.accepted_t0_ns,
                self.runtime_b,
                VALIDATOR_B,  # noqa: F405
                None,
            ),
        )

    def test_record_success_replay_does_not_duplicate_terminal(self) -> None:
        self.bridge.record_launch_reservation(self.reservation)
        self.bridge.bind_runtime(self.runtime_b, self.launch_receipt)
        self.complete_phases()
        invocations: list[str] = []

        def infer_one(_request: bytes, idempotency_key: str) -> bytes:
            invocations.append(idempotency_key)
            return RAW_B_RESPONSE_1

        for _ in range(2):
            self.bridge.execute_semantic_call(
                sequence=1,
                raw_request=RAW_B_REQUEST_1,
                inference=infer_one,
            )
        self.bridge.execute_semantic_call(
            sequence=2,
            raw_request=RAW_B_REQUEST_2,
            inference=fixed_inference(RAW_B_RESPONSE_2),
        )
        for _ in range(2):
            self.bridge.close_success(
                accounting=complete_accounting(), cleanup=no_cleanup()  # noqa: F405
            )
        types = [event["event_type"] for event in load_ledger(self.ledger_path)]
        self.assertEqual(types.count("response.validated"), 1)
        self.assertEqual(types.count("accounting.recorded"), 1)
        self.assertEqual(types.count("cleanup.finished"), 1)
        self.assertEqual(invocations, ["switch-attempt-1.semantic-1"])


class RollbackTraceTests(LedgerFixture):
    def test_failed_b_and_rollback_use_separate_linked_traces(self) -> None:
        # Prepare state through an ambiguous failed B operation and exact cleanup.
        state_clock = FakeClock(self.bridge.accepted_t0_ns + 1_000)  # noqa: F405
        machine = DrainReclaimStateMachine(
            InMemoryStateStore(MachineSnapshot.initial(self.authority, GPU_UUID)),  # noqa: F405
            evidence_trust=trust_store(authority=self.authority),  # noqa: F405
            clock_ns=state_clock,
        )
        fence = machine.claim_controller("controller-1")
        runtime_a = runtime(MODEL_A, 1, operation_id="bootstrap-a", suffix="a", authority=self.authority)  # noqa: F405
        machine.install_serving_a(fence, runtime_a)
        machine.begin_switch(
            fence,
            switch_id="switch-1",
            trace_id="switch-trace-1",
            request_id="switch-request-1",
            attempt_id="switch-attempt-1",
            target=MODEL_B,  # noqa: F405
            validator=VALIDATOR_B,  # noqa: F405
            accepted_t0_ns=self.bridge.accepted_t0_ns,
            drain_timeout_ns=1_000,
        )
        machine.advance_drain(fence, switch_id="switch-1")
        started = machine.snapshot().transitions[-1].at_ns
        stop, absence, gpu = reclaim_bundle(switch_id="switch-1", target=runtime_a, fence=fence, reclaim_started=started)  # noqa: F405
        machine.record_reclaim(fence, switch_id="switch-1", stop_receipt=stop, absence=absence, gpu_release=gpu)
        reservation = machine.begin_start_b(
            fence,
            switch_id="switch-1",
            operation_id="launch-b-op",
            idempotency_key="launch-b-idem",
        )
        self.bridge.record_launch_reservation(reservation)
        machine.fail_start(fence, switch_id="switch-1", reason="B launch response lost")
        cleanup_started = machine.snapshot().transitions[-1].at_ns
        cleanup = signed_action(switch_id="switch-1", operation="cleanup-launch-operation", subject_sha256=reservation.digest, authority=self.authority, fence=fence, started=cleanup_started + 1)  # noqa: F405
        op_absence = signed_operation_absence(switch_id="switch-1", reservation=reservation, authority=self.authority, observed_at=cleanup_started + 3)  # noqa: F405
        op_gpu = signed_gpu_release(switch_id="switch-1", subject_sha256=reservation.digest, authority=self.authority, absence_at=op_absence.observed_at_ns)  # noqa: F405
        machine.record_ambiguous_launch_cleanup(fence, switch_id="switch-1", cleanup_receipt=cleanup, absence=op_absence, gpu_release=op_gpu)
        machine.mark_failed(fence, switch_id="switch-1", reason="B launch failed")

        self.bridge.fail_attempt(
            failed_phase="runtime_launch",
            failure_class="backend",
            reason="B launch response lost",
            retryable=True,
            accounting=complete_accounting(),  # noqa: F405
            cleanup=no_cleanup(),  # noqa: F405
        )
        failure_receipt = self.bridge.failure_receipt()
        validator_a = ValidatorRuntime(  # noqa: F405
            VALIDATOR_A, validator_replay(MODEL_A), VALIDATOR_A_SOURCE
        )
        recovery_path = self.root / "rollback-shared.jsonl"
        recovery_trace = make_trace(  # noqa: F405
            RAW_A_REQUEST_1,
            model=MODEL_A,  # noqa: F405
            occupant=MODEL_B,  # noqa: F405
            trace_id="rollback-trace-1",
            request_id="rollback-request-1",
            attempt_id="rollback-attempt-1",
        )
        write_acceptance(  # noqa: F405
            recovery_path,
            recovery_trace,
            ledger_id="rollback-ledger-1",
        )
        recovery_t0 = load_ledger(recovery_path)[0]["observed_monotonic_ns"]
        verifier = self.verifier(
            validators={
                VALIDATOR_B.source_sha256: self.validator_b,  # noqa: F405
                VALIDATOR_A.source_sha256: validator_a,  # noqa: F405
            },
            recovery_ledgers={"rollback-trace-1": (recovery_path, recovery_trace)},
        )
        machine.ledger_verifier = verifier
        state_clock.value = recovery_t0 + 100
        rollback_reservation = machine.begin_rollback(
            fence,
            switch_id="switch-1",
            failure_receipt=failure_receipt,
            recovery_trace_id="rollback-trace-1",
            recovery_request_id="rollback-request-1",
            recovery_attempt_id="rollback-attempt-1",
            recovery_accepted_t0_ns=recovery_t0,
            recovery_validator=VALIDATOR_A,  # noqa: F405
            operation_id="rollback-a-op",
            idempotency_key="rollback-a-idem",
        )
        self.bridge.begin_recovery(
            failure_receipt=failure_receipt,
            path=recovery_path,
            trace=recovery_trace,
            ledger_id="rollback-ledger-1",
            recorder=recorder(),  # noqa: F405
            trace_id="rollback-trace-1",
            request_id="rollback-request-1",
            attempt_id="rollback-attempt-1",
            model_id=MODEL_A.model_id,  # noqa: F405
            model_version=MODEL_A.model_version,  # noqa: F405
            artifact_sha256=MODEL_A.artifact_sha256,  # noqa: F405
            validator_runtime=validator_a,
        )
        self.bridge.record_recovery_reservation(rollback_reservation)
        rollback_runtime = runtime(MODEL_A, rollback_reservation.runtime_generation, operation_id=rollback_reservation.operation_id, suffix="rollback-a", authority=self.authority)  # noqa: F405
        rollback_launch = signed_action(  # noqa: F405
            switch_id="switch-1",
            operation="launch-runtime",
            subject_sha256=rollback_reservation.digest,
            authority=self.authority,
            fence=fence,
            started=rollback_reservation.reserved_at_ns + 1,
            idempotency_key=rollback_reservation.idempotency_key,
        )
        state_clock.advance(100)
        machine.bind_starting_runtime(
            fence,
            switch_id="switch-1",
            runtime=rollback_runtime,
            launch_receipt=rollback_launch,
        )
        self.bridge.bind_recovery_runtime(rollback_runtime, rollback_launch)
        for phase in (
            "catalog_selection",
            "queue",
            "drain",
            "gpu_release",
            "placement",
            "image_readiness",
            "artifact_readiness",
            "storage_readiness",
            "cache_readiness",
            "runtime_launch",
            "service_readiness",
            "inference",
        ):
            self.bridge.start_recovery_phase(phase)
            self.bridge.finish_recovery_phase(
                phase,
                outcome="completed",
                reason="linked rollback recovery evidence",
            )
        self.bridge.execute_recovery_semantic_call(
            sequence=1,
            raw_request=RAW_A_REQUEST_1,
            inference=fixed_inference(RAW_A_RESPONSE_1),
        )
        self.bridge.execute_recovery_semantic_call(
            sequence=2,
            raw_request=RAW_A_REQUEST_2,
            inference=fixed_inference(RAW_A_RESPONSE_2),
        )
        self.bridge.close_recovery_success(
            accounting=complete_accounting(),  # noqa: F405
            cleanup=no_cleanup(),  # noqa: F405
        )
        rollback_receipt = self.bridge.rollback_qualification_receipt()
        machine.accept_rollback(fence, switch_id="switch-1", ledger_receipt=rollback_receipt)
        self.assertEqual(machine.snapshot().state, SwitchState.ROLLBACK_SERVING)
        sealed = self.bridge.seal_receipt(qualified_receipt=rollback_receipt)
        machine.seal_switch(fence, switch_id="switch-1", ledger_receipt=sealed)
        self.assertEqual(machine.snapshot().state, SwitchState.SERVING_A)
        audit = AuditChainStore(self.audit_path).load()
        failure = [event for event in audit if event["event_type"] == "target.failure.terminal"]
        recovery = [event for event in audit if event["event_type"] == "recovery.started"]
        self.assertEqual(len(failure), 1)
        self.assertEqual(len(recovery), 1)
        self.assertEqual(
            recovery[0]["payload"]["recovery"]["predecessor_failure_receipt_sha256"],
            failure_receipt.receipt_sha256,
        )
        recovery_shared = load_ledger(recovery_path)
        self.assertEqual(recovery_shared[0]["event_type"], "request.accepted")
        self.assertEqual(
            sum(event["event_type"] == "response.validated" for event in recovery_shared),
            1,
        )
        self.assertEqual(
            rollback_receipt.accepted_t0_ns,
            recovery_shared[0]["observed_monotonic_ns"],
        )


if __name__ == "__main__":
    unittest.main()
