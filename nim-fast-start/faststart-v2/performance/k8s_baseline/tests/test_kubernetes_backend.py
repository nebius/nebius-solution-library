from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from performance.k8s_baseline.contract import BaselineError
from performance.k8s_baseline.controller import TerminalResult
from performance.k8s_baseline.kubernetes_backend import KubernetesBackend


class KubernetesBackendTests(unittest.TestCase):
    def backend(self) -> KubernetesBackend:
        backend = object.__new__(KubernetesBackend)
        backend.plan = {
            "project_id": "project-e00z6b02t8ddk96c49",
            "region": "eu-north1",
            "kubernetes": {
                "node_name": "fresh-h100-node",
                "namespace": "mlsp-csw-k8s",
            },
            "cost": {
                "lease_hour_usd": 3.6,
                "transfer_usd_per_gib": 0.02,
                "pre_t0_setup_cost_usd": 0.5,
            },
        }
        backend.models = {
            ("model-a", "v1"): {
                "model_id": "model-a",
                "model_version": "v1",
                "artifact_sha256": "a" * 64,
                "image_digest": "registry.invalid/model-a@sha256:" + "b" * 64,
            }
        }
        backend._events = []
        backend._attempt = {
            "attempt-a": {
                "semantic_calls": [{"call": 1, "status": "PASS"}],
                "two_call_qualified": False,
                "gpu_active_started_ns": None,
                "gpu_active_seconds": 0.0,
                "worker_started_ns": None,
            }
        }
        backend._last_billing_ns = None
        backend._setup_cost_charged = False
        backend._active_occupant = Mock(return_value=None)
        backend.kube = Mock()
        backend.kube.get_json.return_value = {"spec": {"unschedulable": False}}
        return backend

    def request(self) -> dict:
        return {
            "attempt_id": "attempt-a",
            "target": {"model_id": "model-a", "model_version": "v1"},
            "precondition": {
                "current_node_occupant": None,
                "capacity": "allocated",
                "cache": {
                    "image": "local_verified",
                    "artifact": "node_local_hit",
                    "checkpoint": "compatible_hit",
                    "storage": "ready",
                },
            },
        }

    def test_cache_receipt_must_match_the_accepted_precondition(self) -> None:
        backend = self.backend()
        request = self.request()
        model = backend.models[("model-a", "v1")]
        receipt = {
            "schema": "archvteams.nebius.ai/cache-state-receipt/v1",
            "status": "PASS",
            "model_id": "model-a",
            "model_version": "v1",
            "artifact_sha256": model["artifact_sha256"],
            "image_digest": model["image_digest"],
            "cache": request["precondition"]["cache"],
            "evidence_sha256": "c" * 64,
        }
        backend._sentinel = Mock(return_value=json.dumps(receipt))
        backend._verify_trace_precondition(request)
        self.assertEqual(backend._events[-1]["operation"], "cache_precondition_verified")

        receipt["cache"] = {**receipt["cache"], "artifact": "remote_miss"}
        backend._sentinel = Mock(return_value=json.dumps(receipt))
        with self.assertRaisesRegex(BaselineError, "live cache state differs"):
            backend._verify_trace_precondition(request)

    def test_second_call_setup_failure_is_retained_not_raised(self) -> None:
        backend = self.backend()
        backend._call_bundle = Mock(side_effect=BaselineError("bundle unavailable"))
        backend.post_terminal(
            self.request(),
            TerminalResult(
                True,
                response=b"{}",
                validator_id="validator",
                validator_sha256="d" * 64,
            ),
        )
        call = backend._attempt["attempt-a"]["semantic_calls"][1]
        self.assertEqual(call["status"], "FAIL")
        self.assertEqual(call["input_id"], "unresolved-second-call")
        self.assertIn("bundle unavailable", call["reason"])
        self.assertFalse(backend._events[-1]["qualified"])

    def test_product_failure_retains_call_two_not_run(self) -> None:
        backend = self.backend()
        backend.post_terminal(
            self.request(),
            TerminalResult(False, failure_class="capacity", reason="capacity miss"),
        )
        call = backend._attempt["attempt-a"]["semantic_calls"][1]
        self.assertEqual(call["status"], "NOT_RUN")
        self.assertIn("capacity miss", call["reason"])
        self.assertFalse(backend._events[-1]["qualified"])

    def test_accounting_includes_idle_transfer_and_setup_cost(self) -> None:
        backend = self.backend()
        state = backend._attempt["attempt-a"]
        state["gpu_active_seconds"] = 1.0
        backend._last_billing_ns = 1_000_000_000
        with patch(
            "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
            return_value=5_000_000_000,
        ):
            result = backend.accounting(self.request(), 2.0, 1024**3)
        self.assertEqual(result.billed_seconds, 4.0)
        self.assertEqual(result.gpu_active_seconds, 1.0)
        self.assertEqual(result.gpu_idle_seconds, 3.0)
        self.assertEqual(result.cost_usd, 0.524)


if __name__ == "__main__":
    unittest.main()
