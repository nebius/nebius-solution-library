from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "kubernetes_broker.py"
SPEC = importlib.util.spec_from_file_location("kubernetes_broker", MODULE_PATH)
assert SPEC and SPEC.loader
k8s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(k8s)
SUPERVISOR_PATH = MODULE_PATH.parent / "supervisor_ledger.py"
SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "combined_supervisor_ledger", SUPERVISOR_PATH
)
assert SUPERVISOR_SPEC and SUPERVISOR_SPEC.loader
supervisor = importlib.util.module_from_spec(SUPERVISOR_SPEC)
SUPERVISOR_SPEC.loader.exec_module(supervisor)


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def request(**overrides):
    value = {
        "schema_version": "catalog-switch-kubernetes-lease-request/v1",
        "lease_id": "k8s-unit-new-node",
        "task_id": "catalog-switch-k8s-baseline",
        "owner": "catalog-switch-k8s-baseline",
        "cleanup_owner": "catalog-switch-resource-broker",
        "purpose": "Fresh isolated Kubernetes new-node contract unit test.",
        "campaign_arm": "B_new_preemptible_node",
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "nebius_profile": "sandbox",
        "cluster_version": "1.34",
        "node_group_profile": "mk8s-h100-new-node-v1",
        "expected_duration_hours": "2",
        "ttl_hours": 6,
        "cleanup_deadline_utc": (
            dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
        ).isoformat().replace("+00:00", "Z"),
        "hard_cost_cap_usd": "20",
        "artifact_storage": {"max_size_gib": 10},
        "metric_contract_sha256": "1" * 64,
        "trace_sha256": "2" * 64,
        "model_input_sha256s": {"openfold2": "3" * 64, "boltz2": "4" * 64},
        "cleanup_plan": "Broker removes each exact resource ID and proves absence.",
    }
    value.update(overrides)
    return value


