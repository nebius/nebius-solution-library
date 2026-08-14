#!/usr/bin/env python3
"""Keep one cache-preseeded NIM pod ready and promote it on scale-out."""

from __future__ import annotations

import copy
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_LABEL = "nim-fast-start.nebius.com/state"
MANAGED_LABEL = "nim-fast-start.nebius.com/managed"
TERMINAL_PHASES = {"Failed", "Succeeded"}


def log(event: str, **fields: Any) -> None:
    fields["event"] = event
    fields["time"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(fields, sort_keys=True), flush=True)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    namespace: str
    node_selector: str
    threshold: float
    scale_down_threshold: float
    reserve_replicas: int
    gpu_resource: str
    template_configmap: str
    demand_configmap: str
    poll_seconds: float
    cold_fallback: bool
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            namespace=os.getenv("NAMESPACE", "nim-fast-start"),
            node_selector=os.getenv("NODE_SELECTOR", "nvidia.com/gpu.present=true"),
            threshold=float(os.getenv("UTILIZATION_THRESHOLD", "0.8")),
            scale_down_threshold=float(os.getenv("SCALE_DOWN_THRESHOLD", "0.5")),
            reserve_replicas=int(os.getenv("RESERVE_REPLICAS", "1")),
            gpu_resource=os.getenv("GPU_RESOURCE", "nvidia.com/gpu"),
            template_configmap=os.getenv("TEMPLATE_CONFIGMAP", "nim-prewarm-template"),
            demand_configmap=os.getenv("DEMAND_CONFIGMAP", "nim-prewarm-demand"),
            poll_seconds=float(os.getenv("POLL_SECONDS", "15")),
            cold_fallback=env_bool("COLD_FALLBACK", True),
            dry_run=env_bool("DRY_RUN", False),
        )
        if not 0 <= settings.scale_down_threshold <= settings.threshold <= 1:
            raise ValueError("require 0 <= SCALE_DOWN_THRESHOLD <= UTILIZATION_THRESHOLD <= 1")
        if settings.reserve_replicas < 0 or settings.poll_seconds <= 0:
            raise ValueError("RESERVE_REPLICAS must be non-negative and POLL_SECONDS positive")
        return settings


class ApiError(RuntimeError):
    pass


class KubernetesClient:
    def __init__(self) -> None:
        host = os.getenv("KUBERNETES_SERVICE_HOST")
        port = os.getenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST is not set")
        service_account = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.base_url = f"https://{host}:{port}"
        self.token = (service_account / "token").read_text().strip()
        self.context = ssl.create_default_context(cafile=str(service_account / "ca.crt"))

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=20) as response:
                payload = response.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise ApiError(f"{method} {path}: HTTP {error.code}: {detail}") from error

    @staticmethod
    def query(path: str, **params: str) -> str:
        values = {key: value for key, value in params.items() if value}
        return f"{path}?{urllib.parse.urlencode(values)}" if values else path

    def list_nodes(self, selector: str) -> list[dict[str, Any]]:
        path = self.query("/api/v1/nodes", labelSelector=selector)
        return self.request("GET", path).get("items", [])

    def list_pods(self) -> list[dict[str, Any]]:
        return self.request("GET", "/api/v1/pods").get("items", [])

    def get_configmap(self, namespace: str, name: str) -> dict[str, Any]:
        path = f"/api/v1/namespaces/{quote(namespace)}/configmaps/{quote(name)}"
        return self.request("GET", path)

    def create_pod(self, namespace: str, pod: dict[str, Any]) -> dict[str, Any]:
        path = f"/api/v1/namespaces/{quote(namespace)}/pods"
        return self.request("POST", path, pod)

    def patch_pod(self, namespace: str, name: str, patch: dict[str, Any]) -> dict[str, Any]:
        path = f"/api/v1/namespaces/{quote(namespace)}/pods/{quote(name)}"
        return self.request("PATCH", path, patch, "application/merge-patch+json")

    def delete_pod(self, namespace: str, name: str) -> dict[str, Any]:
        path = f"/api/v1/namespaces/{quote(namespace)}/pods/{quote(name)}"
        return self.request("DELETE", path, {"gracePeriodSeconds": 0})


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def quantity(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"GPU quantities must be whole numbers, got {value!r}") from error


