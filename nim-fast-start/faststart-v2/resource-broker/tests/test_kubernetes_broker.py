from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


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


OPENFOLD_TARGET = {
    "model_id": "openfold2",
    "model_version": "2.5.0",
    "artifact_id": "openfold2-unit-v1",
    "artifact_version": "1",
    "artifact_sha256": "6" * 64,
}
OPENFOLD_INPUT = {
    "workload_id": "protein-structure-two-call",
    "input_id": "openfold2-unit-input",
    "payload_sha256": "3" * 64,
    "input_bytes": 423,
}
BOLTZ_TARGET = {
    "model_id": "boltz2",
    "model_version": "unit-v1",
    "artifact_id": "boltz2-unit-v1",
    "artifact_version": "1",
    "artifact_sha256": "7" * 64,
}
BOLTZ_INPUT = {
    "workload_id": "protein-structure-two-call",
    "input_id": "boltz2-unit-input",
    "payload_sha256": "4" * 64,
    "input_bytes": 411,
}


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def request(**overrides):
    value = {
        "schema_version": "catalog-switch-kubernetes-lease-request/v5",
        "lease_id": "k8s-unit-new-node",
        "task_id": "catalog-switch-k8s-baseline",
        "owner": "catalog-switch-k8s-baseline",
        "cleanup_owner": "catalog-switch-resource-broker",
        "purpose": "Fresh isolated Kubernetes new-node contract unit test.",
        "campaign_arm": "B_new_preemptible_node",
        "project_id": "project-e00z6b02t8ddk96c49",
        "region": "eu-north1",
        "nebius_profile": "sandbox",
        "authority_identity": {
            "type": "service_account_profile",
            "id": "serviceaccount-caller",
            "parent_id": "project-i00xz31gpr00xp9jhp982v",
        },
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
        "trace_id": "unit-trace",
        "trace_sha256": "2" * 64,
        "allowed_scenarios": ["a_to_b_remote", "capacity_miss"],
        "model_input_sha256s": {"openfold2": "3" * 64, "boltz2": "4" * 64},
        "model_request_bindings": {
            "openfold2": {"target": OPENFOLD_TARGET, "input": OPENFOLD_INPUT},
            "boltz2": {"target": BOLTZ_TARGET, "input": BOLTZ_INPUT},
        },
        "accepted_event_authority_id": "catalog-switch-k8s-external-client-v1",
        "private_runner_authority_id": "catalog-switch-private-runner-reviewer-v1",
        "private_runner_receipt": {
            "status": "PENDING_CONSUMER_PROOF",
            "path": None,
            "sha256": None,
            "source_commit": None,
        },
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
        self.created_payloads = {}
        self.fail_after_create_kind = None
        self.failed_once = False
        self.capacity_available = True
        self.pool_id = "vpcpool-unit-private"
        self.route_id = "vpcroutetable-unit-default"
        self.node_by_group = {}
        self.fail_delete_id = None
        self.crash_after_delete_id = None
        self.reject_duplicate_delete = True
        self.fail_get_credentials_before_write = False
        self.create_delay_seconds = 0.0
        self.provider_public_ip = None

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

    def replace_node(self, group_id):
        old_id = self.node_by_group[group_id]
        self.absent.add(old_id)
        group = self.resources[group_id]
        role = "system" if group["_kind"] == "system_node_group" else "gpu"
        new_id = f"computeinstance-unitreplacement{role}"
        template = group["spec"]["template"]
        spec = {
            "node_group_id": group_id,
            "resources": dict(template["resources"]),
            "network_interfaces": json.loads(json.dumps(template["network_interfaces"])),
        }
        if role == "gpu":
            spec["preemptible"] = {}
        self.resources[new_id] = {
            "_kind": "node",
            "metadata": {
                "id": new_id,
                "name": f"{group_id}-replacement",
                "parent_id": "project-e00z6b02t8ddk96c49",
                "created_at": timestamp(),
                "labels": {"mk8s.nebius.com/node-group-id": group_id},
            },
            "spec": spec,
            "status": {
                "state": "RUNNING",
                "node_group_id": group_id,
                "network_interfaces": [
                    {
                        "network_id": self.resources[
                            template["network_interfaces"][0]["subnet_id"]
                        ]["spec"]["network_id"],
                        "subnet_id": template["network_interfaces"][0]["subnet_id"],
                        "ip_address": "10.42.0.30" if role == "system" else "10.42.0.40",
                        "public_ip_address": self.provider_public_ip,
                    }
                ],
            },
        }
        self.node_by_group[group_id] = new_id
        return old_id, new_id

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
            if self.fail_get_credentials_before_write:
                raise k8s.common.BrokerError("simulated interruption before kubeconfig write")
            path = Path(args[args.index("--kubeconfig") + 1])
            context = args[args.index("--context-name") + 1]
            path.write_text(
                "apiVersion: v1\n"
                "clusters:\n"
                f"- name: {context}-cluster\n"
                "  cluster:\n"
                "    server: https://unit-cluster.internal:443\n"
                "    certificate-authority-data: dW5pdC1jYQ==\n"
                "contexts:\n"
                f"- name: {context}\n"
                "  context:\n"
                f"    cluster: {context}-cluster\n"
                f"    user: {context}-user\n"
                f"current-context: {context}\n"
                "users:\n"
                f"- name: {context}-user\n"
                "  user:\n"
                "    token: unit-token-not-recorded\n"
            )
            os.chmod(path, 0o600)
            return ""

        kind = self.kind(args)
        action_index = 3 if args[:2] == ["mk8s", "v1"] else 1 if args[0] == "registry" else 2
        action = args[action_index] if len(args) > action_index else None
        if action == "create":
            if self.create_delay_seconds:
                time.sleep(self.create_delay_seconds)
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
            if actual_kind in {"cluster", "system_node_group", "gpu_node_group"}:
                k8s.validate_provider_create_payload(actual_kind, payload)
            number = self.created_count.get(actual_kind, 0) + 1
            self.created_count[actual_kind] = number
            self.created_payloads.setdefault(actual_kind, []).append(
                json.loads(json.dumps(payload))
            )
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
                        "endpoints": {"internal_endpoint": "https://unit-cluster.internal:443"},
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
                node_id = f"computeinstance-unitnode{role}{number}"
                self.node_by_group[resource_id] = node_id
                node_spec = {
                    "node_group_id": resource_id,
                    "resources": dict(payload["spec"]["template"]["resources"]),
                    "network_interfaces": json.loads(
                        json.dumps(payload["spec"]["template"]["network_interfaces"])
                    ),
                }
                if actual_kind == "gpu_node_group":
                    node_spec["preemptible"] = {}
                self.resources[node_id] = {
                    "_kind": "node",
                    "metadata": {
                        "id": node_id,
                        "name": f"{resource_id}-unit-node",
                        "parent_id": "project-e00z6b02t8ddk96c49",
                        "created_at": timestamp(),
                        "labels": {"mk8s.nebius.com/node-group-id": resource_id},
                    },
                    "spec": node_spec,
                    "status": {
                        "state": "RUNNING",
                        "node_group_id": resource_id,
                        "network_interfaces": [
                            {
                                "network_id": self.resources[
                                    payload["spec"]["template"]["network_interfaces"][0][
                                        "subnet_id"
                                    ]
                                ]["spec"]["network_id"],
                                "subnet_id": payload["spec"]["template"][
                                    "network_interfaces"
                                ][0]["subnet_id"],
                                "ip_address": "10.42.0.10"
                                if role == "system"
                                else "10.42.0.20",
                                "public_ip_address": self.provider_public_ip,
                            }
                        ],
                    },
                }
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
            if resource_id in self.absent and self.reject_duplicate_delete:
                raise k8s.common.BrokerError(f"duplicate delete rejected: {resource_id}")
            if resource_id == self.fail_delete_id:
                raise k8s.common.BrokerError(f"simulated delete failure: {resource_id}")
            self.deleted.append(resource_id)
            self.absent.add(resource_id)
            value = self.resources.get(resource_id, {})
            if value.get("_kind") in {"system_node_group", "gpu_node_group"}:
                self.absent.add(self.node_by_group[resource_id])
            if value.get("_kind") == "network":
                self.absent.update({self.pool_id, self.route_id})
            if resource_id == self.crash_after_delete_id:
                self.crash_after_delete_id = None
                raise KeyboardInterrupt("simulated process crash after provider delete")
            return ""
        raise AssertionError(f"unexpected fake CLI call: {args}")

    @staticmethod
    def _not_found(resource_id):
        raise k8s.common.BrokerError(f"not found: {resource_id}")


class FakeKubectl:
    def __init__(self, cli):
        self.cli = cli
        self.gpu_product = "NVIDIA-H100-80GB-HBM3"
        self.gpu_allocatable = "1"

    def run(self, kubeconfig, args, timeout=90):
        if args[:2] == ["config", "view"]:
            return {
                "current-context": "unit",
                "clusters": [{"cluster": {"server": "https://unit-cluster.internal:443"}}],
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
                                **(
                                    {"nvidia.com/gpu.product": self.gpu_product}
                                    if role == "gpu"
                                    else {}
                                ),
                            },
                        },
                        "spec": {"providerID": f"nebius:///{node_id}"},
                        "status": {
                            "conditions": [{"type": "Ready", "status": "True"}],
                            "addresses": [
                                {
                                    "type": "InternalIP",
                                    "address": self.cli.resources[node_id]["status"][
                                        "network_interfaces"
                                    ][0]["ip_address"],
                                },
                                *(
                                    [
                                        {
                                            "type": "ExternalIP",
                                            "address": self.cli.resources[node_id]["status"][
                                                "network_interfaces"
                                            ][0]["public_ip_address"],
                                        }
                                    ]
                                    if self.cli.resources[node_id]["status"][
                                        "network_interfaces"
                                    ][0].get("public_ip_address")
                                    else []
                                ),
                            ],
                            "allocatable": {"nvidia.com/gpu": self.gpu_allocatable}
                            if role == "gpu"
                            else {},
                        },
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
        self.accepted_ledger_path = self.root / "accepted.jsonl"
        self.accepted_receipt_path = self.root / "accepted-receipt.json"
        self.external_private_key = Ed25519PrivateKey.generate()
        self.runner_reviewer_private_key = Ed25519PrivateKey.generate()
        public_key = self.external_private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        runner_reviewer_public_key = self.runner_reviewer_private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        profiles = json.loads((MODULE_PATH.parent / "kubernetes_profiles.json").read_text())
        profiles["accepted_event_authorities"]["catalog-switch-k8s-external-client-v1"] = {
            "status": "REVIEWED_ACTIVE",
            "recorder_id": "catalog-switch-k8s-external-client",
            "receipt_schema_version": k8s.EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA,
            "validator_id": "catalog-switch-request-slo-ledger-validator-v1",
            "validator_sha256": "8" * 64,
            "validator_reviewed_commit": "9" * 40,
            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
        }
        profiles["private_runner_attestation_authorities"][
            "catalog-switch-private-runner-reviewer-v1"
        ] = {
            "status": "REVIEWED_ACTIVE",
            "reviewer_id": "catalog-switch-independent-runner-reviewer",
            "attestation_schema_version": k8s.PRIVATE_RUNNER_RECEIPT_SCHEMA,
            "validator_sha256": "c" * 64,
            "validator_reviewed_commit": "d" * 40,
            "public_key_base64": base64.b64encode(runner_reviewer_public_key).decode("ascii"),
        }
        self.runner_execution = {
            "runner_instance_id": "computeinstance-unit-private-runner",
            "runner_boot_id": "runner-boot-unit",
            "runner_netns_inode": 424242,
            "private_interface": {
                "name": "eth0",
                "mac_address": "02:00:00:00:00:42",
                "ipv4_address": "10.99.0.8",
                "prefix_length": 24,
            },
        }
        self.source_identity = {
            "source_commit": "a" * 40,
            "source_tree_oid": "b" * 40,
            "source_manifest_sha256": "1" * 64,
            "source_manifest": [
                {
                    "path": "nim-fast-start/faststart-v2/resource-broker/broker.py",
                    "sha256": "f" * 64,
                    "size_bytes": 101,
                },
                {
                    "path": "nim-fast-start/faststart-v2/resource-broker/kubernetes_broker.py",
                    "sha256": "e" * 64,
                    "size_bytes": 202,
                },
            ],
            "entrypoint_sha256": "e" * 64,
            "common_cli_sha256": "f" * 64,
        }
        self.runner_observer = mock.patch.object(
            k8s,
            "observe_runner_execution",
            side_effect=lambda _interface: json.loads(json.dumps(self.runner_execution)),
        )
        self.runner_observer.start()
        self.addCleanup(self.runner_observer.stop)
        self.source_observer = mock.patch.object(
            k8s,
            "observe_broker_source_identity",
            side_effect=lambda: json.loads(json.dumps(self.source_identity)),
        )
        self.source_observer.start()
        self.addCleanup(self.source_observer.stop)
        self.profiles_path = self.root / "profiles.json"
        self.profiles_path.write_text(json.dumps(profiles))
        self.request_value = self.make_request()
        k8s.KUBECONFIG_ROOT = self.root / "kubeconfigs"
        k8s.LEASE_KEY_ROOT = self.root / "lease-keys"
        supervisor.k8s.LEASE_KEY_ROOT = k8s.LEASE_KEY_ROOT
        self.cli = FakeCLI()
        self.kubectl = FakeKubectl(self.cli)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, value=None):
        self.request_path.write_text(json.dumps(value or self.request_value))
        return k8s.plan(
            self.request_path, self.lease_path, self.registry_path, self.profiles_path
        )

    def make_request(self, **overrides):
        value = request(**overrides)
        receipt_path = self.root / f"runner-{value['lease_id']}.json"
        material = {
            "schema_version": k8s.PRIVATE_RUNNER_RECEIPT_SCHEMA,
            "authority_id": value["private_runner_authority_id"],
            "reviewer_id": "catalog-switch-independent-runner-reviewer",
            "status": "PASS",
            "consumer_task_id": value["task_id"],
            "lease_id": value["lease_id"],
            "project_id": value["project_id"],
            "region": value["region"],
            "runner_owner_task": value["task_id"],
            "network_path": "task-owned-private-subnet",
            "api_server_access": "internal-only",
            "public_ip": False,
            "public_ingress": False,
            "implementation_sha256": "c" * 64,
            "reviewer_source_commit": "d" * 40,
            **self.source_identity,
            **self.runner_execution,
            "runner_network_id": "vpcnetwork-unit-private-runner",
            "runner_subnet_id": "vpcsubnet-unit-private-runner",
            "attested_at_utc": timestamp(),
        }
        receipt = {
            "material": material,
            "signature_base64": base64.b64encode(
                self.runner_reviewer_private_key.sign(
                    k8s.runner_attestation_message(material)
                )
            ).decode("ascii"),
        }
        receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n")
        os.chmod(receipt_path, 0o600)
        value["private_runner_receipt"] = {
            "status": "REVIEWED_ACTIVE",
            "path": str(receipt_path.resolve()),
            "sha256": k8s.hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "source_commit": self.source_identity["source_commit"],
        }
        return value

    def support(self):
        self.plan()
        return k8s.provision_control_plane(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )

    def demand(
        self,
        *,
        event_overrides=None,
        receipt_overrides=None,
        demand_overrides=None,
        record=True,
    ):
        boot_id = k8s.current_boot_id()
        lease = json.loads(self.lease_path.read_text())
        binding = self.request_value["model_request_bindings"]["openfold2"]
        accepted_event = {
            "schema": "archvteams.nebius.ai/catalog-switch-ledger-event/v1",
            "ledger_id": "unit-ledger",
            "ledger_sequence": 0,
            "trace_id": "unit-trace",
            "request_id": "unit-request-000001",
            "attempt_id": "attempt-000001",
            "attempt_sequence": 0,
            "event_id": "attempt-000001:000000",
            "observed_at_utc": timestamp(),
            "observed_monotonic_ns": time.monotonic_ns() - 1,
            "recorder": {
                "recorder_id": "catalog-switch-k8s-external-client",
                "clock_id": f"linux-boottime:{boot_id}",
                "boot_id": boot_id,
                "utc_sync_source": "unit-test",
                "max_error_ms": 1,
            },
            "event_type": "request.accepted",
            "data": {
                "boundary": "external-client-request-accepted/v1",
                "lease_id": lease["lease_id"],
                "request_sha256": lease["request_sha256"],
                "plan_sha256": lease["plan_sha256"],
                "metric_contract_sha256": self.request_value["metric_contract_sha256"],
                "trace_request_sha256": self.request_value["trace_sha256"],
                "scenario": "capacity_miss",
                "target": json.loads(json.dumps(binding["target"])),
                "input": json.loads(json.dumps(binding["input"])),
                "precondition": {},
                "environment": {},
                "ownership": {},
            },
        }
        if event_overrides:
            for key, value in event_overrides.items():
                if key.startswith("data."):
                    nested = key.split(".")[1:]
                    target = accepted_event["data"]
                    for part in nested[:-1]:
                        target = target[part]
                    target[nested[-1]] = value
                elif key.startswith("recorder."):
                    accepted_event["recorder"][key.split(".", 1)[1]] = value
                else:
                    accepted_event[key] = value
        self.accepted_ledger_path.write_text(k8s.common.canonical(accepted_event) + "\n")
        os.chmod(self.accepted_ledger_path, 0o600)
        details = self.accepted_ledger_path.stat()
        authority = json.loads(self.profiles_path.read_text())["accepted_event_authorities"][
            self.request_value["accepted_event_authority_id"]
        ]
        material = {
            "schema_version": k8s.EXTERNAL_ACCEPTANCE_RECEIPT_SCHEMA,
            "authority_id": self.request_value["accepted_event_authority_id"],
            "recorder_id": authority["recorder_id"],
            "validator_id": authority["validator_id"],
            "validator_sha256": authority["validator_sha256"],
            "validator_reviewed_commit": authority["validator_reviewed_commit"],
            "lease_id": lease["lease_id"],
            "request_sha256": lease["request_sha256"],
            "plan_sha256": lease["plan_sha256"],
            "ledger_path": str(self.accepted_ledger_path.resolve()),
            "ledger_sha256": k8s.hashlib.sha256(self.accepted_ledger_path.read_bytes()).hexdigest(),
            "ledger_device": details.st_dev,
            "ledger_inode": details.st_ino,
            "ledger_mode": format(details.st_mode & 0o777, "04o"),
            "ledger_size_bytes": details.st_size,
            "ledger_mtime_ns": details.st_mtime_ns,
            "line_index": 0,
            "canonical_event_sha256": k8s.common.sha256_json(accepted_event),
            "metric_contract_sha256": self.request_value["metric_contract_sha256"],
            "trace_id": self.request_value["trace_id"],
            "trace_sha256": self.request_value["trace_sha256"],
            "trace_request_sha256": accepted_event["data"]["trace_request_sha256"],
            "ledger_id": accepted_event["ledger_id"],
            "ledger_sequence": accepted_event["ledger_sequence"],
            "request_id": accepted_event["request_id"],
            "attempt_id": accepted_event["attempt_id"],
            "event_id": accepted_event["event_id"],
            "scenario": accepted_event["data"]["scenario"],
            "target": accepted_event["data"]["target"],
            "input": accepted_event["data"]["input"],
            "observed_at_utc": accepted_event["observed_at_utc"],
            "observed_monotonic_ns": accepted_event["observed_monotonic_ns"],
            "recorder": accepted_event["recorder"],
            "validated_at_utc": timestamp(),
        }
        material.update(receipt_overrides or {})
        envelope = {
            "material": material,
            "signature_base64": base64.b64encode(
                self.external_private_key.sign(k8s.external_acceptance_message(material))
            ).decode("ascii"),
        }
        self.accepted_receipt_path.write_text(json.dumps(envelope, sort_keys=True) + "\n")
        os.chmod(self.accepted_receipt_path, 0o600)
        value = {
            "schema_version": "catalog-switch-kubernetes-node-demand/v4",
            "lease_id": lease["lease_id"],
            "request_sha256": lease["request_sha256"],
            "plan_sha256": lease["plan_sha256"],
            "attempt_id": "attempt-000001",
            "accepted_event_path": str(self.accepted_ledger_path.resolve()),
            "accepted_event_sha256": k8s.common.sha256_json(accepted_event),
            "accepted_event_receipt_path": str(self.accepted_receipt_path.resolve()),
            "accepted_event_receipt_sha256": k8s.hashlib.sha256(
                self.accepted_receipt_path.read_bytes()
            ).hexdigest(),
            "ledger_id": accepted_event["ledger_id"],
            "ledger_sequence": accepted_event["ledger_sequence"],
            "trace_id": accepted_event["trace_id"],
            "request_id": accepted_event["request_id"],
            "event_id": accepted_event["event_id"],
            "scenario": accepted_event["data"]["scenario"],
            "target": accepted_event["data"]["target"],
            "input": accepted_event["data"]["input"],
        }
        value.update(demand_overrides or {})
        self.demand_path.write_text(json.dumps(value))
        if record:
            return k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)
        return value

    def test_plan_is_versioned_immutable_and_idempotent(self):
        first = self.plan()
        second = self.plan()
        self.assertEqual("catalog-switch-kubernetes-resource-lease/v6", first["schema_version"])
        self.assertEqual(first["request_sha256"], second["request_sha256"])
        self.assertEqual("PLANNED", second["state"])
        self.assertTrue(second["prefix"].startswith("mlsp-csw-"))
        self.assertIn("{demand_sha256_8}", k8s.graph_name(second, "gpu_node_group"))
        self.assertLessEqual(
            float(second["cost_estimate"]["ttl_cost_ceiling_usd"]),
            float(second["cost_estimate"]["hard_cost_cap_usd"]),
        )
        self.assertEqual("catalog-switch-resource-broker", second["request"]["cleanup_owner"])

    def test_live_creation_requires_reviewed_external_authority_and_private_runner(self):
        pending_runner = json.loads(json.dumps(self.request_value))
        pending_runner["private_runner_receipt"] = {
            "status": "PENDING_CONSUMER_PROOF",
            "path": None,
            "sha256": None,
            "source_commit": None,
        }
        self.plan(pending_runner)
        with self.assertRaisesRegex(k8s.common.BrokerError, "private API runner path"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual({}, self.cli.created_count)

        other_request = self.root / "authority-pending-request.json"
        other_lease = self.root / "authority-pending-lease.json"
        value = request(lease_id="k8s-unit-authority-pending")
        other_request.write_text(json.dumps(value))
        k8s.plan(
            other_request,
            other_lease,
            self.registry_path,
            MODULE_PATH.parent / "kubernetes_profiles.json",
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "authority is unreviewed"):
            k8s.provision_control_plane(
                other_lease, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual({}, self.cli.created_count)

    def test_private_runner_requires_reviewer_signature_mode_and_current_execution(self):
        forged = self.make_request(lease_id="k8s-unit-runner-forged")
        forged_path = Path(forged["private_runner_receipt"]["path"])
        envelope = json.loads(forged_path.read_text())
        envelope["material"]["attested_at_utc"] = "2099-01-01T00:00:00Z"
        forged_path.write_text(json.dumps(envelope, sort_keys=True) + "\n")
        os.chmod(forged_path, 0o600)
        forged["private_runner_receipt"]["sha256"] = k8s.hashlib.sha256(
            forged_path.read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(k8s.common.BrokerError, "reviewer signature is invalid"):
            self.plan(forged)

        for suffix, field, wrong_value, error in (
            ("implementation", "implementation_sha256", "0" * 64, "identity/policy differs"),
            ("commit", "source_commit", "d" * 40, "executing broker source_commit differs"),
            ("bytes", "entrypoint_sha256", "0" * 64, "executing broker entrypoint_sha256 differs"),
        ):
            wrong_provenance = self.make_request(
                lease_id=f"k8s-unit-runner-wrong-{suffix}"
            )
            wrong_path = Path(wrong_provenance["private_runner_receipt"]["path"])
            envelope = json.loads(wrong_path.read_text())
            envelope["material"][field] = wrong_value
            envelope["signature_base64"] = base64.b64encode(
                self.runner_reviewer_private_key.sign(
                    k8s.runner_attestation_message(envelope["material"])
                )
            ).decode("ascii")
            wrong_path.write_text(json.dumps(envelope, sort_keys=True) + "\n")
            os.chmod(wrong_path, 0o600)
            wrong_provenance["private_runner_receipt"].update(
                {
                    "sha256": k8s.hashlib.sha256(wrong_path.read_bytes()).hexdigest(),
                    "source_commit": envelope["material"]["source_commit"],
                }
            )
            with self.assertRaisesRegex(k8s.common.BrokerError, error):
                self.plan(wrong_provenance)

        broad = self.make_request(lease_id="k8s-unit-runner-mode")
        os.chmod(Path(broad["private_runner_receipt"]["path"]), 0o644)
        with self.assertRaisesRegex(k8s.common.BrokerError, "current-user regular mode 0600"):
            self.plan(broad)

        stale = self.make_request(lease_id="k8s-unit-runner-stale")
        self.runner_execution["runner_boot_id"] = "runner-boot-after-review"
        with self.assertRaisesRegex(k8s.common.BrokerError, "runner_boot_id differs"):
            self.plan(stale)
        self.assertEqual({}, self.cli.created_count)

    def test_atomic_state_and_kubeconfig_replace_fsync_parent_directories(self):
        state_path = self.root / "atomic" / "state.json"
        with mock.patch.object(
            k8s.common,
            "fsync_directory",
            wraps=k8s.common.fsync_directory,
        ) as fsync_directory:
            k8s.common.atomic_json(state_path, {"state": "durable"})
        fsync_directory.assert_called_with(state_path.parent)

        source = state_path.parent / ".kubeconfig.broker-staging"
        destination = state_path.parent / "kubeconfig.yaml"
        source.write_text("durable-kubeconfig")
        with mock.patch.object(
            k8s.common,
            "fsync_directory",
            wraps=k8s.common.fsync_directory,
        ) as fsync_directory:
            k8s.durable_replace(source, destination)
        fsync_directory.assert_called_once_with(destination.parent)
        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())

        with mock.patch.object(
            k8s.common,
            "fsync_directory",
            wraps=k8s.common.fsync_directory,
        ) as fsync_directory:
            k8s.durable_unlink(destination)
        fsync_directory.assert_called_once_with(destination.parent)
        self.assertFalse(destination.exists())

        with mock.patch.object(
            k8s,
            "durable_replace",
            wraps=k8s.durable_replace,
        ) as durable_replace:
            support = self.support()
        kubeconfig = Path(support["kubeconfig_path"])
        self.assertTrue(
            any(call.args[1] == kubeconfig for call in durable_replace.call_args_list)
        )

    def test_caller_constructed_event_without_trusted_signature_is_rejected(self):
        self.support()
        self.demand(record=False)
        envelope = json.loads(self.accepted_receipt_path.read_text())
        envelope["signature_base64"] = base64.b64encode(b"\0" * 64).decode("ascii")
        self.accepted_receipt_path.write_text(json.dumps(envelope, sort_keys=True) + "\n")
        os.chmod(self.accepted_receipt_path, 0o600)
        demand = json.loads(self.demand_path.read_text())
        demand["accepted_event_receipt_sha256"] = k8s.hashlib.sha256(
            self.accepted_receipt_path.read_bytes()
        ).hexdigest()
        self.demand_path.write_text(json.dumps(demand))
        with self.assertRaisesRegex(k8s.common.BrokerError, "receipt signature is invalid"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

    def test_arm_b_binds_trace_metric_scenario_and_full_target_identity(self):
        self.support()
        self.demand(
            record=False,
            event_overrides={"data.trace_request_sha256": "5" * 64},
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "trace request digest"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

        self.demand(record=False, receipt_overrides={"metric_contract_sha256": "0" * 64})
        with self.assertRaisesRegex(k8s.common.BrokerError, "exact ledger/metric/trace"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

        self.demand(
            record=False,
            event_overrides={"data.metric_contract_sha256": "0" * 64},
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "event metric contract"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

        self.demand(record=False, event_overrides={"data.scenario": "same_model_hot"})
        with self.assertRaisesRegex(k8s.common.BrokerError, "scenario is outside"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

        self.demand(
            record=False,
            event_overrides={"data.target.model_version": "foreign-version"},
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "target/input identity"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

    def test_arm_b_signed_acceptance_cannot_replay_across_leases(self):
        self.support()
        self.demand(record=False)
        lease_a = json.loads(self.lease_path.read_text())

        request_b_path = self.root / "request-b.json"
        lease_b_path = self.root / "lease-b.json"
        request_b = self.make_request(lease_id="k8s-unit-new-node-b")
        request_b_path.write_text(json.dumps(request_b))
        lease_b = k8s.plan(
            request_b_path,
            lease_b_path,
            self.registry_path,
            self.profiles_path,
        )
        k8s.provision_control_plane(
            lease_b_path,
            self.registry_path,
            self.cli,
            self.kubectl,
        )
        replay = json.loads(self.demand_path.read_text())
        replay.update(
            {
                "lease_id": lease_b["lease_id"],
                "request_sha256": lease_b["request_sha256"],
                "plan_sha256": lease_b["plan_sha256"],
            }
        )
        replay_path = self.root / "replayed-demand.json"
        replay_path.write_text(json.dumps(replay))
        with self.assertRaisesRegex(k8s.common.BrokerError, "receipt provenance/lease commitment"):
            k8s.record_demand(lease_b_path, self.registry_path, replay_path)
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", json.loads(lease_b_path.read_text())["state"])
        self.assertEqual(lease_a["lease_id"], json.loads(self.accepted_receipt_path.read_text())["material"]["lease_id"])

    def test_resource_graph_tamper_breaks_plan_hash(self):
        lease = self.plan()
        lease["resource_graph"][0]["resource_name"] = "foreign-name"
        self.lease_path.write_text(json.dumps(lease))
        with self.assertRaisesRegex(k8s.common.BrokerError, "resource plan hash mismatch"):
            k8s.supervisor_ledger(self.registry_path)

    def test_unauthorized_project_and_non_preemptible_profile_fail_closed(self):
        with self.assertRaisesRegex(k8s.common.BrokerError, "outside the epic allowlist"):
            self.plan(self.make_request(project_id="project-foreign"))
        profiles = json.loads(self.profiles_path.read_text())
        profiles["profiles"]["mk8s-h100-new-node-v1"]["gpu_node_group"]["mode"] = "normal"
        changed = self.root / "profiles.json"
        changed.write_text(json.dumps(profiles))
        self.request_path.write_text(json.dumps(self.make_request()))
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
        self.assertEqual([], support["isolation_proof"]["cluster"]["public_worker_ips"])
        self.assertEqual(
            "10.42.0.10",
            support["isolation_proof"]["system_node_group"]["network_generations"][0][
                "provider"
            ]["private_ipv4"],
        )
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
        prepared = self.make_request(
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
            self.demand(
                event_overrides={
                    "observed_monotonic_ns": time.monotonic_ns() + 1_000_000_000
                }
            )

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
        no_create = lease["attempts"][0]["receipt"]["no_create_absence_receipt"]
        self.assertFalse(no_create["create_admitted"])
        self.assertEqual(0, no_create["exact_provider_matches"])
        released = k8s.cleanup_attempt(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        cleanup = released["attempts"][0]["receipt"]["cleanup"]
        self.assertEqual([], cleanup["exact_id_receipts"])
        self.assertEqual(no_create, cleanup["no_create_absence_receipt"])
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", released["state"])
        tampered = json.loads(json.dumps(released))
        tampered["attempts"][0]["receipt"]["no_create_absence_receipt"][
            "exact_provider_matches"
        ] = 1
        with self.assertRaisesRegex(k8s.common.BrokerError, "ownership signature mismatch"):
            k8s.assert_integrity(tampered)

    def test_interruption_after_create_preserves_ambiguous_exact_name(self):
        self.support()
        self.demand()
        self.cli.fail_after_create_kind = "gpu_node_group"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.cli.fail_after_create_kind = None
        with self.assertRaisesRegex(k8s.common.BrokerError, "no provider correlation"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual(1, self.cli.created_count["gpu_node_group"])
        active = json.loads(self.lease_path.read_text())
        operation = next(
            item
            for item in active["resource_create_operations"]
            if item["kind"] == "gpu_node_group"
        )
        self.assertEqual("AMBIGUOUS_FOREIGN_PRESERVED", operation["status"])
        self.assertTrue(any(item["stage"] == "create:gpu_node_group" for item in active["failures"]))
        group_id = next(
            resource_id
            for resource_id, value in self.cli.resources.items()
            if value.get("_kind") == "gpu_node_group"
        )
        self.assertNotIn(group_id, self.cli.deleted)

    def test_interrupted_gpu_create_cleanup_preserves_without_correlation(self):
        self.support()
        self.demand()
        self.cli.fail_after_create_kind = "gpu_node_group"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        with self.assertRaisesRegex(k8s.common.BrokerError, "lacks provider correlation"):
            k8s.cleanup_attempt(
                self.lease_path,
                self.registry_path,
                self.cli,
                self.kubectl,
                execute=True,
            )
        group_id = next(
            resource_id
            for resource_id, value in self.cli.resources.items()
            if value.get("_kind") == "gpu_node_group"
        )
        self.assertNotIn(group_id, self.cli.deleted)

    def test_control_plane_interruption_preserves_without_provider_correlation(self):
        self.plan()
        self.cli.fail_after_create_kind = "cluster"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.cli.fail_after_create_kind = None
        with self.assertRaisesRegex(k8s.common.BrokerError, "no provider correlation"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual(1, self.cli.created_count["cluster"])
        support = json.loads(self.lease_path.read_text())
        operation = next(
            item for item in support["resource_create_operations"] if item["kind"] == "cluster"
        )
        self.assertEqual("AMBIGUOUS_FOREIGN_PRESERVED", operation["status"])

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
        self.assertEqual("PLAN_ONLY_CREATE_NOT_ADMITTED", row["cleanup_state"])

    def test_profile_and_identity_are_bound_before_mutation(self):
        self.plan()
        self.cli.profile = "switched-profile"
        with self.assertRaisesRegex(k8s.common.BrokerError, "profile mismatch"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual({}, self.cli.created_count)

    def test_every_kubernetes_cleanup_get_fails_closed_on_auth_not_absence(self):
        cli = k8s.common.NebiusCLI("sandbox")
        result = mock.Mock(
            returncode=1,
            stdout="",
            stderr="rpc error: code = Unauthenticated desc = sandbox profile not found",
        )
        cleanup_kinds = sorted(set(k8s.CLEANUP_PRIORITY) - {"kubeconfig_authority"})
        with mock.patch.object(k8s.common.subprocess, "run", return_value=result):
            for kind in cleanup_kinds:
                with self.subTest(kind=kind), self.assertRaisesRegex(
                    k8s.common.AuthenticationError,
                    "do not switch credentials or projects",
                ):
                    cli.run(k8s.get_args(kind, f"{kind}-unit"), allow_not_found=True)
        self.cli.profile = "sandbox"
        other_request = self.root / "other-request.json"
        other_lease = self.root / "other-lease.json"
        other_value = self.make_request(
            lease_id="k8s-unit-other-authority",
            authority_identity={
                "type": "service_account_profile",
                "id": "different-authority",
                "parent_id": "project-i00xz31gpr00xp9jhp982v",
            },
        )
        other_request.write_text(json.dumps(other_value))
        k8s.plan(other_request, other_lease, self.registry_path, self.profiles_path)
        with self.assertRaisesRegex(k8s.common.AuthenticationError, "authority identity differs"):
            k8s.provision_control_plane(
                other_lease, self.registry_path, self.cli, self.kubectl
            )
        self.assertEqual({}, self.cli.created_count)

    def test_installed_provider_schemas_and_serialized_payloads_are_strict(self):
        support = self.support()
        self.assertEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", support["state"])
        cluster = self.cli.created_payloads["cluster"][0]
        control_plane = cluster["spec"]["control_plane"]
        self.assertNotIn("karpenter", control_plane)
        self.assertNotIn("endpoints", control_plane)
        system_boot = self.cli.created_payloads["system_node_group"][0]["spec"][
            "template"
        ]["boot_disk"]
        self.assertEqual(64 * 1024**3, system_boot["size_bytes"])
        self.assertNotIn("size_gibibytes", system_boot)
        self.demand()
        k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        gpu_boot = self.cli.created_payloads["gpu_node_group"][0]["spec"]["template"][
            "boot_disk"
        ]
        self.assertEqual(300 * 1024**3, gpu_boot["size_bytes"])
        self.assertNotIn("size_gibibytes", gpu_boot)
        cluster_help = subprocess.run(
            ["/usr/local/bin/nebius", "mk8s", "v1", "cluster", "create", "--help"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        group_help = subprocess.run(
            ["/usr/local/bin/nebius", "mk8s", "v1", "node-group", "create", "--help"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertIn('"karpenter": {', cluster_help)
        self.assertIn('"size_bytes": 0', group_help)
        self.assertNotIn("size_gibibytes", group_help)

    def test_private_control_plane_and_internal_kubeconfig_only(self):
        support = self.support()
        proof = support["isolation_proof"]["cluster"]
        self.assertIsNone(proof["public_control_plane_endpoint"])
        self.assertEqual(
            "https://unit-cluster.internal:443", proof["private_control_plane_endpoint"]
        )
        operation = next(
            item
            for item in support["resource_create_operations"]
            if item["kind"] == "kubeconfig_authority"
        )
        self.assertEqual("internal", operation["requested_spec"]["access"])

    def test_foreign_kubeconfig_in_intent_crash_window_is_preserved(self):
        self.plan()
        self.cli.fail_get_credentials_before_write = True
        with self.assertRaisesRegex(k8s.common.BrokerError, "before kubeconfig write"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        lease = json.loads(self.lease_path.read_text())
        path = Path(lease["kubeconfig_path"])
        path.write_text("foreign: true\n")
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(k8s.common.BrokerError, "no signed content authority"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertTrue(path.exists())
        persisted = json.loads(self.lease_path.read_text())
        self.assertEqual("CLEANUP_FAILED", persisted["state"])
        operation = next(
            item
            for item in persisted["resource_create_operations"]
            if item["kind"] == "kubeconfig_authority"
        )
        self.assertEqual("AMBIGUOUS_FOREIGN_PRESERVED", operation["status"])
        self.assertNotIn(persisted["cluster_id"], self.cli.deleted)

    def test_receipted_kubeconfig_crash_window_reconciles_exact_content(self):
        original = k8s.authenticate_resource

        def crash_on_kubeconfig(lease, resource):
            if resource["kind"] == "kubeconfig_authority":
                raise k8s.common.BrokerError("simulated crash before kubeconfig resource row")
            return original(lease, resource)

        self.plan()
        with mock.patch.object(k8s, "authenticate_resource", side_effect=crash_on_kubeconfig):
            with self.assertRaisesRegex(k8s.common.BrokerError, "before kubeconfig resource row"):
                k8s.provision_control_plane(
                    self.lease_path, self.registry_path, self.cli, self.kubectl
                )
        lease = json.loads(self.lease_path.read_text())
        path = Path(lease["kubeconfig_path"])
        self.assertTrue(path.exists())
        released = k8s.cleanup(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        row = next(item for item in released["resources"] if item["kind"] == "kubeconfig_authority")
        self.assertTrue(row["absence_verified_at"])
        self.assertFalse(path.exists())

    def test_arm_b_rejects_missing_forged_and_stale_accepted_events(self):
        self.support()
        self.demand(record=False)
        self.accepted_ledger_path.unlink()
        with self.assertRaisesRegex(k8s.common.BrokerError, "ledger is missing"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)
        self.demand(record=False, demand_overrides={"accepted_event_sha256": "a" * 64})
        with self.assertRaisesRegex(k8s.common.BrokerError, "digest is missing"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)
        stale_utc = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.demand(
            record=False,
            event_overrides={
                "observed_at_utc": stale_utc,
                "observed_monotonic_ns": time.monotonic_ns() - 2_000_000_000,
            },
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "predates"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

    def test_arm_b_rejects_forged_identity_and_clock_authority(self):
        self.support()
        self.demand(record=False, demand_overrides={"request_id": "forged-request"})
        with self.assertRaisesRegex(k8s.common.BrokerError, "exact demand identity"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)
        self.demand(
            record=False,
            event_overrides={"recorder.boot_id": "foreign-boot"},
        )
        with self.assertRaisesRegex(k8s.common.BrokerError, "clock/recorder authority"):
            k8s.record_demand(self.lease_path, self.registry_path, self.demand_path)

    def test_system_provider_child_window_preserves_ambiguous_parent_without_kubeconfig(self):
        self.plan()
        self.cli.fail_after_create_kind = "system_node_group"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        lease = json.loads(self.lease_path.read_text())
        self.assertFalse(Path(lease["kubeconfig_path"]).exists())
        with self.assertRaisesRegex(k8s.common.BrokerError, "lacks provider correlation"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        group_id = next(
            resource_id
            for resource_id, value in self.cli.resources.items()
            if value.get("_kind") == "system_node_group"
        )
        self.assertNotIn(group_id, self.cli.deleted)

    def test_gpu_live_product_and_allocatable_are_attested(self):
        self.support()
        self.demand()
        self.kubectl.gpu_product = "NVIDIA-B200"
        with self.assertRaisesRegex(k8s.common.BrokerError, "gpu.product"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        lease = json.loads(self.lease_path.read_text())
        self.assertEqual("GPU_CREATE_FAILED", lease["state"])
        self.kubectl.gpu_product = "NVIDIA-H100-80GB-HBM3"
        self.kubectl.gpu_allocatable = "0"
        with self.assertRaisesRegex(k8s.common.BrokerError, "allocatable GPU"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )

    def test_system_node_public_ip_observation_blocks_support(self):
        self.cli.provider_public_ip = "203.0.113.10"
        with self.assertRaisesRegex(k8s.common.BrokerError, "public IP"):
            self.support()
        lease = json.loads(self.lease_path.read_text())
        self.assertEqual("CONTROL_PLANE_FAILED", lease["state"])
        self.assertNotEqual("SUPPORT_ACTIVE_NO_GPU_NODE_GROUP", lease["state"])

    def test_gpu_replacement_public_ip_observation_is_rejected(self):
        self.support()
        self.demand()
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.cli.provider_public_ip = "203.0.113.10"
        self.cli.replace_node(active["node_group_ids"][0])
        with self.assertRaisesRegex(k8s.common.BrokerError, "public IP"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )

    def test_control_plane_reentry_reattests_replacement_gpu_identity(self):
        self.support()
        self.demand()
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        old_node_id = active["node_ids"][0]
        self.cli.replace_node(active["node_group_ids"][0])
        self.kubectl.gpu_product = "FOREIGN-GPU"
        self.kubectl.gpu_allocatable = "0"
        with self.assertRaisesRegex(k8s.common.BrokerError, "gpu.product"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        failed = json.loads(self.lease_path.read_text())
        self.assertEqual("ACTIVE_RECONCILIATION_FAILED", failed["state"])
        self.assertEqual([old_node_id], failed["node_ids"])
        self.assertEqual(
            old_node_id,
            failed["attempts"][0]["receipt"]["live_gpu_attestation"]["node_id"],
        )
        self.assertEqual("active_graph_reconciliation", failed["failures"][-1]["stage"])
        replacement_id = self.cli.node_by_group[active["node_group_ids"][0]]
        self.kubectl.gpu_product = "NVIDIA-H100-80GB-HBM3"
        self.kubectl.gpu_allocatable = "1"
        recovered = k8s.provision_control_plane(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        self.assertEqual("ACTIVE_ATTEMPT", recovered["state"])
        self.assertEqual([replacement_id], recovered["node_ids"])
        self.assertEqual(
            replacement_id,
            recovered["attempts"][0]["receipt"]["live_gpu_attestation"]["node_id"],
        )

    def test_gpu_reentry_reconciles_replacement_system_network(self):
        self.support()
        self.demand()
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        system_group = next(
            item
            for item in active["resources"]
            if item["kind"] == "system_node_group" and not item["deleted_at"]
        )
        self.cli.provider_public_ip = "203.0.113.55"
        self.cli.replace_node(system_group["id"])
        with self.assertRaisesRegex(k8s.common.BrokerError, "public IP"):
            k8s.provision_gpu_node_group(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        failed = json.loads(self.lease_path.read_text())
        self.assertEqual("ACTIVE_RECONCILIATION_FAILED", failed["state"])
        self.assertEqual("active_graph_reconciliation", failed["failures"][-1]["stage"])

    def test_copied_name_labels_and_exact_spec_remain_ambiguous(self):
        self.plan()
        self.cli.fail_after_create_kind = "cluster"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        cluster_id = next(
            resource_id
            for resource_id, value in self.cli.resources.items()
            if value.get("_kind") == "cluster"
        )
        self.cli.fail_after_create_kind = None
        with self.assertRaisesRegex(k8s.common.BrokerError, "no provider correlation"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        self.assertNotIn(cluster_id, self.cli.deleted)

    def test_exclusive_lease_lock_prevents_concurrent_duplicate_creates(self):
        self.plan()
        self.cli.create_delay_seconds = 0.002
        failures = []

        def worker():
            try:
                k8s.provision_control_plane(
                    self.lease_path, self.registry_path, self.cli, self.kubectl
                )
            except Exception as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], failures)
        for kind in (
            "network",
            "subnet",
            "security_group",
            "service_account",
            "iam_group",
            "group_membership",
            "registry",
            "registry_access_permit",
            "bucket",
            "bucket_access_permit",
            "cluster",
            "system_node_group",
        ):
            self.assertEqual(1, self.cli.created_count[kind], kind)

    def test_active_reconciliation_discovers_preemptible_replacement(self):
        self.support()
        self.demand()
        active = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        group_id = active["node_group_ids"][0]
        old_id, new_id = self.cli.replace_node(group_id)
        reconciled = k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        old = next(item for item in reconciled["resources"] if item["id"] == old_id)
        new = next(item for item in reconciled["resources"] if item["id"] == new_id)
        self.assertTrue(old["absence_verified_at"])
        self.assertTrue(old["absence_receipt_signature"])
        self.assertIsNone(new["absence_verified_at"])
        self.assertEqual(
            "10.42.0.40",
            new["provider_metadata"]["provider_network_attestation"]["private_ipv4"],
        )
        self.assertEqual(
            [],
            new["provider_metadata"]["kubernetes_network_attestation"]["external_ipv4"],
        )
        self.assertEqual([new_id], reconciled["node_ids"])
        self.assertEqual(
            new_id,
            reconciled["attempts"][0]["receipt"]["replacement_reconciliations"][-1][
                "node_id"
            ],
        )

    def test_resource_row_signature_and_live_ownership_block_foreign_delete(self):
        support = self.support()
        pristine = json.loads(json.dumps(support))
        injected = dict(support["resources"][0])
        injected["id"] = "vpcnetwork-injected"
        support["resources"].append(injected)
        self.lease_path.write_text(json.dumps(support))
        with self.assertRaisesRegex(k8s.common.BrokerError, "ownership signature mismatch"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertEqual([], self.cli.deleted)

        self.lease_path.write_text(json.dumps(pristine))
        cluster = next(item for item in pristine["resources"] if item["kind"] == "cluster")
        self.cli.resources[cluster["id"]]["spec"]["control_plane"]["version"] = "1.33"
        with self.assertRaisesRegex(k8s.common.BrokerError, "cleanup incomplete"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertNotIn(cluster["id"], self.cli.deleted)

    def test_forged_cleanup_lifecycle_cannot_skip_live_bucket_delete(self):
        support = self.support()
        bucket = next(item for item in support["resources"] if item["kind"] == "bucket")
        forged_at = timestamp()
        bucket["deleted_at"] = forged_at
        bucket["absence_verified_at"] = forged_at
        bucket["cleanup_evidence"] = "forged NotFound without a provider observation"
        bucket["delete_operation"] = {
            "status": "ABSENCE_VERIFIED",
            "started_at_utc": forged_at,
            "attempt_count": 0,
            "last_failure": None,
            "completed_at_utc": forged_at,
        }
        bucket["absence_receipt"] = {
            "schema_version": k8s.RESOURCE_ABSENCE_RECEIPT_SCHEMA,
            "resource_id": bucket["id"],
            "resource_kind": "bucket",
            "delete_operation_started_at_utc": forged_at,
            "delete_attempt_count": 0,
            "absence_mode": "FORGED",
            "verified_at_utc": forged_at,
            "cleanup_evidence": bucket["cleanup_evidence"],
        }
        bucket["absence_receipt_signature"] = "forged"
        self.lease_path.write_text(json.dumps(support))
        with self.assertRaisesRegex(k8s.common.BrokerError, "resource-lifecycle ownership signature"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertNotIn(bucket["id"], self.cli.deleted)
        self.assertNotIn(bucket["id"], self.cli.absent)

    def test_signed_collection_rejects_omitted_live_bucket_and_create_intent(self):
        planned = self.plan()
        support = self.support()
        pristine = json.loads(json.dumps(support))
        bucket = next(item for item in support["resources"] if item["kind"] == "bucket")
        support["resources"] = [item for item in support["resources"] if item["id"] != bucket["id"]]
        support["resource_create_operations"] = [
            item
            for item in support["resource_create_operations"]
            if item["operation_id"] != bucket["create_operation_id"]
        ]
        self.lease_path.write_text(json.dumps(support))
        with self.assertRaisesRegex(k8s.common.BrokerError, "collection membership/root mismatch"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertNotIn(bucket["id"], self.cli.deleted)
        self.assertNotIn(bucket["id"], self.cli.absent)

        pristine["collection_journal"].pop()
        self.lease_path.write_text(json.dumps(pristine))
        with self.assertRaisesRegex(k8s.common.BrokerError, "collection root differs"):
            k8s.assert_integrity(json.loads(self.lease_path.read_text()))

        rolled_back = json.loads(json.dumps(pristine))
        rolled_back["resources"] = []
        rolled_back["resource_create_operations"] = []
        rolled_back["collection_journal"] = planned["collection_journal"]
        rolled_back["collection_root"] = planned["collection_root"]
        self.lease_path.write_text(json.dumps(rolled_back))
        with self.assertRaisesRegex(k8s.common.BrokerError, "collection anchor differs"):
            k8s.assert_integrity(json.loads(self.lease_path.read_text()))

    def test_cleanup_delete_crash_is_idempotent_and_not_reissued(self):
        support = self.support()
        system_group = next(
            item for item in support["resources"] if item["kind"] == "system_node_group"
        )
        self.cli.crash_after_delete_id = system_group["id"]
        with self.assertRaises(KeyboardInterrupt):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        released = k8s.cleanup(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        self.assertEqual("RELEASED", released["state"])
        self.assertEqual(1, self.cli.deleted.count(system_group["id"]))

    def test_cleanup_failure_barrier_preserves_parent_dependencies(self):
        support = self.support()
        permit = next(
            item for item in support["resources"] if item["kind"] == "registry_access_permit"
        )
        group_id, registry_id = permit["depends_on"]
        self.cli.fail_delete_id = permit["id"]
        with self.assertRaisesRegex(k8s.common.BrokerError, "cleanup incomplete"):
            k8s.cleanup(self.lease_path, self.registry_path, self.cli, execute=True)
        self.assertNotIn(group_id, self.cli.deleted)
        self.assertNotIn(registry_id, self.cli.deleted)

    def test_supervisor_reports_create_ambiguity_not_false_absence(self):
        self.plan()
        self.cli.fail_after_create_kind = "network"
        with self.assertRaisesRegex(k8s.common.BrokerError, "simulated interruption"):
            k8s.provision_control_plane(
                self.lease_path, self.registry_path, self.cli, self.kubectl
            )
        ledger = k8s.supervisor_ledger(self.registry_path)
        row = next(item for item in ledger["resources"] if item["resource_type"] == "network")
        self.assertEqual("CREATE_AMBIGUOUS_RECONCILIATION_REQUIRED", row["cleanup_state"])
        self.assertTrue(row["reconciliation_required"])
        self.assertNotIn("already holds", row["cleanup_evidence"])
        lease = json.loads(self.lease_path.read_text())
        operation = next(item for item in lease["resource_create_operations"] if item["kind"] == "network")
        operation["status"] = "ABSENCE_VERIFIED_AFTER_INTERRUPTION"
        self.lease_path.write_text(json.dumps(lease))
        with self.assertRaisesRegex(k8s.common.BrokerError, "lacks a signed receipt"):
            k8s.supervisor_ledger(self.registry_path)

    def test_every_authorization_bearing_plan_field_is_sealed(self):
        original = self.plan()
        mutations = (
            lambda value: value.__setitem__("lease_id", "other-lease"),
            lambda value: value["labels"].__setitem__("owner", "other-owner"),
            lambda value: value.__setitem__("created_at", "2026-01-01T00:00:00Z"),
            lambda value: value["cleanup_plan"].__setitem__("cleanup_owner", "other-owner"),
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(original))
            mutate(changed)
            with self.assertRaises(k8s.common.BrokerError):
                k8s.assert_integrity(changed)

    def test_attempt_receipt_survives_crashes_after_each_delete_save(self):
        self.support()
        self.demand()
        k8s.provision_gpu_node_group(
            self.lease_path, self.registry_path, self.cli, self.kubectl
        )
        original = k8s.delete_one

        def delete_then_crash(*args, **kwargs):
            original(*args, **kwargs)
            raise k8s.common.BrokerError("simulated crash after durable absence save")

        with mock.patch.object(k8s, "delete_one", side_effect=delete_then_crash):
            with self.assertRaisesRegex(k8s.common.BrokerError, "attempt cleanup incomplete"):
                k8s.cleanup_attempt(
                    self.lease_path, self.registry_path, self.cli, execute=True
                )
        with mock.patch.object(k8s, "delete_one", side_effect=delete_then_crash):
            with self.assertRaisesRegex(k8s.common.BrokerError, "attempt cleanup incomplete"):
                k8s.cleanup_attempt(
                    self.lease_path, self.registry_path, self.cli, execute=True
                )
        released = k8s.cleanup_attempt(
            self.lease_path, self.registry_path, self.cli, execute=True
        )
        receipts = released["attempts"][0]["receipt"]["cleanup"]["exact_id_receipts"]
        self.assertEqual(2, len(receipts))
        self.assertTrue(all(item["absence_verified_at"] for item in receipts))

    def test_combined_supervisor_adds_explicit_absence_evidence(self):
        self.plan()
        ledger = supervisor.build(self.root / "no-vm-registry.json", self.registry_path)
        self.assertEqual("catalog-switch-supervisor-resource-ledger/v2", ledger["schema_version"])
        self.assertTrue(all(item["cleanup_evidence"] for item in ledger["resources"]))
        self.assertFalse(ledger["contains_secrets"])


if __name__ == "__main__":
    unittest.main()
