"""T0 admission and oracle adversaries against real shared-harness ledgers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import helpers
from external_recorder import ExternalRecorder, build_trace
from node_local_oci import admission, binding, contracts
from node_local_oci.errors import Refusal
from node_local_oci.journal import canonical_json
from node_local_oci.keys import KeyRing
from node_local_oci.oracle import verify_verdict
from oracle_service import OracleService


class _Env:
    """A real trace + shared ledger + accepted event + authorization."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.harness = binding.import_shared_harness()
        self.keys_env = helpers.make_keys(tmp)
        self.ring = KeyRing(self.keys_env["agent_dir"])
        self.bin_dir = helpers.make_stub_bins(tmp)
        self.artifact = tmp / "artifact.bin"
        self.artifact.write_bytes(b"stub artifact bytes")
        self.validator = helpers.write_validator(tmp)
        self.payload_1 = json.dumps({"prompt": "fold protein one"}).encode()
        self.payload_2 = json.dumps({"prompt": "fold protein two"}).encode()

        policy_body = helpers.make_policy_body(
            bin_dir=self.bin_dir, artifact_path=self.artifact, port=18091,
            validator_path=self.validator)
        self.policy_envelope = helpers.sign_envelope(
            self.keys_env["privates"]["controller"], "controller",
            contracts.POLICY_SCHEMA, policy_body)
        self.policy = contracts.validate_policy(policy_body)
        self.policy_sha256 = helpers.sha256_bytes(
            canonical_json(self.policy_envelope).encode())

        requests = helpers.make_trace_requests(
            payload_1=self.payload_1, payload_2=self.payload_2,
            artifact_sha256=helpers.sha256_file(self.artifact))
        self.trace = build_trace(trace_id="nlo-t0-test-trace",
                                 catalog={"models": ["stub-model"]},
                                 requests=requests)
        self.exchange = tmp / "exchange"
        self.ledger_path = tmp / "ledger.jsonl"
        (self.keys_env["authority_dir"] / "recorder.key")
        self.recorder = ExternalRecorder(
            recorder_key_path=self.keys_env["authority_dir"] / "recorder.key",
            ledger_path=self.ledger_path, ledger_id="nlo-t0-test-ledger",
            trace=self.trace, exchange_dir=self.exchange,
            recorder_id="nlo-test-external-recorder")
        self.container_id = "nlo-sw-t0-b"
        self.environment = helpers.make_environment(
            policy_sha256=self.policy_sha256, code_revision=helpers.git_head())
        self.recorder.accept(self.trace["requests"][0], payload=self.payload_1,
                             environment=self.environment,
                             ownership=helpers.make_ownership(self.container_id))
        self.bundle = helpers.make_bundle_body(
            policy_envelope=self.policy_envelope,
            trace_id=self.trace["trace_id"], ledger_id="nlo-t0-test-ledger",
            switch_uid="sw-t0", fence=1, nonce="dd" * 32,
            requests=[
                {"attempt_id": requests[0]["attempt_id"],
                 "request_id": requests[0]["request_id"],
                 "payload_sha256": helpers.sha256_bytes(self.payload_1),
                 "input_bytes": len(self.payload_1),
                 "scenario": "a_to_b_local"},
                {"attempt_id": requests[1]["attempt_id"],
                 "request_id": requests[1]["request_id"],
                 "payload_sha256": helpers.sha256_bytes(self.payload_2),
                 "input_bytes": len(self.payload_2),
                 "scenario": "same_model_hot"},
            ],
            prior_occupant={"model_id": "prior-model",
                            "model_version": "prior-1.0.0",
                            "container_id": "nlo-prior-a"})
        contracts.validate_bundle(self.bundle, self.policy, self.policy_sha256)
        auth_path = self.exchange / f"authorization-{requests[0]['attempt_id']}.json"
        envelope = json.loads(auth_path.read_text())
        self.authorization = self.ring.verify_role(
            "recorder", contracts.AUTHORIZATION_SCHEMA, envelope)
        contracts.validate_authorization(self.authorization)


