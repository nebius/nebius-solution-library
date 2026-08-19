from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "broker.py"
SPEC = importlib.util.spec_from_file_location("resource_broker", MODULE_PATH)
assert SPEC and SPEC.loader
broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(broker)


class FakeCLI:
    profile = "sandbox"

    def __init__(self, public_pool_ids=None) -> None:
        self.created = []
        self.deleted = []
        self.absent = set()
        self.public_pool_ids = public_pool_ids or []

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
                            "id": "serviceaccount-test",
                            "parent_id": "project-i00xz31gpr00xp9jhp982v",
                        }
                    }
                }
            }
        if args[:3] == ["iam", "project", "get"]:
            return {
                "metadata": {
                    "id": args[3],
                    "parent_id": "tenant-test",
                    "name": "test-project",
                },
                "status": {"region": "eu-north1", "container_state": "ACTIVE"},
            }
        if args[:3] == ["compute", "platform", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "cpu-e2"},
                        "spec": {"presets": [{"name": "2vcpu-8gb"}]},
                    }
                ]
            }
        if args[:3] == ["quotas", "quota-allowance", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "compute.instance.non-gpu.vcpu"},
                        "spec": {"region": "eu-north1"},
                        "status": {"usage": "0", "unit": "count", "usage_state": "UNUSED"},
                    }
                ]
            }
        if args[:3] == ["capacity", "resource-advice", "list"]:
            return {"items": []}
        if args[-1:] == ["--all"] and "list" in args:
            return {"items": []}
        if args[:3] == ["compute", "instance", "get"]:
            if args[3] in self.absent:
                return None
            return {
                "metadata": {"id": args[3]},
                "spec": {
                    "resources": {"platform": "cpu-e2", "preset": "2vcpu-8gb"},
                    "preemptible": {"on_preemption": "STOP", "priority": 3},
                    "network_interfaces": [{"ip_address": {}}],
                    "service_account_id": None,
                    "local_disks": None,
                },
                "status": {
                    "state": "RUNNING",
                    "network_interfaces": [
                        {"ip_address": {"allocation_id": "allocation-id"}}
                    ],
                },
            }
        if args[:3] == ["vpc", "network", "get"] and not allow_not_found:
            return {
                "metadata": {"id": args[3]},
                "spec": {
                    "ipv4_private_pools": {"pools": [{"id": "private-pool-id"}]},
                    "ipv4_public_pools": {
                        "pools": [{"id": value} for value in self.public_pool_ids]
                    },
                },
                "status": {"default_route_table_id": "route-table-id"},
            }
        if args[:3] == ["vpc", "allocation", "get"] and not allow_not_found:
            return {
                "metadata": {
                    "id": args[3],
                    "name": "auto-allocation",
                    "created_at": "2026-08-19T00:00:00Z",
                }
            }
        if args[:3] == ["vpc", "security-rule", "list"]:
            return {"items": []}
        if args[:3] == ["compute", "disk", "get"] and not allow_not_found:
            return {
                "metadata": {"id": args[3]},
                "spec": {"type": "NETWORK_SSD"},
                "status": {
                    "size_bytes": "21474836480",
                    "source_image_id": "computeimage-test",
                },
            }
        if args[:3] == ["storage", "bucket", "get"] and not allow_not_found:
            return {
                "metadata": {"id": args[3]},
                "spec": {
                    "max_size_bytes": "1073741824",
                    "default_storage_class": "STANDARD",
                    "object_audit_logging": "ALL",
                },
                "status": {"state": "ACTIVE"},
            }
        if args[:3] in (["vpc", "pool", "get"], ["vpc", "route-table", "get"]):
            if not allow_not_found:
                return {
                    "metadata": {
                        "id": args[3],
                        "name": f"managed-{args[1]}",
                        "created_at": "2099-08-19T00:00:00Z",
                    }
                }
        if len(args) >= 3 and args[-2:] == ["--forward"]:
            return "CATALOG_SWITCH_HEALTH_OK lease=unit-test-lease"
        if args[:3] == ["compute", "instance", "logs"]:
            return "CATALOG_SWITCH_HEALTH_OK lease=unit-test-lease"
        if args[:2] in (["vpc", "network"], ["vpc", "subnet"], ["vpc", "security-group"]):
            if len(args) >= 3 and args[2] == "create":
                kind = args[1].replace("-", "_")
                resource_id = f"{kind}-id"
                self.created.append((kind, payload))
                return {"metadata": {"id": resource_id}}
        if args[:2] in (["compute", "disk"], ["compute", "instance"], ["storage", "bucket"]):
            if len(args) >= 3 and args[2] == "create":
                kind = args[1]
                resource_id = f"{kind}-id"
                self.created.append((kind, payload))
                return {"metadata": {"id": resource_id}}
        if len(args) >= 3 and args[2] == "delete":
            resource_id = args[3]
            self.deleted.append(resource_id)
            self.absent.add(resource_id)
            if resource_id == "instance-id":
                self.absent.add("allocation-id")
            if resource_id == "network-id":
                self.absent.update({"private-pool-id", "public-pool-id", "route-table-id"})
            return ""
        if len(args) >= 3 and args[2] == "get" and allow_not_found:
            return None if args[3] in self.absent else {"metadata": {"id": args[3]}}
        raise AssertionError(f"unexpected fake CLI call: {args}")


