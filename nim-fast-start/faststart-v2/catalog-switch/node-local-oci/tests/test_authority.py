"""Command-authority adversaries: forgery, replay, fences, occupancy, chain."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import helpers
from node_local_oci import contracts
from node_local_oci.errors import Refusal
from node_local_oci.journal import (FenceStore, NonceStore, OccupancyLock,
                                    ReceiptJournal)
from node_local_oci.keys import KeyRing, generate_keypair, sign


class KeySeparation(unittest.TestCase):
    def test_role_collision_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = helpers.make_keys(Path(tmp))
            agent_dir = env["agent_dir"]
            # Overwrite the oracle public key with the agent's own public key:
            # one keypair wearing two hats must refuse at startup.
            (agent_dir / "oracle.pub").write_bytes(
                (agent_dir / "agent.pub").read_bytes())
            with self.assertRaises(Refusal) as caught:
                KeyRing(agent_dir)
            self.assertEqual(caught.exception.code, "keys.role-collision")

    def test_agent_cannot_sign_foreign_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = helpers.make_keys(Path(tmp))
            ring = KeyRing(env["agent_dir"])
            body = {"schema": contracts.VERDICT_SCHEMA, "x": 1}
            forged = dict(body)
            forged["signature"] = sign(env["privates"]["agent"], "oracle",
                                       contracts.VERDICT_SCHEMA, body)
            with self.assertRaises(Refusal) as caught:
                ring.verify_role("oracle", contracts.VERDICT_SCHEMA, forged)
            self.assertEqual(caught.exception.code, "keys.signature-invalid")

    def test_signature_tamper_and_unsigned_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = helpers.make_keys(Path(tmp))
            ring = KeyRing(env["agent_dir"])
            body = {"schema": contracts.POLICY_SCHEMA, "x": 1}
            good = helpers.sign_envelope(env["privates"]["controller"],
                                         "controller", contracts.POLICY_SCHEMA, body)
            ring.verify_role("controller", contracts.POLICY_SCHEMA, good)
            tampered = dict(good)
            tampered["x"] = 2
            with self.assertRaises(Refusal):
                ring.verify_role("controller", contracts.POLICY_SCHEMA, tampered)
            unsigned = {"schema": contracts.POLICY_SCHEMA, "x": 1}
            with self.assertRaises(Refusal) as caught:
                ring.verify_role("controller", contracts.POLICY_SCHEMA, unsigned)
            self.assertEqual(caught.exception.code, "keys.envelope-unsigned")


class NonceAndFence(unittest.TestCase):
    def test_nonce_replay_refused_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            nonce = "ab" * 32
            store = NonceStore(Path(tmp) / "nonces")
            store.burn(nonce, {"command_id": "c1"})
            # Same process replay
            with self.assertRaises(Refusal) as caught:
                store.burn(nonce, {"command_id": "c1"})
            self.assertEqual(caught.exception.code, "nonce.replay")
            # Fresh instance over the same durable state = process restart
            restarted = NonceStore(Path(tmp) / "nonces")
            with self.assertRaises(Refusal) as caught:
                restarted.burn(nonce, {"command_id": "c1"})
            self.assertEqual(caught.exception.code, "nonce.replay")

    def test_fence_regression_and_equal_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            fence = FenceStore(Path(tmp) / "fence.json")
            fence.advance(5, {"command_id": "c1"})
            for stale in (5, 4, 1):
                with self.assertRaises(Refusal) as caught:
                    fence.advance(stale, {"command_id": "cX"})
                self.assertEqual(caught.exception.code, "fence.regression")
            restarted = FenceStore(Path(tmp) / "fence.json")
            self.assertEqual(restarted.current(), 5)
            restarted.advance(6, {"command_id": "c2"})


class Occupancy(unittest.TestCase):
    def test_second_occupant_refused_even_with_valid_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = OccupancyLock(Path(tmp) / "occupancy")
            lock.acquire("nlo-switch-1", "boot-1")
            # A second, otherwise fully authorized launch must refuse:
            with self.assertRaises(Refusal) as caught:
                lock.acquire("nlo-switch-2", "boot-1")
            self.assertEqual(caught.exception.code, "occupancy.held")
            # And it must persist across restart.
            restarted = OccupancyLock(Path(tmp) / "occupancy")
            with self.assertRaises(Refusal):
                restarted.acquire("nlo-switch-3", "boot-1")

    def test_release_requires_owner_and_absence_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = OccupancyLock(Path(tmp) / "occupancy")
            lock.acquire("nlo-switch-1", "boot-1")
            with self.assertRaises(Refusal) as caught:
                lock.release("nlo-switch-2", "0" * 64)
            self.assertEqual(caught.exception.code, "occupancy.foreign-release")
            with self.assertRaises(Refusal) as caught:
                lock.release("nlo-switch-1", "short")
            self.assertEqual(caught.exception.code, "occupancy.release-evidence")
            lock.release("nlo-switch-1", "1" * 64)
            self.assertIsNone(lock.holder())


class JournalChain(unittest.TestCase):
    def test_chain_tamper_truncation_and_reorder_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipts.jsonl"
            journal = ReceiptJournal(path)
            journal.append({"n": 1})
            journal.append({"n": 2})
            journal.append({"n": 3})
            lines = path.read_text().splitlines()
            # Tamper a middle entry
            doctored = json.loads(lines[1])
            doctored["entry"]["n"] = 99
            bad = [lines[0], json.dumps(doctored, sort_keys=True,
                                        separators=(",", ":")), lines[2]]
            path.write_text("\n".join(bad) + "\n")
            with self.assertRaises(Refusal):
                ReceiptJournal(path)
            # Reorder
            path.write_text("\n".join([lines[1], lines[0], lines[2]]) + "\n")
            with self.assertRaises(Refusal):
                ReceiptJournal(path)
            # Truncated tail (no trailing newline)
            path.write_text("\n".join(lines)[:-5])
            with self.assertRaises(Refusal):
                ReceiptJournal(path)


class BundleCardinality(unittest.TestCase):
    def _valid_parts(self, tmp: Path):
        bin_dir = helpers.make_stub_bins(tmp)
        artifact = tmp / "artifact.bin"
        artifact.write_bytes(b"artifact-bytes")
        validator = helpers.write_validator(tmp)
        policy_body = helpers.make_policy_body(bin_dir=bin_dir,
                                               artifact_path=artifact,
                                               port=18080,
                                               validator_path=validator)
        env = helpers.make_keys(tmp)
        policy_env = helpers.sign_envelope(env["privates"]["controller"],
                                           "controller", contracts.POLICY_SCHEMA,
                                           policy_body)
        requests = [
            {"attempt_id": "att-1", "request_id": "req-1",
             "payload_sha256": "aa" * 32, "input_bytes": 10,
             "scenario": "a_to_b_local"},
            {"attempt_id": "att-2", "request_id": "req-2",
             "payload_sha256": "bb" * 32, "input_bytes": 11,
             "scenario": "same_model_hot"},
        ]
        bundle = helpers.make_bundle_body(
            policy_envelope=policy_env, trace_id="tr-1", ledger_id="led-1",
            switch_uid="sw-1", fence=1, nonce="cc" * 32, requests=requests,
            prior_occupant=None)
        policy_sha = bundle["policy_sha256"]
        return contracts.validate_policy(policy_body), bundle, policy_sha

    def test_zero_one_three_and_duplicate_requests_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy, bundle, policy_sha = self._valid_parts(Path(tmp))
            contracts.validate_bundle(dict(bundle), policy, policy_sha)
            for bad_requests, code in [
                ([], "contract.bundle-cardinality"),
                (bundle["requests"][:1], "contract.bundle-cardinality"),
                (bundle["requests"] + [dict(bundle["requests"][0],
                                            attempt_id="att-3",
                                            request_id="req-3")],
                 "contract.bundle-cardinality"),
                ([bundle["requests"][0], dict(bundle["requests"][1],
                                              attempt_id="att-1")],
                 "contract.bundle-attempt-dup"),
                ([bundle["requests"][0], dict(bundle["requests"][1],
                                              payload_sha256="aa" * 32)],
                 "contract.bundle-payload-dup"),
            ]:
                candidate = dict(bundle)
                candidate["requests"] = bad_requests
                with self.assertRaises(Refusal) as caught:
                    contracts.validate_bundle(candidate, policy, policy_sha)
                self.assertEqual(caught.exception.code, code, code)

    def test_policy_binding_and_deadline_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy, bundle, policy_sha = self._valid_parts(Path(tmp))
            wrong = dict(bundle)
            wrong["policy_sha256"] = "9" * 64
            with self.assertRaises(Refusal) as caught:
                contracts.validate_bundle(wrong, policy, policy_sha)
            self.assertEqual(caught.exception.code, "contract.bundle-policy-binding")
            swapped = dict(bundle)
            swapped["issued_utc"], swapped["deadline_utc"] = (
                bundle["deadline_utc"], bundle["issued_utc"])
            with self.assertRaises(Refusal) as caught:
                contracts.validate_bundle(swapped, policy, policy_sha)
            self.assertEqual(caught.exception.code, "contract.bundle-deadline-order")

    def test_foreign_node_identity_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy, bundle, policy_sha = self._valid_parts(Path(tmp))
            foreign = dict(bundle)
            foreign["node"] = {"instance_id": "someone-else",
                               "boot_id": policy["node"]["boot_id"]}
            with self.assertRaises(Refusal) as caught:
                contracts.validate_bundle(foreign, policy, policy_sha)
            self.assertEqual(caught.exception.code, "contract.bundle-node-instance")


if __name__ == "__main__":
    unittest.main()
