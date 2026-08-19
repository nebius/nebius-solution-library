from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any


class ContractReject(ValueError):
    pass


def digest(value: Any) -> str:
    import json
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class TrustedState:
    instance_id: str
    boot_id: str
    lease_id: str
    owner: str
    environment_digest: str
    now_ns: int


class V4Gate:
    """Fail-closed offline gate for the live protocol boundary."""

    def __init__(self, key: bytes, state: TrustedState, *, t0_max_age_ns: int = 5_000_000_000) -> None:
        self.key, self.state, self.t0_max_age_ns = key, state, t0_max_age_ns
        self._accepted: set[str] = set()
        self._nonce: set[str] = set()

    def accept_external_t0(self, event: dict[str, Any]) -> None:
        required = {"schema", "request_id", "attempt_id", "accepted_ns", "client_observed_ns", "payload_sha256", "model_id", "model_version", "client_signature", "recorder_id"}
        if set(event) != required or event["schema"] != "external-t0/v2":
            raise ContractReject("T0 schema is not closed")
        if event["attempt_id"] in self._accepted:
            raise ContractReject("duplicate T0")
        if event["accepted_ns"] > self.state.now_ns or self.state.now_ns - event["accepted_ns"] > self.t0_max_age_ns:
            raise ContractReject("T0 is late or from the future")
        if event["client_observed_ns"] > event["accepted_ns"]:
            raise ContractReject("client observation is after acceptance")
        body = {k: event[k] for k in required if k != "client_signature"}
        if not hmac.compare_digest(event["client_signature"], hmac.new(self.key, digest(body).encode(), hashlib.sha256).hexdigest()):
            raise ContractReject("T0 signature invalid")
        if event["recorder_id"] != "trusted-external-recorder-v2":
            raise ContractReject("untrusted recorder")
        self._accepted.add(event["attempt_id"])

    def command(self, command: dict[str, Any], *, attempt_id: str) -> None:
        required = {"schema", "attempt_id", "nonce", "deadline_ns", "instance_id", "boot_id", "lease_id", "owner", "environment_digest", "input_digest", "signature"}
        if set(command) != required or command["schema"] != "admission/v4":
            raise ContractReject("admission schema is not closed")
        if command["attempt_id"] != attempt_id or attempt_id not in self._accepted:
            raise ContractReject("command is not bound to accepted T0")
        if command["nonce"] in self._nonce:
            raise ContractReject("replay nonce")
        if command["deadline_ns"] < self.state.now_ns:
            raise ContractReject("deadline expired")
        expected = {"instance_id": self.state.instance_id, "boot_id": self.state.boot_id, "lease_id": self.state.lease_id, "owner": self.state.owner, "environment_digest": self.state.environment_digest}
        if any(command[k] != v for k, v in expected.items()):
            raise ContractReject("trusted state binding mismatch")
        body = {k: command[k] for k in required if k != "signature"}
        if not hmac.compare_digest(command["signature"], hmac.new(self.key, digest(body).encode(), hashlib.sha256).hexdigest()):
            raise ContractReject("admission signature invalid")
        self._nonce.add(command["nonce"])

    def require_distinct_inputs(self, inputs: list[bytes]) -> None:
        if len(inputs) != 2 or inputs[0] == inputs[1]:
            raise ContractReject("two distinct externally accepted inputs required")

    def validate_response(self, response: dict[str, Any], *, expected_input_digest: str, validator_digest: str) -> None:
        if response.get("input_digest") != expected_input_digest or response.get("validator_digest") != validator_digest or response.get("semantically_valid") is not True:
            raise ContractReject("semantic response is not independently bound")

    def require_cleanup(self, receipt: dict[str, Any], *, resource_ids: list[str], pre_cleanup: bool) -> None:
        if pre_cleanup or receipt.get("schema") != "cleanup-receipt/v3" or not resource_ids:
            raise ContractReject("cleanup receipt must be signed, non-empty, and post-cleanup")
        if {x.get("id") for x in receipt.get("resources", [])} != set(resource_ids) or any(x.get("absent") is not True or x.get("status") != "NOT_FOUND" for x in receipt["resources"]):
            raise ContractReject("exact absence proof missing")

    def require_observation(self, observation: dict[str, Any], *, arm: str) -> None:
        if arm == "network-ssd-control" and observation.get("storage") != "network-ssd":
            raise ContractReject("Network SSD control lacks readiness observation")
        if arm == "local-nvme" and observation.get("storage") != "host-local-nvme":
            raise ContractReject("local NVMe result cannot be claimed")
        if observation.get("observed") is not True or not observation.get("device_id"):
            raise ContractReject("storage readiness is not observed")