class FakeH200CLI(FakeCLI):
    def __init__(self, availability_level, available=None):
        super().__init__()
        self.availability_level = availability_level
        self.available = available

    def run(self, args, **kwargs):
        if args[:3] == ["compute", "platform", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "gpu-h200-sxm"},
                        "spec": {"presets": [{"name": "8gpu-128vcpu-1600gb"}]},
                    }
                ]
            }
        if args[:3] == ["capacity", "resource-advice", "list"]:
            status = {"availability_level": self.availability_level}
            if self.available is not None:
                status["available"] = self.available
            return {
                "items": [
                    {
                        "spec": {
                            "region": "eu-north1",
                            "compute_instance": {
                                "platform": "gpu-h200-sxm",
                                "preset": {"name": "8gpu-128vcpu-1600gb"},
                            },
                        },
                        "status": {"on_demand": status, "preemptible": status},
                    }
                ]
            }
        return super().run(args, **kwargs)


def request(**overrides):
    value = {
        "artifact_storage": {"enabled": True, "max_size_gib": 1},
        "cleanup_owner": "catalog-switch-resource-broker",
        "expected_duration_hours": "0.25",
        "experiment": None,
        "health_proof": {"marker": "CATALOG_SWITCH_HEALTH_OK", "timeout_seconds": 60},
        "lease_id": "unit-test-lease",
        "mode": "preemptible",
        "owner": "catalog-switch-resource-broker",
        "profile": "cpu-e2-smoke",
        "project_id": "project-e00z6b02t8ddk96c49",
        "purpose": "Unit-test disposable resource lifecycle proof.",
        "region": "eu-north1",
        "schema_version": "catalog-switch-lease-request/v1",
        "task_id": "catalog-switch-resource-broker",
        "ttl_hours": 1,
    }
    value.update(overrides)
    return value


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request_path = self.root / "request.json"
        self.lease_path = self.root / "lease.json"
        self.registry_path = self.root / "registry.json"
        self.profiles_path = MODULE_PATH.parent / "profiles.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_request(self, value=None):
        self.request_path.write_text(json.dumps(value or request()))

    def make_plan(self):
        self.write_request()
        return broker.plan(
            self.request_path, self.lease_path, self.registry_path, self.profiles_path
        )

    def test_plan_is_idempotent_and_records_policy(self):
        first = self.make_plan()
        second = broker.plan(
            self.request_path, self.lease_path, self.registry_path, self.profiles_path
        )
        self.assertEqual(first["request_sha256"], second["request_sha256"])
        self.assertEqual("PLANNED", second["state"])
        self.assertEqual("catalog-switch-resource-broker", second["request"]["cleanup_owner"])
        self.assertEqual("1", str(second["request"]["ttl_hours"]))
        self.assertGreater(Decimal(second["cost_estimate"]["ttl_cost_ceiling_usd"]), 0)
        self.assertTrue(all(item["name"].startswith("mlsp-csw-") for item in second["planned_resources"]))

    def test_unauthorized_project_is_rejected(self):
        self.write_request(request(project_id="project-forbidden"))
        with self.assertRaisesRegex(broker.BrokerError, "outside the epic allowlist"):
            broker.plan(
                self.request_path, self.lease_path, self.registry_path, self.profiles_path
            )

    def test_gpu_profile_requires_frozen_experiment(self):
        self.write_request(request(profile="h100-single"))
        with self.assertRaisesRegex(broker.BrokerError, "frozen experiment"):
            broker.plan(
                self.request_path, self.lease_path, self.registry_path, self.profiles_path
            )

    def test_h200_tp8_profile_freezes_exact_shape_and_whole_host_cost(self):
        profiles = broker.load_profiles(self.profiles_path)
        profile = profiles["profiles"]["h200-tp8"]
        self.assertEqual(8, profile["gpu_count"])
        self.assertEqual("gpu-h200-sxm", profile["platform"])
        self.assertEqual("8gpu-128vcpu-1600gb", profile["preset"])
        self.assertEqual(1600, profile["boot_disk_gib"])
        self.assertEqual("36.00", profile["hourly_compute_usd"]["normal"])
        self.assertFalse(profile["local_nvme"]["request"])

    def test_gpu_preflight_rejects_exact_preset_when_mode_is_limit_reached(self):
        profiles = broker.load_profiles(self.profiles_path)
        profile = profiles["profiles"]["h200-tp8"]
        frozen = request(
            profile="h200-tp8",
            mode="normal",
            experiment={
                "model_id": "zai-org/GLM-5.2-FP8@revision",
                "input_sha256": "1" * 64,
                "metric_contract_sha256": "2" * 64,
                "metric_contract_path": "contract.json",
                "cleanup_plan": "exact-ID cleanup",
            },
        )
        with self.assertRaisesRegex(broker.BrokerError, "no eligible normal capacity"):
            broker.run_preflight(
                FakeH200CLI("AVAILABILITY_LEVEL_LIMIT_REACHED"), frozen, profile
            )

    def test_gpu_preflight_accepts_exact_preset_with_available_mode(self):
        profiles = broker.load_profiles(self.profiles_path)
        profile = profiles["profiles"]["h200-tp8"]
        frozen = request(
            profile="h200-tp8",
            mode="preemptible",
            experiment={
                "model_id": "zai-org/GLM-5.2-FP8@revision",
                "input_sha256": "1" * 64,
                "metric_contract_sha256": "2" * 64,
                "metric_contract_path": "contract.json",
                "cleanup_plan": "exact-ID cleanup",
            },
        )
        result = broker.run_preflight(
            FakeH200CLI("AVAILABILITY_LEVEL_MEDIUM", available=9), frozen, profile
        )
        self.assertEqual(1, len(result["capacity_advice"]["eligible"]))

    def test_request_hash_collision_fails(self):
        self.make_plan()
        changed = request(purpose="A different experiment with conflicting lease identity.")
        self.write_request(changed)
        with self.assertRaisesRegex(broker.BrokerError, "lease ID collision"):
            broker.plan(
                self.request_path, self.lease_path, self.registry_path, self.profiles_path
            )

    def test_registry_rejects_same_lease_id_at_a_different_path(self):
        self.make_plan()
        second_path = self.root / "duplicate-path.json"
        with self.assertRaisesRegex(broker.BrokerError, "different canonical path"):
            broker.plan(
                self.request_path, second_path, self.registry_path, self.profiles_path
            )

    def test_public_provision_requires_live_authorization_before_preflight(self):
        self.make_plan()
        fake = FakeCLI()
        with self.assertRaisesRegex(broker.BrokerError, "mandatory live authorization"):
            broker.provision(self.lease_path, self.registry_path, fake)
        self.assertEqual([], fake.created)
        self.assertEqual("PLANNED", broker.load_json(self.lease_path)["state"])

    def test_fabricated_context_keyword_is_not_a_mutation_api(self):
        self.make_plan()
        fake = FakeCLI()
        with self.assertRaises(TypeError):
            broker.provision(
                self.lease_path,
                self.registry_path,
                fake,
                live_authorization={"public": {}},
            )
        self.assertEqual([], fake.created)

    def test_orphan_scan_and_supervisor_export(self):
        lease = self.make_plan()
        report = broker.scan(self.registry_path, None, False)
        self.assertEqual(1, len(report["leases"]))
        export = broker.supervisor_ledger(self.registry_path)
        self.assertFalse(export["contains_secrets"])
        self.assertEqual(len(lease["planned_resources"]), len(export["resources"]))
        row = export["resources"][0]
        expected = {
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
            "cleanup_owner",
            "cleanup_state",
            "deleted_at",
            "absence_verified_at",
        }
        self.assertTrue(expected.issubset(row))
        self.assertEqual("ABSENT", row["desired_final_state"])

if __name__ == "__main__":
    unittest.main()
