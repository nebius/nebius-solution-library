from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from performance.k8s_baseline.build_trace import build_trace
from performance.k8s_baseline.contract import (
    BaselineError,
    _validate_resource_graph,
    admitted_document,
    load_plan,
)
from performance.k8s_baseline.contract import (
    FROZEN_METRIC_FILES,
    RUNTIME_ROOT,
    THREAT_MARKDOWN_PATH,
    THREAT_MARKDOWN_SHA256,
    THREAT_MODEL_PATH,
    THREAT_MODEL_SHA256,
    THREAT_VALIDATOR_PATH,
    THREAT_VALIDATOR_SHA256,
    _validate_security,
    _validate_live_source_revision,
)
from performance.k8s_baseline.kubernetes_backend import KubernetesBackend
from performance.request_slo.harness import (
    CATALOG_SCHEMA,
    canonical_sha256,
    file_sha256,
    write_canonical_json,
)


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.template = self.root / "target.yaml"
        self.validator = self.root / "validator.py"
        self.payload = self.root / "payload.json"
        self.request_a = self.root / "request-a.json"
        self.request_b = self.root / "request-b.json"
        self.threat = self.root / "threat.json"
        self.credential = self.root / "credential.json"
        self.scope_manifest = self.root / "registry-scope.json"
        self.support_receipt = self.root / "support-image-source.json"
        self.support_build_source = self.root / "support-image-build-source.txt"
        self.runtime_sources = self.root / "runtime-sources.json"
        self.metric = self.root / "request-slo-freeze.json"
        self.initial_evidence = self.root / "initial-state-evidence.json"
        self.isolation_evidence = self.root / "isolation-evidence.json"
        self.audit_events = self.root / "audit-events.json"
        self.trace_path = self.root / "trace.json"
        self.lease_path = self.root / "lease.json"
        self.plan_path = self.root / "plan.json"
        self.template.write_text("apiVersion: v1\nkind: Pod\n")
        self.validator.write_text("# pinned validator\n")
        self.support_build_source.write_text("reviewed support image build source\n")
        self.payload.write_text("{}\n")
        write_canonical_json(
            self.metric,
            {
                "schema": "archvteams.nebius.ai/request-slo-contract-freeze/v1",
                "source_reviewed_commit": "ba49c9e20f194e0f419d4209608904cc9335219d",
                "integrated_commit": "138c52fe3d3371b2d84bb3d0b2e770601ebc5609",
                "files": {
                    name: file_sha256(RUNTIME_ROOT / name)
                    for name in sorted(FROZEN_METRIC_FILES)
                },
            },
        )
        write_canonical_json(
            self.credential,
            {
                "schema": "archvteams.nebius.ai/k8s-registry-credential-receipt/v1",
                "status": "ACTIVE", "owner_task_id": "catalog-switch-k8s-baseline",
                "secret_name": "ngc-task-owned", "secret_uid": "secret-uid-1",
                "registry": "nvcr.io", "scope_sha256": "7" * 64,
                "scope_manifest_sha256": "0" * 64,
                "issued_at_utc": "2026-08-19T00:00:00Z",
                "expires_at_utc": "2026-08-20T00:00:00Z",
                "revoke_by_utc": "2026-08-20T01:00:00Z",
                "revocation_scope": "exact-secret-uid-only",
                "source": "catalog-switch-resource-broker-v2",
                "audit_chain_id": "audit-chain-1",
            },
        )
        for path, input_id in ((self.request_a, "input-a"), (self.request_b, "input-b")):
            write_canonical_json(
                path,
                {
                    "schema": "archvteams.nebius.ai/two-semantic-inference-bundle/v1",
                    "calls": [
                        {
                            "input_id": f"{input_id}-1", "payload_path": str(self.payload),
                            "payload_sha256": file_sha256(self.payload), "overrides": {},
                        },
                        {
                            "input_id": f"{input_id}-2", "payload_path": str(self.payload),
                            "payload_sha256": file_sha256(self.payload), "overrides": {},
                        },
                    ],
                },
            )
        long_version = "sha256:" + "1" * 64
        catalog = {
            "schema": CATALOG_SCHEMA,
            "models": [
                self.catalog_model("boltz2", long_version, "artifact-a", "a" * 64, self.request_a),
                self.catalog_model("openfold2", "v1", "artifact-b", "b" * 64, self.request_b),
            ],
        }
        trace = build_trace(
            catalog, scenario="a_to_b_local", seed=2407, request_count=60,
            trace_id="contract-trace", interval_ms=100,
        )
        write_canonical_json(self.trace_path, trace)
        self.plan = self.base_plan(catalog)
        write_canonical_json(
            self.support_receipt,
            {
                "schema": "archvteams.nebius.ai/k8s-support-image-source-receipt/v1",
                "status": "REVIEWED", "owner_task_id": self.plan["task_id"],
                "build_source_commit": "1" * 40,
                "receipt_commit": "2" * 40,
                "build_source_path": str(self.support_build_source),
                "build_source_sha256": file_sha256(self.support_build_source),
                "images": {
                    "readiness_gate": self.plan["security"]["support_images"][
                        "readiness_gate_digest"
                    ],
                    "sentinel": self.plan["security"]["support_images"]["sentinel_digest"],
                },
            },
        )
        self.plan["security"]["support_images"]["source_receipt_sha256"] = file_sha256(
            self.support_receipt
        )
        scoped_images = sorted(
            {
                *(item["image_digest"] for item in self.plan["models"]),
                self.plan["security"]["support_images"]["sentinel_digest"],
                self.plan["security"]["support_images"]["readiness_gate_digest"],
            }
        )
        scope_value = {
            "schema": "archvteams.nebius.ai/registry-scope-manifest/v1",
            "owner_task_id": self.plan["task_id"], "registry": "nvcr.io",
            "secret_uid": self.plan["security"]["credentials"]["secret_uid"],
            "namespace": self.plan["kubernetes"]["namespace"],
            "repositories": sorted({item.split("@", 1)[0] for item in scoped_images}),
            "image_digests": scoped_images,
        }
        write_canonical_json(self.scope_manifest, scope_value)
        scope_sha256 = canonical_sha256(scope_value)
        credential_receipt = json.loads(self.credential.read_text())
        credential_receipt["scope_sha256"] = scope_sha256
        credential_receipt["scope_manifest_sha256"] = file_sha256(self.scope_manifest)
        write_canonical_json(self.credential, credential_receipt)
        self.plan["security"]["credentials"]["scope_sha256"] = scope_sha256
        self.plan["security"]["credentials"]["scope_manifest_sha256"] = file_sha256(
            self.scope_manifest
        )
        self.plan["security"]["credentials"]["receipt_sha256"] = file_sha256(self.credential)
        self.write_runtime_sources()
        self.reseal_lease()
        self.write_plan()

    def catalog_model(
        self, model_id: str, version: str, artifact_id: str, digest: str, request: Path
    ) -> dict:
        return {
            "model_id": model_id,
            "model_version": version,
            "artifact_id": artifact_id,
            "artifact_version": "v1",
            "artifact_sha256": digest,
            "input": {
                "workload_id": "matched",
                "input_id": f"{model_id}-bundle",
                "payload_sha256": file_sha256(request),
                "input_bytes": request.stat().st_size,
            },
        }

    def executable_model(self, catalog: dict, request: Path, label: str) -> dict:
        model = {
            **catalog,
            "version_label": label,
            "image_digest": f"nvcr.io/nim/{catalog['model_id']}@sha256:{catalog['artifact_sha256']}",
            "gpu_profile": "h100-single",
            "strategy_eligibility": {},
            "target_templates": {
                "conventional": {"path": str(self.template), "sha256": file_sha256(self.template)},
                "snapshot": {"path": str(self.template), "sha256": file_sha256(self.template)},
            },
            "semantic_oracle": {
                "validator_id": f"{catalog['model_id']}-validator-v1",
                "validator_path": str(self.validator),
                "validator_sha256": file_sha256(self.validator),
            },
            "validator_adapter": f"{catalog['model_id']}-v1",
            "checkpoint": {
                "checkpoint_id": f"{catalog['model_id']}-checkpoint-v1",
                "checkpoint_sha256": "c" * 64,
                "checkpoint_bytes": 4096,
            },
            "endpoint_path": "/predict", "ready_path": "/ready",
            "request_file": str(request), "request_sha256": file_sha256(request),
            "container_name": catalog["model_id"], "artifact_bytes": 1024, "image_bytes": 2048,
        }
        for strategy in ("conventional", "snapshot"):
            self.set_eligibility(model, strategy, "eligible")
        return model

    def set_eligibility(self, model: dict, strategy: str, state: str) -> None:
        path = self.root / f"{model['model_id']}-{strategy}-{model['gpu_profile']}-{state}.json"
        write_canonical_json(
            path,
            {
                "schema": "archvteams.nebius.ai/k8s-strategy-eligibility/v1",
                "model_id": model["model_id"], "model_version": model["model_version"],
                "strategy": strategy, "state": state, "gpu_profile": model["gpu_profile"],
                "source_reviewed_commit": "9abd49204e7dbfb9be17ebf6c3f213227a88e5ca",
            },
        )
        model["strategy_eligibility"][strategy] = {
            "state": state, "evidence_path": str(path), "evidence_sha256": file_sha256(path),
        }

    def base_plan(self, catalog: dict) -> dict:
        return {
            "schema": "archvteams.nebius.ai/catalog-switch-k8s-baseline-plan/v2",
            "experiment_id": "contract", "task_id": "catalog-switch-k8s-baseline",
            "project_id": "project-e00z6b02t8ddk96c49", "region": "eu-north1",
            "backend": "kubernetes", "backend_version": "v1-36-3", "code_revision": "0" * 40,
            "campaign_arm": "A_prepared_node",
            "boundary_policy": {
                "node_creation": "before_cohort_t0",
                "artifact_localization": "declared_cache_precondition_or_after_t0",
                "model_specific_work": "declared_occupant_precondition_or_after_t0",
            },
            "semantic_calls_per_attempt": 2, "product_terminal_call": 1,
            "variant": "per_run_service", "precreated_support": [],
            "scenario_strategies": {
                "same_model_hot": "none", "idle_local": "snapshot",
                "a_to_b_local": "snapshot", "a_to_b_remote": "conventional",
                "checkpoint_fallback": "conventional", "capacity_miss": "none",
            },
            "promoted_scenarios": ["a_to_b_local"], "minimum_repetitions": 30,
            "metric_contract": {
                "path": str(self.metric), "sha256": file_sha256(self.metric),
                "source_reviewed_commit": "ba49c9e20f194e0f419d4209608904cc9335219d",
                "integrated_commit": "138c52fe3d3371b2d84bb3d0b2e770601ebc5609",
            },
            "trace_path": str(self.trace_path), "trace_sha256": file_sha256(self.trace_path),
            "gpu_profiles": {
                "h100-single": {
                    "product": "NVIDIA-H100-80GB-HBM3", "platform": "gpu-h100-sxm",
                    "preset": "1gpu-16vcpu-200gb", "gpu_count": 1,
                },
                "h200-large": {
                    "product": "NVIDIA-H200-141GB-HBM3E", "platform": "gpu-h200-sxm",
                    "preset": "1gpu-32vcpu-400gb", "gpu_count": 1,
                },
            },
            "models": [
                self.executable_model(catalog["models"][0], self.request_a, "sha256-1111111111111111"),
                self.executable_model(catalog["models"][1], self.request_b, "v1"),
            ],
            "kubernetes": {
                "kubeconfig": str(self.root / "future-kubeconfig"), "context": "fresh-context",
                "expected_server": "https://127.0.0.1:6443", "namespace": "mlsp-csw-k8s",
                "cluster_version": "v1.31.8",
                "node_name": "fresh-h100-node", "node_uid": "node-uid-1",
                "broker_node_id": "computeinstance-node-1",
                "broker_node_group_id": "mk8snodegroup-contract",
                "namespace_resource_id": "namespace-contract", "namespace_uid": "namespace-uid-1",
                "service_account_resource_id": "serviceaccount-contract",
                "service_account_uid": "serviceaccount-uid-1", "gpu_profile": "h100-single",
                "preemptible": True, "sentinel_pod": "gpu-sentinel",
                "ready_timeout_seconds": 900, "drain_timeout_seconds": 30,
            },
            "resource_lease": {
                "path": str(self.lease_path), "sha256": "0" * 64,
                "request_sha256": "0" * 64, "lease_id": "lease-k8s-contract",
                "prefix": "mlsp-csw-k8s-contract", "admitted_states": ["PLANNED", "ACTIVE"],
            },
            "runtime_sources": {
                "path": str(self.runtime_sources), "sha256": "0" * 64,
            },
            "security": {
                "workload_service_account": "catalog-switch-runtime",
                "threat_model": {
                    "path": str(THREAT_MODEL_PATH), "sha256": THREAT_MODEL_SHA256,
                    "markdown_path": str(THREAT_MARKDOWN_PATH),
                    "markdown_sha256": THREAT_MARKDOWN_SHA256,
                    "validator_path": str(THREAT_VALIDATOR_PATH),
                    "validator_sha256": THREAT_VALIDATOR_SHA256,
                    "source_reviewed_commit": "9cfbc1b1311a1f784a407889b215aaec5200fe0e",
                    "integrated_commit": "9b548153385b50d2ad05076a0322840b77bb8027",
                },
                "credentials": {
                    "owner_task_id": "catalog-switch-k8s-baseline", "secret_name": "ngc-task-owned",
                    "secret_uid": "secret-uid-1", "registry": "nvcr.io", "scope_sha256": "7" * 64,
                    "scope_manifest_path": str(self.scope_manifest),
                    "scope_manifest_sha256": "0" * 64,
                    "receipt_path": str(self.credential), "receipt_sha256": file_sha256(self.credential),
                    "expires_at_utc": "2026-08-20T00:00:00Z", "revoke_by_utc": "2026-08-20T01:00:00Z",
                },
                "support_images": {
                    "sentinel_digest": "nvcr.io/mlsp/sentinel@sha256:" + "6" * 64,
                    "readiness_gate_digest": "nvcr.io/mlsp/gate@sha256:" + "5" * 64,
                    "source_receipt_path": str(self.support_receipt),
                    "source_receipt_sha256": "0" * 64,
                },
                "audit": {
                    "schema": "archvteams.nebius.ai/hash-chained-audit/v1",
                    "chain_id": "audit-chain-1", "genesis_sha256": "4" * 64,
                },
            },
            "cost": {
                "lease_hour_usd": 2.2, "transfer_usd_per_gib": 0.01,
                "pre_t0_setup_cost_usd": 0.5, "expected_duration_hours": 4,
                "hard_cap_usd": 12, "price_snapshot_utc": "2026-08-19T00:00:00Z",
                "source": "immutable broker v2 cost estimate",
            },
            "cleanup": {
                "owner": "catalog-switch-k8s-baseline", "deadline_utc": "2026-08-20T00:00:00Z",
                "ttl_hours": 12, "plan": "Delete exact broker IDs after every admitted variant finishes.",
            },
        }

    def write_runtime_sources(self) -> None:
        models = []
        for model in sorted(
            self.plan["models"], key=lambda value: (value["model_id"], value["model_version"])
        ):
            templates = {}
            for strategy in ("conventional", "snapshot"):
                ref = model["target_templates"][strategy]
                if ref is None:
                    templates[strategy] = None
                    continue
                init_names = ["artifact-gate", "cache-gate", "storage-gate"]
                if strategy == "snapshot":
                    init_names.append("snapshot-restore-gate")
                templates[strategy] = {
                    "path": ref["path"], "sha256": ref["sha256"],
                    "container_names": [model["container_name"]],
                    "init_container_names": sorted(init_names),
                }
            models.append(
                {
                    "model_id": model["model_id"], "model_version": model["model_version"],
                    "validator": {
                        "validator_id": model["semantic_oracle"]["validator_id"],
                        "adapter": model["validator_adapter"],
                        "path": model["semantic_oracle"]["validator_path"],
                        "sha256": model["semantic_oracle"]["validator_sha256"],
                    },
                    "target_templates": templates,
                }
            )
        write_canonical_json(
            self.runtime_sources,
            {
                "schema": "archvteams.nebius.ai/k8s-runtime-sources/v1",
                "task_id": self.plan["task_id"], "reviewed_commit": "3" * 40,
                "support_images": self.plan["security"]["support_images"],
                "models": models,
            },
        )
        self.plan["runtime_sources"]["sha256"] = file_sha256(self.runtime_sources)

    def reseal_lease(self) -> None:
        arm_a = self.plan["campaign_arm"] == "A_prepared_node"
        first = json.loads(self.trace_path.read_text())["requests"][0]
        occupant = first["precondition"]["current_node_occupant"]
        full_occupant = None
        if occupant is not None:
            selected = next(
                item for item in self.plan["models"]
                if (item["model_id"], item["model_version"])
                == (occupant["model_id"], occupant["model_version"])
            )
            full_occupant = {
                key: selected[key]
                for key in ("model_id", "model_version", "version_label", "artifact_id", "artifact_version", "artifact_sha256", "image_digest")
            }
        ref = self.plan["resource_lease"]
        profile = self.plan["gpu_profiles"][self.plan["kubernetes"]["gpu_profile"]]
        request = {
            "lease_id": ref["lease_id"], "prefix": ref["prefix"], "task_id": self.plan["task_id"],
            "campaign_arm": self.plan["campaign_arm"], "project_id": self.plan["project_id"],
            "region": self.plan["region"], "code_revision": self.plan["code_revision"],
            "expected_duration_hours": self.plan["cost"]["expected_duration_hours"],
            "ttl_hours": self.plan["cleanup"]["ttl_hours"], "hard_cost_cap_usd": self.plan["cost"]["hard_cap_usd"],
            "metric_contract_sha256": self.plan["metric_contract"]["sha256"], "trace_sha256": self.plan["trace_sha256"],
            "model_input_sha256s": sorted({item["input"]["payload_sha256"] for item in self.plan["models"]}),
            "cleanup_owner": self.plan["cleanup"]["owner"], "cleanup_deadline_utc": self.plan["cleanup"]["deadline_utc"],
            "cluster_version": self.plan["kubernetes"]["cluster_version"],
            "node_group_profile": self.plan["kubernetes"]["gpu_profile"],
            "credential_receipt_sha256": self.plan["security"]["credentials"]["receipt_sha256"],
            "credential_scope_manifest_sha256": self.plan["security"]["credentials"][
                "scope_manifest_sha256"
            ],
            "threat_model_sha256": self.plan["security"]["threat_model"]["sha256"],
            "runtime_sources_sha256": self.plan["runtime_sources"]["sha256"],
        }
        support = [
            ("cluster", "mk8scluster-contract"), ("network", "network-contract"),
            ("subnet", "subnet-contract"),
            ("service_account", "serviceaccount-contract"),
            ("namespace", "namespace-contract"),
        ]
        gpu = [
            ("node_group", "mk8snodegroup-contract"),
            ("node", self.plan["kubernetes"]["broker_node_id"]),
        ] if arm_a else []
        resource_pairs = [support[0], *gpu, *support[1:]]
        ids = [resource_id for _, resource_id in resource_pairs]
        resources = [
            {
                "kind": kind, "id": resource_id, "project_id": self.plan["project_id"],
                "region": self.plan["region"], "prefix": ref["prefix"], "task_id": self.plan["task_id"],
                "task_owned": True, "preexisting": False,
            }
            for kind, resource_id in resource_pairs
        ]
        node_boot_id = "boot-contract-0001" if arm_a else None
        gpu_inventory = (
            [
                {
                    "gpu_uuid": "GPU-contract-0001",
                    "gpu_index": 0,
                    "product": profile["product"],
                    "memory_bytes_total": 80 * 1024**3,
                }
            ]
            if arm_a
            else []
        )
        request_sha256 = canonical_sha256(request)
        isolation_core = {
            "fresh": True, "task_owned": True, "preemptible": True,
            "gpu_product": profile["product"], "gpu_count": profile["gpu_count"],
            "cluster_id": "mk8scluster-contract",
            "node_group_ids": ["mk8snodegroup-contract"] if arm_a else [],
            "node_ids": [self.plan["kubernetes"]["broker_node_id"]] if arm_a else [],
            "node_boot_id": node_boot_id,
            "gpu_inventory_sha256": canonical_sha256(gpu_inventory),
            "resource_graph_sha256": canonical_sha256(resources),
        }
        write_canonical_json(self.isolation_evidence, isolation_core)
        initial_core = {
            "schema": "archvteams.nebius.ai/k8s-initial-state/v2", "node_id": ids[2],
            "node_uid": self.plan["kubernetes"]["node_uid"], "broker_node_id": ids[2],
            "occupant": full_occupant, "cache": first["precondition"]["cache"],
            "cache_targets": [
                {
                    key: item[key]
                    for key in (
                        "model_id", "model_version", "artifact_id", "artifact_version",
                        "artifact_sha256", "artifact_bytes", "image_digest", "image_bytes",
                        "checkpoint",
                    )
                }
                for item in sorted(
                    self.plan["models"], key=lambda value: (value["model_id"], value["model_version"])
                )
            ],
            "observed_at_utc": "2026-08-19T00:00:00Z",
        } if arm_a else None
        if initial_core is not None:
            write_canonical_json(self.initial_evidence, initial_core)
        audit_events = []
        previous = self.plan["security"]["audit"]["genesis_sha256"]
        for index, payload in enumerate(
            ({"operation": "lease.requested", "request_sha256": request_sha256},
             {"operation": "lease.planned", "resource_count": len(resources)})
        ):
            core = {"sequence": index, "previous_sha256": previous, "payload": payload}
            event = {**core, "event_sha256": canonical_sha256(core)}
            audit_events.append(event)
            previous = event["event_sha256"]
        write_canonical_json(self.audit_events, audit_events)
        self.lease = {
            "schema_version": "catalog-switch-kubernetes-resource-lease/v2",
            "lease_id": ref["lease_id"], "request_sha256": request_sha256, "request": request,
            "prefix": ref["prefix"], "state": "PLANNED", "project_id": self.plan["project_id"],
            "region": self.plan["region"], "cluster_id": "mk8scluster-contract",
            "node_group_ids": ["mk8snodegroup-contract"] if arm_a else [],
            "node_ids": [self.plan["kubernetes"]["broker_node_id"]] if arm_a else [],
            "node_boot_id": node_boot_id, "gpu_inventory": gpu_inventory,
            "kubeconfig_path": str(self.root / "future-kubeconfig"),
            "kubernetes_context": self.plan["kubernetes"]["context"],
            "api_server": self.plan["kubernetes"]["expected_server"],
            "gpu_product": profile["product"], "gpu_count": profile["gpu_count"], "preemptible": True,
            "resources": resources,
            "isolation_proof": {
                **isolation_core, "evidence_path": str(self.isolation_evidence),
                "evidence_sha256": file_sha256(self.isolation_evidence),
            },
            "initial_state_receipt": (
                {
                    **initial_core, "evidence_path": str(self.initial_evidence),
                    "evidence_sha256": file_sha256(self.initial_evidence),
                }
                if initial_core is not None else None
            ),
            "resource_create_operations": [
                {
                    "operation_id": f"create-{index}", "resource_id": item["id"],
                    "started_at_utc": "2026-08-19T00:00:00Z",
                    "finished_at_utc": "2026-08-19T00:01:00Z",
                    "request_sha256": request_sha256,
                }
                for index, item in enumerate(resources)
            ],
            "readiness_timestamps": {
                "cluster_ready_at_utc": "2026-08-19T00:02:00Z",
                "node_ready_at_utc": "2026-08-19T00:03:00Z" if arm_a else None,
            },
            "cost_estimate": {
                "currency": "USD", "lease_hour_usd": self.plan["cost"]["lease_hour_usd"],
                "transfer_usd_per_gib": self.plan["cost"]["transfer_usd_per_gib"],
                "pre_t0_setup_cost_usd": self.plan["cost"]["pre_t0_setup_cost_usd"],
                "expected_duration_hours": self.plan["cost"]["expected_duration_hours"],
                "hard_cap_usd": self.plan["cost"]["hard_cap_usd"],
            },
            "cleanup_plan": {
                "owner": self.plan["cleanup"]["owner"], "deadline_utc": self.plan["cleanup"]["deadline_utc"],
                "ttl_hours": self.plan["cleanup"]["ttl_hours"], "delete_exact_ids": sorted(ids),
                "desired_final_state": "ABSENT",
            },
            "audit_chain": {
                "chain_id": self.plan["security"]["audit"]["chain_id"],
                "genesis_sha256": self.plan["security"]["audit"]["genesis_sha256"],
                "head_sha256": previous, "event_count": len(audit_events),
                "events_path": str(self.audit_events),
                "events_sha256": file_sha256(self.audit_events),
            },
        }
        write_canonical_json(self.lease_path, self.lease)
        ref["request_sha256"] = self.lease["request_sha256"]
        ref["sha256"] = file_sha256(self.lease_path)

    def write_plan(self) -> None:
        write_canonical_json(self.plan_path, self.plan)

    def assert_rejected(self, pattern: str) -> None:
        self.write_plan()
        with self.assertRaisesRegex(BaselineError, pattern):
            load_plan(self.plan_path)

    def test_valid_plan_binds_long_version_to_safe_label_and_exact_v2_lease(self) -> None:
        value = load_plan(self.plan_path)
        self.assertEqual(len(value["models"][0]["model_version"]), 71)
        self.assertLessEqual(len(value["models"][0]["version_label"]), 63)
        self.assertTrue(value["_resolved"]["lease_loaded"])

    def test_minimal_forged_lease_is_rejected(self) -> None:
        write_canonical_json(self.lease_path, {"schema_version": "catalog-switch-kubernetes-resource-lease/v2"})
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("resource lease keys differ")

    def test_lease_hash_request_preemptible_gpu_and_node_are_bound(self) -> None:
        for field, value, pattern in (
            ("request_sha256", "f" * 64, "request hash"),
            ("preemptible", False, "preemptible GPU profile"),
            ("gpu_product", "NVIDIA-H200-141GB-HBM3E", "preemptible GPU profile"),
        ):
            with self.subTest(field=field):
                original = copy.deepcopy(self.lease)
                self.lease[field] = value
                write_canonical_json(self.lease_path, self.lease)
                self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
                self.assert_rejected(pattern)
                self.lease = original
                write_canonical_json(self.lease_path, self.lease)
                self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)

    def test_foreign_resource_graph_and_initial_receipt_are_rejected(self) -> None:
        self.lease["resources"][0]["task_owned"] = False
        write_canonical_json(self.lease_path, self.lease)
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("foreign or reused")
        self.reseal_lease()
        self.lease["initial_state_receipt"]["cache"]["artifact"] = "remote_miss"
        write_canonical_json(self.lease_path, self.lease)
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("initial occupant/cache")

    def test_trace_artifact_and_input_mutations_are_rejected(self) -> None:
        trace = json.loads(self.trace_path.read_text())
        trace["requests"][0]["target"]["artifact_sha256"] = "f" * 64
        trace["trace_sha256"] = canonical_sha256(
            {key: value for key, value in trace.items() if key != "trace_sha256"}
        )
        write_canonical_json(self.trace_path, trace)
        self.plan["trace_sha256"] = file_sha256(self.trace_path)
        self.assert_rejected("artifact identity")
        self.setUp_rebuild_after_trace_mutation()
        trace = json.loads(self.trace_path.read_text())
        trace["requests"][0]["input"]["payload_sha256"] = "f" * 64
        trace["trace_sha256"] = canonical_sha256(
            {key: value for key, value in trace.items() if key != "trace_sha256"}
        )
        write_canonical_json(self.trace_path, trace)
        self.plan["trace_sha256"] = file_sha256(self.trace_path)
        self.assert_rejected("input identity")

    def setUp_rebuild_after_trace_mutation(self) -> None:
        # Restore only the immutable trace from the already admitted model catalog.
        catalog = {"schema": CATALOG_SCHEMA, "models": [
            {key: item[key] for key in ("model_id", "model_version", "artifact_id", "artifact_version", "artifact_sha256", "input")}
            for item in self.plan["models"]
        ]}
        write_canonical_json(
            self.trace_path,
            build_trace(
                catalog, scenario="a_to_b_local", seed=2407, request_count=60,
                trace_id="contract-trace", interval_ms=100,
            ),
        )
        self.plan["trace_sha256"] = file_sha256(self.trace_path)
        self.reseal_lease()

    def test_credential_and_threat_receipts_are_source_bound(self) -> None:
        self.plan["security"]["credentials"]["receipt_sha256"] = "f" * 64
        self.assert_rejected("credential receipt")
        self.plan["security"]["credentials"]["receipt_sha256"] = file_sha256(self.credential)
        self.plan["security"]["threat_model"]["sha256"] = "f" * 64
        self.assert_rejected("threat-model document")

    def test_future_issued_active_credential_is_rejected_at_live_admission(self) -> None:
        receipt = json.loads(self.credential.read_text())
        receipt["issued_at_utc"] = "2099-08-19T23:30:00Z"
        receipt["expires_at_utc"] = "2099-08-20T00:00:00Z"
        receipt["revoke_by_utc"] = "2099-08-20T01:00:00Z"
        write_canonical_json(self.credential, receipt)
        credentials = self.plan["security"]["credentials"]
        credentials["receipt_sha256"] = file_sha256(self.credential)
        credentials["expires_at_utc"] = receipt["expires_at_utc"]
        credentials["revoke_by_utc"] = receipt["revoke_by_utc"]
        self.plan["cleanup"]["deadline_utc"] = "2099-08-19T23:50:00Z"
        with self.assertRaisesRegex(BaselineError, "issued after live admission"):
            _validate_security(self.plan, self.plan_path, require_live=True)

    def test_execution_uses_retained_admitted_trace_and_lease_bytes(self) -> None:
        self.write_plan()
        admitted = load_plan(self.plan_path)
        original_trace = admitted_document(admitted, "trace")
        original_lease = admitted_document(admitted, "lease")

        mutated_trace = json.loads(self.trace_path.read_text())
        mutated_trace["requests"][0]["target"] = dict(
            mutated_trace["requests"][1]["target"]
        )
        mutated_trace["trace_sha256"] = canonical_sha256(
            {key: value for key, value in mutated_trace.items() if key != "trace_sha256"}
        )
        write_canonical_json(self.trace_path, mutated_trace)
        mutated_lease = json.loads(self.lease_path.read_text())
        mutated_lease["node_ids"] = ["attacker-node"]
        write_canonical_json(self.lease_path, mutated_lease)

        self.assertEqual(admitted_document(admitted, "trace"), original_trace)
        self.assertEqual(admitted_document(admitted, "lease"), original_lease)
        with patch("performance.k8s_baseline.kubernetes_backend.Kubectl"):
            backend = KubernetesBackend(admitted)
        self.assertEqual(backend.lease["node_ids"], original_lease["node_ids"])
        self.assertNotEqual(
            admitted_document(admitted, "trace")["requests"][0]["target"],
            mutated_trace["requests"][0]["target"],
        )

    def test_minimal_self_asserted_threat_model_cannot_replace_reviewed_validator_input(self) -> None:
        self.threat.write_text('{"status":"reviewed"}\n')
        self.plan["security"]["threat_model"]["path"] = str(self.threat)
        self.plan["security"]["threat_model"]["sha256"] = file_sha256(self.threat)
        self.assert_rejected("reviewed sources")

    def test_security_content_lifecycle_and_exact_scope_adversaries_are_rejected(self) -> None:
        receipt = json.loads(self.credential.read_text())
        receipt["registry"] = "docker.io"
        self.plan["security"]["credentials"]["registry"] = "docker.io"
        write_canonical_json(self.credential, receipt)
        self.plan["security"]["credentials"]["receipt_sha256"] = file_sha256(self.credential)
        self.reseal_lease()
        self.assert_rejected("exact admitted NGC images")

    def test_metric_inventory_audit_and_initial_cache_sources_are_immutable(self) -> None:
        self.plan["metric_contract"]["sha256"] = "f" * 64
        self.assert_rejected("metric contract file")

        self.plan["metric_contract"]["sha256"] = file_sha256(self.metric)
        eligibility_path = Path(
            self.plan["models"][0]["strategy_eligibility"]["snapshot"]["evidence_path"]
        )
        eligibility = json.loads(eligibility_path.read_text())
        eligibility["source_reviewed_commit"] = "f" * 40
        write_canonical_json(eligibility_path, eligibility)
        self.plan["models"][0]["strategy_eligibility"]["snapshot"]["evidence_sha256"] = file_sha256(
            eligibility_path
        )
        self.assert_rejected("eligibility evidence is not source-bound")

    def test_metric_freeze_cannot_self_assert_a_forged_runtime_digest(self) -> None:
        value = json.loads(self.metric.read_text())
        value["files"]["performance/request_slo/harness.py"] = "8" * 64
        write_canonical_json(self.metric, value)
        self.plan["metric_contract"]["sha256"] = file_sha256(self.metric)
        self.reseal_lease()
        self.assert_rejected("runtime file differs from freeze")

    def test_live_source_revision_rejects_wrong_head_or_dirty_runtime(self) -> None:
        with patch(
            "performance.k8s_baseline.contract.subprocess.run",
            side_effect=[
                SimpleNamespace(stdout="f" * 40 + "\n"),
                SimpleNamespace(stdout=""),
            ],
        ):
            with self.assertRaisesRegex(BaselineError, "exact clean code_revision"):
                _validate_live_source_revision("0" * 40)
        with patch(
            "performance.k8s_baseline.contract.subprocess.run",
            side_effect=[
                SimpleNamespace(stdout="0" * 40 + "\n"),
                SimpleNamespace(stdout=" M performance/k8s_baseline/controller.py\n"),
            ],
        ):
            with self.assertRaisesRegex(BaselineError, "exact clean code_revision"):
                _validate_live_source_revision("0" * 40)

    def test_hash_chain_and_exact_cache_target_tampering_are_rejected(self) -> None:
        events = json.loads(self.audit_events.read_text())
        events[0]["payload"]["operation"] = "forged"
        write_canonical_json(self.audit_events, events)
        self.lease["audit_chain"]["events_sha256"] = file_sha256(self.audit_events)
        write_canonical_json(self.lease_path, self.lease)
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("audit event digest")

        self.reseal_lease()
        self.lease["initial_state_receipt"]["cache_targets"][0]["artifact_sha256"] = "f" * 64
        evidence = {
            key: self.lease["initial_state_receipt"][key]
            for key in (
                "schema", "node_id", "node_uid", "broker_node_id", "occupant", "cache",
                "cache_targets", "observed_at_utc",
            )
        }
        write_canonical_json(self.initial_evidence, evidence)
        self.lease["initial_state_receipt"]["evidence_sha256"] = file_sha256(self.initial_evidence)
        write_canonical_json(self.lease_path, self.lease)
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("exact model/artifact/checkpoint")

    def test_label_unsafe_ids_and_unimplemented_validator_are_rejected(self) -> None:
        self.plan["models"][0]["model_id"] = "Bad:Model"
        self.assert_rejected("Kubernetes DNS label")

    def test_label_unsafe_prefix_is_rejected(self) -> None:
        self.plan["resource_lease"]["prefix"] = "mlsp-csw-Bad:Prefix"
        self.assert_rejected("Kubernetes DNS label")

    def test_unimplemented_validator_adapter_is_rejected_before_t0(self) -> None:
        self.plan["models"][0]["validator_adapter"] = "future-model-v1"
        self.assert_rejected("no executable validator adapter")

    def test_hidden_second_gpu_capacity_is_rejected(self) -> None:
        self.lease["resources"].append(
            {
                "kind": "node_group", "id": "hidden-node-group",
                "project_id": self.plan["project_id"], "region": self.plan["region"],
                "prefix": self.plan["resource_lease"]["prefix"],
                "task_id": self.plan["task_id"], "task_owned": True, "preexisting": False,
            }
        )
        write_canonical_json(self.lease_path, self.lease)
        self.plan["resource_lease"]["sha256"] = file_sha256(self.lease_path)
        self.assert_rejected("hidden or duplicate capacity")

    def test_arm_b_support_lease_has_no_pre_t0_gpu_or_model_graph(self) -> None:
        self.plan["campaign_arm"] = "B_new_preemptible_node"
        self.plan["boundary_policy"] = {
            "node_creation": "after_t0", "artifact_localization": "after_t0",
            "model_specific_work": "after_t0",
        }
        self.plan["resource_lease"]["admitted_states"] = [
            "PLANNED", "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"
        ]
        for key in ("node_name", "node_uid", "broker_node_id", "broker_node_group_id"):
            self.plan["kubernetes"][key] = None
        self.reseal_lease()
        _validate_resource_graph(
            self.lease, self.plan, self.plan["resource_lease"], self.plan_path
        )

        self.lease["resources"].append(
            {
                "kind": "node_group", "id": "forged-pre-t0-node-group",
                "project_id": self.plan["project_id"], "region": self.plan["region"],
                "prefix": self.plan["resource_lease"]["prefix"],
                "task_id": self.plan["task_id"], "task_owned": True, "preexisting": False,
            }
        )
        with self.assertRaisesRegex(BaselineError, "forbidden pre-T0 GPU/model work"):
            _validate_resource_graph(
                self.lease, self.plan, self.plan["resource_lease"], self.plan_path
            )

    def test_arm_b_trace_cannot_smuggle_local_cache_before_t0(self) -> None:
        trace = json.loads(self.trace_path.read_text())
        self.plan["campaign_arm"] = "B_new_preemptible_node"
        self.plan["boundary_policy"] = {
            "node_creation": "after_t0", "artifact_localization": "after_t0",
            "model_specific_work": "after_t0",
        }
        for key in ("node_name", "node_uid", "broker_node_id", "broker_node_group_id"):
            self.plan["kubernetes"][key] = None
        trace["trace_sha256"] = canonical_sha256(
            {key: value for key, value in trace.items() if key != "trace_sha256"}
        )
        write_canonical_json(self.trace_path, trace)
        self.plan["trace_sha256"] = file_sha256(self.trace_path)
        self.assert_rejected("smuggles node/model/cache work")

    def test_h200_profile_and_snapshot_not_applicable_are_executable(self) -> None:
        self.plan["kubernetes"]["gpu_profile"] = "h200-large"
        for model in self.plan["models"]:
            model["gpu_profile"] = "h200-large"
            self.set_eligibility(model, "conventional", "eligible")
            self.set_eligibility(model, "snapshot", "not_applicable")
            model["target_templates"]["snapshot"] = None
            model["checkpoint"] = None
        for scenario, strategy in list(self.plan["scenario_strategies"].items()):
            if strategy == "snapshot":
                self.plan["scenario_strategies"][scenario] = "conventional"
        self.write_runtime_sources()
        self.reseal_lease()
        self.write_plan()
        value = load_plan(self.plan_path)
        self.assertEqual(value["gpu_profiles"]["h200-large"]["product"], "NVIDIA-H200-141GB-HBM3E")
        self.assertIsNone(value["models"][0]["_paths"]["snapshot_template"])

    def test_request_file_sha_content_and_oracle_are_bound_before_acceptance(self) -> None:
        self.plan["models"][0]["input"]["input_bytes"] += 1
        self.assert_rejected("exact input identity")
        self.plan["models"][0]["input"]["input_bytes"] -= 1
        self.plan["models"][0]["semantic_oracle"]["validator_sha256"] = "f" * 64
        self.assert_rejected("semantic oracle digest")

    def test_inner_semantic_payload_drift_is_rejected_before_acceptance(self) -> None:
        self.payload.write_text('{"mutated":true}\n')
        self.assert_rejected("payload differs from its exact digest")

    def test_validator_template_and_support_images_require_broker_bound_sources(self) -> None:
        self.validator.write_text("def validate_response(*args, **kwargs): return None\n")
        for model in self.plan["models"]:
            model["semantic_oracle"]["validator_sha256"] = file_sha256(self.validator)
        self.assert_rejected("runtime source manifest")

        self.validator.write_text("# pinned validator\n")
        for model in self.plan["models"]:
            model["semantic_oracle"]["validator_sha256"] = file_sha256(self.validator)
        self.template.write_text("apiVersion: v1\nkind: Pod\n# attacker template\n")
        for model in self.plan["models"]:
            for strategy in ("conventional", "snapshot"):
                model["target_templates"][strategy]["sha256"] = file_sha256(self.template)
        self.assert_rejected("runtime source manifest")

        self.template.write_text("apiVersion: v1\nkind: Pod\n")
        for model in self.plan["models"]:
            for strategy in ("conventional", "snapshot"):
                model["target_templates"][strategy]["sha256"] = file_sha256(self.template)
        self.plan["security"]["support_images"]["sentinel_digest"] = (
            "nvcr.io/attacker/sentinel@sha256:" + "8" * 64
        )
        self.assert_rejected("support-image source receipt")


if __name__ == "__main__":
    unittest.main()
