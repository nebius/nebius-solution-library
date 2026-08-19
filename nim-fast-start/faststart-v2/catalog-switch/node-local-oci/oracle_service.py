"""Independent semantic oracle for the node-local OCI switch adapter.

Runs as the *oracle* authority in its own process with its own signing key.
It answers agent validation requests by executing a source-pinned validator
over the raw response bytes and signing a verdict.  The validator source file
must hash to the pinned sha256 before it is loaded; the verdict binds the
validator pin, the request payload hash, and the raw response hash, so the
agent can neither choose the validator nor validate itself.

A validator module must expose::

    def validate(payload: bytes, response: bytes) -> tuple[bool, str]

returning (semantically_valid, reason).  A response that byte-equals the
request payload is refused here *and* structurally by the verdict contract.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
import uuid as uuid_module
from datetime import datetime, timezone
from pathlib import Path

LANE_DIR = Path(__file__).resolve().parent
FASTSTART_ROOT = LANE_DIR.parent.parent
for entry in (str(FASTSTART_ROOT), str(LANE_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from node_local_oci import contracts  # noqa: E402
from node_local_oci.journal import canonical_json  # noqa: E402
from node_local_oci.keys import load_private, sign  # noqa: E402


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned_validator(source_path: Path, expected_sha256: str):
    observed = _sha256_file(source_path)
    if observed != expected_sha256:
        raise SystemExit(f"validator source drifted: {observed} != {expected_sha256}")
    spec = importlib.util.spec_from_file_location("nlo_pinned_validator", source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate", None)):
        raise SystemExit("validator module exposes no validate(payload, response)")
    return module


class OracleService:
    def __init__(self, *, oracle_key_path: Path, validator_source: Path,
                 validator_id: str, exchange_dir: Path) -> None:
        self.private = load_private(Path(oracle_key_path))
        self.validator_source = Path(validator_source)
        self.validator_sha256 = _sha256_file(self.validator_source)
        self.validator = load_pinned_validator(self.validator_source,
                                               self.validator_sha256)
        self.validator_id = validator_id
        self.exchange_dir = Path(exchange_dir)

    def answer(self, request_path: Path) -> Path:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if request.get("schema") != "catalog-switch/nlo-validation-request/v1":
            raise SystemExit(f"unknown validation request schema in {request_path}")
        response_path = Path(request["response_path"])
        response = response_path.read_bytes()
        observed_sha256 = hashlib.sha256(response).hexdigest()
        if observed_sha256 != request["response_sha256"]:
            raise SystemExit("response bytes drifted between capture and validation")
        payload_path = self.exchange_dir / f"payload-{request['attempt_id']}.bin"
        payload = payload_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != request["request_payload_sha256"]:
            raise SystemExit("payload bytes drifted between offer and validation")
        if response == payload:
            valid, reason = False, "response merely echoes the request payload"
        else:
            valid, reason = self.validator.validate(payload, response)
        body = {
            "schema": contracts.VERDICT_SCHEMA,
            "verdict_id": f"nlo-verdict-{uuid_module.uuid4().hex}",
            "switch_uid": request["switch_uid"],
            "attempt_id": request["attempt_id"],
            "model_id": request["model_id"],
            "model_version": request["model_version"],
            "validator_id": self.validator_id,
            "validator_sha256": self.validator_sha256,
            "request_payload_sha256": request["request_payload_sha256"],
            "response_sha256": observed_sha256,
            "response_bytes": len(response),
            "complete_body": len(response) == request["response_bytes"],
            "semantically_valid": bool(valid),
            "reason": str(reason),
            "issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        envelope = dict(body)
        envelope["signature"] = sign(self.private, "oracle",
                                     contracts.VERDICT_SCHEMA, body)
        out = self.exchange_dir / f"verdict-{request['attempt_id']}.json"
        out.write_text(canonical_json(envelope) + "\n", encoding="utf-8")
        return out

    def answer_pending(self) -> int:
        """Answer every validation request without a verdict yet."""
        answered = 0
        for request_path in sorted(self.exchange_dir.glob("validation-request-*.json")):
            attempt_id = request_path.name[len("validation-request-"):-len(".json")]
            verdict_path = self.exchange_dir / f"verdict-{attempt_id}.json"
            if not verdict_path.exists():
                self.answer(request_path)
                answered += 1
        return answered

    def serve(self, *, poll_s: float = 0.1, stop_marker: Path | None = None) -> None:
        while True:
            self.answer_pending()
            if stop_marker is not None and stop_marker.exists():
                return
            time.sleep(poll_s)
