from __future__ import annotations

import copy
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from performance.k8s_baseline.cli import _finalize_live, _run_live, _smoke_catalog
from performance.k8s_baseline.contract import BaselineError
from performance.k8s_baseline.controller import ScriptedBackend, run_trace
from performance.k8s_baseline.sealing import (
    atomic_write_json,
    file_sha256,
    seal_run,
    seal_staging,
    verify_seal,
)
from performance.k8s_baseline.stratification import (
    _distribution,
    require_promotion_cohorts,
    require_single_promotion_cohort,
    stratify_aggregate,
    validate_broker_release,
)
from performance.request_slo.harness import (
    aggregate_ledger,
    canonical_sha256,
    generate_trace,
    load_ledger,
)


def _provider_receipt(root: Path, name: str, core: dict) -> dict:
    path = root / f"provider-{name}.json"
    atomic_write_json(path, core)
    return {**core, "evidence_path": str(path), "evidence_sha256": file_sha256(path)}


def released_cleanup(root: Path) -> dict:
    cost_estimate = {
        "currency": "USD", "lease_hour_usd": 2.2, "transfer_usd_per_gib": 0.01,
        "pre_t0_setup_cost_usd": 0.5, "expected_duration_hours": 4,
        "hard_cap_usd": 12,
    }
    absence = _provider_receipt(root, "absence", {
        "schema": "archvteams.nebius.ai/exact-resource-absence/v1",
        "lease_id": "lease-1", "status": "ALL_NOT_FOUND",
        "resource_ids": ["node-1", "resource-1"],
        "observed_at_utc": "2026-08-19T01:00:00Z",
    })
    actual_cost = _provider_receipt(root, "actual-cost", {
        "schema": "archvteams.nebius.ai/broker-actual-cost/v1",
        "lease_id": "lease-1", "status": "FINAL", "currency": "USD",
        "actual_cost_usd": 3.0, "billed_seconds": 3600.0, "transfer_bytes": 1024,
        "request_sha256": "d" * 64,
        "rate_contract_sha256": canonical_sha256(cost_estimate),
        "hard_cost_cap_usd": 12,
    })
    provider_children = _provider_receipt(root, "provider-children", {
        "schema": "archvteams.nebius.ai/provider-child-absence/v1",
        "lease_id": "lease-1", "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1", "status": "ALL_NOT_FOUND",
        "discovery_complete": True, "discovered_child_ids": ["provider-child-1"],
        "not_found_child_ids": ["provider-child-1"], "remaining_child_ids": [],
        "observed_at_utc": "2026-08-19T01:00:00Z",
    })
    credential_revocation = _provider_receipt(root, "credential-revocation", {
        "schema": "archvteams.nebius.ai/credential-revocation/v1",
        "lease_id": "lease-1", "secret_uid": "secret-uid-1",
        "scope_sha256": "7" * 64, "original_receipt_sha256": "8" * 64,
        "status": "REVOKED", "secret_not_found": True,
        "external_token_status": "REVOKED",
        "revoked_at_utc": "2026-08-19T01:00:00Z",
    })
    gpu_zero = _provider_receipt(root, "gpu-zero", {
        "schema": "archvteams.nebius.ai/final-gpu-zero/v1",
        "lease_id": "lease-1", "node_id": "node-1", "status": "PASS",
        "compute_process_count": 0, "observed_memory_bytes": 0,
        "baseline_memory_bytes": 0, "observed_at_utc": "2026-08-19T00:59:00Z",
    })
    receipt_hashes = {
        "gpu_zero_receipt_sha256": canonical_sha256(gpu_zero),
        "credential_revocation_receipt_sha256": canonical_sha256(credential_revocation),
        "provider_children_receipt_sha256": canonical_sha256(provider_children),
        "exact_absence_receipt_sha256": canonical_sha256(absence),
        "actual_cost_receipt_sha256": canonical_sha256(actual_cost),
    }
    operations = [
        ("lease.gpu_zero", "gpu_zero_receipt_sha256"),
        ("lease.credential_revoked", "credential_revocation_receipt_sha256"),
        ("lease.provider_children_absent", "provider_children_receipt_sha256"),
        ("lease.resources_absent", "exact_absence_receipt_sha256"),
        ("lease.cost_finalized", "actual_cost_receipt_sha256"),
    ]
    previous = "e" * 64
    events = []
    for offset, (operation, receipt_name) in enumerate(operations):
        core = {
            "sequence": 2 + offset, "previous_sha256": previous,
            "payload": {
                "operation": operation, "lease_id": "lease-1",
                "receipt_sha256": receipt_hashes[receipt_name],
            },
        }
        event = {**core, "event_sha256": canonical_sha256(core)}
        events.append(event)
        previous = event["event_sha256"]
    events_path = root / "provider-final-audit-events.json"
    atomic_write_json(events_path, events)
    audit = {
        "schema": "archvteams.nebius.ai/broker-final-audit-extension/v1",
        "lease_id": "lease-1", "chain_id": "audit-chain-1",
        "previous_head_sha256": "e" * 64, "first_sequence": 2,
        "event_count": len(events), "events_path": str(events_path),
        "events_sha256": file_sha256(events_path), "head_sha256": previous,
    }
    return {
        "schema": "archvteams.nebius.ai/k8s-broker-final-cleanup/v2",
        "status": "PASS", "lease_id": "lease-1", "lease_state": "RELEASED",
        "lease_cleanup_required": False, "final_resource_state": "ABSENT",
        "exact_absence_receipt": absence,
        "exact_absence_receipt_sha256": receipt_hashes["exact_absence_receipt_sha256"],
        "actual_cost_receipt": actual_cost,
        "actual_cost_receipt_sha256": receipt_hashes["actual_cost_receipt_sha256"],
        "provider_children_receipt": provider_children,
        "provider_children_receipt_sha256": receipt_hashes["provider_children_receipt_sha256"],
        "credential_revocation_receipt": credential_revocation,
        "credential_revocation_receipt_sha256": receipt_hashes["credential_revocation_receipt_sha256"],
        "gpu_zero_receipt": gpu_zero,
        "gpu_zero_receipt_sha256": receipt_hashes["gpu_zero_receipt_sha256"],
        "audit_extension_receipt": audit,
        "audit_extension_receipt_sha256": canonical_sha256(audit),
    }


