"""Authenticated admission and signed checkpoint binding enforcement."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from performance.request_slo.harness import canonical_json, canonical_sha256


HEX64 = re.compile(r"^[0-9a-f]{64}$")
COMMAND_KEYS = {
    "schema",
    "nonce",
    "issued_at_unix_ns",
    "expires_at_unix_ns",
    "trace_request_sha256",
    "target",
    "launch_mode",
    "policy_sha256",
    "signature",
}
BINDING_KEYS = {
    "schema",
    "checkpoint_sha256",
    "artifact_sha256",
    "image_digest",
    "driver_version",
    "cuda_version",
    "runtime_version",
    "gpu_type",
    "gpu_topology_sha256",
    "capture_environment_id",
    "capture_source",
    "capture_time",
    "capture_state_classes",
    "egress_policy_sha256",
    "privilege_profile_sha256",
    "mount_policy_sha256",
    "checkpoint_encrypted",
    "checkpoint_key_id",
    "signature_key_id",
    "signature",
}


class AdmissionError(RuntimeError):
    """A command or checkpoint was unauthenticated, replayed, or out of policy."""


@dataclass(frozen=True)
class AdmissionPolicy:
    allowed_targets: tuple[tuple[str, str, str], ...]
    allowed_launch_modes: tuple[str, ...] = ("conventional", "snapshot")
    max_command_lifetime_ns: int = 60_000_000_000

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "catalog-switch-node-admission-policy/v1",
            "allowed_targets": [
                {"model_id": model, "model_version": version, "artifact_sha256": digest}
                for model, version, digest in self.allowed_targets
            ],
            "allowed_launch_modes": list(self.allowed_launch_modes),
            "max_command_lifetime_ns": self.max_command_lifetime_ns,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.as_dict())

    def admits(self, target: dict[str, Any], launch_mode: str) -> bool:
        identity = (target["model_id"], target["model_version"], target["artifact_sha256"])
        return identity in self.allowed_targets and launch_mode in self.allowed_launch_modes


class NonceJournal:
    """Replay-proof O_EXCL nonce claims in a root-owned directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink() or not root.is_dir():
            raise AdmissionError("nonce journal must be a real directory")
        os.chmod(root, 0o700)

    def claim(self, nonce: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9._-]{16,128}", nonce) is None:
            raise AdmissionError("command nonce has an unsafe format")
        path = self.root / hashlib.sha256(nonce.encode()).hexdigest()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise AdmissionError("command nonce was replayed") from exc
        try:
            os.write(fd, b"claimed\n")
            os.fsync(fd)
        finally:
            os.close(fd)
        directory = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _mac(key: bytes, payload: dict[str, Any]) -> str:
    if len(key) < 32:
        raise AdmissionError("authentication key must contain at least 256 bits")
    return hmac.new(key, canonical_json(payload).encode(), hashlib.sha256).hexdigest()


class CommandAuthenticator:
    def __init__(self, key: bytes, key_id: str, policy: AdmissionPolicy, journal: NonceJournal) -> None:
        if not key_id or len(key_id) > 128:
            raise AdmissionError("command key id is invalid")
        self._key = key
        self.key_id = key_id
        self.policy = policy
        self.journal = journal

    def sign(
        self,
        trace_request: dict[str, Any],
        *,
        nonce: str,
        launch_mode: str,
        issued_at_unix_ns: int,
        expires_at_unix_ns: int,
    ) -> dict[str, Any]:
        unsigned = {
            "schema": "catalog-switch-node-command/v1",
            "nonce": nonce,
            "issued_at_unix_ns": issued_at_unix_ns,
            "expires_at_unix_ns": expires_at_unix_ns,
            "trace_request_sha256": canonical_sha256(trace_request),
            "target": trace_request["target"],
            "launch_mode": launch_mode,
            "policy_sha256": self.policy.sha256,
        }
        return {**unsigned, "signature": _mac(self._key, unsigned)}

    def verify(self, command: dict[str, Any], trace_request: dict[str, Any], now_ns: int) -> dict[str, Any]:
        if set(command) != COMMAND_KEYS or command.get("schema") != "catalog-switch-node-command/v1":
            raise AdmissionError("command has the wrong closed schema")
        unsigned = {key: command[key] for key in command if key != "signature"}
        expected = _mac(self._key, unsigned)
        signature = command["signature"]
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise AdmissionError("command signature verification failed")
        issued = command["issued_at_unix_ns"]
        expires = command["expires_at_unix_ns"]
        if not isinstance(issued, int) or not isinstance(expires, int):
            raise AdmissionError("command lifetime must use integer nanoseconds")
        if issued > now_ns or expires < now_ns or expires - issued > self.policy.max_command_lifetime_ns:
            raise AdmissionError("command is not inside its bounded lifetime")
        if command["trace_request_sha256"] != canonical_sha256(trace_request):
            raise AdmissionError("command is not bound to the accepted trace request")
        if command["target"] != trace_request["target"]:
            raise AdmissionError("command target differs from external acceptance")
        if command["policy_sha256"] != self.policy.sha256:
            raise AdmissionError("command admission-policy hash differs")
        if not self.policy.admits(trace_request["target"], command["launch_mode"]):
            raise AdmissionError("command target or launch mode is outside local policy")
        self.journal.claim(command["nonce"])
        return {
            "signature_verified": True,
            "key_id": self.key_id,
            "policy_sha256": self.policy.sha256,
            "launch_mode": command["launch_mode"],
        }


