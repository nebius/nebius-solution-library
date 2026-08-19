"""Ed25519 role keys with hard separation of authorities.

Four authorities participate in one switch and hold four distinct keypairs:

- ``recorder``   external client; owns the shared request-SLO ledger and signs
                 acceptance authorizations over durable ``request.accepted``
                 events.
- ``controller`` control plane; signs the admission policy and the switch
                 command bundle.
- ``oracle``     independent semantic validator; signs response verdicts.
- ``agent``      this node agent; signs its own receipts and journal links.

The agent process loads only its own private key plus the three foreign
*public* keys.  Because signing is asymmetric, the holder of the agent key is
structurally unable to mint T0 authorizations, commands, or verdicts — the
exact forgery class that rejected the prior node-local and Qwen candidates.
``KeyRing`` additionally refuses to start when any two role public keys
coincide, so one keypair can never wear two hats.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .errors import Refusal, require

ROLES = ("recorder", "controller", "oracle", "agent")
_DOMAIN = b"catalog-switch/nlo-signature/v1"


def _canonical_json_bytes(value) -> bytes:
    import json

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def signing_bytes(role: str, schema: str, body: dict) -> bytes:
    """Domain-separated canonical bytes for signing ``body`` (sans signature)."""
    require(role in ROLES, "keys.unknown-role", f"role {role!r}")
    require(isinstance(schema, str) and len(schema) > 0, "keys.schema", "empty schema")
    require(isinstance(body, dict), "keys.body-shape", "signable body must be a dict")
    require("signature" not in body, "keys.body-signature",
            "signable body must not already contain a signature")
    return b"\n".join([_DOMAIN, role.encode(), schema.encode(), _canonical_json_bytes(body)])


def generate_keypair(directory: Path, role: str) -> tuple[Path, Path]:
    """Generate ``<role>.key`` / ``<role>.pub`` PEM files (test/provisioning tool)."""
    require(role in ROLES, "keys.unknown-role", f"role {role!r}")
    directory.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    key_path = directory / f"{role}.key"
    pub_path = directory / f"{role}.pub"
    key_path.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    pub_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return key_path, pub_path


def load_private(path: Path) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError) as error:
        raise Refusal("keys.private-unreadable", f"{path}: {error}") from error
    require(isinstance(key, Ed25519PrivateKey), "keys.private-type",
            f"{path} is not an Ed25519 private key")
    return key


def load_public(path: Path) -> Ed25519PublicKey:
    try:
        key = serialization.load_pem_public_key(path.read_bytes())
    except (OSError, ValueError) as error:
        raise Refusal("keys.public-unreadable", f"{path}: {error}") from error
    require(isinstance(key, Ed25519PublicKey), "keys.public-type",
            f"{path} is not an Ed25519 public key")
    return key


def public_fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def sign(private: Ed25519PrivateKey, role: str, schema: str, body: dict) -> str:
    return private.sign(signing_bytes(role, schema, body)).hex()


def verify(public: Ed25519PublicKey, role: str, schema: str, body: dict, signature: str) -> None:
    require(isinstance(signature, str) and len(signature) == 128,
            "keys.signature-shape", "signature must be 128 hex chars")
    try:
        raw = bytes.fromhex(signature)
    except ValueError as error:
        raise Refusal("keys.signature-hex", "signature is not hex") from error
    try:
        public.verify(raw, signing_bytes(role, schema, body))
    except Exception as error:  # cryptography raises InvalidSignature
        raise Refusal("keys.signature-invalid",
                      f"{role}/{schema}: signature verification failed") from error


class KeyRing:
    """The agent's view: own private key + three foreign public keys, all distinct."""

    def __init__(self, keys_dir: Path) -> None:
        keys_dir = Path(keys_dir)
        self.agent_private = load_private(keys_dir / "agent.key")
        self.publics = {
            "agent": self.agent_private.public_key(),
            "recorder": load_public(keys_dir / "recorder.pub"),
            "controller": load_public(keys_dir / "controller.pub"),
            "oracle": load_public(keys_dir / "oracle.pub"),
        }
        fingerprints = {role: public_fingerprint(key) for role, key in self.publics.items()}
        require(len(set(fingerprints.values())) == len(ROLES),
                "keys.role-collision",
                f"role public keys are not pairwise distinct: {fingerprints}")
        self.fingerprints = fingerprints

    def verify_role(self, role: str, schema: str, signed: dict) -> dict:
        """Verify a signed envelope; returns the body (envelope minus signature)."""
        require(role in ("recorder", "controller", "oracle"),
                "keys.verify-role", f"agent only verifies foreign roles, got {role!r}")
        require(isinstance(signed, dict), "keys.envelope-shape", "envelope must be a dict")
        require("signature" in signed, "keys.envelope-unsigned", f"{role} envelope unsigned")
        body = {k: v for k, v in signed.items() if k != "signature"}
        verify(self.publics[role], role, schema, body, signed["signature"])
        return body

    def sign_agent(self, schema: str, body: dict) -> dict:
        """Return ``body`` with an agent signature attached."""
        envelope = dict(body)
        envelope["signature"] = sign(self.agent_private, "agent", schema, body)
        return envelope
