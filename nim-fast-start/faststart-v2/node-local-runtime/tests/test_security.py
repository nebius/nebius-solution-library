from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from node_runtime.security import (
    AdmissionError,
    AdmissionPolicy,
    CommandAuthenticator,
    NonceJournal,
    verify_checkpoint_binding,
)

from .helpers import (
    ARTIFACT_SHA,
    AUTH_KEY,
    CHECKPOINT_KEY,
    MODEL_B,
    PROFILES,
    VERSION_B,
    binding,
    checkpoint_environment,
    target,
    trace,
)


class CheckpointBindingTests(unittest.TestCase):
    def test_exact_signed_encrypted_golden_binding_passes(self) -> None:
        receipt = verify_checkpoint_binding(
            binding(),
            CHECKPOINT_KEY,
            target=target(),
            environment=checkpoint_environment(),
            expected_profiles=PROFILES,
        )
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["capture_source"], "golden-pre-tenant-traffic")

    def test_every_environment_identity_mismatch_is_named_and_refused(self) -> None:
        mapping = {
            "driver_version": "wrong-driver",
            "runtime_version": "wrong-runtime",
            "gpu_topology_sha256": "f" * 64,
            "artifact_sha256": "e" * 64,
        }
        for field, value in mapping.items():
            with self.subTest(field=field):
                candidate = target() if field == "artifact_sha256" else checkpoint_environment()
                candidate[field] = value
                kwargs = {
                    "target": candidate if field == "artifact_sha256" else target(),
                    "environment": checkpoint_environment() if field == "artifact_sha256" else candidate,
                    "expected_profiles": PROFILES,
                }
                with self.assertRaisesRegex(AdmissionError, field):
                    verify_checkpoint_binding(binding(), CHECKPOINT_KEY, **kwargs)

    def test_tamper_unsigned_non_golden_and_secret_state_fail(self) -> None:
        tampered = binding()
        tampered["checkpoint_sha256"] = "f" * 64
        with self.assertRaisesRegex(AdmissionError, "signature"):
            verify_checkpoint_binding(
                tampered,
                CHECKPOINT_KEY,
                target=target(),
                environment=checkpoint_environment(),
                expected_profiles=PROFILES,
            )
        for candidate, reason in (
            (binding(capture_source="tenant-serving"), "golden"),
            (
                binding(
                    capture_state_classes={
                        "established_external_sockets": 1,
                        "secret_bearing_fds": 0,
                    }
                ),
                "forbidden",
            ),
            (binding(checkpoint_encrypted=False), "encrypted"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(AdmissionError, reason):
                verify_checkpoint_binding(
                    candidate,
                    CHECKPOINT_KEY,
                    target=target(),
                    environment=checkpoint_environment(),
                    expected_profiles=PROFILES,
                )


class CommandAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.policy = AdmissionPolicy(((MODEL_B, VERSION_B, ARTIFACT_SHA),))
        self.auth = CommandAuthenticator(
            AUTH_KEY,
            "cpu-test-command-key",
            self.policy,
            NonceJournal(self.root / "journal"),
        )
        self.request = trace(suffix="security")["requests"][0]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def command(self, **overrides: object) -> dict[str, object]:
        now = time.time_ns()
        command = self.auth.sign(
            self.request,
            nonce="security-nonce-0123456789",
            launch_mode="snapshot",
            issued_at_unix_ns=now - 1_000_000,
            expires_at_unix_ns=now + 30_000_000_000,
        )
        command.update(overrides)
        return command

    def test_signed_bounded_command_passes_once_and_replay_fails(self) -> None:
        command = self.command()
        receipt = self.auth.verify(command, self.request, time.time_ns())
        self.assertTrue(receipt["signature_verified"])
        with self.assertRaisesRegex(AdmissionError, "replayed"):
            self.auth.verify(command, self.request, time.time_ns())

    def test_signature_tamper_expiry_and_wrong_request_fail(self) -> None:
        tampered = self.command(signature="0" * 64)
        with self.assertRaisesRegex(AdmissionError, "signature"):
            self.auth.verify(tampered, self.request, time.time_ns())

        now = time.time_ns()
        expired = self.auth.sign(
            self.request,
            nonce="expired-nonce-0123456789",
            launch_mode="snapshot",
            issued_at_unix_ns=now - 120_000_000_000,
            expires_at_unix_ns=now - 60_000_000_000,
        )
        with self.assertRaisesRegex(AdmissionError, "lifetime"):
            self.auth.verify(expired, self.request, now)

        other = trace(suffix="other")["requests"][0]
        bound = self.command()
        with self.assertRaisesRegex(AdmissionError, "trace request"):
            self.auth.verify(bound, other, time.time_ns())

    def test_nonce_journal_rejects_symlink_root(self) -> None:
        destination = self.root / "real"
        destination.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(AdmissionError, "real directory"):
            NonceJournal(alias)


if __name__ == "__main__":
    unittest.main()
