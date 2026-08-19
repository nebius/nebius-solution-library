from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_contract import ContractError, validate  # noqa: E402


def inputs():
    contract = json.loads((ROOT / "contract.json").read_text())
    threat = json.loads(
        (ROOT.parent / "security-reliability" / "threat_model.json").read_text()
    )
    return contract, threat


class ContractEquivalenceTests(unittest.TestCase):
    def test_contract_matches_exact_code_sources_controls_and_tests(self) -> None:
        contract, threat = inputs()
        result = validate(contract, threat)
        self.assertEqual(result["status"], "valid-independent-review-required")
        self.assertEqual(result["memory_rule"], "post-scrub-nvml-used-bytes-equals-zero")
        self.assertEqual(result["backends"], ["kubernetes", "node-local"])

    def test_changed_source_commit_or_tree_hash_rejects(self) -> None:
        for field in (
            "request_slo_commit",
            "request_slo_tree_oid_sha1",
            "request_slo_content_manifest_sha256",
            "security_model_commit",
            "security_model_tree_oid_sha1",
            "security_model_content_manifest_sha256",
        ):
            with self.subTest(field=field):
                contract, threat = inputs()
                contract["source_contracts"][field] = "0" * (
                    40 if field.endswith("commit") else 40
                )
                with self.assertRaisesRegex(ContractError, "pinned prerequisite"):
                    validate(contract, threat)

    def test_empty_scrub_method_or_absence_gate_rejects(self) -> None:
        for field in ("active_scrub_methods",):
            contract, threat = inputs()
            contract["proof_gates"]["gpu_release"][field] = []
            with self.assertRaisesRegex(ContractError, "GPU release exact gates"):
                validate(contract, threat)
        contract, threat = inputs()
        contract["proof_gates"]["runtime_absence"]["required"] = []
        with self.assertRaisesRegex(ContractError, "runtime absence exact gate"):
            validate(contract, threat)
        contract, threat = inputs()
        contract["proof_gates"]["quarantine_recovery"]["required"] = []
        with self.assertRaisesRegex(ContractError, "quarantine recovery exact gate"):
            validate(contract, threat)

    def test_false_but_nonempty_invariant_statement_rejects(self) -> None:
        contract, threat = inputs()
        contract["invariants"][2]["statement"] = "GPU use is fine when convenient."
        with self.assertRaisesRegex(ContractError, "invariant identifiers/statements"):
            validate(contract, threat)

    def test_zero_memory_rule_cannot_be_changed_to_baseline(self) -> None:
        contract, threat = inputs()
        contract["proof_gates"]["gpu_release"][
            "nvml_memory_used_bytes"
        ] = "less-than-or-equal-to-pinned-idle-baseline"
        with self.assertRaisesRegex(ContractError, "GPU release exact gates"):
            validate(contract, threat)

    def test_acceptance_validator_and_receiver_occupancy_gates_are_exact(self) -> None:
        mutations = [
            ("request_acceptance", "constructor_verifier_required", False),
            ("request_acceptance", "exact_request_accepted_first_event", False),
            ("semantic", "source_derived_validator_execution", False),
            ("semantic", "raw_false_response_rejected", False),
            ("receiver_occupancy", "durable_before_dispatch", False),
            (
                "receiver_occupancy",
                "key_fields",
                ["gpu_uuid", "runtime_generation"],
            ),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                contract, threat = inputs()
                contract["proof_gates"][section][field] = value
                with self.assertRaisesRegex(ContractError, "exact gate"):
                    validate(contract, threat)

    def test_proof_authority_and_pod_inventory_gates_are_exact(self) -> None:
        mutations = [
            (
                "evidence_authority",
                "broad_trust_membership_is_insufficient",
                False,
            ),
            (
                "evidence_authority",
                "required_source_id",
                "any-trusted-source",
            ),
            (
                "evidence_authority",
                "required_source_key_sha256",
                "any-trusted-key",
            ),
            ("kubernetes_pod_inventory", "explicit_items_field", False),
            (
                "kubernetes_pod_inventory",
                "missing_null_or_non_list",
                "treat-as-empty",
            ),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                contract, threat = inputs()
                contract["proof_gates"][section][field] = value
                with self.assertRaisesRegex(ContractError, "exact gate"):
                    validate(contract, threat)

    def test_every_inv_ctl_tst_and_code_binding_is_exact(self) -> None:
        mutations = [
            ("DR-INV-01", "controls", ["CTL-10"]),
            ("DR-INV-03", "threat_tests", ["TST-01"]),
            ("DR-INV-08", "code", ["DrainReclaimStateMachine._commit"]),
            ("DR-INV-10", "tests", ["test_nonexistent"]),
        ]
        for invariant, field, value in mutations:
            with self.subTest(invariant=invariant, field=field):
                contract, threat = inputs()
                contract["bindings"][invariant][field] = value
                with self.assertRaisesRegex(ContractError, "exact binding"):
                    validate(contract, threat)

    def test_state_and_transition_mutations_reject(self) -> None:
        contract, threat = inputs()
        contract["states"][0]["runtime"] = "maybe-present"
        with self.assertRaisesRegex(ContractError, "state admission/runtime"):
            validate(contract, threat)
        contract, threat = inputs()
        contract["transitions"]["accept_b"]["from"] = ["GPU_FREE"]
        with self.assertRaisesRegex(ContractError, "transition relation"):
            validate(contract, threat)

    def test_modal_cannot_reenter_adapter_scope(self) -> None:
        contract, threat = inputs()
        contract["backends"]["measured_internal"].append("modal")
        with self.assertRaisesRegex(ContractError, "Modal"):
            validate(contract, threat)


if __name__ == "__main__":
    unittest.main()