def pod_resource_request(pod: dict[str, Any], resource: str) -> int:
    spec = pod.get("spec", {})
    regular = sum(
        quantity(container.get("resources", {}).get("requests", {}).get(resource))
        for container in spec.get("containers", [])
    )
    init = max(
        (
            quantity(container.get("resources", {}).get("requests", {}).get(resource))
            for container in spec.get("initContainers", [])
        ),
        default=0,
    )
    overhead = quantity(spec.get("overhead", {}).get(resource))
    return max(regular, init) + overhead


def node_ready(node: dict[str, Any]) -> bool:
    if node.get("spec", {}).get("unschedulable"):
        return False
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in node.get("status", {}).get("conditions", [])
    )


def pod_ready(pod: dict[str, Any]) -> bool:
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
    )


def pod_state(pod: dict[str, Any]) -> str:
    return pod.get("metadata", {}).get("labels", {}).get(STATE_LABEL, "")


def nonterminal(pod: dict[str, Any]) -> bool:
    return pod.get("status", {}).get("phase") not in TERMINAL_PHASES


class Controller:
    def __init__(self, client: Any, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def load_template(self) -> dict[str, Any]:
        configmap = self.client.get_configmap(
            self.settings.namespace, self.settings.template_configmap
        )
        raw = configmap.get("data", {}).get("pod-template.json")
        if not raw:
            raise ValueError("template ConfigMap must contain data['pod-template.json']")
        template = json.loads(raw)
        if template.get("kind") != "Pod" or template.get("apiVersion") != "v1":
            raise ValueError("pod-template.json must contain a v1 Pod")
        if pod_resource_request(template, self.settings.gpu_resource) < 1:
            raise ValueError(f"pod template must request {self.settings.gpu_resource}")
        return template

    def desired_active(self) -> int:
        configmap = self.client.get_configmap(
            self.settings.namespace, self.settings.demand_configmap
        )
        raw = configmap.get("data", {}).get("desired-active", "0")
        desired = int(raw)
        if desired < 0:
            raise ValueError("desired-active must be non-negative")
        return desired

    def pod_from_template(self, template: dict[str, Any], state: str) -> dict[str, Any]:
        pod = copy.deepcopy(template)
        metadata = pod.setdefault("metadata", {})
        for field in ("creationTimestamp", "name", "namespace", "resourceVersion", "uid"):
            metadata.pop(field, None)
        metadata.setdefault("generateName", "nim-prewarm-")
        labels = metadata.setdefault("labels", {})
        labels[MANAGED_LABEL] = "true"
        labels[STATE_LABEL] = state
        annotations = metadata.setdefault("annotations", {})
        annotations["nim-fast-start.nebius.com/created-at"] = datetime.now(
            timezone.utc
        ).isoformat()
        pod.pop("status", None)
        return pod

    def create(self, template: dict[str, Any], state: str) -> None:
        pod = self.pod_from_template(template, state)
        if self.settings.dry_run:
            log("create_dry_run", state=state, pod=pod)
            return
        created = self.client.create_pod(self.settings.namespace, pod)
        log("pod_created", name=created.get("metadata", {}).get("name"), state=state)

    def promote(self, pod: dict[str, Any]) -> None:
        name = pod["metadata"]["name"]
        patch = {
            "metadata": {
                "labels": {STATE_LABEL: "active"},
                "annotations": {
                    "nim-fast-start.nebius.com/promoted-at": datetime.now(
                        timezone.utc
                    ).isoformat()
                },
            }
        }
        if self.settings.dry_run:
            log("promote_dry_run", name=name)
            return
        self.client.patch_pod(self.settings.namespace, name, patch)
        log("reserve_promoted", name=name)

    def delete(self, pod: dict[str, Any]) -> None:
        name = pod["metadata"]["name"]
        if self.settings.dry_run:
            log("delete_dry_run", name=name)
            return
        self.client.delete_pod(self.settings.namespace, name)
        log("reserve_deleted", name=name)

    def reconcile_once(self) -> dict[str, Any]:
        template = self.load_template()
        template_slots = pod_resource_request(template, self.settings.gpu_resource)
        nodes = [node for node in self.client.list_nodes(self.settings.node_selector) if node_ready(node)]
        pool_names = {node["metadata"]["name"] for node in nodes}
        total_slots = sum(
            quantity(node.get("status", {}).get("allocatable", {}).get(self.settings.gpu_resource))
            for node in nodes
        )
        if total_slots == 0:
            raise RuntimeError("selected node pool has no allocatable GPU slots")

        pods = [pod for pod in self.client.list_pods() if nonterminal(pod)]
        allocated_slots = 0
        signal_slots = 0
        for pod in pods:
            if pod.get("spec", {}).get("nodeName") not in pool_names:
                continue
            slots = pod_resource_request(pod, self.settings.gpu_resource)
            allocated_slots += slots
            if pod_state(pod) != "reserve":
                signal_slots += slots

        managed = [
            pod
            for pod in pods
            if pod.get("metadata", {}).get("namespace") == self.settings.namespace
            and pod.get("metadata", {}).get("labels", {}).get(MANAGED_LABEL) == "true"
        ]
        active = [pod for pod in managed if pod_state(pod) == "active"]
        reserves = [pod for pod in managed if pod_state(pod) == "reserve"]
        desired = self.desired_active()

        deficit = max(0, desired - len(active))
        ready_reserves = [pod for pod in reserves if pod_ready(pod)]
        promoted = ready_reserves[:deficit]
        for pod in promoted:
            self.promote(pod)
        reserves = [pod for pod in reserves if pod not in promoted]
        deficit -= len(promoted)
        signal_slots += len(promoted) * template_slots

        if deficit and self.settings.cold_fallback:
            for _ in range(deficit):
                self.create(template, "active")
            log("cold_fallback", replicas=deficit)

        utilization = signal_slots / total_slots
        reserve_count = len(reserves)
        if utilization >= self.settings.threshold:
            missing = max(0, self.settings.reserve_replicas - len(reserves))
            free_slots = max(0, total_slots - allocated_slots)
            creatable = min(missing, free_slots // template_slots)
            for _ in range(creatable):
                self.create(template, "reserve")
            reserve_count += creatable
            if missing > creatable:
                log(
                    "reserve_capacity_unavailable",
                    requested=missing,
                    creatable=creatable,
                    free_slots=free_slots,
                )
        elif utilization <= self.settings.scale_down_threshold:
            for pod in reserves:
                self.delete(pod)
            reserve_count = 0

        result = {
            "active": len(active) + len(promoted) + (deficit if self.settings.cold_fallback else 0),
            "allocated_slots": allocated_slots,
            "desired_active": desired,
            "reserve": reserve_count,
            "signal_slots": signal_slots,
            "total_slots": total_slots,
            "utilization": round(utilization, 4),
        }
        log("reconciled", **result)
        return result

    def run(self) -> None:
        log(
            "controller_started",
            namespace=self.settings.namespace,
            node_selector=self.settings.node_selector,
            threshold=self.settings.threshold,
        )
        while True:
            try:
                self.reconcile_once()
            except Exception as error:  # keep the controller alive after transient API failures
                log("reconcile_failed", error=str(error), error_type=type(error).__name__)
            time.sleep(self.settings.poll_seconds)


def main() -> None:
    settings = Settings.from_env()
    Controller(KubernetesClient(), settings).run()


if __name__ == "__main__":
    main()
