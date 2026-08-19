from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock


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

    def test_allow_not_found_never_masks_authentication_failure(self):
        cli = broker.NebiusCLI("sandbox")
        result = mock.Mock(
            returncode=1,
            stdout="",
            stderr="Unauthenticated: sandbox profile not found",
        )
        with mock.patch.object(broker.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(
                broker.AuthenticationError,
                "do not switch credentials or projects",
            ):
                cli.run(
                    ["compute", "instance", "get", "computeinstance-unit"],
                    allow_not_found=True,
                )

    def test_gpu_profile_requires_frozen_experiment(self):
        self.write_request(request(profile="h100-single"))
        with self.assertRaisesRegex(broker.BrokerError, "frozen experiment"):
            broker.plan(
                self.request_path, self.lease_path, self.registry_path, self.profiles_path
            )

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

    def test_full_fake_provision_and_exact_cleanup(self):
        lease = self.make_plan()
        fake = FakeCLI()
        active = broker.provision(self.lease_path, self.registry_path, fake)
        self.assertEqual("ACTIVE", active["state"])
        self.assertTrue(active["health_proof"]["serial_log_marker_observed"])
        self.assertEqual([], active["isolation_proof"]["network"]["public_pool_ids"])
        self.assertEqual(0, active["isolation_proof"]["security_group"]["rule_count"])
        self.assertEqual(9, len(active["resources"]))
        network_payload = next(payload for kind, payload in fake.created if kind == "network")
        self.assertEqual([], network_payload["spec"]["ipv4_public_pools"]["pools"])
        self.assertEqual(
            {"allocation", "pool", "route_table"},
            {
                item["kind"]
                for item in active["resources"]
                if item.get("deletion_mode") == "PROVIDER_CASCADE"
            },
        )
        disk_payload = next(payload for kind, payload in fake.created if kind == "disk")
        self.assertNotIn("disk_encryption", disk_payload["spec"])
        self.assertEqual("NETWORK_SSD", disk_payload["spec"]["type"])
        instance_payload = next(payload for kind, payload in fake.created if kind == "instance")
        self.assertNotIn("service_account_id", instance_payload["spec"])
        self.assertNotIn("public_ip_address", instance_payload["spec"]["network_interfaces"][0])
        dry_run = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=False
        )
        self.assertEqual("instance", dry_run["delete_plan"][0]["kind"])
        released = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertTrue(all(item["delete_verified_at"] for item in released["resources"]))

    def test_public_pool_association_fails_isolation_gate(self):
        self.make_plan()
        fake = FakeCLI(public_pool_ids=["public-pool-id"])
        with self.assertRaisesRegex(broker.BrokerError, "public-pool association"):
            broker.provision(self.lease_path, self.registry_path, fake)
        failed = broker.load_json(self.lease_path)
        self.assertEqual("FAILED", failed["state"])

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