class T0Admission(unittest.TestCase):
    def test_valid_durable_t0_admits(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            result = admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                         env.authorization, env.bundle,
                                         env.bundle["requests"][0], env.policy)
            self.assertEqual(result["ledger_line_number"], 1)

    def test_agent_key_cannot_sign_an_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            forged = helpers.sign_envelope(env.keys_env["privates"]["agent"],
                                           "recorder",
                                           contracts.AUTHORIZATION_SCHEMA,
                                           env.authorization)
            with self.assertRaises(Refusal) as caught:
                env.ring.verify_role("recorder", contracts.AUTHORIZATION_SCHEMA,
                                     forged)
            self.assertEqual(caught.exception.code, "keys.signature-invalid")

    def test_tampered_ledger_line_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            raw = env.ledger_path.read_bytes()
            self.assertIn(b"a_to_b_local", raw)
            env.ledger_path.write_bytes(raw.replace(b"a_to_b_local",
                                                    b"a_to_b_locaX"))
            with self.assertRaises(Refusal) as caught:
                admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                    env.authorization, env.bundle,
                                    env.bundle["requests"][0], env.policy)
            self.assertIn(caught.exception.code,
                          ("admission.t0-line-hash", "admission.ledger-tail"))

    def test_in_memory_only_ledger_is_not_durable_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            env.ledger_path.unlink()
            with self.assertRaises(Refusal) as caught:
                admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                    env.authorization, env.bundle,
                                    env.bundle["requests"][0], env.policy)
            self.assertEqual(caught.exception.code, "admission.ledger-missing")

    def test_forged_model_input_and_artifact_bindings_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            base = env.bundle["requests"][0]
            for mutation, code in [
                ({"payload_sha256": "9" * 64}, "admission.t0-input-hash"),
                ({"input_bytes": 1}, "admission.t0-input-bytes"),
                ({"attempt_id": "nlo-e2e-attempt-000002"}, "admission.t0-attempt"),
            ]:
                with self.assertRaises(Refusal) as caught:
                    admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                        env.authorization, env.bundle,
                                        dict(base, **mutation), env.policy)
                self.assertEqual(caught.exception.code, code, code)

    def test_policy_pin_drift_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            doctored = json.loads(json.dumps(env.policy))
            doctored["models"]["stub-model"]["artifact_sha256"] = "8" * 64
            with self.assertRaises(Refusal) as caught:
                admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                    env.authorization, env.bundle,
                                    env.bundle["requests"][0], doctored)
            self.assertEqual(caught.exception.code, "admission.t0-artifact-hash")

    def test_acceptance_outside_command_window_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            stale = dict(env.bundle)
            stale["issued_utc"] = helpers.utc_in(3600)
            stale["deadline_utc"] = helpers.utc_in(7200)
            with self.assertRaises(Refusal) as caught:
                admission.verify_t0(env.harness, env.trace, env.ledger_path,
                                    env.authorization, stale,
                                    env.bundle["requests"][0], env.policy)
            self.assertEqual(caught.exception.code, "admission.t0-window")

    def test_wrong_boot_id_refuses_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            doctored = json.loads(json.dumps(env.policy))
            doctored["node"]["boot_id"] = "11111111-2222-4333-8444-555555555555"
            from node_local_oci.execute import PinnedBinaries
            with self.assertRaises(Refusal) as caught:
                admission.verify_node_identity(doctored, PinnedBinaries(doctored))
            self.assertEqual(caught.exception.code, "admission.boot-id")

    def test_wrong_storage_identity_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            doctored = json.loads(json.dumps(env.policy))
            doctored["storage"]["fs_uuid"] = "00000000-dead-beef-0000-000000000000"
            with self.assertRaises(Refusal) as caught:
                admission.verify_storage(doctored)
            self.assertEqual(caught.exception.code, "admission.storage-uuid")

    def test_artifact_drift_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _Env(Path(tmp))
            env.artifact.write_bytes(b"different artifact bytes")
            with self.assertRaises(Refusal) as caught:
                admission.verify_artifact(env.policy, "stub-model")
            self.assertEqual(caught.exception.code, "admission.artifact-hash")


