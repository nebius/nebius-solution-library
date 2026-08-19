from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from performance.k8s_baseline.contract import BaselineError, load_plan
from performance.request_slo.harness import (
    CATALOG_SCHEMA,
    canonical_json,
    file_sha256,
    generate_trace,
    write_canonical_json,
)


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.template = self.root / "target.yaml"
        self.validator = self.root / "validator.py"
        self.request_a = self.root / "request-a.json"
        self.request_b = self.root / "request-b.json"
        self.template.write_text("apiVersion: v1\nkind: Pod\n")
        self.validator.write_text("# pinned validator\n")
        self.request_a.write_text("{}\n")
        self.request_b.write_text("{}\n")
        catalog = {
            "schema": CATALOG_SCHEMA,
            "models": [
                {
                    "model_id": "model-a",
                    "model_version": "v1",
                    "artifact_id": "artifact-a",
                    "artifact_version": "v1",
                    "artifact_sha256": "a" * 64,
                    "input": {
                        "workload_id": "matched",
                        "input_id": "input-a",
                        "payload_sha256": file_sha256(self.request_a),
                        "input_bytes": self.request_a.stat().st_size,
                    },
                },
                {
                    "model_id": "model-b",
                    "model_version": "v1",
                    "artifact_id": "artifact-b",
                    "artifact_version": "v1",
                    "artifact_sha256": "b" * 64,
                    "input": {
                        "workload_id": "matched",
                        "input_id": "input-b",
                        "payload_sha256": file_sha256(self.request_b),
                        "input_bytes": self.request_b.stat().st_size,
                    },
                },
            ],
        }
        trace = generate_trace(
            catalog,
            distribution="adversarial",
            seed=2407,
            request_count=180,
            trace_id="k8s-promoted-matrix",
            interval_ms=1000,
        )
        self.trace_path = self.root / "trace.json"
        write_canonical_json(self.trace_path, trace)
        self.lease_path = self.root / "lease.json"
        self.lease = {
            "schema_version": "catalog-switch-kubernetes-resource-lease/v2",
            "lease_id": "k8s-baseline-test",
            "prefix": "mlsp-csw-k8s-baseline-deadbeef",
            "state": "PLANNED",
            "request": {
                "task_id": "catalog-switch-k8s-baseline",
                "project_id": "project-e00z6b02t8ddk96c49",
                "region": "eu-north1",
                "campaign_arm": "A_prepared_node",
            },
            "cluster_id": None,
            "node_group_ids": [],
            "node_ids": [],
            "resources": [],
        }
        write_canonical_json(self.lease_path, self.lease)
        self.plan_path = self.root / "plan.json"
        self.plan = {
            "schema": "archvteams.nebius.ai/catalog-switch-k8s-baseline-plan/v1",
            "experiment_id": "k8s-baseline-test",
            "task_id": "catalog-switch-k8s-baseline",
            "project_id": "project-e00z6b02t8ddk96c49",
            "region": "eu-north1",
            "backend": "kubernetes",
            "backend_version": "v1-36-3",
            "code_revision": "0" * 40,
            "campaign_arm": "A_prepared_node",
            "boundary_policy": {
                "node_creation": "before_cohort_t0",
                "artifact_localization": "declared_cache_precondition_or_after_t0",
                "model_specific_work": "declared_occupant_precondition_or_after_t0",
            },
            "semantic_calls_per_attempt": 2,
            "product_terminal_call": 1,
            "variant": "per_run_service",
            "precreated_support": [],
            "scenario_strategies": {
                "same_model_hot": "conventional",
                "idle_local": "snapshot",
                "a_to_b_local": "snapshot",
                "a_to_b_remote": "conventional",
                "checkpoint_fallback": "conventional",
                "capacity_miss": "none",
            },
            "promoted_scenarios": [
                "same_model_hot",
                "idle_local",
                "a_to_b_local",
                "a_to_b_remote",
                "checkpoint_fallback",
                "capacity_miss",
            ],
            "minimum_repetitions": 30,
            "trace_path": str(self.trace_path),
            "trace_sha256": file_sha256(self.trace_path),
            "models": [self.model("model-a", "artifact-a", "a" * 64, self.request_a), self.model("model-b", "artifact-b", "b" * 64, self.request_b)],
            "kubernetes": {
                "kubeconfig": str(self.root / "future-kubeconfig"),
                "context": "fresh-k8s-context",
                "expected_server": "https://127.0.0.1:6443",
                "namespace": "mlsp-csw-k8s",
                "node_name": "fresh-h100-node",
                "gpu_type": "H100",
                "gpu_count": 1,
                "sentinel_pod": "gpu-sentinel",
                "ready_timeout_seconds": 900,
                "drain_timeout_seconds": 30,
            },
            "resource_lease": {
                "path": str(self.lease_path),
                "lease_id": self.lease["lease_id"],
                "prefix": self.lease["prefix"],
                "admitted_states": ["PLANNED", "ACTIVE"],
            },
            "cost": {
                "lease_hour_usd": 2.2,
                "transfer_usd_per_gib": 0.01,
                "pre_t0_setup_cost_usd": 0.5,
                "expected_duration_hours": 4,
                "hard_cap_usd": 12,
                "price_snapshot_utc": "2026-08-19T00:00:00Z",
                "source": "immutable broker v2 cost estimate",
            },
            "cleanup": {
                "owner": "codex",
                "deadline_utc": "2026-08-20T00:00:00Z",
                "plan": "Delete exact broker IDs after every admitted variant finishes.",
            },
        }
        self.write_plan()

    def model(self, model_id: str, artifact_id: str, digest: str, request: Path) -> dict:
        return {
            "model_id": model_id,
            "model_version": "v1",
            "artifact_id": artifact_id,
            "artifact_version": "v1",
            "artifact_sha256": digest,
            "image_digest": f"example.invalid/{model_id}@sha256:{digest}",
            "target_templates": {
                "conventional": str(self.template),
                "snapshot": str(self.template),
            },
            "validator_id": f"{model_id}-validator-v1",
            "validator_path": str(self.validator),
            "endpoint_path": "/predict",
            "ready_path": "/ready",
            "request_file": str(request),
            "request_sha256": file_sha256(request),
            "container_name": model_id,
            "artifact_bytes": 1024,
            "image_bytes": 2048,
        }

    def write_plan(self) -> None:
        write_canonical_json(self.plan_path, self.plan)

    def test_valid_plan_freezes_harness_lease_and_thirty_repetitions(self) -> None:
        value = load_plan(self.plan_path)
        self.assertEqual(value["variant"], "per_run_service")
        self.assertTrue(value["_resolved"]["lease_loaded"])

    def test_only_one_precreated_support_change_is_admitted(self) -> None:
        self.plan["variant"] = "precreated_service"
        self.plan["precreated_support"] = ["service", "configmap"]
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "differs from baseline"):
            load_plan(self.plan_path)

    def test_checkpoint_miss_cannot_be_relabelled_snapshot(self) -> None:
        self.plan["scenario_strategies"]["checkpoint_fallback"] = "snapshot"
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "honest conventional"):
            load_plan(self.plan_path)

    def test_project_region_is_fail_closed(self) -> None:
        self.plan["region"] = "us-central1"
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "project and region"):
            load_plan(self.plan_path)

    def test_promoted_cohort_cannot_have_fewer_than_thirty(self) -> None:
        self.plan["minimum_repetitions"] = 29
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "at least 30"):
            load_plan(self.plan_path)

    def test_image_must_be_digest_pinned(self) -> None:
        self.plan["models"][0]["image_digest"] = "example.invalid/model-a:latest"
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "digest-pinned"):
            load_plan(self.plan_path)

    def test_request_digest_drift_is_rejected(self) -> None:
        self.plan["models"][0]["request_sha256"] = "f" * 64
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "request digest"):
            load_plan(self.plan_path)

    def test_live_gate_requires_active_isolated_lease(self) -> None:
        self.plan["kubernetes"]["kubeconfig"] = str(self.request_a)
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "requires an ACTIVE"):
            load_plan(self.plan_path, require_live=True)

    def test_vm_only_broker_lease_is_refused(self) -> None:
        self.lease["schema_version"] = "catalog-switch-resource-lease/v1"
        write_canonical_json(self.lease_path, self.lease)
        with self.assertRaisesRegex(BaselineError, "cluster/node-group"):
            load_plan(self.plan_path)

    def test_arm_b_live_gate_requires_target_neutral_support_only(self) -> None:
        self.plan["campaign_arm"] = "B_new_preemptible_node"
        self.plan["boundary_policy"] = {
            "node_creation": "after_t0",
            "artifact_localization": "after_t0",
            "model_specific_work": "after_t0",
        }
        self.plan["resource_lease"]["admitted_states"] = [
            "PLANNED",
            "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP",
        ]
        self.lease["state"] = "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"
        self.lease["request"]["campaign_arm"] = "B_new_preemptible_node"
        self.lease["cluster_id"] = "mk8scluster-fresh-task-owned"
        self.lease["isolation_proof"] = {"fresh": True, "task_owned": True}
        write_canonical_json(self.lease_path, self.lease)
        self.write_plan()
        value = load_plan(self.plan_path, require_live=True)
        self.assertEqual(value["campaign_arm"], "B_new_preemptible_node")

    def test_arm_b_forbids_all_pre_t0_creation_localization_and_model_work(self) -> None:
        self.plan["campaign_arm"] = "B_new_preemptible_node"
        self.plan["boundary_policy"] = {
            "node_creation": "after_t0",
            "artifact_localization": "after_t0",
            "model_specific_work": "before_t0",
        }
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, "T0 boundary policy"):
            load_plan(self.plan_path)

    def test_plan_is_canonical(self) -> None:
        value = json.loads(self.plan_path.read_text())
        self.plan_path.write_text(json.dumps(value, indent=2) + "\n")
        with self.assertRaisesRegex(BaselineError, "canonical JSON"):
            load_plan(self.plan_path)


if __name__ == "__main__":
    unittest.main()
