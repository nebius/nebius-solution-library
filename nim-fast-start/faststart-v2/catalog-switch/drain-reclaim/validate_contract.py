#!/usr/bin/env python3
"""Fail-closed consistency checks for the drain/reclaim v1 contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from state_machine import (
    ABSENCE_SCHEMA,
    GPU_RELEASE_SCHEMA,
    SEMANTIC_PROBE_SCHEMA,
    STATE_SCHEMA,
    SwitchState,
)


CONTRACT_SCHEMA = "archvteams.nebius.ai/catalog-switch-drain-reclaim-contract/v1"
REQUIRED_INVARIANTS = {f"DR-INV-{index:02d}" for index in range(1, 11)}
EXPECTED_BACKENDS = {"kubernetes", "node-local"}
REQUIRED_OPERATIONS = {
    "install_serving_a",
    "begin_switch",
    "advance_drain",
    "record_reclaim",
    "reject_reclaim_proof",
    "begin_start_b",
    "accept_b",
    "fail_start",
    "mark_failed",
    "begin_rollback",
    "accept_rollback",
    "seal_switch",
}


class ContractError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ContractError(f"{path} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain an object")
    return value


def validate(contract: dict[str, Any], threat_model: dict[str, Any]) -> dict[str, Any]:
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("version") != 1:
        raise ContractError("contract schema/version differs from v1")
    if contract.get("state_schema") != STATE_SCHEMA:
        raise ContractError("contract state schema differs from implementation")
    state_names = [item.get("name") for item in contract.get("states", [])]
    expected_states = {state.value for state in SwitchState}
    if len(state_names) != len(set(state_names)) or set(state_names) != expected_states:
        raise ContractError("contract states differ from implementation enum")
    for item in contract["states"]:
        if item.get("admission") not in {"open", "closed"} or not item.get("runtime"):
            raise ContractError("state admission/runtime semantics are incomplete")
    invariants = [item.get("id") for item in contract.get("invariants", [])]
    if len(invariants) != len(set(invariants)) or set(invariants) != REQUIRED_INVARIANTS:
        raise ContractError("contract invariant set is incomplete or duplicated")
    if any(not item.get("statement") for item in contract["invariants"]):
        raise ContractError("contract invariant statement is empty")
    transitions = contract.get("transitions", [])
    operations = {item.get("operation") for item in transitions}
    if operations != REQUIRED_OPERATIONS:
        raise ContractError("contract transition operations differ from implementation")
    for item in transitions:
        if not set(item.get("from", [])) <= expected_states or item.get("to") not in expected_states:
            raise ContractError("transition references an unknown state")
        if not item.get("gate"):
            raise ContractError("transition lacks a fail-closed gate")
    backends = contract.get("backends", {})
    if set(backends.get("measured_internal", [])) != EXPECTED_BACKENDS:
        raise ContractError("lane backend scope must be Kubernetes and node-local only")
    if backends.get("excluded_from_this_lane") != ["modal"]:
        raise ContractError("Modal exclusion must remain explicit")
    proofs = contract.get("proof_gates", {})
    if proofs.get("runtime_absence", {}).get("schema") != ABSENCE_SCHEMA:
        raise ContractError("runtime absence proof schema differs")
    gpu = proofs.get("gpu_release", {})
    if gpu.get("schema") != GPU_RELEASE_SCHEMA or gpu.get(
        "minimum_ordered_nvml_samples"
    ) != 2:
        raise ContractError("GPU release proof schema/sample gate differs")
    if gpu.get("nvml_memory_used_bytes") != "less-than-or-equal-to-pinned-idle-baseline":
        raise ContractError("GPU release must require the pinned NVML idle baseline")
    semantic = proofs.get("semantic_probe", {})
    if (
        semantic.get("schema") != SEMANTIC_PROBE_SCHEMA
        or semantic.get("distinct_inference_count") != 2
        or semantic.get("each_semantically_valid") is not True
        or semantic.get("first_valid_response_remains_product_terminal") is not True
        or semantic.get("product_terminal_event_digest_must_match_first_inference")
        is not True
    ):
        raise ContractError("semantic probe gate differs from implementation")
    ledger = contract.get("ledger", {})
    if ledger.get("phases_owned") != ["drain", "gpu_release"]:
        raise ContractError("canonical drain/GPU-release phases are not pinned")
    if threat_model.get("status") != "reviewed":
        raise ContractError("security model is not reviewed")
    controls = {item.get("id") for item in threat_model.get("controls", [])}
    required_controls = set(contract.get("source_contracts", {}).get("security_controls", []))
    if not required_controls or not required_controls <= controls:
        raise ContractError("contract references missing security controls")
    return {
        "status": "valid",
        "schema": CONTRACT_SCHEMA,
        "state_count": len(expected_states),
        "transition_count": len(transitions),
        "invariant_count": len(invariants),
        "security_control_count": len(required_controls),
        "backends": sorted(EXPECTED_BACKENDS),
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    contract_path = root / "contract.json"
    threat_path = root.parent / "security-reliability" / "threat_model.json"
    try:
        result = validate(_load(contract_path), _load(threat_path))
    except ContractError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
