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

from .contract import BaselineError
from .controller import (
    AccountingResult,
    CleanupResult,
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
        self.requires_durable_t0_before_accepted_hook = (
            plan["campaign_arm"] == "B_new_preemptible_node"
        )
        kube = plan["kubernetes"]
        self.kube = Kubectl(
            Path(plan["_resolved"]["kubeconfig"]), kube["context"], kube["namespace"]
        )
        self.models = {
            (item["model_id"], item["model_version"]): item for item in plan["models"]
        }
        self.lease = json.loads(Path(plan["_resolved"]["lease_path"]).read_text())
        self._attempt: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._active_pod: str | None = None
        self._port_forward: subprocess.Popen[str] | None = None
        self._port: int | None = None
        self._prepared = False
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
        return value.get("items", [])

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
        labels = pod.get("metadata", {}).get("labels", {})
        model_id = labels.get("mlsp.nebius.ai/model-id")
        model_version = labels.get("mlsp.nebius.ai/model-version")
        if not model_id or not model_version:
            raise BaselineError("active target Pod lacks immutable model identity labels")
        self._active_pod = pod["metadata"]["name"]
        return {"model_id": model_id, "model_version": model_version}

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
        labels = namespace.get("metadata", {}).get("labels", {})
        if labels.get("mlsp.nebius.ai/resource-prefix") != self.plan["resource_lease"]["prefix"]:
            raise BaselineError("namespace is not owned by this broker lease")
        node = self.kube.get_json(
            "node", self.plan["kubernetes"]["node_name"], namespace=False
        )
        ready = any(
            item.get("type") == "Ready" and item.get("status") == "True"
            for item in node.get("status", {}).get("conditions", [])
        )
        allocatable = int(node.get("status", {}).get("allocatable", {}).get("nvidia.com/gpu", 0))
        product = node.get("metadata", {}).get("labels", {}).get("nvidia.com/gpu.product", "")
        if not ready or allocatable != 1 or "H100" not in product.upper():
            raise BaselineError("node is not the admitted Ready single-H100 target")
        sentinel = self.kube.get_json("pod", self.plan["kubernetes"]["sentinel_pod"])
        if sentinel.get("spec", {}).get("nodeName") != self.plan["kubernetes"]["node_name"]:
            raise BaselineError("GPU sentinel is not bound to the admitted node")
        if self.plan["variant"] == "precreated_service":
            # This object is target-neutral: no model, request, attempt, or switch UID.
            self.kube.apply(self._generic_service("catalog-switch-endpoint"))
        self._active_occupant()
        self._record(
            "prepare",
            target_specific=False,
            server=server,
            node=self.plan["kubernetes"]["node_name"],
            variant=self.plan["variant"],
        )
        self._prepared = True

    def environment(self, request: dict[str, Any]) -> dict[str, Any]:
        model = self._model(request)
        return {
            "backend": self.plan["backend"],
            "backend_version": self.plan["backend_version"],
            "provider": "nebius",
            "project_id": self.plan["project_id"],
            "region": self.plan["region"],
            "node_id": self.plan["kubernetes"]["node_name"],
            "gpu_type": self.plan["kubernetes"]["gpu_type"],
            "gpu_count": self.plan["kubernetes"]["gpu_count"],
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
            "gpu_active_seconds": 0.0,
            "response": None,
            "validator": None,
            "semantic_calls": [],
            "two_call_qualified": False,
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
                return "same digest already serves on the exclusive H100"
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
            "artifact_sha256",
            "image_digest",
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
            or receipt["artifact_sha256"] != model["artifact_sha256"]
            or receipt["image_digest"] != model["image_digest"]
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
            name = item.get("metadata", {}).get("name")
            uid = item.get("metadata", {}).get("uid")
            if name:
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
            "bytes_scrubbed",
            "compute_process_count",
            "baseline_memory_bytes",
            "observed_memory_bytes",
            "status",
        }
        if set(receipt) != required:
            raise BaselineError("GPU scrub receipt has the wrong shape")
        if (
            receipt["schema"] != "archvteams.nebius.ai/gpu-zero-receipt/v1"
            or receipt["switch_uid"] != request["attempt_id"]
            or receipt["method"] not in {"full-vram-zero", "gpu-reset"}
            or receipt["bytes_scrubbed"] <= 0
            or receipt["compute_process_count"] != 0
            or receipt["observed_memory_bytes"] != receipt["baseline_memory_bytes"]
            or receipt["status"] != "PASS"
        ):
            raise BaselineError("GPU scrub/zero proof failed; node must be quarantined")
        self._record("gpu_zero", attempt_id=request["attempt_id"], receipt=receipt)
        return receipt

    def _render_target(self, request: dict[str, Any]) -> str:
        model = self._model(request)
        state = self._attempt[request["attempt_id"]]
        strategy = self.plan["scenario_strategies"][request["scenario"]]
        template_key = f"{strategy}_template"
        if template_key not in model["_paths"]:
            raise BaselineError(f"no target template for strategy {strategy}")
        text = Path(model["_paths"][template_key]).read_text(encoding="utf-8")
        tokens = {
            "@@NAMESPACE@@": self.plan["kubernetes"]["namespace"],
            "@@POD_NAME@@": state["pod_name"],
            "@@NODE_NAME@@": self.plan["kubernetes"]["node_name"],
            "@@SWITCH_UID@@": request["attempt_id"],
            "@@MODEL_ID@@": model["model_id"],
            "@@MODEL_VERSION@@": model["model_version"],
            "@@IMAGE_DIGEST@@": model["image_digest"],
            "@@CONTAINER_NAME@@": model["container_name"],
        }
        for token, replacement in tokens.items():
            text = text.replace(token, replacement)
        if "@@" in text:
            raise BaselineError("target manifest contains an unresolved template token")
        return text

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
        try:
            value = json.loads(Path(model["_paths"]["request_file"]).read_text())
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
        bundle_path = Path(model["_paths"]["request_file"])
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
        module = _load_module(path, "catalog_switch_validator_" + model["model_id"])
        if model["model_id"] == "proteinmpnn":
            module._validate_response(value, int(payload["random_seed"]))
        elif model["model_id"] == "boltz2":
            polymer = payload["polymers"][0]
            module.validate_response(value, polymer["sequence"], polymer["id"])
        elif model["model_id"] == "openfold2":
            module.validate_response(value, payload["input_id"], payload["sequence"])
        else:
            raise BaselineError("no audited semantic validator adapter for selected model")

    def run_phase(self, request: dict[str, Any], phase: str) -> PhaseResult:
        state = self._attempt[request["attempt_id"]]
        model = self._model(request)
        if phase == "catalog_selection":
            self._verify_trace_precondition(request)
            return PhaseResult("completed", "catalog identity and live precondition matched")
        if phase == "queue":
            state["worker_started_ns"] = time.monotonic_ns()
            return PhaseResult("completed", "exclusive H100 worker dequeued attempt")
        if phase == "drain":
            self._delete_active(request["attempt_id"])
            return PhaseResult("completed", "prior target Pod UID deleted within drain deadline")
        if phase == "gpu_release":
            receipt = self._gpu_scrub(request)
            return PhaseResult(
                "completed",
                f"{receipt['method']} scrubbed {receipt['bytes_scrubbed']} bytes with zero processes",
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
                return PhaseResult("failed", "task-owned H100 node is cordoned/unavailable")
            if request["scenario"] != "same_model_hot":
                manifest = self._render_target(request)
                self.kube.run(
                    ["apply", "--dry-run=client", "-f", "-"], stdin=manifest, timeout=60
                )
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
            if terminated.get("exitCode") != 0:
                raise BaselineError(f"{gate_name} did not complete successfully")
            try:
                gate = json.loads(terminated.get("message", ""))
            except json.JSONDecodeError as exc:
                raise BaselineError(f"{gate_name} termination receipt is invalid") from exc
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
            return PhaseResult("completed", f"{phase} attestation is verified", moved)
        if phase == "runtime_launch":
            state["gpu_active_started_ns"] = time.monotonic_ns()

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
            return PhaseResult("completed", "model container entered Running with exact digest")
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
            if state["gpu_active_started_ns"] is None:
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
            if state["gpu_active_started_ns"] is not None:
                state["gpu_active_seconds"] = (
                    time.monotonic_ns() - state["gpu_active_started_ns"]
                ) / 1_000_000_000
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
                    "t0_to_call2_response_seconds": round(
                        (received_ns - state["t0_monotonic_ns"]) / 1_000_000_000, 9
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
        if state["gpu_active_started_ns"] is not None:
            state["gpu_active_seconds"] = (
                time.monotonic_ns() - state["gpu_active_started_ns"]
            ) / 1_000_000_000
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
        if not self._prepared:
            return {
                "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
                "status": "NOT_RUN",
                "reason": "backend preflight did not complete; no cohort mutation was admitted",
                "lease_state": self.lease["state"],
                "lease_cleanup_required": True,
            }
        self._delete_active("cohort-final-cleanup")
        if self.plan["variant"] == "precreated_service":
            self.kube.delete("service", "catalog-switch-endpoint", 30)
        receipt = self._gpu_scrub(
            {
                "attempt_id": "cohort-final-cleanup",
            }
        )
        final = {
            "schema": "archvteams.nebius.ai/k8s-cohort-cleanup/v1",
            "status": "PASS",
            "target_pod_count": len(self._pods()),
            "gpu_zero_receipt": receipt,
            "lease_state": self.lease["state"],
            "lease_cleanup_required": True,
            "post_attempt_billing": self._post_attempt_billing(),
        }
        self._record("final_cleanup", receipt=final)
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
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "schema": "archvteams.nebius.ai/k8s-backend-evidence/v1",
            "classification": self.classification,
            "experiment_id": self.plan["experiment_id"],
            "variant": self.plan["variant"],
            "project_id": self.plan["project_id"],
            "region": self.plan["region"],
            "resource_prefix": self.plan["resource_lease"]["prefix"],
            "cost_contract": self.plan["cost"],
            "events": self._events,
            "two_call_qualification": self.qualification_summary(),
        }
        path.write_text(canonical_json(value) + "\n", encoding="utf-8")

    def qualification_summary(self) -> dict[str, Any]:
        states = list(self._attempt.values())
        values = [
            item["semantic_calls"][1].get("t0_to_call2_response_seconds")
            for item in states
            if item.get("two_call_qualified") and len(item["semantic_calls"]) == 2
        ]
        return {
            "required_semantic_calls": 2,
            "product_terminal_call": 1,
            "attempt_count": len(states),
            "qualified_count": sum(bool(item.get("two_call_qualified")) for item in states),
            "failed_or_incomplete_count": sum(
                not bool(item.get("two_call_qualified")) for item in states
            ),
            "t0_to_call2_response_seconds_raw": values,
        }