class OracleRules(unittest.TestCase):
    def _verdict_env(self, tmp: Path):
        env = _Env(tmp)
        response_path = tmp / "response.bin"
        response_path.write_bytes(json.dumps({
            "model": "stub",
            "payload_sha256": helpers.sha256_bytes(env.payload_1),
            "result": "prediction-abcdef0123456789"}).encode())
        service = OracleService(
            oracle_key_path=env.keys_env["authority_dir"] / "oracle.key",
            validator_source=env.validator,
            validator_id="stub-validator-v1",
            exchange_dir=env.exchange)
        request = {
            "schema": "catalog-switch/nlo-validation-request/v1",
            "switch_uid": env.bundle["switch_uid"],
            "attempt_id": env.bundle["requests"][0]["attempt_id"],
            "model_id": "stub-model",
            "model_version": "stub-1.0.0",
            "request_payload_sha256": helpers.sha256_bytes(env.payload_1),
            "response_path": str(response_path),
            "response_sha256": helpers.sha256_file(response_path),
            "response_bytes": response_path.stat().st_size,
        }
        request_path = env.exchange / "validation-request-x.json"
        request_path.write_text(json.dumps(request))
        verdict_path = service.answer(request_path)
        envelope = json.loads(verdict_path.read_text())
        return env, response_path, envelope

    def test_pinned_oracle_verdict_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, response_path, envelope = self._verdict_env(Path(tmp))
            verdict = verify_verdict(
                env.ring, envelope, policy=env.policy, bundle=env.bundle,
                attempt_id=env.bundle["requests"][0]["attempt_id"],
                payload_sha256=helpers.sha256_bytes(env.payload_1),
                response_path=response_path)
            self.assertIs(verdict["semantically_valid"], True)

    def test_echo_response_is_never_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            env = _Env(base)
            echo_path = base / "echo.bin"
            echo_path.write_bytes(env.payload_1)
            service = OracleService(
                oracle_key_path=env.keys_env["authority_dir"] / "oracle.key",
                validator_source=env.validator,
                validator_id="stub-validator-v1", exchange_dir=env.exchange)
            request = {
                "schema": "catalog-switch/nlo-validation-request/v1",
                "switch_uid": env.bundle["switch_uid"],
                "attempt_id": env.bundle["requests"][0]["attempt_id"],
                "model_id": "stub-model", "model_version": "stub-1.0.0",
                "request_payload_sha256": helpers.sha256_bytes(env.payload_1),
                "response_path": str(echo_path),
                "response_sha256": helpers.sha256_file(echo_path),
                "response_bytes": echo_path.stat().st_size,
            }
            request_path = env.exchange / "validation-request-echo.json"
            request_path.write_text(json.dumps(request))
            verdict_path = service.answer(request_path)
            envelope = json.loads(verdict_path.read_text())
            # Even before agent-side checks, the oracle refused semantically.
            self.assertIs(envelope["semantically_valid"], False)
            # And the agent-side contract refuses the echo shape structurally.
            with self.assertRaises(Refusal):
                verify_verdict(env.ring, envelope, policy=env.policy,
                               bundle=env.bundle,
                               attempt_id=env.bundle["requests"][0]["attempt_id"],
                               payload_sha256=helpers.sha256_bytes(env.payload_1),
                               response_path=echo_path)

    def test_self_signed_verdict_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, response_path, envelope = self._verdict_env(Path(tmp))
            body = {k: v for k, v in envelope.items() if k != "signature"}
            for forger in ("agent", "controller", "recorder"):
                forged = helpers.sign_envelope(env.keys_env["privates"][forger],
                                               "oracle", contracts.VERDICT_SCHEMA,
                                               body)
                with self.assertRaises(Refusal) as caught:
                    verify_verdict(env.ring, forged, policy=env.policy,
                                   bundle=env.bundle,
                                   attempt_id=env.bundle["requests"][0]["attempt_id"],
                                   payload_sha256=helpers.sha256_bytes(env.payload_1),
                                   response_path=response_path)
                self.assertEqual(caught.exception.code, "keys.signature-invalid")

    def test_verdict_bound_to_response_bytes_and_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, response_path, envelope = self._verdict_env(Path(tmp))
            response_path.write_bytes(response_path.read_bytes() + b" ")
            with self.assertRaises(Refusal) as caught:
                verify_verdict(env.ring, envelope, policy=env.policy,
                               bundle=env.bundle,
                               attempt_id=env.bundle["requests"][0]["attempt_id"],
                               payload_sha256=helpers.sha256_bytes(env.payload_1),
                               response_path=response_path)
            self.assertIn(caught.exception.code,
                          ("oracle.response-hash", "oracle.response-bytes"))
            # replay against the other attempt refuses
            with self.assertRaises(Refusal) as caught:
                verify_verdict(env.ring, envelope, policy=env.policy,
                               bundle=env.bundle,
                               attempt_id=env.bundle["requests"][1]["attempt_id"],
                               payload_sha256=helpers.sha256_bytes(env.payload_2),
                               response_path=response_path)
            self.assertEqual(caught.exception.code, "oracle.attempt")

    def test_validator_pin_mismatch_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            env, response_path, envelope = self._verdict_env(Path(tmp))
            doctored_policy = json.loads(json.dumps(env.policy))
            doctored_policy["oracle"]["validator_sha256"] = "7" * 64
            with self.assertRaises(Refusal) as caught:
                verify_verdict(env.ring, envelope, policy=doctored_policy,
                               bundle=env.bundle,
                               attempt_id=env.bundle["requests"][0]["attempt_id"],
                               payload_sha256=helpers.sha256_bytes(env.payload_1),
                               response_path=response_path)
            self.assertEqual(caught.exception.code, "oracle.validator-hash")


if __name__ == "__main__":
    unittest.main()