class FakeCLI:
    profile = "sandbox"

    def __init__(self) -> None:
        self.resources = {}
        self.absent = set()
        self.deleted = []
        self.created_count = {}
        self.fail_after_create_kind = None
        self.failed_once = False
        self.capacity_available = True
        self.pool_id = "vpcpool-unit-private"
        self.route_id = "vpcroutetable-unit-default"
        self.node_by_group = {}

    @staticmethod
    def kind(args):
        head = tuple(args[:3])
        pair = tuple(args[:2])
        if pair == ("vpc", "network"):
            return "network"
        if pair == ("vpc", "subnet"):
            return "subnet"
        if pair == ("vpc", "security-group"):
            return "security_group"
        if pair == ("iam", "service-account"):
            return "service_account"
        if pair == ("iam", "group"):
            return "iam_group"
        if pair == ("iam", "group-membership"):
            return "group_membership"
        if pair == ("iam", "access-permit"):
            return "access_permit"
        if args and args[0] == "registry":
            return "registry"
        if pair == ("storage", "bucket"):
            return "bucket"
        if head == ("mk8s", "v1", "cluster"):
            return "cluster"
        if head == ("mk8s", "v1", "node-group"):
            return "node_group"
        if pair == ("compute", "instance"):
            return "node"
        if pair == ("vpc", "pool"):
            return "pool"
        if pair == ("vpc", "route-table"):
            return "route_table"
        return None

    def inject_foreign(self, kind, name, parent_id):
        resource_id = f"{kind}-foreign"
        self.resources[resource_id] = {
            "_kind": kind,
            "metadata": {
                "id": resource_id,
                "name": name,
                "parent_id": parent_id,
                "created_at": timestamp(),
                "labels": {"program": "somebody-else"},
            },
            "spec": {},
            "status": {},
        }

    def run(
        self,
        args,
        *,
        payload=None,
        json_output=True,
        timeout=90,
        allow_not_found=False,
    ):
        if args[:2] == ["iam", "whoami"]:
            return {
                "service_account_profile": {
                    "info": {
                        "metadata": {
                            "id": "serviceaccount-caller",
                            "parent_id": "project-i00xz31gpr00xp9jhp982v",
                        }
                    }
                }
            }
        if args[:3] == ["iam", "project", "get"]:
            return {
                "metadata": {"id": args[3], "parent_id": "tenant-unit"},
                "status": {"region": "eu-north1", "container_state": "ACTIVE"},
            }
        if args[:5] == ["mk8s", "v1", "cluster", "list-control-plane-versions"]:
            return {"versions": ["1.34", "1.35"]}
        if args[:4] == ["mk8s", "v1", "node-group", "get-compatibility-matrix"]:
            return {"items": [{"os": "ubuntu24.04", "drivers_preset": "cuda13.0"}]}
        if args[:3] == ["compute", "platform", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "cpu-e2"},
                        "spec": {"presets": [{"name": "2vcpu-8gb"}]},
                    },
                    {
                        "metadata": {"name": "gpu-h100-sxm"},
                        "spec": {"presets": [{"name": "1gpu-16vcpu-200gb"}]},
                    },
                ]
            }
        if args[:3] == ["quotas", "quota-allowance", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "compute.instance.gpu.h100"},
                        "spec": {"region": "eu-north1"},
                        "status": {"usage": "0", "unit": "count"},
                    }
                ]
            }
        if args[:3] == ["capacity", "resource-advice", "list"]:
            available = 4 if self.capacity_available else 0
            return {
                "items": [
                    {
                        "spec": {
                            "region": "eu-north1",
                            "fabric": "fabric-unit",
                            "compute_instance": {
                                "platform": "gpu-h100-sxm",
                                "preset": {"name": "1gpu-16vcpu-200gb"},
                            },
                        },
                        "status": {
                            "preemptible": {
                                "data_state": "DATA_STATE_FRESH",
                                "available": available,
                                "availability_level": "AVAILABILITY_LEVEL_HIGH"
                                if available
                                else "AVAILABILITY_LEVEL_LIMIT_REACHED",
                            }
                        },
                    }
                ]
            }
        if args[:3] == ["vpc", "security-rule", "list"]:
            return {"items": []}
        if args[:4] == ["mk8s", "v1", "cluster", "get-credentials"]:
            path = Path(args[args.index("--kubeconfig") + 1])
            path.write_text("apiVersion: v1\nclusters: unit\n")
            os.chmod(path, 0o600)
            return ""

        kind = self.kind(args)
        action_index = 3 if args[:2] == ["mk8s", "v1"] else 1 if args[0] == "registry" else 2
        action = args[action_index] if len(args) > action_index else None
        if action == "create":
            metadata = dict(payload["metadata"])
            actual_kind = kind
            if kind == "access_permit":
                actual_kind = (
                    "registry_access_permit"
                    if payload["spec"]["role"] == "viewer"
                    else "bucket_access_permit"
                )
            if kind == "node_group":
                actual_kind = (
                    "system_node_group"
                    if metadata["name"].endswith("-system")
                    else "gpu_node_group"
                )
            number = self.created_count.get(actual_kind, 0) + 1
            self.created_count[actual_kind] = number
            prefixes = {
                "cluster": "mk8scluster",
                "system_node_group": "mk8snodegroup",
                "gpu_node_group": "mk8snodegroup",
                "network": "vpcnetwork",
                "subnet": "vpcsubnet",
                "security_group": "vpcsecuritygroup",
                "service_account": "serviceaccount",
                "iam_group": "group",
                "group_membership": "groupmembership",
                "registry": "registry",
                "registry_access_permit": "accesspermit",
                "bucket": "storagebucket",
                "bucket_access_permit": "accesspermit",
            }
            resource_id = f"{prefixes[actual_kind]}-unit-{actual_kind}-{number}"
            metadata.update({"id": resource_id, "created_at": timestamp()})
            status = {"state": "RUNNING"}
            if actual_kind == "cluster":
                status = {
                    "state": "RUNNING",
                    "control_plane": {
                        "version": "1.34",
                        "endpoints": {"public_endpoint": "https://unit-cluster.example:443"},
                    },
                }
            if actual_kind in {"system_node_group", "gpu_node_group"}:
                status = {
                    "state": "RUNNING",
                    "target_node_count": "1",
                    "node_count": "1",
                    "ready_node_count": "1",
                }
                role = "system" if actual_kind == "system_node_group" else "gpu"
                self.node_by_group[resource_id] = f"computeinstance-unitnode{role}{number}"
            value = {
                "_kind": actual_kind,
                "metadata": metadata,
                "spec": payload.get("spec", {}),
                "status": status,
            }
            self.resources[resource_id] = value
            if actual_kind == "network":
                self.resources[self.pool_id] = {
                    "_kind": "pool",
                    "metadata": {
                        "id": self.pool_id,
                        "name": "provider-private-pool",
                        "parent_id": resource_id,
                        "created_at": timestamp(),
                    },
                }
                self.resources[self.route_id] = {
                    "_kind": "route_table",
                    "metadata": {
                        "id": self.route_id,
                        "name": "provider-route-table",
                        "parent_id": resource_id,
                        "created_at": timestamp(),
                    },
                }
            if self.fail_after_create_kind == actual_kind and not self.failed_once:
                self.failed_once = True
                raise k8s.common.BrokerError(f"simulated interruption after {actual_kind} create")
            return value
        if action == "list":
            parent_id = args[args.index("--parent-id") + 1]
            wanted = kind
            if kind == "access_permit":
                accepted = {"registry_access_permit", "bucket_access_permit"}
            elif kind == "node_group":
                accepted = {"system_node_group", "gpu_node_group"}
            else:
                accepted = {wanted}
            return {
                "items": [
                    value
                    for resource_id, value in self.resources.items()
                    if resource_id not in self.absent
                    and value.get("_kind") in accepted
                    and value.get("metadata", {}).get("parent_id") == parent_id
                ]
            }
        if action == "get":
            resource_id = args[action_index + 1]
            if resource_id in self.absent:
                return None if allow_not_found else self._not_found(resource_id)
            if kind == "node":
                return {
                    "metadata": {"id": resource_id, "name": resource_id},
                    "status": {"state": "RUNNING"},
                }
            try:
                value = self.resources[resource_id]
            except KeyError:
                return None if allow_not_found else self._not_found(resource_id)
            if value.get("_kind") == "network":
                result = json.loads(json.dumps(value))
                result["spec"]["ipv4_private_pools"] = {"pools": [{"id": self.pool_id}]}
                result["spec"]["ipv4_public_pools"] = {"pools": []}
                result["status"] = {"default_route_table_id": self.route_id}
                return result
            return value
        if action == "delete":
            resource_id = args[action_index + 1]
            self.deleted.append(resource_id)
            self.absent.add(resource_id)
            value = self.resources.get(resource_id, {})
            if value.get("_kind") in {"system_node_group", "gpu_node_group"}:
                self.absent.add(self.node_by_group[resource_id])
            if value.get("_kind") == "network":
                self.absent.update({self.pool_id, self.route_id})
            return ""
        raise AssertionError(f"unexpected fake CLI call: {args}")

    @staticmethod
    def _not_found(resource_id):
        raise k8s.common.BrokerError(f"not found: {resource_id}")


