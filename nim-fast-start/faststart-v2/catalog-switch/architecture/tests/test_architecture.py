from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

import jsonschema


ARCH_DIR = Path(__file__).resolve().parents[1]
ROOT = ARCH_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location(
    "architecture_validator", ARCH_DIR / "validate_architecture.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ArchitectureValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = VALIDATOR.load_json(ARCH_DIR / "architecture.json")

    def validate(self, document: dict) -> list[str]:
        return VALIDATOR.validate_document(document, ROOT)

    def assert_rejected(self, document: dict, fragment: str) -> None:
        errors = self.validate(document)
        self.assertTrue(errors, "mutation unexpectedly validated")
        self.assertTrue(any(fragment in error for error in errors), errors)

    def test_shipped_document_passes(self) -> None:
        self.assertEqual([], self.validate(copy.deepcopy(self.document)))

    def test_modal_cannot_be_empirical(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["scope"]["empirical_backends"].append("modal")
        self.assert_rejected(mutated, "empirical backends")

    def test_internal_project_allowlist_is_exact(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["scope"]["internal_project_allowlist"] = [
            "project-attacker-1",
            "project-attacker-2",
            "project-attacker-3",
        ]
        self.assert_rejected(mutated, "exact three approved projects")

    def test_modal_cannot_enter_benchmark_matrix(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["benchmark_matrix"][0]["backends"].append("modal")
        self.assert_rejected(mutated, "Modal is forbidden")

    def test_security_evidence_is_bounded_to_internal_backends(self) -> None:
        mutated = copy.deepcopy(self.document)
        security = next(item for item in mutated["evidence"] if item["id"] == "E-SECURITY-001")
        security["applicable_backends"].append("cerebrium")
        self.assert_rejected(mutated, "bounded to internal backends")

    def test_security_evidence_cannot_overstate_internal_coverage(self) -> None:
        mutated = copy.deepcopy(self.document)
        security = next(item for item in mutated["evidence"] if item["id"] == "E-SECURITY-001")
        security["internal_control_count"] = 21
        self.assert_rejected(mutated, "exact source/internal coverage counts")

    def test_provisional_evidence_cannot_be_relabelled_accepted(self) -> None:
        mutated = copy.deepcopy(self.document)
        target = next(item for item in mutated["evidence"] if item["id"] == "E-CEREBRIUM-001")
        target["status"] = "accepted"
        self.assert_rejected(mutated, "evidence status changed")

    def test_cerebrium_security_gate_cannot_be_removed(self) -> None:
        mutated = copy.deepcopy(self.document)
        backend = next(item for item in mutated["backends"] if item["name"] == "cerebrium")
        backend["promotion_gates"].remove("G-CEREBRIUM-SECURITY")
        self.assert_rejected(mutated, "provider-boundary security gate")

    def test_scenario_cannot_be_omitted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["scenarios"].pop()
        self.assert_rejected(mutated, "scenario routing")

    def test_evidence_hash_is_verified(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence"][0]["sha256"] = "0" * 64
        self.assert_rejected(mutated, "sha256 mismatch")

    def test_evidence_source_commit_is_verified(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence"][0]["source_commit"] = "not-a-commit"
        self.assert_rejected(mutated, "source_commit")

    def test_evidence_blob_is_bound_to_source_commit(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence"][0]["source_commit"] = "0180915001fff47fbed0f82292fe32edc40e40ea"
        self.assert_rejected(mutated, "source_commit/path blob does not match sha256")

    def test_evidence_path_cannot_escape_the_checkout(self) -> None:
        mutated = copy.deepcopy(self.document)
        hosts = Path("/etc/hosts").read_bytes()
        mutated["evidence"][0]["path"] = "/etc/hosts"
        mutated["evidence"][0]["sha256"] = hashlib.sha256(hosts).hexdigest()
        mutated["evidence"][0]["source_commit"] = None
        self.assert_rejected(mutated, "contained regular file")

    def test_evidence_claim_cannot_invent_a_production_winner(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["evidence"][0]["allowed_claim"] = "This proves Kubernetes wins production"
        self.assert_rejected(mutated, "forbidden production/winner claim")

    def test_prepared_stage_cannot_be_product_evidence(self) -> None:
        mutated = copy.deepcopy(self.document)
        target = next(
            item
            for item in mutated["evidence"]
            if item["kind"] == "prepared-node-internal-stage"
        )
        target["product_slo_eligible"] = True
        self.assert_rejected(mutated, "prepared-node evidence cannot be product eligible")

    def test_approved_recommendation_needs_accepted_evidence(self) -> None:
        mutated = copy.deepcopy(self.document)
        recommendation = next(
            item for item in mutated["recommendations"] if item["id"] == "R-CEREBRIUM"
        )
        recommendation["status"] = "approved"
        recommendation["evidence_ids"] = ["E-CEREBRIUM-001"]
        self.assert_rejected(mutated, "approved recommendation lacks accepted evidence")

    def test_recommendation_cannot_invent_a_production_winner(self) -> None:
        mutated = copy.deepcopy(self.document)
        recommendation = next(
            item for item in mutated["recommendations"] if item["id"] == "R-METRIC"
        )
        recommendation["statement"] = "Kubernetes is the production winner"
        self.assert_rejected(mutated, "forbidden production/winner claim")

    def test_normative_recommendation_set_is_exact(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["recommendations"].pop()
        self.assert_rejected(mutated, "exact normative v1 set")

    def test_experimental_recommendation_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        recommendation = next(
            item
            for item in mutated["recommendations"]
            if item["id"] == "R-CONTROL-DATA-PLANE"
        )
        recommendation["status"] = "approved"
        self.assert_rejected(mutated, "recommendation status changed")

    def test_backend_cannot_be_promoted(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["backends"][0]["production_disposition"] = "promoted"
        self.assert_rejected(mutated, "no backend may be promoted")

    def test_percentile_sample_gate_cannot_be_weakened(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["metric_contract"]["percentile_minimum_samples"]["p95"] = 3
        self.assert_rejected(mutated, "percentile sample gates changed")

    def test_benchmark_requires_p95_sample_count(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["benchmark_matrix"][0]["attempts_per_homogeneous_cell"] = 19
        self.assert_rejected(mutated, "too few attempts for p95")

    def test_failure_budget_cannot_hide_semantic_errors(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["budgets"]["universal_promotion"]["semantic_invalid_successes_max"] = 1
        self.assert_rejected(mutated, "semantic_invalid_successes_max must remain zero")

    def test_success_rate_cannot_be_disabled(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["budgets"]["universal_promotion"]["success_rate_min"] = 0
        self.assert_rejected(mutated, "success_rate_min must remain 0.99")

    def test_standard_budget_cannot_be_invented(self) -> None:
        mutated = copy.deepcopy(self.document)
        budget = next(
            item
            for item in mutated["budgets"]["latency_classes"]
            if item["name"] == "standard-on-demand"
        )
        budget["p95_seconds_max"] = 90
        self.assert_rejected(mutated, "absolute p95 cannot be invented")

    def test_fast_switch_candidate_cannot_be_relabelled_product_slo(self) -> None:
        mutated = copy.deepcopy(self.document)
        budget = next(
            item
            for item in mutated["budgets"]["latency_classes"]
            if item["name"] == "fast-switch"
        )
        budget["status"] = "approved-product-slo"
        self.assert_rejected(mutated, "unratified provisional candidate")

    def test_prefetch_defaults_off(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["cache_policy"]["prefetch_default"] = "enabled"
        self.assert_rejected(mutated, "prefetch must default disabled")

    def test_eviction_policy_remains_unranked(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["cache_policy"]["eviction"]["status"] = "winner"
        self.assert_rejected(mutated, "eviction policy cannot be ranked")

    def test_gate_references_are_closed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rollout_gates"][0]["requires"].append("UNKNOWN")
        self.assert_rejected(mutated, "unknown requirements")

    def test_contract_gate_requires_exact_accepted_contracts(self) -> None:
        mutated = copy.deepcopy(self.document)
        gate = next(item for item in mutated["rollout_gates"] if item["id"] == "G-CONTRACT")
        gate["requires"] = ["E-CHAOS-PENDING-001"]
        self.assert_rejected(mutated, "exact contract requirements")

    def test_live_gate_cannot_drop_trace_replay(self) -> None:
        mutated = copy.deepcopy(self.document)
        gate = next(item for item in mutated["rollout_gates"] if item["id"] == "G-LIVE-K8S")
        gate["requires"].remove("B-TRACE-REPLAY")
        self.assert_rejected(mutated, "requirements changed from the normative v1 gate")

    def test_backend_cannot_drop_cost_gate(self) -> None:
        mutated = copy.deepcopy(self.document)
        backend = next(item for item in mutated["backends"] if item["name"] == "node-vm")
        backend["promotion_gates"].remove("G-COST")
        self.assert_rejected(mutated, "promotion gates changed")

    def test_independent_review_gate_cannot_be_removed(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["rollout_gates"] = [
            gate
            for gate in mutated["rollout_gates"]
            if gate["id"] != "G-INDEPENDENT-REVIEW"
        ]
        self.assert_rejected(mutated, "exact normative v1 set")

    def test_api_owner_and_fragments_are_required(self) -> None:
        for field, fragment in (
            ("owner", "owner must be"),
            ("request_schema", "request schema is missing or incorrect"),
            ("response_schema", "response schema is missing or incorrect"),
            ("failure_schema", "failure schema is missing or incorrect"),
            ("idempotency", "idempotency semantics are required"),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(self.document)
                del mutated["apis"][0][field]
                self.assert_rejected(mutated, fragment)

    def test_blocker_requires_exit_criteria(self) -> None:
        mutated = copy.deepcopy(self.document)
        mutated["blockers"][0]["exit"] = ""
        self.assert_rejected(mutated, "blocker needs owner and exit criteria")

    def test_product_budget_blocker_cannot_be_substituted(self) -> None:
        mutated = copy.deepcopy(self.document)
        blocker = next(
            item
            for item in mutated["blockers"]
            if item["id"] == "BLK-PRODUCT-BUDGETS"
        )
        blocker["id"] = "BLK-JUNK"
        self.assert_rejected(mutated, "exact normative v1 set")

    def test_all_normative_ids_appear_in_review_docs(self) -> None:
        text = "\n".join(
            (ARCH_DIR / name).read_text(encoding="utf-8")
            for name in ("ADR.md", "EVIDENCE_INDEX.md", "IMPLEMENTATION_ROADMAP.md")
        )
        for collection in ("recommendations", "rollout_gates", "blockers"):
            for item in self.document[collection]:
                self.assertIn(item["id"], text)

    def test_architecture_schema_is_valid_and_applied(self) -> None:
        schema = json.loads((ARCH_DIR / "architecture.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(self.document)

    def test_control_schema_root_rejects_untyped_empty_request(self) -> None:
        schema = json.loads((ARCH_DIR / "control-plane-api.schema.json").read_text())
        validator = jsonschema.Draft202012Validator(schema)
        self.assertFalse(
            validator.is_valid({"operation": "AcceptRequest", "request": {}})
        )

    def test_error_codes_have_stage_specific_terminal_semantics(self) -> None:
        schema = json.loads((ARCH_DIR / "control-plane-api.schema.json").read_text())
        resolver = jsonschema.RefResolver.from_schema(schema)
        error_validator = jsonschema.Draft202012Validator(
            schema["$defs"]["ErrorEnvelope"], resolver=resolver
        )
        attempt_failure_validator = jsonschema.Draft202012Validator(
            schema["$defs"]["AttemptFailureEnvelope"], resolver=resolver
        )
        digest = "sha256:" + "a" * 64
        base = {
            "error_schema_version": "catalog-switch-error/v1",
            "correlation_id": "correlation-1",
            "request_id": "request-1",
            "attempt_id": "attempt-1",
            "operation": "CommitAttempt",
            "stage": "post_accept",
            "idempotency_key": "key-1",
            "terminal": True,
            "error": {
                "code": "cleanup_incomplete",
                "message": "quarantined after product terminal",
                "retryable": False,
                "details_digest": digest,
            },
        }
        self.assertTrue(error_validator.is_valid(base))
        self.assertFalse(attempt_failure_validator.is_valid(base))
        wrong_auth = copy.deepcopy(base)
        wrong_auth["operation"] = "ResolveCatalog"
        wrong_auth["error"]["code"] = "authentication_denied"
        self.assertFalse(error_validator.is_valid(wrong_auth))
        wrong_runtime = copy.deepcopy(base)
        wrong_runtime["operation"] = "ResolveCatalog"
        wrong_runtime["error"]["code"] = "runtime_failed"
        self.assertFalse(error_validator.is_valid(wrong_runtime))
        nonterminal = copy.deepcopy(base)
        nonterminal["terminal"] = False
        self.assertFalse(error_validator.is_valid(nonterminal))

    def test_control_schema_enforces_external_input_and_fallback_order(self) -> None:
        schema = json.loads((ARCH_DIR / "control-plane-api.schema.json").read_text())
        resolver = jsonschema.RefResolver.from_schema(schema)
        digest = "sha256:" + "a" * 64
        accept = {
            "model_id": "model-1",
            "input": {"kind": "inline", "media_type": "application/json", "value": {}},
            "idempotency_key": "key-1",
            "deadline_utc": "2026-08-19T16:00:00Z",
            "tenant_id": "tenant-1",
            "trace_context": {},
        }
        accept_validator = jsonschema.Draft202012Validator(
            schema["$defs"]["AcceptRequestRequest"], resolver=resolver
        )
        self.assertTrue(accept_validator.is_valid(accept))
        self.assertFalse(accept_validator.is_valid({**accept, "artifact_digest": digest}))

        resolution = {
            "catalog_digest": digest,
            "model_id": "model-1",
            "model_version": "v1",
            "workload": "generation",
            "api_contract_digest": digest,
            "input_schema_digest": digest,
            "image_digest": digest,
            "artifact": {"digest": digest, "bytes": 1, "publication_id": "pub-1"},
            "validator_digest": digest,
            "hardware_runtime": {
                "gpu_sku": "gpu-h100-sxm",
                "gpu_count": 1,
                "gpu_memory_gib_min": 80,
                "runtime": "oci",
                "driver_version": "580.1",
                "cuda_version": "13.0",
                "topology_digest": digest,
            },
            "storage": {
                "l1_eligible": True,
                "l2_publication_required": True,
                "writable_state": [],
                "external_mounts": [],
            },
            "snapshot_status": "eligible",
            "checkpoint": {
                "digest": digest,
                "bytes": 1,
                "binding_digest": digest,
                "encrypted": True,
                "signature": "signature",
                "signer_key_id": "key-1",
                "evidence_refs": ["evidence-1"],
            },
            "fallback_ladder": ["conventional", "fail"],
            "policy": {
                "tenant_eligible": True,
                "license_eligible": True,
                "required_secret_refs": [],
                "egress_policy_digest": digest,
                "eligible_backends": ["node-vm"],
            },
        }
        resolution_validator = jsonschema.Draft202012Validator(
            schema["$defs"]["CatalogResolution"], resolver=resolver
        )
        self.assertTrue(resolution_validator.is_valid(resolution))
        self.assertFalse(
            resolution_validator.is_valid(
                {**resolution, "fallback_ladder": ["snapshot"]}
            )
        )
        self.assertFalse(
            resolution_validator.is_valid({**resolution, "checkpoint": None})
        )
        self.assertFalse(
            resolution_validator.is_valid(
                {
                    **resolution,
                    "policy": {
                        **resolution["policy"],
                        "license_eligible": False,
                    },
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
