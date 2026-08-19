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

    def __init__(
        self,
        public_pool_ids=None,
        subnet_public_pool_ids=None,
        *,
        fail_on_create=None,
        interrupt_on_create=None,
        health_log="CATALOG_SWITCH_HEALTH_OK lease=unit-test-lease",
        include_created_in_lists=False,
    ) -> None:
        self.created = []
        self.deleted = []
        self.absent = set()
        self.public_pool_ids = public_pool_ids or []
        self.subnet_public_pool_ids = subnet_public_pool_ids or []
        self.objects = {}
        self.security_rules = []
        self.fail_on_create = fail_on_create
        self.interrupt_on_create = interrupt_on_create
        self.health_log = health_log
        self.include_created_in_lists = include_created_in_lists

    def object_metadata(self, resource_id):
        return self.objects.get(resource_id, {}).get(
            "metadata", {"id": resource_id, "name": f"managed-{resource_id}"}
        )

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
        if args[:3] == ["vpc", "security-rule", "list"]:
            return {"items": self.security_rules}
        if args[-1:] == ["--all"] and "list" in args:
            if self.include_created_in_lists:
                kind_by_command = {
                    ("vpc", "network"): "network-id",
                    ("vpc", "subnet"): "subnet-id",
                    ("vpc", "security-group"): "security_group-id",
                    ("compute", "disk"): "disk-id",
                    ("compute", "instance"): "instance-id",
                    ("storage", "bucket"): "bucket-id",
                }
                resource_id = kind_by_command.get(tuple(args[:2]))
                if resource_id and resource_id in self.objects and resource_id not in self.absent:
                    return {"items": [self.objects[resource_id]]}
            return {"items": []}
        if args[:3] == ["compute", "instance", "get"]:
            if args[3] in self.absent:
                return None
            created_spec = self.objects.get(args[3], {}).get("spec", {})
            interface_spec = (created_spec.get("network_interfaces") or [{}])[0]
            status_interface = {"ip_address": {"allocation_id": "allocation-id"}}
            if "public_ip_address" in interface_spec:
                status_interface["public_ip_address"] = {
                    "allocation_id": "public-allocation-id"
                }
            return {
                "metadata": self.object_metadata(args[3]),
                "spec": {
                    "resources": created_spec.get(
                        "resources", {"platform": "cpu-e2", "preset": "2vcpu-8gb"}
                    ),
                    "preemptible": created_spec.get(
                        "preemptible", {"on_preemption": "STOP", "priority": 3}
                    ),
                    "network_interfaces": created_spec.get(
                        "network_interfaces", [{"ip_address": {}}]
                    ),
                    "service_account_id": created_spec.get("service_account_id"),
                    "local_disks": created_spec.get("local_disks"),
                },
                "status": {
                    "state": "RUNNING",
                    "network_interfaces": [status_interface],
                },
            }
        if args[:3] == ["vpc", "network", "get"] and not allow_not_found:
            return {
                "metadata": self.object_metadata(args[3]),
                "spec": {
                    "ipv4_private_pools": {"pools": [{"id": "private-pool-id"}]},
                    "ipv4_public_pools": {
                        "pools": [{"id": value} for value in self.public_pool_ids]
                    },
                },
                "status": {"default_route_table_id": "route-table-id"},
            }
        if args[:3] == ["vpc", "subnet", "get"] and not allow_not_found:
            return {
                "metadata": self.object_metadata(args[3]),
                "spec": {
                    "ipv4_private_pools": {"pools": []},
                    "ipv4_public_pools": {
                        "pools": [{"id": value} for value in self.subnet_public_pool_ids]
                    },
                },
            }
        if args[:3] == ["vpc", "allocation", "get"] and not allow_not_found:
            return {
                "metadata": {
                    "id": args[3],
                    "name": "auto-allocation",
                    "created_at": "2026-08-19T00:00:00Z",
                }
            }
        if args[:3] == ["compute", "disk", "get"] and not allow_not_found:
            created_spec = self.objects.get(args[3], {}).get("spec", {})
            return {
                "metadata": self.object_metadata(args[3]),
                "spec": {"type": created_spec.get("type", "NETWORK_SSD")},
                "status": {
                    "size_bytes": str(created_spec.get("size_bytes", 21474836480)),
                    "source_image_id": "computeimage-test",
                },
            }
        if args[:3] == ["storage", "bucket", "get"] and not allow_not_found:
            created_spec = self.objects.get(args[3], {}).get("spec", {})
            return {
                "metadata": self.object_metadata(args[3]),
                "spec": {
                    "max_size_bytes": str(created_spec.get("max_size_bytes", 1073741824)),
                    "default_storage_class": created_spec.get(
                        "default_storage_class", "STANDARD"
                    ),
                    "object_audit_logging": created_spec.get(
                        "object_audit_logging", "ALL"
                    ),
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
            return self.health_log
        if args[:3] == ["compute", "instance", "logs"]:
            return self.health_log
        if args[:2] in (["vpc", "network"], ["vpc", "subnet"], ["vpc", "security-group"]):
            if len(args) >= 3 and args[2] == "create":
                kind = args[1].replace("-", "_")
                if self.interrupt_on_create == kind:
                    raise KeyboardInterrupt(f"interrupted during {kind} create")
                if self.fail_on_create == kind:
                    raise broker.BrokerError(f"injected {kind} create failure")
                resource_id = f"{kind}-id"
                self.created.append((kind, payload))
                value = {
                    "metadata": {**payload["metadata"], "id": resource_id},
                    "spec": payload["spec"],
                }
                self.objects[resource_id] = value
                return value
        if args[:2] in (["compute", "disk"], ["compute", "instance"], ["storage", "bucket"]):
            if len(args) >= 3 and args[2] == "create":
                kind = args[1]
                if self.interrupt_on_create == kind:
                    raise KeyboardInterrupt(f"interrupted during {kind} create")
                if self.fail_on_create == kind:
                    raise broker.BrokerError(f"injected {kind} create failure")
                resource_id = f"{kind}-id"
                self.created.append((kind, payload))
                value = {
                    "metadata": {**payload["metadata"], "id": resource_id},
                    "spec": payload["spec"],
                }
                self.objects[resource_id] = value
                return value
        if args[:3] == ["vpc", "security-rule", "create"]:
            if self.interrupt_on_create == "security_rule":
                raise KeyboardInterrupt("interrupted during security_rule create")
            if self.fail_on_create == "security_rule":
                raise broker.BrokerError("injected security_rule create failure")
            resource_id = f"security-rule-{len(self.security_rules) + 1}-id"
            value = {
                "metadata": {**payload["metadata"], "id": resource_id},
                "spec": payload["spec"],
            }
            self.created.append(("security_rule", payload))
            self.objects[resource_id] = value
            self.security_rules.append(value)
            return value
        if len(args) >= 3 and args[2] == "delete":
            resource_id = args[3]
            self.deleted.append(resource_id)
            self.absent.add(resource_id)
            if resource_id == "instance-id":
                self.absent.update({"allocation-id", "public-allocation-id"})
            if resource_id == "security_group-id":
                self.absent.update(
                    item["metadata"]["id"] for item in self.security_rules
                )
            if resource_id == "subnet-id":
                self.absent.update(self.subnet_public_pool_ids)
            if resource_id == "network-id":
                self.absent.update({"private-pool-id", "public-pool-id", "route-table-id"})
            return ""
        if len(args) >= 3 and args[2] == "get" and allow_not_found:
            if args[3] in self.absent:
                return None
            return self.objects.get(args[3], {"metadata": {"id": args[3]}})
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


class FakeH100CLI(FakeCLI):
    def __init__(self, **kwargs):
        super().__init__(
            subnet_public_pool_ids=["subnet-public-pool-id"],
            health_log=(
                "CATSWITCH_QWEN3_H100_OK "
                "lease=catswitch-qwen3-h100-scout-20260819"
            ),
            **kwargs,
        )

    def run(self, args, **kwargs):
        if args[:3] == ["compute", "platform", "list"]:
            return {
                "items": [
                    {
                        "metadata": {"name": "gpu-h100-sxm"},
                        "spec": {"presets": [{"name": "1gpu-16vcpu-200gb"}]},
                    }
                ]
            }
        if args[:3] == ["capacity", "resource-advice", "list"]:
            return {
                "items": [
                    {
                        "spec": {
                            "region": "eu-north1",
                            "compute_instance": {
                                "platform": "gpu-h100-sxm",
                                "preset": {"name": "1gpu-16vcpu-200gb"},
                            },
                        },
                        "status": {
                            "preemptible": {
                                "availability_level": "AVAILABILITY_LEVEL_HIGH",
                                "available": 1,
                            }
                        },
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


def qwen_request(**overrides):
    value = request(
        artifact_storage={"enabled": True, "max_size_gib": 64},
        cleanup_owner="cerebrium-comparator",
        expected_duration_hours="2",
        experiment={
            "model_id": (
                "Qwen/Qwen3-8B@"
                "b968826d9c46dd6066d109eabc6255188de91218"
            ),
            "input_sha256": (
                "c3e3250abbb92869b7a51325a5fd5358"
                "eb98122d73698956cf064ed491d3291d"
            ),
            "metric_contract_sha256": (
                "e6a36c56455cdb5a603eadc1d017816"
                "92899ba789a4459bc26e631b5d4d11cba"
            ),
            "metric_contract_path": (
                "catalog-switch/cerebrium-comparator/contracts/campaign.json"
            ),
            "cleanup_plan": "exact-ID and cascade-child cleanup with absence proof",
        },
        health_proof={"marker": "CATSWITCH_QWEN3_H100_OK", "timeout_seconds": 900},
        lease_id="catswitch-qwen3-h100-scout-20260819",
        owner="cerebrium-comparator",
        profile="h100-single",
        purpose="Fresh isolated H100 Qwen scout used only by authorization unit tests.",
        task_id="catalog-switch-cerebrium-qwen3-glm52-benchmark",
        ttl_hours=4,
    )
    value.update(overrides)
    return value


def live_context():
    source = Path(__file__).resolve().parents[2] / "catalog-switch" / "cerebrium-comparator"
    artifacts = [
        {
            "path": "catalog-switch/cerebrium-comparator/live/bootstrap_internal_qwen.sh",
            "sha256": broker.file_sha256(source / "live" / "bootstrap_internal_qwen.sh"),
            "target": "/opt/catswitch/bootstrap_internal_qwen.sh",
        },
        {
            "path": "catalog-switch/cerebrium-comparator/live/internal_scout_server.py",
            "sha256": broker.file_sha256(source / "live" / "internal_scout_server.py"),
            "target": "/opt/catswitch/internal_scout_server.py",
        },
    ]
    egress = [
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [443], "protocol": "TCP", "purpose": "TLS artifact and container-registry localization"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [80], "protocol": "TCP", "purpose": "bootstrap OS packages only when the image lacks Docker"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [53], "protocol": "UDP", "purpose": "DNS resolution"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [53], "protocol": "TCP", "purpose": "DNS fallback"},
        {"destination_cidrs": ["0.0.0.0/0"], "ports": [123], "protocol": "UDP", "purpose": "UTC clock synchronization for external recorder evidence"},
    ]
    return {
        "public": {
            "authorization_id": "internal-qwen3-h100-scout-v2-20260819",
            "authorization_sha256": "a" * 64,
            "state": "PRE_CREATION_REVIEW",
            "recorder_cidr_sha256": broker.hashlib.sha256(b"203.0.113.7/32").hexdigest(),
            "bearer_token_sha256": broker.hashlib.sha256(b"b" * 64).hexdigest(),
            "bootstrap_artifacts": artifacts,
            "network_policy": {},
            "secret_values_published": False,
            "independent_clearance": {"decision": "CLEARED"},
        },
        "authorization": {
            "bootstrap_artifacts": artifacts,
            "network": {"egress": egress},
        },
        "_recorder_cidr": "203.0.113.7/32",
        "_bearer_token": "b" * 64,
    }


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

    def make_qwen_plan(self):
        self.write_request(qwen_request())
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

    def test_precreation_candidate_cannot_promote_without_independent_clearance(self):
        self.make_qwen_plan()
        context = live_context()
        context["public"].pop("independent_clearance")
        with self.assertRaisesRegex(broker.BrokerError, "independent review"):
            broker.provision(
                self.lease_path,
                self.registry_path,
                FakeH100CLI(),
                live_authorization=context,
            )
        self.assertEqual("PLANNED", broker.load_json(self.lease_path)["state"])
        self.assertEqual([], broker.load_json(self.lease_path)["resources"])

    def test_authorized_network_is_exact_and_default_air_gap_is_unchanged(self):
        self.make_qwen_plan()
        fake = FakeH100CLI()
        active = broker.provision(
            self.lease_path,
            self.registry_path,
            fake,
            live_authorization=live_context(),
        )
        self.assertEqual("ACTIVE", active["state"])
        self.assertEqual(1, len(active["isolation_proof"]["instance"]["public_ip_allocation_ids"]))
        self.assertEqual(1, len(active["isolation_proof"]["subnet"]["public_pool_ids"]))
        rules = active["isolation_proof"]["security_group"]["rules"]
        self.assertEqual(6, len(rules))
        ingress = [item for item in rules if item["direction"] == "ingress"]
        self.assertEqual([8080], ingress[0]["ports"])
        self.assertNotIn(22, ingress[0]["ports"])
        self.assertNotIn(8000, ingress[0]["ports"])
        serialized = json.dumps(active)
        self.assertNotIn("203.0.113.7", serialized)
        instance_payload = next(
            payload for kind, payload in fake.created if kind == "instance"
        )
        self.assertIn(
            "public_ip_address", instance_payload["spec"]["network_interfaces"][0]
        )
        released = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        deleted_before = list(fake.deleted)
        replay = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", replay["state"])
        self.assertEqual(deleted_before, fake.deleted)

    def test_partial_create_failure_retains_ledger_and_cleans_every_known_child(self):
        self.make_qwen_plan()
        fake = FakeH100CLI(fail_on_create="disk")
        with self.assertRaisesRegex(broker.BrokerError, "injected disk"):
            broker.provision(
                self.lease_path,
                self.registry_path,
                fake,
                live_authorization=live_context(),
            )
        failed = broker.load_json(self.lease_path)
        self.assertEqual("FAILED", failed["state"])
        self.assertTrue(any(item["kind"] == "security_rule" for item in failed["resources"]))
        self.assertTrue(any(item["id"] == "subnet-public-pool-id" for item in failed["resources"]))
        released = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertTrue(all(item["delete_verified_at"] for item in released["resources"]))

    def test_keyboard_interrupt_leaves_recoverable_creating_ledger(self):
        self.make_qwen_plan()
        fake = FakeH100CLI(interrupt_on_create="disk")
        with self.assertRaises(KeyboardInterrupt):
            broker.provision(
                self.lease_path,
                self.registry_path,
                fake,
                live_authorization=live_context(),
            )
        interrupted = broker.load_json(self.lease_path)
        self.assertEqual("CREATING", interrupted["state"])
        self.assertGreater(len(interrupted["resources"]), 0)
        released = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])

    def test_interruption_gap_recovers_provider_created_resource_before_cleanup(self):
        self.make_qwen_plan()
        fake = FakeH100CLI(include_created_in_lists=True)
        active = broker.provision(
            self.lease_path,
            self.registry_path,
            fake,
            live_authorization=live_context(),
        )
        active["resources"] = [
            item for item in active["resources"] if item["id"] != "disk-id"
        ]
        active["state"] = "FAILED"
        broker.save_lease(self.lease_path, self.registry_path, active)
        released = broker.cleanup(
            self.lease_path, self.registry_path, fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertIn("disk-id", fake.deleted)
        self.assertTrue(
            any(
                event["type"] == "INTERRUPTED_CREATE_RECONCILED"
                and "disk:disk-id" in event["details"]
                for event in released["events"]
            )
        )

    def test_foreign_replacement_is_never_deleted(self):
        self.make_qwen_plan()
        fake = FakeH100CLI(fail_on_create="instance")
        with self.assertRaisesRegex(broker.BrokerError, "injected instance"):
            broker.provision(
                self.lease_path,
                self.registry_path,
                fake,
                live_authorization=live_context(),
            )
        disk_labels = dict(fake.objects["disk-id"]["metadata"]["labels"])
        disk_labels["lease"] = "foreign-lease"
        fake.objects["disk-id"]["metadata"]["labels"] = disk_labels
        with self.assertRaisesRegex(broker.BrokerError, "foreign replacement"):
            broker.cleanup(self.lease_path, self.registry_path, fake, execute=True)
        self.assertNotIn("disk-id", fake.deleted)
        self.assertEqual("CLEANUP_FAILED", broker.load_json(self.lease_path)["state"])

    def test_versioned_authorization_rejects_ip_drift_and_publishes_hashes_only(self):
        source_root = Path(__file__).resolve().parents[2]
        lease = broker.load_json(
            source_root
            / "catalog-switch/cerebrium-comparator/resource-requests/qwen3-h100-scout.lease.json"
        )
        lease["expires_at"] = "2099-08-19T18:25:41Z"
        lease_path = self.root / "authorization-lease.json"
        broker.atomic_json(lease_path, lease)
        authorization = broker.load_json(
            source_root
            / "catalog-switch/cerebrium-comparator/authorizations/internal-qwen3-h100-scout-v2.json"
        )
        authorization["expires_at"] = lease["expires_at"]
        authorization["frozen"]["lease_plan_sha256"] = broker.file_sha256(lease_path)
        bearer = "b" * 64
        authorization["bearer_token_sha256"] = broker.hashlib.sha256(
            bearer.encode()
        ).hexdigest()
        authorization["network"]["recorder_cidr_sha256"] = broker.hashlib.sha256(
            b"203.0.113.7/32"
        ).hexdigest()
        for artifact in authorization["bootstrap_artifacts"]:
            artifact["sha256"] = broker.file_sha256(source_root / artifact["path"])
        authorization_path = self.root / "authorization.json"
        broker.atomic_json(authorization_path, authorization)
        bearer_path = self.root / "bearer-token"
        bearer_path.write_text(bearer)
        bearer_path.chmod(0o600)
        context = broker.validate_live_authorization(
            authorization_path,
            lease_path,
            bearer_path,
            observed_recorder_cidr="203.0.113.7/32",
        )
        published = json.dumps(context["public"], sort_keys=True)
        self.assertNotIn("203.0.113.7", published)
        self.assertNotIn(bearer, published)
        self.assertFalse(context["public"]["secret_values_published"])
        with self.assertRaisesRegex(broker.BrokerError, "IP drift"):
            broker.validate_live_authorization(
                authorization_path,
                lease_path,
                bearer_path,
                observed_recorder_cidr="203.0.113.8/32",
            )
        with self.assertRaisesRegex(broker.BrokerError, "independent PRE-CREATION REVIEW"):
            broker.validate_live_authorization(
                authorization_path,
                lease_path,
                bearer_path,
                observed_recorder_cidr="203.0.113.7/32",
                require_cleared=True,
            )

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
