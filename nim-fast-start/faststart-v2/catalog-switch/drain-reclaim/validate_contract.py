#!/usr/bin/env python3
"""Executable contract-to-code/source/threat-model equivalence validator."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FASTSTART_ROOT = Path(__file__).resolve().parents[2]
if str(FASTSTART_ROOT) not in sys.path:
    sys.path.insert(0, str(FASTSTART_ROOT))

import adapters
import ledger
import state_machine
from state_machine import PROOF_GATE_SPEC, STATE_SEMANTICS, TRANSITION_SPECS, SwitchState


CONTRACT_SCHEMA = "archvteams.nebius.ai/catalog-switch-drain-reclaim-contract/v5"
EXPECTED_SOURCE = {
    "request_slo_commit": "ba49c9e20f194e0f419d4209608904cc9335219d",
    "request_slo_path": "performance/request_slo",
    "request_slo_tree_oid_sha1": "ee9ae33ff4af61187e9afb00b2be4fb1e5293725",
    "request_slo_content_manifest_sha256": "0095bf61bf8891040731956f97188af4031c18a3fd06fd713f8b6de271d13bbd",
    "security_model_commit": "9cfbc1b1311a1f784a407889b215aaec5200fe0e",
    "security_model_path": "catalog-switch/security-reliability",
    "security_model_tree_oid_sha1": "a6ad3555b819a0b58e0c937b42f1cf770fa05743",
    "security_model_content_manifest_sha256": "9edf0231aa36ecc07a611ca44f7745c2709a8851517cfadb532446fcbbd7684b",
    "security_controls": ["CTL-04", "CTL-05", "CTL-09", "CTL-10", "CTL-13", "CTL-19", "CTL-20", "CTL-21"],
    "security_tests": ["TST-01", "TST-02", "TST-11", "TST-12", "TST-16", "TST-17"],
}
EXPECTED_INVARIANTS = {
    "DR-INV-01": "Admission is open only for one exact runtime after an exact bridge receipt proves two distinct, ordered, raw-evidence-backed semantic calls executed by the canonical validator derived from the pinned source artifact and an independently reread complete off-node durable chain segment.",
    "DR-INV-02": "Every state mutation, physical command, request lease, and response is controller-lease- and runtime-generation-fenced; late responses are durably terminal before rejection.",
    "DR-INV-03": "GPU_FREE requires every action, runtime-absence, and GPU proof signer to equal the runtime authority's exact node-agent ID and key, stop completion, exact process/cgroup/container/Pod and host-residue absence, then an approved scrub bound to the exact GPU UUID and total bytes, then exactly two NVML samples with zero compute processes, zero graphics processes, and zero used bytes.",
    "DR-INV-04": "The target switch begins only after a mandatory canonical verifier reconstructs an exact request.accepted receipt from the pinned trace, shared ledger, predecessor-hash audit, and off-node durable segment; every request-specific event remains causally after that immutable external-client T0.",
    "DR-INV-05": "Drain, timeout, reclaim, semantic validation, every admitted failure, accounting, and cleanup are durably retained in the shared denominator and hash-chained audit segment; rollback A has its own later external T0, trace, terminal, accounting, and cleanup linked to B failure.",
    "DR-INV-06": "Unknown cleanup quarantines the node; reuse requires placement-lease revocation, a newly created resource with a fresh boot identity, and signed requalification covering sentinel VRAM, host residue, occupancy, audit continuity, and command replay refusal.",
    "DR-INV-07": "Reclaim cannot begin while an active lease belongs to the retiring runtime; the bounded drain durably completes or times out every admitted lease before stop.",
    "DR-INV-08": "Canonical snapshots use compare-and-swap revisions whose predecessor-hash records embed every complete post-transition state detail; state restart and agent actions reject stale controller generations.",
    "DR-INV-09": "Every launch has a durable pre-launch operation identity and agent-side executing intent; bound and ambiguous failed launches require exact-authority-signed generation cleanup and GPU-zero proof before rollback or any new generation, Kubernetes operation absence requires an explicit authoritative PodList items array, and ambiguous commands are never replayed.",
    "DR-INV-10": "Exact duplicate reservations and commands are idempotent and conflicting retries are rejected; before either node-local or exact-cluster Kubernetes dispatch, the receiver validates the complete hash-bound machine snapshot, durably joins bootstrap runtime occupancy, requires STARTING_B or ROLLING_BACK plus the exact state-machine reservation and controller fence, and refuses caller-made or second launches before the physical runner.",
}
EXPECTED_BINDING_REQUIREMENTS = {
    "DR-INV-01": {
        "code": {"DrainReclaimStateMachine.accept_b", "DrainReclaimStateMachine.accept_rollback", "ExactLedgerReceiptVerifier.verify", "ExactLedgerReceiptVerifier._verify_durability", "ValidatorRuntime.validate"},
        "controls": {"CTL-10", "CTL-19"},
        "tests": {"test_exact_bridge_receipt_is_mandatory_for_admission", "test_semantic_response_loss_reuses_durable_intent_and_idempotency_key", "test_semantic_mismatch_missing_duplicate_reordered_and_prior_calls_reject", "test_pinned_validator_artifact_rejects_raw_false_response", "test_validator_source_authority_tamper_rejects"},
        "threat_tests": {"TST-11", "TST-12"},
    },
    "DR-INV-02": {
        "code": {"CommandAdmissionPolicy.authorize", "DrainReclaimStateMachine.complete_response", "FencedActionExecutor.execute"},
        "controls": {"CTL-13", "CTL-20"},
        "tests": {"test_restart_preserves_state_and_fences_the_old_controller", "test_stale_generation_and_stale_controller_commands_reject", "test_late_response_timeout_is_persisted_before_exception", "test_signed_out_of_policy_command_is_refused_before_side_effect"},
        "threat_tests": {"TST-17"},
    },
    "DR-INV-03": {
        "code": {"DrainReclaimStateMachine.record_reclaim", "EvidenceTrustStore.verify_authority", "GpuReleaseProof.validate_for", "NvidiaSmiNvmlProbe.observe", "RuntimeAbsenceProof.validate_for"},
        "controls": {"CTL-04", "CTL-05"},
        "tests": {"test_exact_total_absence_before_scrub_and_zero_nvml_are_required", "test_graphics_process_rejects_gpu_release", "test_empty_and_header_only_pmon_are_not_zero_process_proofs", "test_trusted_foreign_node_cannot_attest_target_node_reclaim"},
        "threat_tests": {"TST-01", "TST-02"},
    },
    "DR-INV-04": {
        "code": {"DrainReclaimStateMachine.__init__", "DrainReclaimStateMachine.begin_switch", "ExactLedgerReceiptVerifier.verify_acceptance", "SwitchLedgerBridge.__init__", "SwitchLedgerBridge.acceptance_receipt"},
        "controls": {"CTL-10"},
        "tests": {"test_begin_switch_rejects_fabricated_acceptance_without_state_change", "test_bridge_refuses_work_before_external_t0", "test_state_machine_requires_canonical_verifier_at_construction"},
        "threat_tests": {"TST-12"},
    },
    "DR-INV-05": {
        "code": {"SwitchLedgerBridge.fail_attempt", "SwitchLedgerBridge.close_success", "SwitchLedgerBridge.close_recovery_success"},
        "controls": {"CTL-10", "CTL-13"},
        "tests": {"test_failure_recovery_is_idempotent_and_retained_in_denominator"},
        "threat_tests": {"TST-12"},
    },
    "DR-INV-06": {
        "code": {"DrainReclaimStateMachine.reject_reclaim_proof", "DrainReclaimStateMachine.record_requalification", "NodeLocalActions.revoke_placement", "PlacementRevocationProof.validate_for"},
        "controls": {"CTL-04", "CTL-05"},
        "tests": {"test_concrete_scrub_and_cleanup_receipt_producers", "test_quarantine_revoke_recycle_new_boot_and_requalify"},
        "threat_tests": {"TST-16"},
    },
    "DR-INV-07": {
        "code": {"DrainReclaimStateMachine.advance_drain", "DrainReclaimStateMachine.record_reclaim"},
        "controls": {"CTL-13"},
        "tests": {"test_active_a_completes_during_drain_before_reclaim", "test_hung_a_is_timed_out_and_late_a_response_rejected"},
        "threat_tests": {"TST-17"},
    },
    "DR-INV-08": {
        "code": {"DrainReclaimStateMachine._commit", "DrainReclaimStateMachine._validate_snapshot", "FencedActionExecutor.execute"},
        "controls": {"CTL-10", "CTL-20"},
        "tests": {"test_transition_chain_binds_every_state_detail", "test_stale_generation_and_stale_controller_commands_reject"},
        "threat_tests": {"TST-12", "TST-17"},
    },
    "DR-INV-09": {
        "code": {"DrainReclaimStateMachine.fail_start", "DrainReclaimStateMachine.record_ambiguous_launch_cleanup", "DrainReclaimStateMachine.begin_rollback", "KubernetesEvidenceAdapter._pod_inventory_items", "LaunchOperationAbsenceProof.validate_for"},
        "controls": {"CTL-04", "CTL-05", "CTL-10"},
        "tests": {"test_ambiguous_launch_must_be_proved_absent_before_new_generation", "test_action_crash_window_is_durable_and_never_replays", "test_cancelled_bound_b_requires_exact_partial_cleanup", "test_failed_b_and_rollback_use_separate_linked_traces", "test_many_seed_drain_cancel_failure_and_cleanup_preserve_invariants", "test_operation_absence_requires_explicit_pod_items_list", "test_trusted_foreign_node_cannot_attest_target_node_reclaim"},
        "threat_tests": {"TST-01", "TST-02", "TST-12"},
    },
    "DR-INV-10": {
        "code": {"DrainReclaimStateMachine.begin_start_b", "ActionJournal.load", "FencedActionExecutor.execute", "FencedActionExecutor.synchronize_machine_state", "FencedActionExecutor._require_durable_launch_authorization", "KubernetesActions.launch", "NodeLocalActions.launch", "validate_machine_snapshot"},
        "controls": {"CTL-19", "CTL-20"},
        "tests": {"test_concurrent_duplicate_b_reserves_one_generation", "test_duplicate_launch_reservation_is_idempotent_and_conflict_rejects", "test_receiving_agent_refuses_second_valid_launch_before_physical_dispatch", "test_kubernetes_adapter_pins_kubeconfig_context_cluster_ca_namespace_node", "test_node_local_direct_launch_cannot_bypass_serving_a", "test_kubernetes_direct_launch_cannot_bypass_serving_a", "test_launch_without_machine_snapshot_authority_fails_closed"},
        "threat_tests": {"TST-11", "TST-17"},
    },
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


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args), check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise ContractError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _resolve_symbol(name: str) -> None:
    if "." not in name:
        if any(callable(getattr(module, name, None)) for module in (state_machine, ledger, adapters)):
            return
        raise ContractError(f"binding function does not exist: {name}")
    class_name, method = name.split(".", 1)
    for module in (state_machine, ledger, adapters):
        owner = getattr(module, class_name, None)
        if owner is not None:
            if getattr(owner, method, None) is None:
                raise ContractError(f"binding code symbol does not exist: {name}")
            return
    raise ContractError(f"binding class does not exist: {name}")


def _test_methods(root: Path) -> set[str]:
    names: set[str] = set()
    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return names


def validate(
    contract: dict[str, Any],
    threat_model: dict[str, Any],
    *,
    package_root: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    package_root = package_root or Path(__file__).resolve().parent
    repo_root = repo_root or Path(__file__).resolve().parents[4]
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("version") != 5:
        raise ContractError("contract schema/version differs from v5")
    if contract.get("status") != "independent-review-required":
        raise ContractError("replacement cannot claim approval before independent review")
    if contract.get("state_schema") != state_machine.STATE_SCHEMA:
        raise ContractError("state schema differs from implementation")
    expected_states = {state.value for state in SwitchState}
    states = contract.get("states")
    if not isinstance(states, list) or {item.get("name") for item in states} != expected_states:
        raise ContractError("contract states differ from implementation enum")
    actual_semantics = {
        item["name"]: {"admission": item.get("admission"), "runtime": item.get("runtime")}
        for item in states
    }
    if actual_semantics != STATE_SEMANTICS:
        raise ContractError("state admission/runtime semantics differ from code")
    invariants = contract.get("invariants")
    if not isinstance(invariants, list):
        raise ContractError("invariants must be a list")
    invariant_map = {item.get("id"): item.get("statement") for item in invariants}
    if invariant_map != EXPECTED_INVARIANTS or len(invariants) != len(EXPECTED_INVARIANTS):
        raise ContractError("invariant identifiers/statements differ from executable v5 semantics")
    if contract.get("transitions") != TRANSITION_SPECS:
        raise ContractError("transition relation differs from implementation")
    backends = contract.get("backends")
    if backends != {
        "excluded_from_this_lane": ["modal"],
        "measured_internal": ["kubernetes", "node-local"],
        "sole_external_measured_comparator": "cerebrium-not-an-adapter-in-this-package",
    }:
        raise ContractError("backend scope differs; Modal must remain excluded")
    proofs = contract.get("proof_gates", {})
    runtime_absence = proofs.get("runtime_absence", {})
    gpu = proofs.get("gpu_release", {})
    quarantine = proofs.get("quarantine_recovery", {})
    semantic = proofs.get("semantic", {})
    acceptance = proofs.get("request_acceptance", {})
    occupancy = proofs.get("receiver_occupancy", {})
    authority = proofs.get("evidence_authority", {})
    pod_inventory = proofs.get("kubernetes_pod_inventory", {})
    if runtime_absence != {
        "schema": state_machine.ABSENCE_SCHEMA,
        "required": PROOF_GATE_SPEC["runtime_absence_required"],
    }:
        raise ContractError("runtime absence exact gate set differs from code")
    if gpu != {
        "active_scrub_methods": PROOF_GATE_SPEC["active_scrub_methods"],
        "full_vram_bytes_rule": "bytes-scrubbed-equals-exact-nvml-total",
        "minimum_ordered_nvml_samples": PROOF_GATE_SPEC["nvml_samples"],
        "nvml_compute_processes": "empty",
        "nvml_graphics_processes": "observed-and-empty",
        "nvml_memory_used_bytes": "equals-zero",
        "order": ["stop-completed", "runtime-or-operation-absence", "scrub-completed", "nvml-zero-sample-1", "nvml-zero-sample-2"],
        "schema": state_machine.GPU_RELEASE_SCHEMA,
    }:
        raise ContractError("GPU release exact gates/order differ from code")
    if quarantine != {
        "required": PROOF_GATE_SPEC["quarantine_recovery_required"],
        "placement_revocation_schema": state_machine.PLACEMENT_REVOCATION_SCHEMA,
        "node_recycle_schema": state_machine.RECYCLE_SCHEMA,
        "requalification_schema": state_machine.REQUALIFICATION_SCHEMA,
    }:
        raise ContractError("quarantine recovery exact gates differ from code")
    if semantic != {
        "bridge_owned_inference_execution": True,
        "call_count": PROOF_GATE_SPEC["semantic_calls"],
        "distinct_raw_request_bodies": True,
        "distinct_raw_response_bodies": True,
        "durable_idempotent_intents": True,
        "source_derived_validator_execution": True,
        "exact_validator_source_authority": True,
        "raw_false_response_rejected": True,
        "no_prior_call_or_restart": True,
        "raw_authority_hash_and_bytes": True,
        "strict_call_order": True,
    }:
        raise ContractError("semantic exact gate set differs from bridge/verifier")
    if acceptance != {
        "constructor_verifier_required": True,
        "exact_request_accepted_first_event": True,
        "offnode_durable_predecessor_hash_segment": True,
        "receipt_schema": state_machine.ACCEPTANCE_GATE_SCHEMA,
        "switch_attempt_target_bound": True,
    }:
        raise ContractError("request acceptance exact gate differs from implementation")
    if occupancy != adapters.RECEIVER_MACHINE_JOIN_SPEC:
        raise ContractError("receiver occupancy exact gate differs from implementation")
    if authority != PROOF_GATE_SPEC["evidence_authority"]:
        raise ContractError("evidence authority exact gate differs from implementation")
    if pod_inventory != adapters.KUBERNETES_POD_INVENTORY_SPEC:
        raise ContractError("Kubernetes Pod inventory exact gate differs from implementation")
    expected_ledger = {
        "audit_event_schema": ledger.AUDIT_EVENT_SCHEMA,
        "acceptance_gate_receipt_schema": state_machine.ACCEPTANCE_GATE_SCHEMA,
        "boundary": T0_BOUNDARY,
        "failure_terminal": "attempt.failed",
        "gate_receipt_schema": state_machine.LEDGER_GATE_SCHEMA,
        "offnode_receipt_schema": ledger.OFFNODE_RECEIPT_SCHEMA,
        "immutable_object_exact_version_reread_required": True,
        "predecessor_hash_required": True,
        "rollback_external_t0_and_trace_required": True,
        "shared_schema": "archvteams.nebius.ai/catalog-switch-ledger-event/v1",
        "success_terminal": TERMINAL_BOUNDARY,
    }
    if contract.get("ledger") != expected_ledger:
        raise ContractError("ledger/hash-chain/off-node gate differs from implementation")
    source = contract.get("source_contracts")
    if source != EXPECTED_SOURCE:
        raise ContractError("pinned prerequisite commits/trees/control sets differ")
    for commit_key, tree_key, manifest_key, path_key in (
        ("request_slo_commit", "request_slo_tree_oid_sha1", "request_slo_content_manifest_sha256", "request_slo_path"),
        ("security_model_commit", "security_model_tree_oid_sha1", "security_model_content_manifest_sha256", "security_model_path"),
    ):
        commit, tree, relative = source[commit_key], source[tree_key], source[path_key]
        git_path = f"nim-fast-start/faststart-v2/{relative}"
        if _git(repo_root, "rev-parse", f"{commit}:{git_path}") != tree:
            raise ContractError(f"pinned {path_key} Git tree differs")
        listing = subprocess.run(
            ("git", "-C", str(repo_root), "ls-tree", "-r", commit, "--", git_path),
            check=False,
            capture_output=True,
        )
        if listing.returncode != 0 or hashlib.sha256(listing.stdout).hexdigest() != source[manifest_key]:
            raise ContractError(f"pinned {path_key} content manifest differs")
        diff = subprocess.run(
            ("git", "-C", str(repo_root), "diff", "--quiet", commit, "--", git_path),
            check=False,
        )
        if diff.returncode != 0:
            raise ContractError(f"working {path_key} content differs from pinned source")
    if threat_model.get("status") != "reviewed":
        raise ContractError("security model is not reviewed")
    controls = {item.get("id") for item in threat_model.get("controls", [])}
    threat_tests = {item.get("id") for item in threat_model.get("tests", [])}
    if not set(EXPECTED_SOURCE["security_controls"]) <= controls:
        raise ContractError("a bound security control is absent")
    if not set(EXPECTED_SOURCE["security_tests"]) <= threat_tests:
        raise ContractError("a bound threat test is absent")
    bindings = contract.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(EXPECTED_BINDING_REQUIREMENTS):
        raise ContractError("INV/CTL/TST binding set differs")
    tests = _test_methods(package_root)
    for invariant, expected in EXPECTED_BINDING_REQUIREMENTS.items():
        actual = bindings[invariant]
        if set(actual) != {"code", "controls", "tests", "threat_tests"}:
            raise ContractError(f"{invariant} binding shape differs")
        normalized = {key: set(value) for key, value in actual.items()}
        if normalized != expected:
            raise ContractError(f"{invariant} exact binding differs")
        for symbol in expected["code"]:
            _resolve_symbol(symbol)
        if not expected["tests"] <= tests:
            raise ContractError(f"{invariant} references a missing executable test")
        if not expected["controls"] <= controls or not expected["threat_tests"] <= threat_tests:
            raise ContractError(f"{invariant} references missing reviewed CTL/TST IDs")
    return {
        "status": "valid-independent-review-required",
        "schema": CONTRACT_SCHEMA,
        "state_count": len(expected_states),
        "transition_count": len(TRANSITION_SPECS),
        "invariant_count": len(EXPECTED_INVARIANTS),
        "binding_count": len(bindings),
        "backends": ["kubernetes", "node-local"],
        "memory_rule": PROOF_GATE_SPEC["memory_rule"],
    }


# Import only after definitions to keep the implementation source pins obvious.
from performance.request_slo.harness import T0_BOUNDARY, TERMINAL_BOUNDARY  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    try:
        result = validate(
            _load(root / "contract.json"),
            _load(root.parent / "security-reliability" / "threat_model.json"),
        )
    except ContractError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
