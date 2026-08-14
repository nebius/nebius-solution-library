import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "controller.py"
SPEC = importlib.util.spec_from_file_location("prewarm_controller", MODULE_PATH)
controller = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


def node(name="gpu-1", slots=10):
    return {
        "metadata": {"name": name},
        "spec": {},
        "status": {
            "allocatable": {"nvidia.com/gpu": str(slots)},
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }


def pod(name, state="active", ready=True, namespace="nim-fast-start", node_name="gpu-1"):
    labels = {
        controller.MANAGED_LABEL: "true",
        controller.STATE_LABEL: state,
    }
    return {
        "metadata": {"name": name, "namespace": namespace, "labels": labels},
        "spec": {
            "nodeName": node_name,
            "containers": [
                {"resources": {"requests": {"nvidia.com/gpu": "1"}}}
            ],
        },
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def template():
    value = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "source", "labels": {"app": "nim"}},
        "spec": {
            "containers": [
                {"name": "nim", "resources": {"requests": {"nvidia.com/gpu": "1"}}}
            ]
        },
        "status": {"phase": "Running"},
    }
    return {"data": {"pod-template.json": json.dumps(value)}}


class FakeClient:
    def __init__(self, pods=None, desired=0):
        self.nodes = [node()]
        self.pods = pods or []
        self.desired = desired
        self.created = []
        self.patched = []
        self.deleted = []

    def get_configmap(self, namespace, name):
        if name == "template":
            return template()
        return {"data": {"desired-active": str(self.desired)}}

    def list_nodes(self, selector):
        return self.nodes

    def list_pods(self):
        return copy.deepcopy(self.pods)

    def create_pod(self, namespace, body):
        body = copy.deepcopy(body)
        body.setdefault("metadata", {})["name"] = f"created-{len(self.created) + 1}"
        body["metadata"]["namespace"] = namespace
        self.created.append(body)
        return body

    def patch_pod(self, namespace, name, patch):
        self.patched.append((namespace, name, patch))
        return {}

    def delete_pod(self, namespace, name):
        self.deleted.append((namespace, name))
        return {}


def settings(**overrides):
    values = {
        "namespace": "nim-fast-start",
        "node_selector": "pool=test",
        "threshold": 0.8,
        "scale_down_threshold": 0.5,
        "reserve_replicas": 1,
        "gpu_resource": "nvidia.com/gpu",
        "template_configmap": "template",
        "demand_configmap": "demand",
        "poll_seconds": 1,
        "cold_fallback": True,
        "dry_run": False,
    }
    values.update(overrides)
    return controller.Settings(**values)


class ControllerTests(unittest.TestCase):
    def test_creates_reserve_at_threshold(self):
        client = FakeClient([pod(f"active-{index}") for index in range(8)], desired=8)
        result = controller.Controller(client, settings()).reconcile_once()

        self.assertEqual(result["utilization"], 0.8)
        self.assertEqual(result["reserve"], 1)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(
            client.created[0]["metadata"]["labels"][controller.STATE_LABEL], "reserve"
        )

    def test_promotes_ready_reserve_before_cold_fallback(self):
        pods = [pod(f"active-{index}") for index in range(8)] + [pod("reserve", "reserve")]
        client = FakeClient(pods, desired=9)
        controller.Controller(client, settings()).reconcile_once()

        self.assertEqual(client.patched[0][1], "reserve")
        self.assertEqual(
            client.patched[0][2]["metadata"]["labels"][controller.STATE_LABEL], "active"
        )
        self.assertFalse(any(p["metadata"]["labels"][controller.STATE_LABEL] == "active" for p in client.created))

    def test_creates_active_pod_when_no_reserve_is_ready(self):
        client = FakeClient([], desired=1)
        controller.Controller(client, settings()).reconcile_once()

        self.assertEqual(len(client.created), 1)
        self.assertEqual(
            client.created[0]["metadata"]["labels"][controller.STATE_LABEL], "active"
        )

    def test_deletes_reserve_below_scale_down_threshold(self):
        client = FakeClient([pod("reserve", "reserve")])
        result = controller.Controller(client, settings()).reconcile_once()

        self.assertEqual(client.deleted, [("nim-fast-start", "reserve")])
        self.assertEqual(result["reserve"], 0)

    def test_uses_scheduler_semantics_for_init_container_requests(self):
        value = {
            "spec": {
                "initContainers": [
                    {"resources": {"requests": {"nvidia.com/gpu": "2"}}}
                ],
                "containers": [
                    {"resources": {"requests": {"nvidia.com/gpu": "1"}}},
                    {"resources": {"requests": {"nvidia.com/gpu": "1"}}},
                ],
                "overhead": {"nvidia.com/gpu": "1"},
            }
        }
        self.assertEqual(controller.pod_resource_request(value, "nvidia.com/gpu"), 3)

    def test_template_is_sanitized(self):
        client = FakeClient()
        instance = controller.Controller(client, settings())
        value = json.loads(template()["data"]["pod-template.json"])
        rendered = instance.pod_from_template(value, "reserve")

        self.assertNotIn("name", rendered["metadata"])
        self.assertNotIn("status", rendered)
        self.assertEqual(rendered["metadata"]["labels"][controller.MANAGED_LABEL], "true")


if __name__ == "__main__":
    unittest.main()
