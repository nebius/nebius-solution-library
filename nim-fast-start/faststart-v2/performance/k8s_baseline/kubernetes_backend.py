#!/usr/bin/env python3
"""Fail-closed kubectl backend for the causal switch controller."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from performance.request_slo.harness import canonical_json

from .contract import BaselineError, admitted_document
from .controller import (
    AccountingResult,
    CleanupResult,
    PhaseExecutionError,
    PhaseResult,
    TerminalResult,
)


TARGET_SELECTOR = "mlsp.nebius.ai/role=catalog-switch-target"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BaselineError(f"cannot load validator module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Kubectl:
    def __init__(self, kubeconfig: Path, context: str, namespace: str) -> None:
        self.prefix = [
            "kubectl",
            "--kubeconfig",
            str(kubeconfig),
            "--context",
            context,
        ]
        self.namespace = namespace

    def run(
        self,
        args: list[str],
        *,
        stdin: str | None = None,
        timeout: int = 60,
        json_output: bool = False,
        namespace: bool = True,
        allow_not_found: bool = False,
    ) -> Any:
        command = list(self.prefix)
        if namespace:
            command.extend(["--namespace", self.namespace])
        command.extend(args)
        result = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        combined = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode:
            lowered = combined.lower()
            if allow_not_found and "notfound" in lowered:
                return None
            if any(item in lowered for item in ("unauthorized", "forbidden", "login", "credential")):
                raise PermissionError(
                    "Kubernetes authentication/authorization failed; do not switch credentials: "
                    + combined[:1000]
                )
            raise BaselineError(
                f"kubectl failed ({result.returncode}): {' '.join(command[-6:])}: "
                f"{combined[:2000]}"
            )
        if not json_output:
            return result.stdout
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise BaselineError("kubectl returned invalid JSON") from exc

    def get_json(self, kind: str, name: str | None = None, *, namespace: bool = True) -> Any:
        args = ["get", kind]
        if name is not None:
            args.append(name)
        args.extend(["-o", "json"])
        return self.run(args, json_output=True, namespace=namespace)

    def apply(self, manifest: str) -> None:
        self.run(["apply", "-f", "-"], stdin=manifest, timeout=120)

    def delete(self, kind: str, name: str, timeout_seconds: int) -> None:
        self.run(
            [
                "delete",
                kind,
                name,
                "--ignore-not-found=true",
                "--wait=true",
                f"--timeout={timeout_seconds}s",
            ],
            timeout=timeout_seconds + 15,
        )


class KubernetesBackend:
    """Execute only task-owned Pods and Services on the pinned leased node."""

    classification = "live-kubernetes-request-to-valid-response-evidence"

    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.requires_durable_t0_before_accepted_hook = True
        kube = plan["kubernetes"]
        self.kube = Kubectl(
            Path(plan["_resolved"]["kubeconfig"]), kube["context"], kube["namespace"]
        )
        self.models = {
            (item["model_id"], item["model_version"]): item for item in plan["models"]
        }
        self.lease = admitted_document(plan, "lease")
        self._attempt: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._active_pod: str | None = None
        self._port_forward: subprocess.Popen[str] | None = None
        self._port: int | None = None
        self._prepared = False
        self._prepare_owned: set[tuple[str, str]] = set()
        self._prepare_cleanup_failures: list[str] = []
        self._final_cleanup_receipt: dict[str, Any] | None = None
        self._last_billing_ns: int | None = None
        self._setup_cost_charged = False

    def _record(self, operation: str, **data: Any) -> None:
        self._events.append(
            {
                "sequence": len(self._events),
                "observed_at_utc": _utc_now(),
                "observed_monotonic_ns": time.monotonic_ns(),
                "operation": operation,
                **data,
            }
        )

    def _model(self, request: dict[str, Any]) -> dict[str, Any]:
        key = (request["target"]["model_id"], request["target"]["model_version"])
        try:
            return self.models[key]
        except KeyError as exc:
            raise BaselineError(f"request selects unadmitted model {key}") from exc

    def _pods(self) -> list[dict[str, Any]]:
        value = self.kube.run(
            ["get", "pods", "-l", TARGET_SELECTOR, "-o", "json"], json_output=True
        )
        if (
            not isinstance(value, dict)
            or value.get("apiVersion") != "v1"
            or value.get("kind") != "List"
            or not isinstance(value.get("metadata"), dict)
            or not isinstance(value.get("items"), list)
        ):
            raise BaselineError("target Pod inventory is not a canonical Kubernetes v1 List")
        items = value["items"]
        for item in items:
            if (
                not isinstance(item, dict)
                or item.get("apiVersion") != "v1"
                or item.get("kind") != "Pod"
                or not isinstance(item.get("metadata"), dict)
            ):
                raise BaselineError("target Pod inventory contains a noncanonical Pod object")
            metadata = item["metadata"]
            labels = metadata.get("labels")
            if (
                not isinstance(metadata.get("name"), str)
                or not metadata["name"]
                or not isinstance(metadata.get("uid"), str)
                or not metadata["uid"]
                or metadata.get("namespace") != self.plan["kubernetes"]["namespace"]
                or not isinstance(labels, dict)
                or labels.get("mlsp.nebius.ai/role") != "catalog-switch-target"
                or labels.get("mlsp.nebius.ai/task") != self.plan["task_id"]
                or labels.get("mlsp.nebius.ai/resource-prefix")
                != self.plan["resource_lease"]["prefix"]
                or not isinstance(labels.get("mlsp.nebius.ai/model-id"), str)
                or not labels["mlsp.nebius.ai/model-id"]
                or not isinstance(labels.get("mlsp.nebius.ai/model-version-id"), str)
                or not labels["mlsp.nebius.ai/model-version-id"]
            ):
                raise BaselineError(
                    "target Pod inventory lacks exact deletable task-owned identity"
                )
        return items

    def _active_occupant(self) -> dict[str, str] | None:
        live = [
            item
            for item in self._pods()
            if item.get("metadata", {}).get("deletion_timestamp") is None
            and item.get("status", {}).get("phase") not in {"Failed", "Succeeded"}
        ]
        if len(live) > 1:
            raise BaselineError("exclusive-occupancy invariant violated: multiple target Pods")
        if not live:
            self._active_pod = None
            return None
        pod = live[0]
        metadata = pod.get("metadata", {})
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        model_id = labels.get("mlsp.nebius.ai/model-id")
        version_label = labels.get("mlsp.nebius.ai/model-version-id")
        matches = [
            model
            for model in self.models.values()
            if model["model_id"] == model_id and model["version_label"] == version_label
        ]
        if len(matches) != 1:
            raise BaselineError("active target Pod lacks immutable model identity labels")
        model = matches[0]
        if (
            labels.get("mlsp.nebius.ai/role") != "catalog-switch-target"
            or labels.get("mlsp.nebius.ai/task") != self.plan["task_id"]
            or labels.get("mlsp.nebius.ai/resource-prefix")
            != self.plan["resource_lease"]["prefix"]
        ):
            raise BaselineError("active target Pod is not task/lease owned")
        expected_annotations = {
            "mlsp.nebius.ai/model-version-full": model["model_version"],
            "mlsp.nebius.ai/artifact-id": model["artifact_id"],
            "mlsp.nebius.ai/artifact-version": model["artifact_version"],
            "mlsp.nebius.ai/artifact-sha256": model["artifact_sha256"],
            "mlsp.nebius.ai/image-digest": model["image_digest"],
        }
        if any(annotations.get(key) != value for key, value in expected_annotations.items()):
            raise BaselineError("active target Pod full-digest annotation receipt drifted")
        spec = pod.get("spec", {})
        containers = [
            item for item in spec.get("containers", [])
            if item.get("name") == model["container_name"]
        ]
        statuses = [
            item for item in pod.get("status", {}).get("containerStatuses", [])
            if item.get("name") == model["container_name"]
        ]
        expected_digest = model["image_digest"].split("@", 1)[1]
        if (
            spec.get("nodeName") != self.plan["kubernetes"]["node_name"]
            or spec.get("serviceAccountName") != self.plan["security"]["workload_service_account"]
            or len(containers) != 1
            or containers[0].get("image") != model["image_digest"]
            or len(statuses) != 1
            or expected_digest not in statuses[0].get("imageID", "")
        ):
            raise BaselineError("active target Pod runtime node/image identity differs from annotations")
        self._active_pod = pod["metadata"]["name"]
        return {"model_id": model_id, "model_version": model["model_version"]}

    def _generic_service(self, name: str) -> str:
        namespace = self.plan["kubernetes"]["namespace"]
        return canonical_json(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": {
                        "mlsp.nebius.ai/program": "catalog-switch",
                        "mlsp.nebius.ai/task": self.plan["task_id"],
                        "mlsp.nebius.ai/resource-prefix": self.plan["resource_lease"]["prefix"],
                    },
                },
                "spec": {
                    "type": "ClusterIP",
                    "publishNotReadyAddresses": False,
                    "selector": {"mlsp.nebius.ai/role": "catalog-switch-target"},
                    "ports": [
                        {
                            "name": "http",
                            "port": 8000,
                            "targetPort": "http",
                            "protocol": "TCP",
                        }
                    ],
                },
            }
        )

    def prepare(self) -> None:
        config = self.kube.run(
            ["config", "view", "--minify", "-o", "json"],
            json_output=True,
            namespace=False,
        )
        clusters = config.get("clusters", [])
        server = clusters[0].get("cluster", {}).get("server") if len(clusters) == 1 else None
        if server != self.plan["kubernetes"]["expected_server"]:
            raise BaselineError("kubeconfig server differs from the admitted fresh cluster")
        namespace = self.kube.get_json(
            "namespace", self.plan["kubernetes"]["namespace"], namespace=False
        )
        namespace_metadata = namespace.get("metadata", {})
        namespace_labels = namespace_metadata.get("labels", {})
        namespace_annotations = namespace_metadata.get("annotations", {})
        if (
            namespace_metadata.get("uid") != self.plan["kubernetes"]["namespace_uid"]
            or namespace_labels.get("mlsp.nebius.ai/task") != self.plan["task_id"]
            or namespace_labels.get("mlsp.nebius.ai/resource-prefix")
            != self.plan["resource_lease"]["prefix"]
            or namespace_annotations.get("mlsp.nebius.ai/lease-id")
            != self.plan["resource_lease"]["lease_id"]
            or namespace_annotations.get("mlsp.nebius.ai/broker-resource-id")
            != self.plan["kubernetes"]["namespace_resource_id"]
        ):
            raise BaselineError("namespace is not owned by this broker lease")
        service_account = self.kube.get_json(
            "serviceaccount", self.plan["security"]["workload_service_account"]
        )
        sa_metadata = service_account.get("metadata", {})
        sa_labels = sa_metadata.get("labels", {})
        sa_annotations = sa_metadata.get("annotations", {})
        if (
            sa_metadata.get("uid") != self.plan["kubernetes"]["service_account_uid"]
            or sa_labels.get("mlsp.nebius.ai/task") != self.plan["task_id"]
            or sa_labels.get("mlsp.nebius.ai/resource-prefix")
            != self.plan["resource_lease"]["prefix"]
            or sa_annotations.get("mlsp.nebius.ai/lease-id")
            != self.plan["resource_lease"]["lease_id"]
            or sa_annotations.get("mlsp.nebius.ai/broker-resource-id")
            != self.plan["kubernetes"]["service_account_resource_id"]
        ):
            raise BaselineError("workload ServiceAccount is not owned by this broker lease")
        node = self.kube.get_json(
            "node", self.plan["kubernetes"]["node_name"], namespace=False
        )
        ready = any(
            item.get("type") == "Ready" and item.get("status") == "True"
            for item in node.get("status", {}).get("conditions", [])
        )
        metadata = node.get("metadata", {})
        node_labels = metadata.get("labels", {})
        node_annotations = metadata.get("annotations", {})
        profile = self.plan["gpu_profiles"][self.plan["kubernetes"]["gpu_profile"]]
        allocatable = int(node.get("status", {}).get("allocatable", {}).get("nvidia.com/gpu", 0))
        product = node_labels.get("nvidia.com/gpu.product", "")
        expected_node_annotations = {
            "mlsp.nebius.ai/broker-node-id": self.plan["kubernetes"]["broker_node_id"],
            "mlsp.nebius.ai/broker-node-group-id": self.plan["kubernetes"]["broker_node_group_id"],
            "mlsp.nebius.ai/lease-id": self.plan["resource_lease"]["lease_id"],
            "mlsp.nebius.ai/resource-prefix": self.plan["resource_lease"]["prefix"],
            "mlsp.nebius.ai/preemptible": "true",
        }
        if (
            not ready
            or node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion")
            != self.plan["kubernetes"]["cluster_version"]
            or node.get("status", {}).get("nodeInfo", {}).get("bootID")
            != self.lease["node_boot_id"]
            or metadata.get("uid") != self.plan["kubernetes"]["node_uid"]
            or self.lease["node_ids"] != [self.plan["kubernetes"]["broker_node_id"]]
            or allocatable != profile["gpu_count"]
            or product != profile["product"]
            or self.plan["kubernetes"]["preemptible"] is not True
            or any(node_annotations.get(key) != value for key, value in expected_node_annotations.items())
        ):
            raise BaselineError("node is not the exact broker-bound Ready preemptible GPU target")

        credentials = self.plan["security"]["credentials"]
        secret = self.kube.get_json("secret", credentials["secret_name"])
        secret_metadata = secret.get("metadata", {})
        secret_annotations = secret_metadata.get("annotations", {})
        if (
            secret.get("type") != "kubernetes.io/dockerconfigjson"
            or secret_metadata.get("uid") != credentials["secret_uid"]
            or secret_metadata.get("labels", {}).get("mlsp.nebius.ai/task") != self.plan["task_id"]
            or secret_annotations.get("mlsp.nebius.ai/scope-sha256") != credentials["scope_sha256"]
            or secret_annotations.get("mlsp.nebius.ai/scope-manifest-sha256")
            != credentials["scope_manifest_sha256"]
            or secret_annotations.get("mlsp.nebius.ai/receipt-sha256") != credentials["receipt_sha256"]
            or secret_annotations.get("mlsp.nebius.ai/expires-at") != credentials["expires_at_utc"]
            or secret_annotations.get("mlsp.nebius.ai/revoke-by") != credentials["revoke_by_utc"]
        ):
            raise BaselineError("task-owned scoped registry credential receipt did not match")
        sentinel = self.kube.get_json("pod", self.plan["kubernetes"]["sentinel_pod"])
        sentinel_spec = sentinel.get("spec", {})
        sentinel_metadata = sentinel.get("metadata", {})
        containers = sentinel_spec.get("containers", [])
        statuses = sentinel.get("status", {}).get("containerStatuses", [])
        expected_sentinel = self.plan["security"]["support_images"]["sentinel_digest"]
        if (
            sentinel_spec.get("nodeName") != self.plan["kubernetes"]["node_name"]
            or sentinel_spec.get("serviceAccountName")
            != self.plan["security"]["workload_service_account"]
            or sentinel_metadata.get("labels", {}).get("mlsp.nebius.ai/task") != self.plan["task_id"]
            or sentinel_metadata.get("annotations", {}).get("mlsp.nebius.ai/broker-node-id")
            != self.plan["kubernetes"]["broker_node_id"]
            or [item.get("name") for item in sentinel_spec.get("imagePullSecrets", [])]
            != [credentials["secret_name"]]
            or len(containers) != 1 or containers[0].get("image") != expected_sentinel
            or len(statuses) != 1 or expected_sentinel.split("@", 1)[1] not in statuses[0].get("imageID", "")
        ):
            raise BaselineError("digest-pinned sentinel is not bound to the admitted node/credential")
        initial = self.lease["initial_state_receipt"]
        expected_initial = {
            key: value for key, value in initial.items() if key != "evidence_path"
        }
        try:
            observed_initial = json.loads(
                self._sentinel(
                    [
                        "/usr/local/bin/initial-state-receipt", "--node-id",
                        self.plan["kubernetes"]["broker_node_id"], "--json",
                    ],
                    timeout=30,
                )
            )
        except (json.JSONDecodeError, OSError) as exc:
            raise BaselineError("live initial occupant/cache receipt is unreadable") from exc
        if observed_initial != expected_initial:
            raise BaselineError(
                "live initial occupant/cache targets differ from the broker evidence receipt"
            )
        try:
            if self.plan["variant"] == "precreated_service":
                # This object is target-neutral: no model, request, attempt, or switch UID.
                self._prepare_owned.add(("service", "catalog-switch-endpoint"))
                self._record(
                    "prepare_resource_intent", kind="service", name="catalog-switch-endpoint"
                )
                self.kube.apply(self._generic_service("catalog-switch-endpoint"))
            occupant = self._active_occupant()
            initial_identity = None if initial["occupant"] is None else {
                "model_id": initial["occupant"]["model_id"],
                "model_version": initial["occupant"]["model_version"],
            }
            if occupant != initial_identity:
                raise BaselineError("live occupant differs from the broker initial-state receipt")
            self._record(
                "prepare", target_specific=False, server=server,
                node=self.plan["kubernetes"]["node_name"], variant=self.plan["variant"],
                broker_node_id=self.plan["kubernetes"]["broker_node_id"], preemptible=True,
            )
            self._prepared = True
        except Exception:
            self._cleanup_partial_prepare()
            raise

    def _cleanup_partial_prepare(self) -> None:
        for kind, name in sorted(self._prepare_owned, reverse=True):
            try:
                self.kube.delete(kind, name, 30)
                self._record("prepare_resource_deleted", kind=kind, name=name)
                self._prepare_owned.discard((kind, name))
            except Exception as exc:
                reason = f"{kind}/{name}: {type(exc).__name__}: {exc}"[:1000]
                self._prepare_cleanup_failures.append(reason)
                self._record("prepare_resource_cleanup_failed", kind=kind, name=name, reason=reason)

    def environment(self, request: dict[str, Any]) -> dict[str, Any]:
        model = self._model(request)
        profile = self.plan["gpu_profiles"][model["gpu_profile"]]
        return {
            "backend": self.plan["backend"],
            "backend_version": self.plan["backend_version"],
            "provider": "nebius",
            "project_id": self.plan["project_id"],
            "region": self.plan["region"],
            "node_id": self.plan["kubernetes"]["node_name"],
            "gpu_type": profile["product"],
            "gpu_count": profile["gpu_count"],
            "image_digest": model["image_digest"],
            "code_revision": self.plan["code_revision"],
            "config_sha256": self.plan["_resolved"]["config_sha256"],
            "experiment_id": self.plan["experiment_id"],
        }

    def accepted(self, request: dict[str, Any], event: dict[str, Any]) -> None:
        self._attempt[request["attempt_id"]]["t0_monotonic_ns"] = event[
            "observed_monotonic_ns"
        ]
        self._attempt[request["attempt_id"]]["t0_utc"] = event["observed_at_utc"]
        if request["scenario"] == "same_model_hot":
            # The admitted live occupant owns the GPU at T0.  Count the whole
            # demand interval conservatively, including readiness/validator
            # failures that happen before the inference phase can start.
            self._attempt[request["attempt_id"]]["gpu_active_started_ns"] = event[
                "observed_monotonic_ns"
            ]
        if self._last_billing_ns is None:
            self._last_billing_ns = event["observed_monotonic_ns"]
        self._record(
            "external_request_accepted",
            attempt_id=request["attempt_id"],
            t0_monotonic_ns=event["observed_monotonic_ns"],
            boundary="external-client-request-accepted/v1",
        )

    def _resource(self, kind: str, resource_id: str) -> dict[str, str]:
        return {
            "kind": kind,
            "id": resource_id,
            "project_id": self.plan["project_id"],
            "region": self.plan["region"],
        }

    def _names(self, request: dict[str, Any]) -> tuple[str, str]:
        suffix = request["attempt_id"].lower().replace("_", "-")[-40:].strip("-")
        return f"cs-target-{suffix}"[:63].rstrip("-"), f"cs-svc-{suffix}"[:63].rstrip("-")

    def ownership(self, request: dict[str, Any]) -> dict[str, Any]:
        pod_name, service_name = self._names(request)
        namespace = self.plan["kubernetes"]["namespace"]
        resources = [
            self._resource(item["kind"], item["id"])
            for item in self.lease.get("resources", [])
            if not item.get("deleted_at")
        ]
        owned_pod = (
            self._active_pod
            if request["scenario"] == "same_model_hot" and self._active_pod
            else pod_name
        )
        resources.append(self._resource("pod", f"k8s:{namespace}/pod/{owned_pod}"))
        if self.plan["variant"] == "per_run_service":
            resources.append(
                self._resource("service", f"k8s:{namespace}/service/{service_name}")
            )
        self._attempt[request["attempt_id"]] = {
            "pod_name": pod_name,
            "owned_pod_name": owned_pod,
            "service_name": (
                service_name
                if self.plan["variant"] == "per_run_service"
                else "catalog-switch-endpoint"
            ),
            "resource_ids": tuple(item["id"] for item in resources),
            "deleted": [],
            "worker_started_ns": None,
            "gpu_active_started_ns": None,
            "gpu_active_closed_ns": None,
            "gpu_active_seconds": 0.0,
            "placement_submitted_ns": None,
            "strategy_receipt": None,
            "strategy_active_elapsed_ns": None,
            "strategy_accounting_failure": None,
            "byte_accounting_failures": {},
            "phase_bytes": {},
            "response": None,
            "validator": None,
            "semantic_calls": [],
            "two_call_qualified": False,
            "cohort": {
                "model_id": request["target"]["model_id"],
                "model_version": request["target"]["model_version"],
                "arm": self.plan["campaign_arm"],
                "scenario": request["scenario"],
                "strategy": self.plan["scenario_strategies"][request["scenario"]],
                "variant": self.plan["variant"],
                "cache": request["precondition"]["cache"],
                "gpu_profile": self._model(request)["gpu_profile"],
            },
        }
        return {
            "owner_task_id": self.plan["task_id"],
            "resource_prefix": self.plan["resource_lease"]["prefix"],
            "dedicated": True,
            "cleanup_required": True,
            "resources": resources,
        }

    def should_skip(self, request: dict[str, Any], phase: str) -> str | None:
        scenario = request["scenario"]
        if scenario == "same_model_hot":
            if phase in {
                "drain",
                "gpu_release",
                "image_readiness",
                "artifact_readiness",
                "storage_readiness",
                "cache_readiness",
                "runtime_launch",
            }:
                return "same digest already serves on the exclusive admitted GPU"
            if phase == "placement" and self.plan["variant"] == "precreated_service":
                return "target-neutral Service and hot Pod already exist"
        if scenario == "idle_local" and phase in {"drain", "gpu_release"}:
            return "node is already idle"
        return None

    def _verify_trace_precondition(self, request: dict[str, Any]) -> None:
        occupant = self._active_occupant()
        if occupant != request["precondition"]["current_node_occupant"]:
            raise BaselineError(
                f"live occupant {occupant} differs from accepted trace precondition "
                f"{request['precondition']['current_node_occupant']}"
            )
        node = self.kube.get_json(
            "node", self.plan["kubernetes"]["node_name"], namespace=False
        )
        unschedulable = bool(node.get("spec", {}).get("unschedulable", False))
        capacity = request["precondition"]["capacity"]
        if capacity == "unavailable" and not unschedulable:
            raise BaselineError("capacity-miss trace requires the task node to be cordoned")
        if capacity != "unavailable" and unschedulable:
            raise BaselineError("available-capacity trace cannot run on a cordoned node")
        model = self._model(request)
        raw = self._sentinel(
            [
                "/usr/local/bin/cache-state",
                "--model-id",
                model["model_id"],
                "--model-version",
                model["model_version"],
                "--artifact-sha256",
                model["artifact_sha256"],
                "--checkpoint-sha256",
                model["checkpoint"]["checkpoint_sha256"] if model["checkpoint"] else "not-applicable",
                "--image-digest",
                model["image_digest"],
                "--json",
            ],
            timeout=120,
        )
        try:
            receipt = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaselineError("cache sentinel returned a non-JSON receipt") from exc
        required = {
            "schema",
            "status",
            "model_id",
            "model_version",
            "artifact_id",
            "artifact_version",
            "artifact_sha256",
            "artifact_bytes",
            "image_digest",
            "image_bytes",
            "checkpoint",
            "cache",
            "evidence_sha256",
        }
        if set(receipt) != required:
            raise BaselineError("cache-state receipt has the wrong shape")
        if (
            receipt["schema"] != "archvteams.nebius.ai/cache-state-receipt/v1"
            or receipt["status"] != "PASS"
            or receipt["model_id"] != model["model_id"]
            or receipt["model_version"] != model["model_version"]
            or receipt["artifact_id"] != model["artifact_id"]
            or receipt["artifact_version"] != model["artifact_version"]
            or receipt["artifact_sha256"] != model["artifact_sha256"]
            or receipt["artifact_bytes"] != model["artifact_bytes"]
            or receipt["image_digest"] != model["image_digest"]
            or receipt["image_bytes"] != model["image_bytes"]
            or receipt["checkpoint"] != model["checkpoint"]
            or receipt["cache"] != request["precondition"]["cache"]
            or not isinstance(receipt["evidence_sha256"], str)
            or len(receipt["evidence_sha256"]) != 64
        ):
            raise BaselineError("live cache state differs from the accepted trace precondition")
        self._record(
            "cache_precondition_verified",
            attempt_id=request["attempt_id"],
            receipt=receipt,
            pre_t0=False,
        )

    def _delete_active(self, switch_uid: str) -> tuple[str, ...]:
        pods = self._pods()
        deleted: list[str] = []
        for item in pods:
            name = item["metadata"]["name"]
            uid = item["metadata"]["uid"]
            self.kube.delete(
                "pod", name, self.plan["kubernetes"]["drain_timeout_seconds"]
            )
            self._record("pod_deleted", switch_uid=switch_uid, name=name, uid=uid)
            deleted.append(
                f"k8s:{self.plan['kubernetes']['namespace']}/pod/{name}"
            )
        if self._pods():
            raise BaselineError("drain completed with surviving target Pods")
        self._active_pod = None
        return tuple(deleted)

    def _evict_model_cache_for_next_attempt(self, request: dict[str, Any]) -> None:
        occupant = request["precondition"]["current_node_occupant"]
        if occupant is None:
            raise BaselineError("remote A-to-B cleanup lacks the prior model identity")
        key = (occupant["model_id"], occupant["model_version"])
        try:
            model = self.models[key]
        except KeyError as exc:
            raise BaselineError("remote A-to-B prior model is absent from the plan") from exc
        raw = self._sentinel(
            [
                "/usr/local/bin/cache-evict",
                "--model-id",
                model["model_id"],
                "--model-version",
                model["model_version"],
                "--artifact-sha256",
                model["artifact_sha256"],
                "--image-digest",
                model["image_digest"],
                "--json",
            ],
            timeout=600,
        )
        try:
            receipt = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaselineError("cache eviction returned a non-JSON receipt") from exc
        required = {
            "schema",
            "status",
            "model_id",
            "model_version",
            "artifact_sha256",
            "image_digest",
            "image_absent",
            "artifact_absent",
            "checkpoint_absent",
            "evidence_sha256",
        }
        if set(receipt) != required or (
            receipt["schema"] != "archvteams.nebius.ai/cache-eviction-receipt/v1"
            or receipt["status"] != "PASS"
            or receipt["model_id"] != model["model_id"]
            or receipt["model_version"] != model["model_version"]
            or receipt["artifact_sha256"] != model["artifact_sha256"]
            or receipt["image_digest"] != model["image_digest"]
            or receipt["image_absent"] is not True
            or receipt["artifact_absent"] is not True
            or receipt["checkpoint_absent"] is not True
            or not isinstance(receipt["evidence_sha256"], str)
            or len(receipt["evidence_sha256"]) != 64
        ):
            raise BaselineError("cache eviction did not prove the next remote-miss precondition")
        self._record(
            "next_attempt_cache_precondition_established",
            attempt_id=request["attempt_id"],
            receipt=receipt,
            outside_product_boundary=True,
        )

    def _sentinel(self, args: list[str], *, timeout: int = 120) -> str:
        return self.kube.run(
            ["exec", self.plan["kubernetes"]["sentinel_pod"], "--", *args],
            timeout=timeout,
        )

    def _gpu_scrub(self, request: dict[str, Any]) -> dict[str, Any]:
        raw = self._sentinel(
            ["/usr/local/bin/gpu-scrub", "--switch-uid", request["attempt_id"], "--json"],
            timeout=300,
        )
        try:
            receipt = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaselineError("GPU sentinel returned a non-JSON scrub receipt") from exc
        required = {
            "schema",
            "switch_uid",
            "method",
            "lease_id",
            "node_name",
            "node_uid",
            "broker_node_id",
            "node_boot_id",
            "sentinel_image_digest",
            "sentinel_source_receipt_sha256",
            "observed_at_utc",
            "gpus",
            "status",
        }
        if set(receipt) != required:
            raise BaselineError("GPU scrub receipt has the wrong shape")
        if (
            receipt["schema"] != "archvteams.nebius.ai/gpu-zero-receipt/v2"
            or receipt["switch_uid"] != request["attempt_id"]
            or receipt["method"] != "full-vram-zero"
            or receipt["lease_id"] != self.plan["resource_lease"]["lease_id"]
            or receipt["node_name"] != self.plan["kubernetes"]["node_name"]
            or receipt["node_uid"] != self.plan["kubernetes"]["node_uid"]
            or receipt["broker_node_id"] != self.plan["kubernetes"]["broker_node_id"]
            or receipt["node_boot_id"] != self.lease["node_boot_id"]
            or receipt["sentinel_image_digest"]
            != self.plan["security"]["support_images"]["sentinel_digest"]
            or receipt["sentinel_source_receipt_sha256"]
            != self.plan["security"]["support_images"]["source_receipt_sha256"]
            or receipt["status"] != "PASS"
        ):
            raise BaselineError("GPU scrub/zero proof failed; node must be quarantined")
        if not isinstance(receipt["observed_at_utc"], str) or not receipt[
            "observed_at_utc"
        ].endswith("Z"):
            raise BaselineError("GPU scrub receipt has an invalid UTC observation")
        try:
            observed_at = datetime.fromisoformat(
                receipt["observed_at_utc"].removesuffix("Z") + "+00:00"
            )
        except (AttributeError, ValueError) as exc:
            raise BaselineError("GPU scrub receipt has an invalid UTC observation") from exc
        if observed_at.tzinfo != UTC:
            raise BaselineError("GPU scrub receipt observation is not UTC")
        gpus = receipt["gpus"]
        inventory = sorted(self.lease["gpu_inventory"], key=lambda item: item["gpu_index"])
        if not isinstance(gpus, list) or len(gpus) != len(inventory):
            raise BaselineError("GPU scrub receipt does not cover the admitted inventory")
        gpu_required = {
            "gpu_uuid", "gpu_index", "product", "memory_bytes_total", "bytes_scrubbed",
            "compute_process_count", "graphics_process_count", "baseline_memory_bytes",
            "observed_memory_bytes",
        }
        if any(not isinstance(item, dict) or set(item) != gpu_required for item in gpus):
            raise BaselineError("GPU scrub receipt has a malformed per-GPU proof")
        for actual, expected in zip(
            sorted(gpus, key=lambda item: item["gpu_index"]), inventory, strict=True
        ):
            numeric = (
                "gpu_index", "memory_bytes_total", "bytes_scrubbed",
                "compute_process_count", "graphics_process_count",
                "baseline_memory_bytes", "observed_memory_bytes",
            )
            if (
                any(
                    not isinstance(actual[key], int) or isinstance(actual[key], bool)
                    for key in numeric
                )
                or any(actual[key] != expected[key] for key in expected)
                or actual["bytes_scrubbed"] != expected["memory_bytes_total"]
                or actual["compute_process_count"] != 0
                or actual["graphics_process_count"] != 0
                or actual["baseline_memory_bytes"] < 0
                or actual["observed_memory_bytes"] != actual["baseline_memory_bytes"]
            ):
                raise BaselineError("GPU scrub receipt is not a full per-GPU VRAM-zero proof")
        self._record("gpu_zero", attempt_id=request["attempt_id"], receipt=receipt)
        return receipt

    def _render_target(self, request: dict[str, Any]) -> str:
        model = self._model(request)
        state = self._attempt[request["attempt_id"]]
        strategy = self.plan["scenario_strategies"][request["scenario"]]
        checkpoint = model["checkpoint"] if strategy == "snapshot" else None
        template_key = f"{strategy}_template"
        if template_key not in model["_paths"]:
            raise BaselineError(f"no target template for strategy {strategy}")
        template_path = Path(model["_paths"][template_key])
        expected_template_sha = model["target_templates"][strategy]["sha256"]
        try:
            template_bytes = template_path.read_bytes()
        except OSError as exc:
            raise BaselineError("target template became unavailable after admission") from exc
        if hashlib.sha256(template_bytes).hexdigest() != expected_template_sha:
            raise BaselineError("target template drifted after immutable plan admission")
        try:
            text = template_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BaselineError("target template is not UTF-8") from exc
        tokens = {
            "@@NAMESPACE@@": self.plan["kubernetes"]["namespace"],
            "@@POD_NAME@@": state["pod_name"],
            "@@NODE_NAME@@": self.plan["kubernetes"]["node_name"],
            "@@SWITCH_UID@@": request["attempt_id"],
            "@@MODEL_ID@@": model["model_id"],
            "@@MODEL_VERSION_ID@@": model["version_label"],
            "@@MODEL_VERSION_FULL@@": model["model_version"],
            "@@ARTIFACT_ID@@": model["artifact_id"],
            "@@ARTIFACT_VERSION@@": model["artifact_version"],
            "@@ARTIFACT_SHA256@@": model["artifact_sha256"],
            "@@IMAGE_DIGEST@@": model["image_digest"],
            "@@CONTAINER_NAME@@": model["container_name"],
            "@@IMAGE_PULL_SECRET@@": self.plan["security"]["credentials"]["secret_name"],
            "@@READINESS_GATE_DIGEST@@": self.plan["security"]["support_images"]["readiness_gate_digest"],
            "@@STRATEGY@@": strategy,
            "@@CHECKPOINT_ID@@": checkpoint["checkpoint_id"] if checkpoint else "not-used",
            "@@CHECKPOINT_SHA256@@": checkpoint["checkpoint_sha256"] if checkpoint else "0" * 64,
            "@@CHECKPOINT_BYTES@@": str(checkpoint["checkpoint_bytes"] if checkpoint else 0),
        }
        for token, replacement in tokens.items():
            text = text.replace(token, replacement)
        if "@@" in text:
            raise BaselineError("target manifest contains an unresolved template token")
        return text

    def _verify_rendered_target(
        self, value: dict[str, Any], request: dict[str, Any]
    ) -> None:
        model = self._model(request)
        state = self._attempt[request["attempt_id"]]
        if value.get("kind") != "Pod" or value.get("apiVersion") != "v1":
            raise BaselineError("rendered target is not one canonical Pod")
        metadata = value.get("metadata", {})
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        expected_labels = {
            "mlsp.nebius.ai/role": "catalog-switch-target",
            "mlsp.nebius.ai/task": self.plan["task_id"],
            "mlsp.nebius.ai/resource-prefix": self.plan["resource_lease"]["prefix"],
            "mlsp.nebius.ai/model-id": model["model_id"],
            "mlsp.nebius.ai/model-version-id": model["version_label"],
        }
        expected_annotations = {
            "mlsp.nebius.ai/model-version-full": model["model_version"],
            "mlsp.nebius.ai/artifact-id": model["artifact_id"],
            "mlsp.nebius.ai/artifact-version": model["artifact_version"],
            "mlsp.nebius.ai/artifact-sha256": model["artifact_sha256"],
            "mlsp.nebius.ai/image-digest": model["image_digest"],
            "mlsp.nebius.ai/strategy": self.plan["scenario_strategies"][request["scenario"]],
        }
        strategy = self.plan["scenario_strategies"][request["scenario"]]
        checkpoint_annotations = {
            "mlsp.nebius.ai/checkpoint-id",
            "mlsp.nebius.ai/checkpoint-sha256",
            "mlsp.nebius.ai/checkpoint-bytes",
        }
        if strategy == "snapshot":
            expected_annotations.update(
                {
                    "mlsp.nebius.ai/checkpoint-id": model["checkpoint"]["checkpoint_id"],
                    "mlsp.nebius.ai/checkpoint-sha256": model["checkpoint"]["checkpoint_sha256"],
                    "mlsp.nebius.ai/checkpoint-bytes": str(model["checkpoint"]["checkpoint_bytes"]),
                }
            )
        elif checkpoint_annotations & set(annotations):
            raise BaselineError("conventional target falsely declares snapshot checkpoint work")
        spec = value.get("spec", {})
        credentials = self.plan["security"]["credentials"]
        if (
            metadata.get("name") != state["pod_name"]
            or metadata.get("namespace") != self.plan["kubernetes"]["namespace"]
            or any(labels.get(key) != expected for key, expected in expected_labels.items())
            or any(annotations.get(key) != expected for key, expected in expected_annotations.items())
            or spec.get("nodeName") != self.plan["kubernetes"]["node_name"]
            or spec.get("serviceAccountName") != self.plan["security"]["workload_service_account"]
            or [item.get("name") for item in spec.get("imagePullSecrets", [])]
            != [credentials["secret_name"]]
        ):
            raise BaselineError("rendered target identity/ownership receipt differs from the plan")
        containers = spec.get("containers", [])
        selected = [item for item in containers if item.get("name") == model["container_name"]]
        if (
            len(containers) != 1
            or len(selected) != 1
            or selected[0].get("image") != model["image_digest"]
        ):
            raise BaselineError(
                "rendered target container set differs from the reviewed runtime source allowlist"
            )
        limits = selected[0].get("resources", {}).get("limits", {})
        profile = self.plan["gpu_profiles"][model["gpu_profile"]]
        if int(limits.get("nvidia.com/gpu", 0)) != profile["gpu_count"]:
            raise BaselineError("rendered target GPU request differs from its compatible profile")
        all_images = [item.get("image", "") for item in [*spec.get("initContainers", []), *containers]]
        if any("@sha256:" not in image for image in all_images):
            raise BaselineError("rendered target contains a mutable container image")
        readiness = self.plan["security"]["support_images"]["readiness_gate_digest"]
        init_containers = spec.get("initContainers", [])
        expected_init_names = ["artifact-gate", "cache-gate", "storage-gate"]
        if strategy == "snapshot":
            expected_init_names.append("snapshot-restore-gate")
        actual_init_names = [item.get("name") for item in init_containers]
        if (
            sorted(actual_init_names) != sorted(expected_init_names)
            or len(set(actual_init_names)) != len(actual_init_names)
            or any(item.get("image") != readiness for item in init_containers)
        ):
            raise BaselineError(
                "rendered target init-container set differs from the reviewed runtime source allowlist"
            )
        restore_gates = [item for item in init_containers if item.get("name") == "snapshot-restore-gate"]
        if (strategy == "snapshot" and len(restore_gates) != 1) or (
            strategy != "snapshot" and restore_gates
        ):
            raise BaselineError("rendered target snapshot restore gate differs from strategy")

    def _capture_strategy_receipt(
        self, request: dict[str, Any], model: dict[str, Any], *, require_complete: bool
    ) -> dict[str, Any]:
        strategy = self.plan["scenario_strategies"][request["scenario"]]
        receipt = json.loads(
            self._sentinel(
                [
                    "/usr/local/bin/strategy-receipt", "--attempt-id", request["attempt_id"],
                    "--pod", self._attempt[request["attempt_id"]]["pod_name"],
                    "--allow-incomplete", "--json",
                ],
                timeout=30,
            )
        )
        receipt = receipt if isinstance(receipt, dict) else {}
        expected_identity = {
            "schema": "archvteams.nebius.ai/k8s-strategy-receipt/v2",
            "attempt_id": request["attempt_id"],
            "model_id": model["model_id"],
            "model_version": model["model_version"],
            "artifact_sha256": model["artifact_sha256"],
            "strategy": strategy,
            "checkpoint": model["checkpoint"] if strategy == "snapshot" else None,
            "node_clock_id": "CLOCK_MONOTONIC",
        }
        expected_keys = {
            *expected_identity,
            "status", "strategy_work_duration_ns", "gpu_active_elapsed_ns",
            "gpu_process_active", "observed_at_utc", "evidence_sha256",
        }
        state = self._attempt[request["attempt_id"]]
        statuses = {
            "snapshot": {"NOT_STARTED", "RUNNING", "RESTORED", "FAILED"},
            "conventional": {"NOT_STARTED", "RUNNING", "LOADED", "FAILED"},
            "none": {"NOT_USED"},
        }[strategy]
        work_duration = receipt.get("strategy_work_duration_ns")
        active_elapsed = receipt.get("gpu_active_elapsed_ns")
        process_active = receipt.get("gpu_process_active")
        if (
            set(receipt) != expected_keys
            or any(receipt.get(key) != value for key, value in expected_identity.items())
            or receipt.get("status") not in statuses
            or not isinstance(receipt.get("observed_at_utc"), str)
            or not receipt["observed_at_utc"].endswith("Z")
            or not isinstance(process_active, bool)
            or not isinstance(receipt.get("evidence_sha256"), str)
            or len(receipt["evidence_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in receipt["evidence_sha256"])
        ):
            raise BaselineError("runtime strategy/checkpoint receipt differs from the executable plan")
        if receipt["status"] in {"NOT_STARTED", "NOT_USED"}:
            if work_duration != 0 or active_elapsed != 0 or process_active:
                raise BaselineError("strategy receipt claims GPU time before work began")
        elif (
            not isinstance(active_elapsed, int)
            or active_elapsed <= 0
            or (
                work_duration is not None
                and (not isinstance(work_duration, int) or work_duration <= 0)
            )
            or (isinstance(work_duration, int) and work_duration > active_elapsed)
        ):
            raise BaselineError("strategy receipt has invalid same-node GPU durations")
        if receipt["status"] in {"RESTORED", "LOADED", "FAILED"} and not isinstance(
            work_duration, int
        ):
            raise BaselineError("terminal strategy receipt lacks a GPU-work duration")
        if receipt["status"] == "RUNNING" and work_duration is not None:
            raise BaselineError("running strategy receipt already claims a work duration")
        if receipt["status"] in {"RESTORED", "LOADED", "RUNNING"} and not process_active:
            raise BaselineError("successful/running strategy receipt lacks the active GPU process")
        if receipt["status"] in {"FAILED", "NOT_STARTED", "NOT_USED"} and process_active:
            raise BaselineError("terminal/nonstarted strategy receipt falsely claims an active process")
        expected_complete = "RESTORED" if strategy == "snapshot" else "LOADED"
        if require_complete and receipt["status"] != expected_complete:
            raise BaselineError("runtime strategy did not complete the admitted restore/load")
        prior_elapsed = state.get("strategy_active_elapsed_ns")
        if (
            isinstance(prior_elapsed, int)
            and process_active
            and active_elapsed <= prior_elapsed
        ):
            raise BaselineError(
                "refreshed active-process strategy receipt did not advance GPU time"
            )
        state["strategy_active_elapsed_ns"] = active_elapsed
        state["gpu_active_seconds"] = active_elapsed / 1_000_000_000
        state["strategy_receipt"] = receipt
        self._record(
            "strategy_receipt", attempt_id=request["attempt_id"], receipt=receipt
        )
        return receipt

    def _verify_strategy_receipt(
        self, request: dict[str, Any], model: dict[str, Any]
    ) -> None:
        self._capture_strategy_receipt(request, model, require_complete=True)

    def _pod(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.kube.get_json("pod", self._attempt[request["attempt_id"]]["pod_name"])

    def _wait(self, description: str, timeout: int, predicate: Any) -> Any:
        deadline = time.monotonic() + timeout
        last: Any = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(0.2)
        raise BaselineError(f"timed out waiting for {description}; last={last!r}")

    def _start_port_forward(self, request: dict[str, Any]) -> None:
        if self._port_forward is not None:
            self._stop_port_forward()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = int(reservation.getsockname()[1])
        service = self._attempt[request["attempt_id"]]["service_name"]
        command = [
            *self.kube.prefix,
            "--namespace",
            self.plan["kubernetes"]["namespace"],
            "port-forward",
            f"service/{service}",
            f"127.0.0.1:{port}:8000",
        ]
        self._port_forward = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._port = port
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self._port_forward.poll() is not None:
                stderr = self._port_forward.stderr.read() if self._port_forward.stderr else ""
                raise BaselineError(f"kubectl port-forward failed: {stderr[:1000]}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return
            except OSError:
                time.sleep(0.05)
        raise BaselineError("kubectl port-forward did not become reachable")

    def _stop_port_forward(self) -> None:
        process = self._port_forward
        self._port_forward = None
        self._port = None
        if process is None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _http(self, path: str, body: bytes | None = None) -> bytes:
        if self._port is None:
            raise BaselineError("port-forward is not active")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}{path}",
            data=body,
            method="POST" if body is not None else "GET",
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                result = response.read(32 * 1024 * 1024 + 1)
                if response.status != 200:
                    raise BaselineError(f"model endpoint returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise BaselineError(f"model endpoint returned HTTP {exc.code}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise BaselineError(f"model endpoint transport failed: {type(exc).__name__}") from exc
        if len(result) > 32 * 1024 * 1024:
            raise BaselineError("model response exceeded the 32 MiB bound")
        return result

    def _call_bundle(self, model: dict[str, Any]) -> list[dict[str, Any]]:
        bundle_path = Path(model["_paths"]["request_file"])
        try:
            bundle_bytes = bundle_path.read_bytes()
            if hashlib.sha256(bundle_bytes).hexdigest() != model["request_sha256"]:
                raise BaselineError("two-call request bundle drifted after durable admission")
            value = json.loads(bundle_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise BaselineError("two-call request bundle is invalid") from exc
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "calls"}
            or value["schema"]
            != "archvteams.nebius.ai/two-semantic-inference-bundle/v1"
            or not isinstance(value["calls"], list)
            or len(value["calls"]) != 2
        ):
            raise BaselineError("request bundle must contain exactly two semantic calls")
        calls = value["calls"]
        if any(
            not isinstance(item, dict)
            or set(item) != {"input_id", "payload_path", "payload_sha256", "overrides"}
            or not isinstance(item["input_id"], str)
            or not isinstance(item["payload_path"], str)
            or not isinstance(item["payload_sha256"], str)
            or len(item["payload_sha256"]) != 64
            or not isinstance(item["overrides"], dict)
            for item in calls
        ):
            raise BaselineError("two-call request bundle has the wrong shape")
        resolved: list[dict[str, Any]] = []
        for item in calls:
            payload_path = Path(item["payload_path"])
            if not payload_path.is_absolute():
                payload_path = (bundle_path.parent / payload_path).resolve()
            if payload_path.is_symlink() or not payload_path.is_file():
                raise BaselineError("semantic call payload must be a regular non-symlink file")
            payload_bytes = payload_path.read_bytes()
            if hashlib.sha256(payload_bytes).hexdigest() != item["payload_sha256"]:
                raise BaselineError("semantic call payload digest drifted")
            try:
                payload = json.loads(payload_bytes)
            except json.JSONDecodeError as exc:
                raise BaselineError("semantic call payload is invalid JSON") from exc
            if not isinstance(payload, dict):
                raise BaselineError("semantic call payload must be an object")
            payload.update(item["overrides"])
            resolved.append({"input_id": item["input_id"], "payload": payload})
        return resolved

    def _validate_response(
        self, model: dict[str, Any], payload: dict[str, Any], body: bytes
    ) -> None:
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BaselineError("model response is not JSON") from exc
        path = Path(model["_paths"]["validator_path"])
        try:
            validator_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise BaselineError("semantic validator became unavailable after admission") from exc
        if validator_sha256 != model["validator_sha256"]:
            raise BaselineError("semantic validator drifted after immutable plan admission")
        module = _load_module(path, "catalog_switch_validator_" + model["model_id"])
        adapter = model["validator_adapter"]
        if adapter == "proteinmpnn-v1":
            module._validate_response(value, int(payload["random_seed"]))
        elif adapter == "boltz2-v1":
            polymer = payload["polymers"][0]
            module.validate_response(value, polymer["sequence"], polymer["id"])
        elif adapter == "openfold2-v1":
            module.validate_response(value, payload["input_id"], payload["sequence"])
        else:
            raise BaselineError("no audited semantic validator adapter for selected model")

    def _close_gpu_active(self, state: dict[str, Any]) -> None:
        started = state.get("gpu_active_started_ns")
        if started is None or state.get("gpu_active_closed_ns") is not None:
            return
        closed = time.monotonic_ns()
        state["gpu_active_closed_ns"] = closed
        state["gpu_active_seconds"] = max(0.0, (closed - started) / 1_000_000_000)

    def _partial_phase_bytes(self, request: dict[str, Any], phase: str) -> int:
        state = self._attempt[request["attempt_id"]]
        observed = int(state.get("phase_bytes", {}).get(phase, 0))
        if phase not in {"image_readiness", "artifact_readiness", "storage_readiness"}:
            return observed
        try:
            raw = self._sentinel(
                [
                    "/usr/local/bin/phase-progress", "--attempt-id", request["attempt_id"],
                    "--phase", phase, "--json",
                ],
                timeout=30,
            )
            receipt = json.loads(raw)
            if not (
                set(receipt) == {"schema", "attempt_id", "phase", "bytes_moved", "evidence_sha256"}
                and receipt["schema"] == "archvteams.nebius.ai/phase-progress/v1"
                and receipt["attempt_id"] == request["attempt_id"] and receipt["phase"] == phase
                and isinstance(receipt["bytes_moved"], int) and receipt["bytes_moved"] >= 0
                and isinstance(receipt["evidence_sha256"], str)
                and len(receipt["evidence_sha256"]) == 64
                and all(character in "0123456789abcdef" for character in receipt["evidence_sha256"])
            ):
                raise BaselineError("phase progress receipt is malformed or foreign")
            observed = max(observed, receipt["bytes_moved"])
        except Exception as exc:
            # Once a transfer-capable phase faults, an unavailable progress
            # receipt means the byte count is unknown, not zero.  Preserve a
            # conservative upper bound in the canonical ledger and force the
            # accounting/cleanup path to fail closed so it cannot promote as
            # measured transfer evidence.
            model = self._model(request)
            conservative = {
                "image_readiness": int(model["image_bytes"]),
                "artifact_readiness": int(model["artifact_bytes"]),
                "storage_readiness": max(
                    int(model["artifact_bytes"]),
                    int((model.get("checkpoint") or {}).get("checkpoint_bytes", 0)),
                ),
            }[phase]
            state.setdefault("byte_accounting_failures", {})[phase] = (
                f"{type(exc).__name__}: {exc}; ledger_bytes_are_conservative_upper_bound"
            )[:1000]
            observed = max(observed, conservative)
        return observed

    def run_phase(self, request: dict[str, Any], phase: str) -> PhaseResult:
        try:
            return self._run_phase_inner(request, phase)
        except Exception as exc:
            state = self._attempt[request["attempt_id"]]
            strategy = self.plan["scenario_strategies"][request["scenario"]]
            if state.get("placement_submitted_ns") is not None and strategy != "none":
                try:
                    self._capture_strategy_receipt(
                        request, self._model(request), require_complete=False
                    )
                except Exception as receipt_exc:
                    # A Pod was admitted and may have consumed GPU before its
                    # timing receipt became readable.  Conservatively account
                    # from submission and make the attempt unpromotable rather
                    # than inventing zero active time.
                    state["strategy_accounting_failure"] = (
                        f"{type(receipt_exc).__name__}: {receipt_exc}"[:1000]
                    )
                    if state.get("gpu_active_started_ns") is None:
                        state["gpu_active_started_ns"] = state["placement_submitted_ns"]
            moved = max(
                getattr(exc, "bytes_moved", 0)
                if isinstance(getattr(exc, "bytes_moved", 0), int)
                else 0,
                self._partial_phase_bytes(request, phase),
            )
            self._close_gpu_active(state)
            raise PhaseExecutionError(
                f"{type(exc).__name__}: {exc}", bytes_moved=moved
            ) from exc

    def _run_phase_inner(self, request: dict[str, Any], phase: str) -> PhaseResult:
        state = self._attempt[request["attempt_id"]]
        model = self._model(request)
        if phase == "catalog_selection":
            self._verify_trace_precondition(request)
            return PhaseResult("completed", "catalog identity and live precondition matched")
        if phase == "queue":
            state["worker_started_ns"] = time.monotonic_ns()
            return PhaseResult("completed", "exclusive admitted-GPU worker dequeued attempt")
        if phase == "drain":
            self._delete_active(request["attempt_id"])
            return PhaseResult("completed", "prior target Pod UID deleted within drain deadline")
        if phase == "gpu_release":
            receipt = self._gpu_scrub(request)
            return PhaseResult(
                "completed",
                f"{receipt['method']} scrubbed "
                f"{sum(item['bytes_scrubbed'] for item in receipt['gpus'])} bytes "
                "with zero compute/graphics processes",
            )
        if phase == "placement":
            if self.plan["variant"] == "per_run_service":
                self.kube.apply(self._generic_service(state["service_name"]))
                self._record(
                    "support_object_created",
                    attempt_id=request["attempt_id"],
                    kind="Service",
                    name=state["service_name"],
                    pre_t0=False,
                )
            if request["scenario"] == "capacity_miss":
                return PhaseResult("failed", "task-owned admitted GPU node is cordoned/unavailable")
            if request["scenario"] != "same_model_hot":
                manifest = self._render_target(request)
                rendered = self.kube.run(
                    ["apply", "--dry-run=client", "-f", "-", "-o", "json"],
                    stdin=manifest, timeout=60, json_output=True,
                )
                self._verify_rendered_target(rendered, request)
                state["placement_submitted_ns"] = time.monotonic_ns()
                self.kube.apply(manifest)
                self._active_pod = state["pod_name"]
            return PhaseResult("completed", "target Pod and request-scoped support submitted")
        if phase == "image_readiness":
            expected = model["image_digest"].split("@", 1)[-1]

            def image_ready() -> bool:
                pod = self._pod(request)
                statuses = pod.get("status", {}).get("containerStatuses", [])
                return any(
                    item.get("name") == model["container_name"]
                    and expected in item.get("imageID", "")
                    for item in statuses
                )

            self._wait("digest-pinned image readiness", 900, image_ready)
            moved = (
                model["image_bytes"]
                if request["precondition"]["cache"]["image"] == "remote_required"
                else 0
            )
            state["phase_bytes"][phase] = moved
            return PhaseResult("completed", "container status proved exact image digest", moved)
        if phase in {"artifact_readiness", "storage_readiness", "cache_readiness"}:
            pod = self._pod(request)
            gate_name = {
                "artifact_readiness": "artifact-gate",
                "storage_readiness": "storage-gate",
                "cache_readiness": "cache-gate",
            }[phase]
            statuses = pod.get("status", {}).get("initContainerStatuses", [])
            matches = [item for item in statuses if item.get("name") == gate_name]
            if len(matches) != 1:
                raise BaselineError(f"target Pod lacks unique {gate_name} init status")
            terminated = matches[0].get("state", {}).get("terminated", {})
            try:
                gate = json.loads(terminated.get("message", ""))
            except json.JSONDecodeError as exc:
                raise BaselineError(f"{gate_name} termination receipt is invalid") from exc
            observed_bytes = gate.get("bytes_moved", 0)
            if isinstance(observed_bytes, int) and observed_bytes >= 0:
                state["phase_bytes"][phase] = observed_bytes
            if terminated.get("exitCode") != 0:
                raise PhaseExecutionError(
                    f"{gate_name} did not complete successfully",
                    bytes_moved=state["phase_bytes"].get(phase, 0),
                )
            if gate.get("schema") != "archvteams.nebius.ai/k8s-readiness-gate/v1" or gate.get(
                "status"
            ) != "PASS":
                raise BaselineError(f"{gate_name} receipt did not pass")
            moved = 0
            if phase == "artifact_readiness" and request["precondition"]["cache"]["artifact"] == "remote_miss":
                observed = gate.get("bytes_moved")
                if observed != model["artifact_bytes"]:
                    raise BaselineError("remote artifact bytes differ from the pinned catalog")
                moved = int(observed)
            if phase == "artifact_readiness" and gate.get("artifact_sha256") != model[
                "artifact_sha256"
            ]:
                raise BaselineError("artifact readiness receipt has the wrong digest")
            state["phase_bytes"][phase] = moved
            return PhaseResult("completed", f"{phase} attestation is verified", moved)
        if phase == "runtime_launch":
            def started() -> bool:
                statuses = self._pod(request).get("status", {}).get("containerStatuses", [])
                return any(
                    item.get("name") == model["container_name"]
                    and item.get("state", {}).get("running", {}).get("startedAt")
                    for item in statuses
                )

            self._wait(
                "runtime container start",
                self.plan["kubernetes"]["ready_timeout_seconds"],
                started,
            )
            self._verify_strategy_receipt(request, model)
            return PhaseResult(
                "completed", "model container and exact strategy/checkpoint receipt verified"
            )
        if phase == "service_readiness":
            self._start_port_forward(request)

            def ready() -> bool:
                try:
                    body = self._http(model["ready_path"])
                    value = json.loads(body)
                    return value is True or (
                        isinstance(value, dict) and value.get("status") == "ready"
                    )
                except Exception:
                    return False

            self._wait(
                "NIM readiness",
                self.plan["kubernetes"]["ready_timeout_seconds"],
                ready,
            )
            return PhaseResult("completed", "external port-forward observed semantic service ready")
        if phase == "inference":
            call = self._call_bundle(model)[0]
            payload = canonical_json(call["payload"]).encode("utf-8")
            call_started_ns = time.monotonic_ns()
            if (
                state["gpu_active_started_ns"] is None
                and self.plan["scenario_strategies"][request["scenario"]] == "none"
            ):
                state["gpu_active_started_ns"] = call_started_ns
            response = self._http(model["endpoint_path"], payload)
            response_received_ns = time.monotonic_ns()
            self._validate_response(model, call["payload"], response)
            validation_finished_ns = time.monotonic_ns()
            state["response"] = response
            state["validator"] = (model["validator_id"], model["validator_sha256"])
            state["semantic_calls"].append(
                {
                    "call": 1,
                    "input_id": call["input_id"],
                    "status": "PASS",
                    "request_started_monotonic_ns": call_started_ns,
                    "response_received_monotonic_ns": response_received_ns,
                    "validation_finished_monotonic_ns": validation_finished_ns,
                    "response_sha256": hashlib.sha256(response).hexdigest(),
                    "response_bytes": len(response),
                }
            )
            return PhaseResult("completed", "complete response passed pinned semantic validator")
        raise BaselineError(f"unsupported phase: {phase}")

    def terminal(
        self, request: dict[str, Any], failed: PhaseResult | None
    ) -> TerminalResult:
        state = self._attempt[request["attempt_id"]]
        if failed is not None:
            return TerminalResult(
                False,
                failure_class=(
                    "capacity" if request["scenario"] == "capacity_miss" else "backend"
                ),
                reason=failed.reason,
                retryable=True,
            )
        validator_id, validator_sha256 = state["validator"]
        return TerminalResult(
            True,
            response=state["response"],
            validator_id=validator_id,
            validator_sha256=validator_sha256,
        )

    def post_terminal(
        self, request: dict[str, Any], terminal: TerminalResult
    ) -> None:
        state = self._attempt[request["attempt_id"]]
        if not terminal.success:
            state["semantic_calls"].append(
                {"call": 2, "status": "NOT_RUN", "reason": terminal.reason}
            )
            self._record(
                "two_call_qualification",
                attempt_id=request["attempt_id"],
                calls=state["semantic_calls"],
                qualified=False,
            )
            return
        model = self._model(request)
        started_ns = time.monotonic_ns()
        call_id = "unresolved-second-call"
        try:
            call = self._call_bundle(model)[1]
            call_id = call["input_id"]
            response = self._http(
                model["endpoint_path"], canonical_json(call["payload"]).encode("utf-8")
            )
            received_ns = time.monotonic_ns()
            self._validate_response(model, call["payload"], response)
            finished_ns = time.monotonic_ns()
            state["semantic_calls"].append(
                {
                    "call": 2,
                    "input_id": call_id,
                    "status": "PASS",
                    "request_started_monotonic_ns": started_ns,
                    "response_received_monotonic_ns": received_ns,
                    "validation_finished_monotonic_ns": finished_ns,
                    "response_sha256": hashlib.sha256(response).hexdigest(),
                    "response_bytes": len(response),
                    "t0_to_call2_validation_seconds": round(
                        (finished_ns - state["t0_monotonic_ns"]) / 1_000_000_000, 9
                    ),
                }
            )
            state["two_call_qualified"] = True
        except Exception as exc:
            state["semantic_calls"].append(
                {
                    "call": 2,
                    "input_id": call_id,
                    "status": "FAIL",
                    "request_started_monotonic_ns": started_ns,
                    "reason": f"{type(exc).__name__}: {exc}"[:1000],
                }
            )
        self._close_gpu_active(state)
        self._record(
            "two_call_qualification",
            attempt_id=request["attempt_id"],
            calls=state["semantic_calls"],
            qualified=state["two_call_qualified"],
        )

    def accounting(
        self, request: dict[str, Any], elapsed_seconds: float, bytes_moved: int
    ) -> AccountingResult:
        state = self._attempt[request["attempt_id"]]
        strategy = self.plan["scenario_strategies"][request["scenario"]]
        if state.get("placement_submitted_ns") is not None and strategy != "none":
            try:
                self._capture_strategy_receipt(
                    request, self._model(request), require_complete=False
                )
            except Exception as exc:
                state["strategy_accounting_failure"] = f"{type(exc).__name__}: {exc}"[:1000]
        self._close_gpu_active(state)
        if state.get("strategy_accounting_failure"):
            raise BaselineError(
                "strategy GPU timing receipt unavailable after admitted Pod work: "
                + state["strategy_accounting_failure"]
            )
        if state.get("byte_accounting_failures"):
            raise BaselineError(
                "transfer byte progress receipt unavailable; conservative bytes cannot be "
                "promoted: " + canonical_json(state["byte_accounting_failures"])
            )
        now_ns = time.monotonic_ns()
        period_start_ns = self._last_billing_ns or state["worker_started_ns"] or now_ns
        billed = max(0.0, (now_ns - period_start_ns) / 1_000_000_000)
        self._last_billing_ns = now_ns
        active = min(float(state["gpu_active_seconds"]), billed)
        idle = max(0.0, billed - active)
        cost = billed * float(self.plan["cost"]["lease_hour_usd"]) / 3600
        cost += (
            bytes_moved / (1024**3) * float(self.plan["cost"]["transfer_usd_per_gib"])
        )
        if not self._setup_cost_charged:
            cost += float(self.plan["cost"]["pre_t0_setup_cost_usd"])
            self._setup_cost_charged = True
        return AccountingResult(round(cost, 9), active, idle, billed)

    def cleanup(self, request: dict[str, Any]) -> CleanupResult:
        state = self._attempt[request["attempt_id"]]
        self._stop_port_forward()
        deleted = list(state["deleted"])
        if request["scenario"] == "idle_local":
            deleted.extend(self._delete_active(request["attempt_id"] + "-rearm-idle"))
            self._gpu_scrub(
                {"attempt_id": request["attempt_id"] + "-rearm-idle"}
            )
        elif request["scenario"] == "a_to_b_remote":
            self._evict_model_cache_for_next_attempt(request)
        if self.plan["variant"] == "per_run_service":
            self.kube.delete("service", state["service_name"], 30)
            deleted.append(
                f"k8s:{self.plan['kubernetes']['namespace']}/service/{state['service_name']}"
            )
        owned = set(state["resource_ids"])
        retained = sorted(owned - set(deleted))
        receipt = {
            "attempt_id": request["attempt_id"],
            "deleted": sorted(deleted),
            "retained": retained,
            "active_occupant": self._active_occupant(),
        }
        receipt_sha = hashlib.sha256(canonical_json(receipt).encode()).hexdigest()
        state["cleanup_receipt"] = receipt
        state["cleanup_receipt_sha256"] = receipt_sha
        self._record(
            "attempt_cleanup", attempt_id=request["attempt_id"],
            receipt=receipt, receipt_sha256=receipt_sha,
        )
        return CleanupResult(
            True,
            "retained" if retained else "complete",
            tuple(sorted(deleted)),
            tuple(retained),
            receipt_sha,
            "per-run support removed; task lease and current occupant retained until cohort cleanup",
        )

    def final_cleanup(self) -> dict[str, Any]:
        self._stop_port_forward()
        if self._final_cleanup_receipt is not None:
            return self._final_cleanup_receipt
        if not self._prepared and not self._prepare_owned:
            final = {
                "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
                "status": "NOT_RUN",
                "reason": "backend preflight did not complete; no cohort mutation was admitted",
                "lease_state": self.lease["state"],
                "lease_cleanup_required": True,
                "partial_prepare_cleanup_failures": self._prepare_cleanup_failures,
            }
            self._record("final_cleanup", receipt=final)
            self._final_cleanup_receipt = final
            return final
        if not self._prepared:
            self._cleanup_partial_prepare()
            status = "WORKLOAD_PASS_BROKER_RELEASE_REQUIRED" if not self._prepare_owned else "FAIL"
            final = {
                "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
                "status": status,
                "reason": (
                    "partial prepare resources cleaned; broker lease release still required"
                    if status == "WORKLOAD_PASS_BROKER_RELEASE_REQUIRED"
                    else "partial prepare resources retained"
                ),
                "retained_prepare_resources": [f"{kind}/{name}" for kind, name in sorted(self._prepare_owned)],
                "partial_prepare_cleanup_failures": self._prepare_cleanup_failures,
                "lease_state": self.lease["state"],
                "lease_cleanup_required": True,
            }
            self._record("final_cleanup", receipt=final)
            self._final_cleanup_receipt = final
            return final
        self._delete_active("cohort-final-cleanup")
        if self.plan["variant"] == "precreated_service":
            self.kube.delete("service", "catalog-switch-endpoint", 30)
            self._prepare_owned.discard(("service", "catalog-switch-endpoint"))
        receipt = self._gpu_scrub(
            {
                "attempt_id": "cohort-final-cleanup",
            }
        )
        final = {
            "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
            "status": "WORKLOAD_PASS_BROKER_RELEASE_REQUIRED",
            "target_pod_count": len(self._pods()),
            "gpu_zero_receipt": receipt,
            "lease_state": self.lease["state"],
            "lease_cleanup_required": True,
            "final_resource_state": "BROKER_RESOURCES_RETAINED",
            "post_attempt_billing": self._post_attempt_billing(),
        }
        self._record("final_cleanup", receipt=final)
        self._final_cleanup_receipt = final
        return final

    def _post_attempt_billing(self) -> dict[str, Any]:
        now_ns = time.monotonic_ns()
        seconds = (
            max(0.0, (now_ns - self._last_billing_ns) / 1_000_000_000)
            if self._last_billing_ns is not None
            else 0.0
        )
        self._last_billing_ns = now_ns
        return {
            "billed_seconds": round(seconds, 9),
            "cost_usd": round(
                seconds * float(self.plan["cost"]["lease_hour_usd"]) / 3600, 9
            ),
            "requires_broker_actual_cost_reconciliation": True,
        }

    def write_evidence(self, path: Path) -> None:
        from .sealing import atomic_write_json

        qualification = self.qualification_summary()
        value = {
            "schema": "archvteams.nebius.ai/k8s-backend-evidence/v2",
            "classification": self.classification,
            "experiment_id": self.plan["experiment_id"],
            "variant": self.plan["variant"],
            "project_id": self.plan["project_id"],
            "region": self.plan["region"],
            "resource_prefix": self.plan["resource_lease"]["prefix"],
            "cost_contract": self.plan["cost"],
            "resource_lease_sha256": self.plan["resource_lease"]["sha256"],
            "threat_model_sha256": self.plan["security"]["threat_model"]["sha256"],
            "credential_receipt_sha256": self.plan["security"]["credentials"]["receipt_sha256"],
            "final_cleanup": self._final_cleanup_receipt,
            "events": self._events,
            "two_call_qualification": qualification,
            "two_call_qualification_sha256": hashlib.sha256(
                canonical_json(qualification).encode()
            ).hexdigest(),
        }
        atomic_write_json(path, value)

    def qualification_summary(self) -> dict[str, Any]:
        states = list(self._attempt.values())
        return {
            "required_semantic_calls": 2,
            "product_terminal_call": 1,
            "attempt_count": len(states),
            "qualified_count": sum(bool(item.get("two_call_qualified")) for item in states),
            "failed_or_incomplete_count": sum(
                not bool(item.get("two_call_qualified")) for item in states
            ),
            "cleanup_receipts": [
                {
                    "attempt_id": attempt_id,
                    "receipt": item["cleanup_receipt"],
                    "receipt_sha256": item["cleanup_receipt_sha256"],
                }
                for attempt_id, item in self._attempt.items()
                if "cleanup_receipt" in item
            ],
            "attempts": [
                {
                    "attempt_id": attempt_id,
                    "qualified": bool(item.get("two_call_qualified")),
                    "t0_to_call2_validation_seconds": (
                        item["semantic_calls"][1].get("t0_to_call2_validation_seconds")
                        if len(item.get("semantic_calls", [])) == 2 else None
                    ),
                    "failure_reason": (
                        None
                        if item.get("two_call_qualified")
                        else (
                            item["semantic_calls"][1].get("reason", "second semantic call incomplete")
                            if len(item.get("semantic_calls", [])) == 2
                            else "second semantic call not completed"
                        )
                    ),
                }
                for attempt_id, item in self._attempt.items()
            ],
        }
