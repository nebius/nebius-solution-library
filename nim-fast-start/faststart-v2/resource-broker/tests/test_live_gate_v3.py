from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "broker.py"
FASTSTART_ROOT = MODULE_PATH.parent.parent
AUTH_SOURCE = (
    FASTSTART_ROOT
    / "catalog-switch/cerebrium-comparator/authorizations/internal-qwen3-h100-scout-v3.json"
)
LEASE_SOURCE = (
    FASTSTART_ROOT
    / "catalog-switch/cerebrium-comparator/resource-requests/qwen3-h100-scout-v3.lease.json"
)
GLM_LEASE_SOURCE = (
    FASTSTART_ROOT
    / "catalog-switch/cerebrium-comparator/resource-requests/glm52-fp8-h200-tp8-smoke.lease.json"
)
SPEC = importlib.util.spec_from_file_location("resource_broker_live_v3", MODULE_PATH)
assert SPEC and SPEC.loader
broker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(broker)


class NoCallCLI:
    profile = "sandbox"

    def __init__(self):
        self.calls = []

    def run(self, args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("provider CLI must not be reached")


class PartialCreateCLI:
    profile = "sandbox"

    def __init__(self):
        self.created = []

    def run(self, args, *, payload=None, json_output=True, timeout=90, allow_not_found=False):
        if args[:2] == ["iam", "whoami"]:
            return {"service_account_profile": {"info": {"metadata": {"parent_id": "project-e00z6b02t8ddk96c49"}}}}
        if args[:3] == ["iam", "project", "get"]:
            return {"metadata": {"id": args[3]}, "status": {"region": "eu-north1", "container_state": "ACTIVE"}}
        if args[:3] == ["compute", "platform", "list"]:
            return {"items": [{"metadata": {"name": "gpu-h100-sxm"}, "spec": {"presets": [{"name": "1gpu-16vcpu-200gb"}]}}]}
        if args[:3] == ["quotas", "quota-allowance", "list"]:
            return {"items": []}
        if args[:3] == ["capacity", "resource-advice", "list"]:
            return {
                "items": [
                    {
                        "spec": {"region": "eu-north1", "compute_instance": {"platform": "gpu-h100-sxm", "preset": {"name": "1gpu-16vcpu-200gb"}}},
                        "status": {"preemptible": {"availability_level": "AVAILABILITY_LEVEL_MEDIUM", "available": 1}},
                    }
                ]
            }
        if args[-1:] == ["--all"] and "list" in args:
            return {"items": []}
        if args[:3] == ["vpc", "network", "create"]:
            self.created.append("network")
            return {"metadata": {"id": "network-partial"}}
        if args[:3] == ["vpc", "subnet", "create"]:
            raise KeyboardInterrupt("simulated interruption after network create")
        raise AssertionError(f"unexpected fake call: {args}")


class CleanupCLI:
    profile = "sandbox"

    def __init__(self, lease, *, foreign=False):
        self.deleted = []
        self.values = {}
        for resource in lease["resources"]:
            if resource.get("deletion_mode") == "PROVIDER_CASCADE":
                continue
            metadata = {
                "id": resource["id"],
                "name": resource["name"],
                "parent_id": resource.get("parent_id", lease["request"]["project_id"]),
                "labels": dict(lease["labels"]),
            }
            self.values[(resource["kind"], resource["id"])] = {"metadata": metadata}
        if foreign:
            first = next(iter(self.values.values()))
            first["metadata"]["labels"]["lease"] = "foreign-lease"

    def run(self, args, *, payload=None, json_output=True, timeout=90, allow_not_found=False):
        kind_map = {
            ("vpc", "network"): "network",
            ("compute", "disk"): "disk",
        }
        kind = kind_map.get(tuple(args[:2]))
        if kind is None:
            raise AssertionError(f"unexpected cleanup call: {args}")
        operation = args[2]
        resource_id = args[3]
        key = (kind, resource_id)
        if operation == "get":
            return self.values.get(key)
        if operation == "delete":
            self.deleted.append(resource_id)
            self.values.pop(key, None)
            return ""
        raise AssertionError(f"unexpected cleanup operation: {args}")


class RuleCLI:
    profile = "sandbox"

    def __init__(self, lease, *, interrupt_on_delete=None, foreign_id=None):
        self.delete_count = 0
        self.deleted = []
        self.interrupt_on_delete = interrupt_on_delete
        self.values = {}
        for resource in lease["resources"]:
            metadata = {
                "id": resource["id"],
                "name": resource["name"],
                "parent_id": resource["parent_id"],
                "labels": dict(lease["labels"]),
            }
            if resource["id"] == foreign_id:
                metadata["labels"]["task"] = "foreign-task"
            self.values[resource["id"]] = {"metadata": metadata}

    def run(self, args, *, payload=None, json_output=True, timeout=90, allow_not_found=False):
        if args[:3] == ["vpc", "security-rule", "get"]:
            return self.values.get(args[3])
        if args[:3] == ["vpc", "security-rule", "delete"]:
            self.delete_count += 1
            if self.delete_count == self.interrupt_on_delete:
                raise KeyboardInterrupt("simulated egress narrowing interruption")
            self.deleted.append(args[3])
            self.values.pop(args[3], None)
            return ""
        raise AssertionError(f"unexpected rule call: {args}")


class ManagedChildrenCLI:
    profile = "sandbox"

    def run(self, args, **_kwargs):
        if args[:3] == ["compute", "instance", "get"]:
            return {
                "metadata": {"id": args[3]},
                "status": {"network_interfaces": [{"ip_address": {"allocation_id": "private-allocation"}, "public_ip_address": {"allocation_id": "public-allocation"}}]},
            }
        if args[:3] == ["vpc", "allocation", "get"]:
            return {"metadata": {"id": args[3], "name": args[3], "created_at": "2026-08-19T15:28:00Z"}}
        if args[:3] == ["vpc", "network", "get"]:
            return {
                "metadata": {"id": args[3]},
                "spec": {"ipv4_private_pools": {"pools": [{"id": "network-private-pool"}]}, "ipv4_public_pools": {"pools": []}},
                "status": {"default_route_table_id": "route-table"},
            }
        if args[:3] == ["vpc", "subnet", "get"]:
            return {
                "metadata": {"id": args[3]},
                "spec": {"ipv4_private_pools": {"pools": [{"id": "network-private-pool"}]}, "ipv4_public_pools": {"pools": [{"id": "subnet-public-pool"}]}},
            }
        if args[:3] == ["vpc", "pool", "get"]:
            return {"metadata": {"id": args[3], "name": args[3], "created_at": "2026-08-19T15:28:00Z"}}
        if args[:3] == ["vpc", "route-table", "get"]:
            return {"metadata": {"id": args[3], "name": args[3], "created_at": "2026-08-19T15:28:00Z"}}
        raise AssertionError(f"unexpected managed-child call: {args}")


class LiveGateV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.auth_path = self.root / "authorization.json"
        self.clearance_path = self.root / "clearance.json"
        self.lease_path = self.root / "lease.json"
        self.token_path = self.root / "bearer-token"
        self.token = "a" * 64
        shutil.copyfile(LEASE_SOURCE, self.lease_path)
        auth = json.loads(AUTH_SOURCE.read_text())
        auth["network"]["bearer_token_sha256"] = hashlib.sha256(
            self.token.encode()
        ).hexdigest()
        auth["network"]["recorder_cidr_sha256"] = hashlib.sha256(
            b"203.0.113.10/32"
        ).hexdigest()
        for artifact in auth["artifacts"]:
            artifact["sha256"] = broker.file_sha256(FASTSTART_ROOT / artifact["path"])
        self.write_auth(auth)
        self.token_path.write_text(self.token + "\n")
        os.chmod(self.token_path, 0o600)
        self.write_clearance()

    def tearDown(self):
        self.temp.cleanup()

    def write_auth(self, value):
        self.auth_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

    def write_clearance(self, **updates):
        value = {
            "schema": "catalog-switch-independent-precreation-clearance/v2",
            "authorization_id": "internal-qwen3-h100-scout-v3-20260819",
            "authorization_sha256": broker.file_sha256(self.auth_path),
            "clearance_id": "independent-review-v3-unit",
            "decision": "CLEARED",
            "reviewed_at": "2026-08-19T15:29:00Z",
            "reviewed_commit": "a" * 40,
            "reviewer": "catalog-switch-independent-precreation-reviewer-v2",
            "expires_at": "2026-08-19T16:00:00Z",
        }
        value.update(updates)
        self.clearance_path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

    def validate(self, **updates):
        defaults = {
            "observed_recorder_cidr": "203.0.113.10/32",
            "current_commit": "a" * 40,
            "current_branch": "agent/catalog-switch-cerebrium-qwen3-glm52-benchmark",
            "worktree_clean": True,
            "now": dt.datetime(2026, 8, 19, 15, 30, tzinfo=dt.timezone.utc),
        }
        defaults.update(updates)
        return broker.validate_live_authorization(
            self.auth_path,
            self.clearance_path,
            self.lease_path,
            self.token_path,
            **defaults,
        )

    def test_exact_gate_returns_nonserializable_validated_context(self):
        context = self.validate()
        self.assertIsInstance(context, broker.LiveAuthorizationContext)
        self.assertNotIn(self.token, repr(context))
        self.assertEqual("CLEARED", context["public"]["clearance"]["decision"])

    def test_forged_or_zero_reviewed_commit_is_rejected(self):
        self.write_clearance(reviewed_commit="0" * 40)
        with self.assertRaisesRegex(broker.BrokerError, "exact current candidate commit"):
            self.validate(current_commit="0" * 40)
        self.write_clearance(reviewed_commit="b" * 40)
        with self.assertRaisesRegex(broker.BrokerError, "exact current candidate commit"):
            self.validate(current_commit="a" * 40)

    def test_invalid_timestamp_and_wrong_reviewer_are_rejected(self):
        self.write_clearance(reviewed_at="not-a-time")
        with self.assertRaisesRegex(broker.BrokerError, "canonical UTC"):
            self.validate()
        self.write_clearance(reviewer="self-reviewer")
        with self.assertRaisesRegex(broker.BrokerError, "exactly required reviewer"):
            self.validate()

    def test_dirty_or_wrong_branch_candidate_is_rejected(self):
        with self.assertRaisesRegex(broker.BrokerError, "clean reviewed worktree"):
            self.validate(worktree_clean=False)
        with self.assertRaisesRegex(broker.BrokerError, "reviewed branch"):
            self.validate(current_branch="main")

    def test_recorder_ip_drift_is_rejected_without_disclosing_address(self):
        with self.assertRaisesRegex(broker.BrokerError, "recorder IP drift") as caught:
            self.validate(observed_recorder_cidr="203.0.113.11/32")
        self.assertNotIn("203.0.113", str(caught.exception))

    def test_authorization_requires_two_requests_and_post_bootstrap_zero_egress(self):
        auth = json.loads(self.auth_path.read_text())
        auth["qualification"]["requests_per_runtime"] = 1
        self.write_auth(auth)
        self.write_clearance()
        with self.assertRaisesRegex(broker.BrokerError, "two validations"):
            self.validate()
        auth = json.loads(AUTH_SOURCE.read_text())
        auth["network"]["bearer_token_sha256"] = hashlib.sha256(self.token.encode()).hexdigest()
        auth["network"]["recorder_cidr_sha256"] = hashlib.sha256(b"203.0.113.10/32").hexdigest()
        auth["network"]["runtime_egress"] = [
            {"destination_cidrs": ["0.0.0.0/0"], "ports": [443], "protocol": "TCP"}
        ]
        for artifact in auth["artifacts"]:
            artifact["sha256"] = broker.file_sha256(FASTSTART_ROOT / artifact["path"])
        self.write_auth(auth)
        self.write_clearance()
        with self.assertRaisesRegex(broker.BrokerError, "network lifecycle"):
            self.validate()

    def test_observed_gpu_proof_rejects_h200_and_multiple_gpus(self):
        def marker(value):
            import base64

            raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
            return "CATSWITCH_GPU_PROOF_B64=" + base64.urlsafe_b64encode(raw).decode().rstrip("=") + "\n"

        valid = marker({"count": 1, "names": ["NVIDIA H100 80GB HBM3"], "uuids": ["GPU-aaaaaaaa-bbbb"]})
        self.assertEqual(1, broker.parse_observed_gpu_proof(valid)["count"])
        with self.assertRaisesRegex(broker.BrokerError, "not an H100"):
            broker.parse_observed_gpu_proof(
                marker({"count": 1, "names": ["NVIDIA H200"], "uuids": ["GPU-aaaaaaaa-bbbb"]})
            )
        with self.assertRaisesRegex(broker.BrokerError, "exactly one"):
            broker.parse_observed_gpu_proof(
                marker({"count": 2, "names": ["NVIDIA H100", "NVIDIA H100"], "uuids": ["GPU-aaaaaaaa-bbbb", "GPU-cccccccc-dddd"]})
            )

    def test_qwen_and_glm_provision_paths_both_fail_without_authorization(self):
        for source in (LEASE_SOURCE, GLM_LEASE_SOURCE):
            lease = self.root / (source.stem + ".json")
            shutil.copyfile(source, lease)
            fake = NoCallCLI()
            with self.assertRaisesRegex(broker.BrokerError, "mandatory live authorization"):
                broker.provision(lease, self.root / "registry.json", fake)
            self.assertEqual([], fake.calls)

    def test_plain_dictionary_cannot_forge_validated_context(self):
        fake = NoCallCLI()
        with self.assertRaisesRegex(broker.BrokerError, "not produced by the validator"):
            broker.provision(
                self.lease_path,
                self.root / "registry.json",
                fake,
                live_authorization={
                    "public": {"authorization_id": broker.QWEN_SCOUT_AUTHORIZATION_ID}
                },
            )
        self.assertEqual([], fake.calls)

    def test_interruption_after_first_create_keeps_exact_recoverable_ledger(self):
        context = self.validate()
        fake = PartialCreateCLI()
        with self.assertRaises(KeyboardInterrupt):
            broker.provision(
                self.lease_path,
                self.root / "registry.json",
                fake,
                live_authorization=context,
            )
        lease = broker.load_json(self.lease_path)
        self.assertEqual("CREATING", lease["state"])
        self.assertEqual(["network-partial"], [item["id"] for item in lease["resources"]])

    def test_partial_cleanup_is_idempotent_and_foreign_replacement_is_preserved(self):
        lease = broker.load_json(self.lease_path)
        lease["state"] = "FAILED"
        lease["resources"] = [
            {
                "kind": "network",
                "id": "network-partial",
                "name": lease["planned_resources"][0]["name"],
                "project_id": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "created_at": lease["created_at"],
                "deleted_at": None,
                "delete_verified_at": None,
            },
            {
                "kind": "disk",
                "id": "disk-partial",
                "name": next(item["name"] for item in lease["planned_resources"] if item["kind"] == "disk"),
                "project_id": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "created_at": lease["created_at"],
                "deleted_at": None,
                "delete_verified_at": None,
            },
        ]
        self.lease_path.write_text(json.dumps(lease, indent=2, sort_keys=True) + "\n")
        fake = CleanupCLI(lease)
        released = broker.cleanup(
            self.lease_path, self.root / "cleanup-registry.json", fake, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertEqual(["disk-partial", "network-partial"], fake.deleted)
        again = broker.cleanup(
            self.lease_path, self.root / "cleanup-registry.json", fake, execute=True
        )
        self.assertEqual("RELEASED", again["state"])
        self.assertEqual(2, len(fake.deleted))

        foreign_path = self.root / "foreign-lease.json"
        lease["state"] = "FAILED"
        for resource in lease["resources"]:
            resource["deleted_at"] = None
            resource["delete_verified_at"] = None
        foreign_path.write_text(json.dumps(lease, indent=2, sort_keys=True) + "\n")
        foreign = CleanupCLI(lease, foreign=True)
        with self.assertRaisesRegex(broker.BrokerError, "foreign replacement"):
            broker.cleanup(
                foreign_path, self.root / "foreign-registry.json", foreign, execute=True
            )
        self.assertLess(len(foreign.deleted), 2)

    def rule_lease(self):
        lease = broker.load_json(self.lease_path)
        lease["state"] = "CREATING"
        lease["resources"] = [
            {
                "kind": "security_rule",
                "id": f"security-rule-{index}",
                "name": f"{lease['prefix']}-bootstrap-egress-{index}",
                "parent_id": "security-group-id",
                "project_id": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "created_at": lease["created_at"],
                "deleted_at": None,
                "delete_verified_at": None,
            }
            for index in range(1, 5)
        ]
        self.lease_path.write_text(json.dumps(lease, indent=2, sort_keys=True) + "\n")
        return lease

    def test_post_bootstrap_narrowing_removes_all_egress_and_is_idempotent(self):
        lease = self.rule_lease()
        fake = RuleCLI(lease)
        broker.narrow_bootstrap_egress(
            self.lease_path, self.root / "rule-registry.json", fake
        )
        narrowed = broker.load_json(self.lease_path)
        self.assertTrue(all(item["deleted_at"] for item in narrowed["resources"]))
        self.assertEqual(4, len(fake.deleted))
        broker.narrow_bootstrap_egress(
            self.lease_path, self.root / "rule-registry.json", fake
        )
        self.assertEqual(4, len(fake.deleted))

    def test_interrupted_narrowing_resumes_and_foreign_rule_is_never_deleted(self):
        lease = self.rule_lease()
        interrupted = RuleCLI(lease, interrupt_on_delete=2)
        with self.assertRaises(KeyboardInterrupt):
            broker.narrow_bootstrap_egress(
                self.lease_path, self.root / "interrupt-registry.json", interrupted
            )
        partial = broker.load_json(self.lease_path)
        self.assertEqual(1, sum(item["deleted_at"] is not None for item in partial["resources"]))
        resumed = RuleCLI(partial)
        resumed.values.pop("security-rule-1", None)
        broker.narrow_bootstrap_egress(
            self.lease_path, self.root / "interrupt-registry.json", resumed
        )
        self.assertTrue(all(item["deleted_at"] for item in broker.load_json(self.lease_path)["resources"]))

        lease = self.rule_lease()
        foreign = RuleCLI(lease, foreign_id="security-rule-1")
        with self.assertRaisesRegex(broker.BrokerError, "foreign replacement"):
            broker.narrow_bootstrap_egress(
                self.lease_path, self.root / "foreign-rule-registry.json", foreign
            )
        self.assertNotIn("security-rule-1", foreign.deleted)

    def test_public_ip_pool_allocations_and_route_are_lease_bound_children(self):
        lease = broker.load_json(self.lease_path)
        lease["resources"] = [
            {
                "kind": kind,
                "id": f"{kind}-id",
                "name": f"{lease['prefix']}-{kind}",
                "project_id": lease["request"]["project_id"],
                "region": lease["request"]["region"],
                "created_at": lease["created_at"],
                "deleted_at": None,
                "delete_verified_at": None,
            }
            for kind in ("instance", "network", "subnet")
        ]
        broker.reconcile_managed_children(lease, ManagedChildrenCLI())
        children = {
            item["id"]: item["managed_by_resource_id"]
            for item in lease["resources"]
            if item.get("deletion_mode") == "PROVIDER_CASCADE"
        }
        self.assertEqual(
            {
                "private-allocation": "instance-id",
                "public-allocation": "instance-id",
                "network-private-pool": "network-id",
                "subnet-public-pool": "subnet-id",
                "route-table": "network-id",
            },
            children,
        )


if __name__ == "__main__":
    unittest.main()
