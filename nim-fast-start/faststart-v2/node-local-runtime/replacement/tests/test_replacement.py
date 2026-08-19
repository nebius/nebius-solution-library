from __future__ import annotations

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from performance.request_slo import harness
from node_runtime.audit import AuditChain
from replacement.external_t0 import ExternalT0Recorder
from replacement.runtime import (
    BoundAdmission,
    DeterministicReplacementBackend,
    LeaseGuard,
    ReplacementSession,
    RuntimeFailure,
    _mac,
)
from tests.helpers import PAYLOAD, ARTIFACT_SHA, checkpoint_environment, environment, target, precondition


def cohort() -> dict:
    requests = []
    for index, scenario in enumerate(("a_to_b_local", "same_model_hot")):
        requests.append({
            "sequence": index,
            "request_id": f"replacement-request-{index}",
            "attempt_id": f"replacement-attempt-{index}",
            "offered_at_offset_ms": index,
            "scenario": scenario,
            "target": target(),
            "input": {"workload_id": "replacement", "input_id": f"input-{index}", "payload_sha256": hashlib.sha256(PAYLOAD).hexdigest(), "input_bytes": len(PAYLOAD)},
            "precondition": precondition(scenario),
        })
    trace = {"schema": harness.TRACE_SCHEMA, "trace_id": "replacement-trace", "distribution": "adversarial", "seed": 2407, "catalog_sha256": "8" * 64, "request_count": 2, "scenario_labels": list(harness.SCENARIOS), "requests": requests}
    trace["trace_sha256"] = harness.canonical_sha256(trace)
    return harness.validate_trace(trace)


class ReplacementTests(unittest.TestCase):
    def make(self, *, snapshot_refused=False, semantic_false_index=None, accept=True):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        trace = cohort()
        ledger, audit_path = root / "ledger.jsonl", root / "audit.jsonl"
        ext = ExternalT0Recorder(ledger, audit_path, trace)
        own = {"owner_task_id": "catalog-switch-node-local-runtime", "resource_prefix": "mlsp-replacement", "dedicated": True, "cleanup_required": False, "resources": []}
        env, cenv = environment(), checkpoint_environment()
        if accept:
            ext.accept(0, environment=env, ownership=own)
            ext.accept(1, environment=env, ownership=own)
        env_sha, cenv_sha = harness.canonical_sha256(env), harness.canonical_sha256(cenv)
        own_sha = harness.canonical_sha256(own)
        admission = BoundAdmission(b"r" * 32, policy_sha256="f" * 64)
        commands = [admission.sign(req, nonce=f"n-{i}", instance_id="instance-1", boot_id="boot-1", lease_id="lease-1", owner_task_id=own["owner_task_id"], ownership_sha256=own_sha, environment_sha256=env_sha, checkpoint_environment_sha256=cenv_sha, deadline_ns=10**30, launch_mode="snapshot") for i, req in enumerate(trace["requests"])]
        checkpoint = b"replacement-checkpoint"
        unsigned = {"checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(), "artifact_sha256": ARTIFACT_SHA, "environment_sha256": env_sha, "capture_source": "golden-pre-tenant-traffic"}
        binding = {**unsigned, "signature": _mac(admission.key, unsigned)}
        session = ReplacementSession(trace=trace, ledger=ledger, audit=ext.audit, recorder=ext.recorder, admission=admission, lease=LeaseGuard(root / "lease.lock"), instance_id="instance-1", boot_id="boot-1", lease_id="lease-1", owner_task_id=own["owner_task_id"], ownership_sha256=own_sha, environment_sha256=env_sha, checkpoint_environment_sha256=cenv_sha)
        return tmp, session, commands, [PAYLOAD, PAYLOAD], checkpoint, binding, root

    def test_two_validated_requests_and_exact_cleanup(self):
        tmp, session, commands, payloads, checkpoint, binding, _ = self.make()
        try:
            backend = DeterministicReplacementBackend()
            result = session.run(commands=commands, payloads=payloads, backend=backend, checkpoint_bytes=checkpoint, checkpoint_binding=binding, resource_ids=["vm-1", "disk-1"])
            self.assertEqual([item["success"] for item in result["results"]], [True, True])
            self.assertEqual((backend.start_count, backend.infer_count, backend.cleanup_count), (1, 2, 1))
            events = harness.load_ledger(session.ledger)
            self.assertEqual(sum(e["event_type"] == "request.accepted" for e in events), 2)
            self.assertEqual(sum(e["event_type"] == "response.validated" for e in events), 2)
        finally:
            tmp.cleanup()

    def test_snapshot_refusal_falls_back_once(self):
        tmp, session, commands, payloads, checkpoint, binding, _ = self.make(snapshot_refused=True)
        try:
            backend = DeterministicReplacementBackend(snapshot_refused=True)
            result = session.run(commands=commands, payloads=payloads, backend=backend, checkpoint_bytes=checkpoint, checkpoint_binding=binding, resource_ids=["vm-1"])
            self.assertEqual(result["launch_mode"], "conventional-fallback")
            self.assertEqual(backend.start_count, 1)
        finally:
            tmp.cleanup()

    def test_denied_contender_cannot_cleanup_owner(self):
        tmp, session, commands, payloads, checkpoint, binding, root = self.make()
        owner = LeaseGuard(root / "lease.lock")
        self.assertTrue(owner.acquire("active-owner"))
        backend = DeterministicReplacementBackend()
        try:
            with self.assertRaises(RuntimeFailure):
                session.run(commands=commands, payloads=payloads, backend=backend, checkpoint_bytes=checkpoint, checkpoint_binding=binding, resource_ids=["vm-1"])
            self.assertEqual(backend.cleanup_count, 0)
            self.assertTrue(owner.owned)
        finally:
            owner.release_if_owned()
            tmp.cleanup()

    def test_missing_external_t0_is_rejected(self):
        tmp, session, commands, payloads, checkpoint, binding, _ = self.make(accept=False)
        try:
            with self.assertRaises(RuntimeFailure):
                session.run(commands=commands, payloads=payloads, backend=DeterministicReplacementBackend(), checkpoint_bytes=checkpoint, checkpoint_binding=binding, resource_ids=[])
        finally:
            tmp.cleanup()

    def test_semantic_false_is_not_success(self):
        tmp, session, commands, payloads, checkpoint, binding, _ = self.make(semantic_false_index=1)
        try:
            result = session.run(commands=commands, payloads=payloads, backend=DeterministicReplacementBackend(semantic_false_index=1), checkpoint_bytes=checkpoint, checkpoint_binding=binding, resource_ids=[])
            self.assertEqual([item["success"] for item in result["results"]], [True, False])
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