def sign_checkpoint_binding(binding: dict[str, Any], key: bytes) -> dict[str, Any]:
    if "signature" in binding:
        raise AdmissionError("unsigned binding input must not contain a signature")
    if set(binding) != BINDING_KEYS - {"signature"}:
        raise AdmissionError("checkpoint binding has the wrong closed schema")
    return {**binding, "signature": _mac(key, binding)}


def verify_checkpoint_binding(
    binding: dict[str, Any],
    key: bytes,
    *,
    target: dict[str, Any],
    environment: dict[str, Any],
    expected_profiles: dict[str, str],
) -> dict[str, Any]:
    if set(binding) != BINDING_KEYS or binding.get("schema") != "catalog-switch-checkpoint-binding/v1":
        raise AdmissionError("checkpoint binding has the wrong closed schema")
    unsigned = {key_name: binding[key_name] for key_name in binding if key_name != "signature"}
    if not hmac.compare_digest(str(binding["signature"]), _mac(key, unsigned)):
        raise AdmissionError("checkpoint binding signature verification failed")
    for key_name in (
        "checkpoint_sha256",
        "artifact_sha256",
        "gpu_topology_sha256",
        "egress_policy_sha256",
        "privilege_profile_sha256",
        "mount_policy_sha256",
    ):
        if not isinstance(binding[key_name], str) or HEX64.fullmatch(binding[key_name]) is None:
            raise AdmissionError(f"checkpoint binding {key_name} is not a SHA-256")
    checks = {
        "artifact_sha256": target["artifact_sha256"],
        "image_digest": environment["image_digest"],
        "driver_version": environment.get("driver_version"),
        "cuda_version": environment.get("cuda_version"),
        "runtime_version": environment.get("runtime_version"),
        "gpu_type": environment["gpu_type"],
        "gpu_topology_sha256": environment.get("gpu_topology_sha256"),
        "egress_policy_sha256": expected_profiles["egress_policy_sha256"],
        "privilege_profile_sha256": expected_profiles["privilege_profile_sha256"],
        "mount_policy_sha256": expected_profiles["mount_policy_sha256"],
    }
    mismatches = [key_name for key_name, expected in checks.items() if binding[key_name] != expected]
    if mismatches:
        raise AdmissionError(f"checkpoint binding mismatch: {mismatches[0]}")
    state = binding["capture_state_classes"]
    if state != {"established_external_sockets": 0, "secret_bearing_fds": 0}:
        raise AdmissionError("checkpoint capture state contains forbidden descriptors")
    if binding["capture_source"] != "golden-pre-tenant-traffic":
        raise AdmissionError("checkpoint was not captured from a golden pre-traffic instance")
    if binding["checkpoint_encrypted"] is not True or not binding["checkpoint_key_id"]:
        raise AdmissionError("checkpoint is not encrypted under a recorded key")
    return {
        "binding_sha256": canonical_sha256(unsigned),
        "signature_key_id": binding["signature_key_id"],
        "checkpoint_sha256": binding["checkpoint_sha256"],
        "checkpoint_key_id": binding["checkpoint_key_id"],
        "capture_source": binding["capture_source"],
        "verified": True,
    }