class FakeKubectl:
    def __init__(self, cli):
        self.cli = cli

    def run(self, kubeconfig, args, timeout=90):
        if args[:2] == ["config", "view"]:
            return {
                "current-context": "unit",
                "clusters": [{"cluster": {"server": "https://unit-cluster.example:443"}}],
            }
        if args[:2] == ["get", "nodes"]:
            items = []
            for group_id, node_id in self.cli.node_by_group.items():
                if group_id in self.cli.absent:
                    continue
                group = self.cli.resources[group_id]
                role = "system" if group["_kind"] == "system_node_group" else "gpu"
                items.append(
                    {
                        "metadata": {
                            "name": f"{group_id}-unit-node",
                            "uid": f"uid-{node_id}",
                            "creationTimestamp": timestamp(),
                            "labels": {
                                "mk8s.nebius.com/node-group-id": group_id,
                                "mlsp.nebius.ai/node-role": role,
                            },
                        },
                        "spec": {"providerID": f"nebius:///{node_id}"},
                        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                    }
                )
            return {"items": items}
        raise AssertionError(f"unexpected fake kubectl call: {args}")


class KubernetesBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request_path = self.root / "request.json"
        self.lease_path = self.root / "lease.json"
        self.registry_path = self.root / "registry.json"
        self.demand_path = self.root / "demand.json"
        self.profiles_path = MODULE_PATH.parent / "kubernetes_profiles.json"
        self.request_value = request()
        k8s.KUBECONFIG_ROOT = self.root / "kubeconfigs"
        self.cli = FakeCLI()
        self.kubectl = FakeKubectl(self.cli)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, value=None):
        self.request_path.write_text(json.dumps(value or self.request_value))
        return k8s.plan(
            self.request_path, self.lease_path, self.registry_path, self.profiles_path
        )

    def support(self):
        self.plan()
        return k8s.provision_control_plane(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )

    def demand(self, **overrides):
        value = {
            "schema_version": "catalog-switch-kubernetes-node-demand/v1",
            "lease_id": "k8s-unit-new-node",
            "attempt_id": "attempt-000001",
            "accepted_event_sha256": "a" * 64,
            "t0_observed_at_utc": timestamp(),
            "t0_observed_monotonic_ns": time.monotonic_ns() - 1,
        }
        value.update(overrides)
        self.demand_path.write_text(json.dumps(value))
        return k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

    def test_plan_is_versioned_immutable_and_idempotent(self):
        first = self.plan()
        second = self.plan()
        self.assertEqual("catalog-switch-kubernetes-resource-lease/v2", first["schema_version"])
        self.assertEqual(first["request_sha256"], second["request_sha256"])
        self.assertEqual("PLANNED", second["state"])
        self.assertTrue(second["prefix"].startswith("mlsp-csw-"))
        self.assertIn("{demand_sha256_8}", k8s.graph_name(second, "gpu_node_group"))
        self.assertLessEqual(
            float(second["cost_estimate"]["ttl_cost_ceiling_usd"]),
            float(second["cost_estimate"]["hard_cost_cap_usd"]),
        )
        self.assertEqual("catalog-switch-resource-broker", second["request"]["cleanup_owner"])

    def test_resource_graph_tamper_breaks_plan_hash(self):
        lease = self.plan()
        lease["resource_graph"][0]["resource_name"] = "foreign-name"
        self.lease_path.write_text(json.dumps(lease))
        with self.assertRaisesRegex(k8s.common.BrokerError, "resource plan hash mismatch"):
            k8s.supervisor_ledger(self.registry_path)

    def test_unauthorized_project_and_non_preemptible_profile_fail_closed(self):
        with self.assertRaisesRegex(k8s.common.BrokerError, "outside the epic allowlist"):
            self.plan(request(project_id="project-foreign"))
        profiles = json.loads(self.profiles_path.read_text())
        profiles["profiles"]["mk8s-h100-new-node-v1"]["gpu_node_group"]["mode"] = "normal"
        changed = self.root / "profiles.json"
        changed.write_text(json.dumps(profiles))
        self.request_path.write_text(json.dumps(request()))
        with self.assertRaisesRegex(k8s.common.BrokerError, "preemptible"):
            k8s.plan(self.request_path, self.lease_path, self.registry_path, changed)

    def test_support_demand_gpu_and_exact_attempt_cleanup(self):
        support = self.support()
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", support["state"])
        self.assertIsNotNone(support["cluster_id"])
        self.assertEqual([], support["node_group_ids"])
        self.assertEqual([], support["node_ids"])
        self.assertTrue(support["isolation_proof"]["target_neutral"])
        self.assertEqual([], support["isolation_proof"]["network"]["public_pool_ids"])
        demand = self.demand()
        self.assertEqual("DEMAND_RECORDED", demand["state"])
        repeated = k8s.record_demand(
            self.lease_path, self.registry_path, self.demand_path
        )
        self.assertEqual(demand["demand"]["demand_sha256"], repeated["demand"]["demand_sha256"])
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("ACTIVE_ATTEMPT", active["state"])
        self.assertEqual(1, len(active["node_group_ids"]))
        self.assertEqual(1, len(active["node_ids"]))
        receipt = active["attempts"][0]["receipt"]
        self.assertTrue(receipt["causal_order_pass"])
        self.assertGreaterEqual(
            receipt["create_operation_started_monotonic_ns"],
            receipt["t0_observed_monotonic_ns"],
        )
        released = k8s.cleanup_attempt(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", released["state"])
        self.assertEqual([], released["node_group_ids"])
        self.assertEqual([], released["node_ids"])
        self.assertIsNone(released["demand"])
        self.assertTrue(released["attempts"][0]["receipt"]["cleanup"]["node_absent"])

    def test_prepared_arm_creates_preemptible_gpu_without_post_t0_demand(self):
        prepared = request(
            lease_id="k8s-unit-prepared",
            campaign_arm="A_prepared_node",
            purpose="Fresh isolated Kubernetes prepared-node contract unit test.",
        )
        self.plan(prepared)
        support = k8s.provision_control_plane(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", support["state"])
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("ACTIVE", active["state"])
        self.assertTrue(active["isolation_proof"]["gpu_node_group"]["preemptible"])
        self.assertEqual("prepared-node", active["attempts"][0]["attempt_id"])

    def test_gpu_create_is_blocked_before_durable_demand(self):
        self.support()
        with self.assertRaisesRegex(k8s.common.BrokerError, "recorded durable post-T0 demand"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        lease = json.loads(self.lease_path.read_text())
        self.assertFalse(any(item["kind"] == "gpu_node_group" for item in lease["resources"]))

    def test_future_t0_is_rejected(self):
        self.support()
        with self.assertRaisesRegex(k8s.common.BrokerError, "precede its accepted T0"):
            self.demand(t0_observed_monotonic_ns=time.monotonic_ns() + 1_000_000_000)

    def test_capacity_failure_is_retained_and_no_gpu_create_occurs(self):
        self.support()
        self.demand()
        self.cli.capacity_available = False
        with self.assertRaisesRegex(k8s.common.BrokerError, "no fresh preemptible capacity"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        lease = json.loads(self.lease_path.read_text())
        self.assertEqual("GPU_CAPACITY_FAILED", lease["state"])
        self.assertEqual("NO_PREEMPTIBLE_CAPACITY", lease["attempts"][0]["receipt"]["capacity_advice"]["result"])
        self.assertEqual(0, self.cli.created_count.get("gpu_node_group", 0))
        self.assertTrue(any(item["stage"] == "gpu_capacity_advice" for item in lease["failures"]))

    def test_interruption_after_create_reconciles_without_duplicate(self):
        self.support()
        self.demand()
        self.cli.fail_after_create_kind = "gpu_node_group"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.cli.fail_after_create_kind = None
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("ACTIVE_ATTEMPT", active["state"])
        self.assertEqual(1, self.cli.created_count["gpu_node_group"])
        operation = next(
            item
            for item in active["resource_create_operations"]
            if item["kind"] == "gpu_node_group"
        )
        self.assertEqual("RECONCILED_AFTER_INTERRUPTION", operation["status"])
        self.assertTrue(any(item["stage"] == "create:gpu_node_group" for item in active["failures"]))
        create_attempts = active["attempts"][0]["receipt"]["create_attempts"]
        self.assertEqual(["FAIL", "CREATED_OR_RECONCILED"], [item["outcome"] for item in create_attempts])

    def test_interrupted_gpu_create_is_reconciled_for_exact_cleanup(self):
        self.support()
        self.demand()
        self.cli.fail_after_create_kind = "gpu_node_group"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        released = k8s.cleanup_attempt(
            self.lease_path,
            self.registry_path,
            self.cli,
            self.kubectl,
            execute=True,
        )
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", released["state"])
        receipt = released["attempts"][0]["receipt"]
        self.assertIsNotNone(receipt["node_group_id"])
        self.assertIsNotNone(receipt["node_id"])
        self.assertEqual(2, len(receipt["cleanup"]["exact_id_receipts"]))
        self.assertTrue(all(item["absence_verified_at"] for item in receipt["cleanup"]["exact_id_receipts"]))

    def test_control_plane_interruption_reconciles_without_duplicate(self):
        self.plan()
        self.cli.fail_after_create_kind = "cluster"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.cli.fail_after_create_kind = None
        support = k8s.provision_control_plane(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", support["state"])
        self.assertEqual(1, self.cli.created_count["cluster"])
        operation = next(
            item for item in support["resource_create_operations"] if item["kind"] == "cluster"
        )
        self.assertEqual("RECONCILED_AFTER_INTERRUPTION", operation["status"])

    def test_foreign_exact_name_collision_is_preserved(self):
        lease = self.plan()
        self.cli.inject_foreign("network", k8s.graph_name(lease, "network"), lease["project_id"])
        with self.assertRaisesRegex(k8s.common.BrokerError, "foreign or pre-existing"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertNotIn("network-foreign", self.cli.deleted)
        persisted = json.loads(self.lease_path.read_text())
        self.assertEqual("CONTROL_PLANE_FAILED", persisted["state"])

    def test_full_cleanup_is_dependency_ordered_and_proves_absence(self):
        self.support()
        released = k8s.cleanup(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertTrue(all(item["absence_verified_at"] for item in released["resources"]))
        by_kind = {item["kind"]: item["id"] for item in released["resources"]}
        self.assertLess(
            self.cli.deleted.index(by_kind["system_node_group"]),
            self.cli.deleted.index(by_kind["cluster"]),
        )
        self.assertLess(
            self.cli.deleted.index(by_kind["cluster"]),
            self.cli.deleted.index(by_kind["subnet"]),
        )
        self.assertLess(
            self.cli.deleted.index(by_kind["subnet"]),
            self.cli.deleted.index(by_kind["network"]),
        )

    def test_modified_kubeconfig_is_preserved_and_cleanup_fails(self):
        support = self.support()
        path = Path(support["kubeconfig_path"])
        path.write_text(path.read_text() + "foreign-change: true\n")
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(k8s.common.BrokerError, "cleanup incomplete"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertTrue(path.exists())
        lease = json.loads(self.lease_path.read_text())
        self.assertEqual("CLEANUP_FAILED", lease["state"])

    def test_supervisor_ledger_has_exact_manager_fields(self):
        lease = self.plan()
        ledger = k8s.supervisor_ledger(self.registry_path)
        self.assertFalse(ledger["contains_secrets"])
        row = next(item for item in ledger["resources"] if item["resource_type"] == "cluster")
        for field in (
            "project",
            "region",
            "resource_type",
            "resource_name",
            "resource_id",
            "owner_task",
            "purpose",
            "created_at",
            "expires_at",
            "desired_final_state",
            "cleanup_evidence",
        ):
            self.assertIn(field, row)
        self.assertEqual(lease["prefix"] + "-cluster", row["resource_name"])
        self.assertEqual("NOT_CREATED", row["cleanup_state"])

    def test_combined_supervisor_adds_explicit_absence_evidence(self):
        self.plan()
        ledger = supervisor.build(self.root / "no-vm-registry.json", self.registry_path)
        self.assertEqual("catalog-switch-supervisor-resource-ledger/v2", ledger["schema_version"])
        self.assertTrue(all(item["cleanup_evidence"] for item in ledger["resources"]))
        self.assertFalse(ledger["contains_secrets"])


if __name__ == "__main__":
    unittest.main()
