"""Agent-side verification of oracle verdicts (the agent cannot self-validate).

The oracle is a separate authority holding its own signing key.  The agent
only ever *verifies*: signature under the oracle public key, binding to this
switch/attempt/model, binding to the controller-pinned validator source, and
binding to the exact raw response bytes the agent captured.  A verdict that
merely echoes the request payload is refused structurally (the contract
forbids ``response_sha256 == request_payload_sha256``), and a verdict signed
by any non-oracle key fails signature verification.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import contracts
from .errors import Refusal, require
from .keys import KeyRing


def hash_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), size


def verify_verdict(keyring: KeyRing, envelope: dict, *, policy: dict, bundle: dict,
                   attempt_id: str, payload_sha256: str, response_path: Path) -> dict:
    body = keyring.verify_role("oracle", contracts.VERDICT_SCHEMA, envelope)
    contracts.validate_verdict(body)
    require(body["switch_uid"] == bundle["switch_uid"], "oracle.switch-uid",
            "verdict is bound to a different switch")
    require(body["attempt_id"] == attempt_id, "oracle.attempt",
            f"verdict is for attempt {body['attempt_id']!r}, not {attempt_id!r}")
    model = policy["models"][bundle["target_model_id"]]
    require(body["model_id"] == bundle["target_model_id"], "oracle.model",
            "verdict model_id != admitted target model")
    require(body["model_version"] == model["model_version"], "oracle.model-version",
            "verdict model_version != policy pin")
    require(body["validator_id"] == policy["oracle"]["validator_id"],
            "oracle.validator-id", "verdict validator_id != policy pin")
    require(body["validator_sha256"] == policy["oracle"]["validator_sha256"],
            "oracle.validator-hash", "verdict validator source hash != policy pin")
    require(body["request_payload_sha256"] == payload_sha256, "oracle.payload",
            "verdict request payload hash != admitted payload hash")
    observed_sha256, observed_bytes = hash_file(response_path)
    require(body["response_sha256"] == observed_sha256, "oracle.response-hash",
            "verdict response hash != agent-captured raw response bytes")
    require(body["response_bytes"] == observed_bytes, "oracle.response-bytes",
            "verdict response byte count != agent-captured byte count")
    require(body["complete_body"] is True, "oracle.incomplete",
            f"oracle marked the response body incomplete: {body['reason']!r}")
    require(body["semantically_valid"] is True, "oracle.invalid",
            f"oracle rejected the response semantically: {body['reason']!r}")
    return body