def expected_lease() -> dict:
    return {
        "lease_id": "lease-1", "request_sha256": "d" * 64,
        "project_id": "project-e00z6b02t8ddk96c49", "region": "eu-north1",
        "cost_estimate": {
            "currency": "USD", "lease_hour_usd": 2.2,
            "transfer_usd_per_gib": 0.01, "pre_t0_setup_cost_usd": 0.5,
            "expected_duration_hours": 4, "hard_cap_usd": 12,
        },
        "credential": {
            "secret_uid": "secret-uid-1", "scope_sha256": "7" * 64,
            "receipt_sha256": "8" * 64, "revoke_by_utc": "2026-08-20T00:00:00Z",
        },
        "audit_chain": {
            "chain_id": "audit-chain-1", "genesis_sha256": "4" * 64,
            "head_sha256": "e" * 64, "event_count": 2,
        },
        "resources": [
            {"kind": "node", "id": "node-1"},
            {"kind": "cluster", "id": "resource-1"},
        ],
    }


class SealingAndStratificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.provider_root = Path(self.temporary.name)

    def test_broker_release_reconciles_node_children_cost_billing_and_bytes(self) -> None:
        aggregate = {
            "raw_global_bookkeeping": {
                "gpu_active_seconds_total": 3000.0,
                "gpu_idle_seconds_total": 100.0,
                "bytes_moved_total": 1024,
            }
        }
        cleanup = released_cleanup(self.provider_root)
        validate_broker_release(
            cleanup, expected_lease=expected_lease(), expected_aggregate=aggregate
        )
        adversaries = []
        under_billed = copy.deepcopy(cleanup)
        under_billed["actual_cost_receipt"]["billed_seconds"] = 3000.0
        under_billed["actual_cost_receipt_sha256"] = canonical_sha256(
            under_billed["actual_cost_receipt"]
        )
        adversaries.append(under_billed)
        under_cost = copy.deepcopy(cleanup)
        under_cost["actual_cost_receipt"]["actual_cost_usd"] = 0.0
        under_cost["actual_cost_receipt_sha256"] = canonical_sha256(
            under_cost["actual_cost_receipt"]
        )
        adversaries.append(under_cost)
        over_cap = copy.deepcopy(cleanup)
        over_cap["actual_cost_receipt"]["actual_cost_usd"] = 13.0
        over_cap["actual_cost_receipt_sha256"] = canonical_sha256(
            over_cap["actual_cost_receipt"]
        )
        adversaries.append(over_cap)
        wrong_node = copy.deepcopy(cleanup)
        wrong_node["gpu_zero_receipt"]["node_id"] = "foreign-node"
        wrong_node["gpu_zero_receipt_sha256"] = canonical_sha256(
            wrong_node["gpu_zero_receipt"]
        )
        adversaries.append(wrong_node)
        child_remaining = copy.deepcopy(cleanup)
        child_remaining["provider_children_receipt"]["remaining_child_ids"] = [
            "provider-child-1"
        ]
        child_remaining["provider_children_receipt_sha256"] = canonical_sha256(
            child_remaining["provider_children_receipt"]
        )
        adversaries.append(child_remaining)
        active_credential = copy.deepcopy(cleanup)
        active_credential["credential_revocation_receipt"]["status"] = "ACTIVE"
        active_credential["credential_revocation_receipt_sha256"] = canonical_sha256(
            active_credential["credential_revocation_receipt"]
        )
        adversaries.append(active_credential)
        wrong_secret = copy.deepcopy(cleanup)
        wrong_secret["credential_revocation_receipt"]["secret_uid"] = "foreign-secret"
        wrong_secret["credential_revocation_receipt_sha256"] = canonical_sha256(
            wrong_secret["credential_revocation_receipt"]
        )
        adversaries.append(wrong_secret)
        late_revocation = copy.deepcopy(cleanup)
        late_revocation["credential_revocation_receipt"]["revoked_at_utc"] = (
            "2026-08-21T00:00:00Z"
        )
        late_revocation["credential_revocation_receipt_sha256"] = canonical_sha256(
            late_revocation["credential_revocation_receipt"]
        )
        adversaries.append(late_revocation)
        invalid_child_time = copy.deepcopy(cleanup)
        invalid_child_time["provider_children_receipt"]["observed_at_utc"] = "not-a-time"
        invalid_child_time["provider_children_receipt_sha256"] = canonical_sha256(
            invalid_child_time["provider_children_receipt"]
        )
        adversaries.append(invalid_child_time)
        self_asserted = copy.deepcopy(cleanup)
        for name in (
            "exact_absence_receipt", "actual_cost_receipt", "provider_children_receipt",
            "credential_revocation_receipt", "gpu_zero_receipt",
        ):
            self_asserted[name].pop("evidence_path", None)
            self_asserted[name]["evidence_sha256"] = "a" * 64
            self_asserted[name + "_sha256"] = canonical_sha256(self_asserted[name])
        adversaries.append(self_asserted)
        for value in adversaries:
            with self.assertRaisesRegex(
                BaselineError, "broker RELEASED|provider evidence|source-bound"
            ):
                validate_broker_release(
                    value, expected_lease=expected_lease(), expected_aggregate=aggregate
                )

    def test_typed_broker_release_finalizes_a_new_seal_without_overwriting_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging"
            staging.mkdir()
            (staging / "ledger.jsonl").write_text("{}\n")
            workload_cleanup = {"status": "WORKLOAD_PASS_BROKER_RELEASE_REQUIRED"}
            atomic_write_json(
                staging / "backend-evidence.json",
                {"events": [], "final_cleanup": workload_cleanup},
            )
            atomic_write_json(staging / "aggregate.json", {"schema": "test-aggregate"})
            atomic_write_json(
                staging / "cohort-cleanup.json",
                workload_cleanup,
            )
            staged = seal_staging(
                staging,
                receipt_payload={
                    "status": "STAGED_AWAITING_BROKER_RELEASE",
                    "promotion_allowed": False,
                    "expected_broker_lease": expected_lease(),
                },
                ledger_path=staging / "ledger.jsonl",
                evidence_path=staging / "backend-evidence.json",
                aggregate_path=staging / "aggregate.json",
                cleanup_path=staging / "cohort-cleanup.json",
            )
            cleanup = root / "broker-final-cleanup.json"
            atomic_write_json(cleanup, released_cleanup(self.provider_root))
            output = root / "final"
            result = _finalize_live(
                SimpleNamespace(
                    staging_dir=staging, broker_final_cleanup=cleanup,
                    output_dir=output, promote=False,
                )
            )
            self.assertEqual(result["status"], "FINAL")
            self.assertEqual(
                result["workload_staging_seal_sha256"], staged["evidence_seal_sha256"]
            )
            self.assertEqual(
                verify_seal(output)["schema"],
                "archvteams.nebius.ai/k8s-evidence-seal/v2",
            )
            self.assertEqual(
                verify_seal(staging)["schema"],
                "archvteams.nebius.ai/k8s-workload-staging-seal/v1",
            )
            blocked = root / "blocked-promotion"
            with self.assertRaisesRegex(BaselineError, "pair-handoff/rearm"):
                _finalize_live(
                    SimpleNamespace(
                        staging_dir=staging, broker_final_cleanup=cleanup,
                        output_dir=blocked, promote=True,
                    )
                )
            blocked_receipt = __import__("json").loads(
                (blocked / "receipt.json").read_text()
            )
            self.assertFalse(blocked_receipt["promotion_allowed"])
            self.assertIsNone(blocked_receipt["comparison_attestation"])
            (self.provider_root / "provider-gpu-zero.json").write_text("{}\n")
            with self.assertRaisesRegex(BaselineError, "provider evidence"):
                verify_seal(output)

    def test_failed_live_run_is_cleaned_and_jointly_sealed_before_error(self) -> None:
        class FailedBackend:
            def __init__(self, plan):
                self.plan = plan
                self.lease = {**expected_lease(), "state": "ACTIVE"}
                self._events = []
                self._final_cleanup_receipt = None

            def _record(self, operation, **data):
                self._events.append({"operation": operation, **data})

            def final_cleanup(self):
                value = {"status": "PASS", "schema": "cleanup", "lease_cleanup_required": True}
                self._final_cleanup_receipt = value
                return value

            def write_evidence(self, path):
                atomic_write_json(
                    path,
                    {"events": self._events, "final_cleanup": self._final_cleanup_receipt},
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = generate_trace(
                _smoke_catalog(), distribution="adversarial", seed=11, request_count=1,
                trace_id="failed-live-seal", interval_ms=1,
            )
            trace_path = root / "trace.json"
            atomic_write_json(trace_path, trace)
            output = root / "failed-output"
            plan = {
                "campaign_arm": "A_prepared_node",
                "experiment_id": "failed-live-seal",
                "variant": "per_run_service",
                "security": {
                    "credentials": {
                        "secret_uid": "secret-uid-1", "scope_sha256": "7" * 64,
                        "receipt_sha256": "8" * 64,
                        "revoke_by_utc": "2026-08-20T00:00:00Z",
                    }
                },
                "trace_sha256": file_sha256(trace_path),
                "_admitted_sources": {
                    "trace": trace_path.read_text(),
                    "lease": None,
                },
                "_resolved": {"trace_path": str(trace_path), "config_sha256": "e" * 64},
            }
            atomic_write_json(root / "plan.json", {})
            args = SimpleNamespace(
                execute=True, output_dir=output, plan=root / "plan.json", promote=False
            )
            with (
                patch("performance.k8s_baseline.cli.load_plan", return_value=plan),
                patch("performance.k8s_baseline.cli.KubernetesBackend", FailedBackend),
                patch(
                    "performance.k8s_baseline.cli.run_trace",
                    side_effect=BaselineError("controller fault"),
                ),
            ):
                with self.assertRaisesRegex(BaselineError, "workload failed and evidence was staged"):
                    _run_live(args)
            manifest = verify_seal(output)
            self.assertEqual(
                manifest["schema"],
                "archvteams.nebius.ai/k8s-workload-staging-seal/v1",
            )
            self.assertEqual(
                manifest["files"]["cohort-cleanup.json"],
                file_sha256(output / "cohort-cleanup.json"),
            )
            receipt = __import__("json").loads((output / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "STAGED_FAILED_AWAITING_BROKER_RELEASE")
            cleanup = root / "broker-final-cleanup.json"
            atomic_write_json(cleanup, released_cleanup(self.provider_root))
            final = root / "failed-final"
            result = _finalize_live(
                SimpleNamespace(
                    staging_dir=output, broker_final_cleanup=cleanup,
                    output_dir=final, promote=False, comparison_contract=None,
                )
            )
            self.assertEqual(result["status"], "FINAL_UNPROMOTABLE_FAILED")
            self.assertFalse(result["promotion_allowed"])

    def test_qualification_rows_are_exact_complete_and_unique(self) -> None:
        trace = generate_trace(
            _smoke_catalog(), distribution="adversarial", seed=10, request_count=6,
            trace_id="qualification-integrity", interval_ms=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = run_trace(
                trace, ScriptedBackend(), root / "ledger", root / "evidence",
                ledger_id="qualification-integrity-ledger",
            )
            events = load_ledger(root / "ledger")
            raw = aggregate_ledger(events, trace)
            missing = {
                **receipt["two_call_qualification"],
                "attempts": receipt["two_call_qualification"]["attempts"][:-1],
            }
            with self.assertRaisesRegex(BaselineError, "does not retain every offered"):
                stratify_aggregate(
                    raw, trace, plan=None, qualification=missing,
                    classification="synthetic", events=events,
                )
            duplicate = {
                **receipt["two_call_qualification"],
                "attempts": [
                    *receipt["two_call_qualification"]["attempts"],
                    receipt["two_call_qualification"]["attempts"][0],
                ],
            }
            with self.assertRaisesRegex(BaselineError, "foreign or duplicate"):
                stratify_aggregate(
                    raw, trace, plan=None, qualification=duplicate,
                    classification="synthetic", events=events,
                )
            forged_cleanup = {
                **receipt["two_call_qualification"],
                "cleanup_receipts": [
                    {**item, "receipt": {**item["receipt"], "retained": ["forged"]}}
                    if index == 0 else item
                    for index, item in enumerate(
                        receipt["two_call_qualification"]["cleanup_receipts"]
                    )
                ],
            }
            with self.assertRaisesRegex(BaselineError, "receipt body differs"):
                stratify_aggregate(
                    raw, trace, plan=None, qualification=forged_cleanup,
                    classification="synthetic", events=events,
                )

            forged_raw = copy.deepcopy(raw)
            forged_raw["attempts"]["results"][0]["success"] = False
            forged_raw["attempts"]["results"][0]["failure_class"] = "runtime"
            forged_raw["attempts"]["valid_responses"] -= 1
            forged_raw["attempts"]["failures"] += 1
            with self.assertRaisesRegex(
                BaselineError, "successful first semantic terminal"
            ):
                stratify_aggregate(
                    forged_raw, trace, plan=None,
                    qualification=receipt["two_call_qualification"],
                    classification="synthetic", events=events,
                )

    def test_promotion_requires_call2_cleanup_accounting_final_cleanup_and_seal(self) -> None:
        results = [
            {
                "attempt_id": f"attempt-{index}", "success": True,
                "terminal_seconds": 1.0 + index / 1000,
            }
            for index in range(30)
        ]
        cohort = {
            "attempts": {
                "offered": 30, "valid_responses": 30, "failures": 0,
                "results": results,
            },
            "request_to_first_semantic_validation_seconds": _distribution(
                [item["terminal_seconds"] for item in results]
            ),
            "two_semantic_qualification": {"offered": 30, "qualified": 30},
            "integrity": {
                "cleanup_admitted": 30, "cleanup_failed_or_unreceipted": 0,
                "accounting_failure_sentinel_count": 0,
            },
        }
        aggregate = {
            "promotion": {"minimum_offered_and_qualified": 30},
            "strata": [cohort],
        }
        released = released_cleanup(self.provider_root)
        self.assertIs(
            require_single_promotion_cohort(
                aggregate, final_cleanup=released, seal_verified=True
            ),
            cohort,
        )
        cohort["two_semantic_qualification"]["qualified"] = 29
        with self.assertRaisesRegex(BaselineError, "two-semantically-qualified"):
            require_single_promotion_cohort(
                aggregate, final_cleanup=released, seal_verified=True
            )
        cohort["two_semantic_qualification"]["qualified"] = 30
        failed = copy.deepcopy(cohort)
        for item in failed["attempts"]["results"]:
            item["success"] = False
            item["failure_class"] = "runtime"
        failed["attempts"]["valid_responses"] = 0
        failed["attempts"]["failures"] = 30
        failed["request_to_first_semantic_validation_seconds"] = _distribution([])
        aggregate["strata"] = [failed]
        with self.assertRaisesRegex(BaselineError, "first- and two-semantically-qualified"):
            require_single_promotion_cohort(
                aggregate, final_cleanup=released, seal_verified=True
            )
        aggregate["strata"] = [cohort]
        cohort["integrity"]["accounting_failure_sentinel_count"] = 1
        with self.assertRaisesRegex(BaselineError, "cleanup and accounting"):
            require_single_promotion_cohort(
                aggregate, final_cleanup=released, seal_verified=True
            )
        cohort["integrity"]["accounting_failure_sentinel_count"] = 0
        with self.assertRaisesRegex(BaselineError, "broker RELEASED"):
            require_single_promotion_cohort(
                aggregate,
                final_cleanup={
                    **released, "lease_state": "ACTIVE", "lease_cleanup_required": True,
                },
                seal_verified=True,
            )
        forged_release = copy.deepcopy(released)
        forged_release["actual_cost_receipt"]["actual_cost_usd"] = 0.0
        with self.assertRaisesRegex(BaselineError, "broker RELEASED"):
            require_single_promotion_cohort(
                aggregate, final_cleanup=forged_release, seal_verified=True
            )
        with self.assertRaisesRegex(BaselineError, "verified joint seal"):
            require_single_promotion_cohort(
                aggregate, final_cleanup=released, seal_verified=False
            )

    def test_two_model_campaign_promotes_each_exact_stratum_without_pooling(self) -> None:
        def cohort(model_id: str) -> dict:
            results = [
                {
                    "attempt_id": f"{model_id}-{index}", "success": True,
                    "terminal_seconds": 2.0 + index / 1000,
                }
                for index in range(30)
            ]
            return {
                "key": {"model_id": model_id},
                "attempts": {
                    "offered": 30, "valid_responses": 30, "failures": 0,
                    "results": results,
                },
                "request_to_first_semantic_validation_seconds": _distribution(
                    [item["terminal_seconds"] for item in results]
                ),
                "two_semantic_qualification": {"offered": 30, "qualified": 30},
                "integrity": {
                    "cleanup_admitted": 30, "cleanup_failed_or_unreceipted": 0,
                    "accounting_failure_sentinel_count": 0,
                },
            }

        aggregate = {
            "promotion": {
                "minimum_offered_and_qualified": 30,
                "mixed_headline_percentile": None,
                "mixed_promotion_allowed": False,
            },
            "strata": [cohort("boltz2"), cohort("openfold2")],
        }
        released = released_cleanup(self.provider_root)
        promoted = require_promotion_cohorts(
            aggregate, final_cleanup=released, seal_verified=True
        )
        self.assertEqual([item["key"]["model_id"] for item in promoted], ["boltz2", "openfold2"])
        self.assertIsNone(aggregate["promotion"]["mixed_headline_percentile"])

    def test_mixed_models_have_no_pooled_promotion_percentile(self) -> None:
        trace = generate_trace(
            _smoke_catalog(), distribution="adversarial", seed=9, request_count=24,
            trace_id="mixed-strata", interval_ms=20,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = ScriptedBackend()
            receipt = run_trace(
                trace, backend, root / "ledger", root / "evidence", ledger_id="mixed-ledger"
            )
            events = load_ledger(root / "ledger")
            value = stratify_aggregate(
                aggregate_ledger(events, trace), trace,
                plan=None, qualification=receipt["two_call_qualification"],
                classification=backend.classification,
                events=events,
            )
            self.assertGreater(len(value["strata"]), 1)
            self.assertIsNone(value["promotion"]["mixed_headline_percentile"])
            self.assertNotIn("product_latency_seconds", value)
            with self.assertRaisesRegex(BaselineError, "mixed aggregate"):
                require_single_promotion_cohort(value)

    def test_final_cleanup_evidence_aggregate_and_receipt_are_jointly_sealed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ledger.jsonl").write_text('{"event":"durable"}\n')
            atomic_write_json(root / "cohort-cleanup.json", {"status": "PASS"})
            atomic_write_json(
                root / "backend-evidence.json",
                {"events": [{"operation": "final_cleanup", "status": "PASS"}]},
            )
            atomic_write_json(root / "aggregate.json", {"strata": [], "pooled": None})
            payload = {
                "ledger_sha256": file_sha256(root / "ledger.jsonl"),
                "backend_evidence_sha256": file_sha256(root / "backend-evidence.json"),
                "aggregate_sha256": file_sha256(root / "aggregate.json"),
                "cohort_cleanup_sha256": file_sha256(root / "cohort-cleanup.json"),
            }
            seal_run(
                root, receipt_payload=payload, ledger_path=root / "ledger.jsonl",
                evidence_path=root / "backend-evidence.json", aggregate_path=root / "aggregate.json",
                cleanup_path=root / "cohort-cleanup.json",
            )
            self.assertEqual(verify_seal(root)["files"]["backend-evidence.json"], payload["backend_evidence_sha256"])
            (root / "backend-evidence.json").write_text('{"events":[]}\n')
            with self.assertRaisesRegex(BaselineError, "drifted"):
                verify_seal(root)

    def test_stale_receipt_hash_is_rejected_even_when_files_match_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ledger.jsonl").write_text("x\n")
            for name in ("backend-evidence.json", "aggregate.json", "cohort-cleanup.json"):
                atomic_write_json(root / name, {"name": name})
            with self.assertRaisesRegex(BaselineError, "stale"):
                seal_run(
                    root,
                    receipt_payload={
                        "ledger_sha256": file_sha256(root / "ledger.jsonl"),
                        "backend_evidence_sha256": "0" * 64,
                    },
                    ledger_path=root / "ledger.jsonl", evidence_path=root / "backend-evidence.json",
                    aggregate_path=root / "aggregate.json", cleanup_path=root / "cohort-cleanup.json",
                )


if __name__ == "__main__":
    unittest.main()
