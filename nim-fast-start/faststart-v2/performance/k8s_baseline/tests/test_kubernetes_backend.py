from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from performance.k8s_baseline.contract import BaselineError
from performance.k8s_baseline.controller import PhaseExecutionError, TerminalResult
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
                "cluster_version": "v1.31.8",
                "node_uid": "node-uid-1",
                "broker_node_id": "computeinstance-node-1",
                "broker_node_group_id": "mk8snodegroup-test",
                "namespace_resource_id": "namespace-test",
                "namespace_uid": "namespace-uid-1",
                "service_account_resource_id": "serviceaccount-test",
                "service_account_uid": "serviceaccount-uid-1",
                "gpu_profile": "h100-single",
                "preemptible": True,
                "sentinel_pod": "gpu-sentinel",
            },
            "gpu_profiles": {
                "h100-single": {
                    "product": "NVIDIA-H100-80GB-HBM3", "gpu_count": 1,
                }
            },
            "task_id": "catalog-switch-k8s-baseline",
            "scenario_strategies": {
                "a_to_b_local": "conventional", "same_model_hot": "none",
            },
            "resource_lease": {"lease_id": "lease-1", "prefix": "mlsp-csw-test", "sha256": "a" * 64},
            "security": {
                "workload_service_account": "catalog-switch-runtime",
                "credentials": {
                    "secret_name": "ngc-task-owned", "secret_uid": "secret-uid-1",
                    "scope_sha256": "c" * 64, "receipt_sha256": "d" * 64,
                    "scope_manifest_sha256": "8" * 64,
                    "expires_at_utc": "2026-08-20T00:00:00Z", "revoke_by_utc": "2026-08-20T01:00:00Z",
                },
                "support_images": {
                    "sentinel_digest": "example.invalid/sentinel@sha256:" + "e" * 64,
                    "readiness_gate_digest": "example.invalid/gate@sha256:" + "f" * 64,
                },
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
                "version_label": "v1",
                "artifact_id": "artifact-a",
                "artifact_version": "v1",
                "artifact_sha256": "a" * 64,
                "image_digest": "registry.invalid/model-a@sha256:" + "b" * 64,
                "gpu_profile": "h100-single",
                "endpoint_path": "/predict",
                "container_name": "model-a",
                "artifact_bytes": 1024,
                "image_bytes": 2048,
                "validator_adapter": "boltz2-v1",
                "checkpoint": {
                    "checkpoint_id": "model-a-checkpoint", "checkpoint_sha256": "c" * 64,
                    "checkpoint_bytes": 4096,
                },
            }
        }
        backend._events = []
        backend._attempt = {
            "attempt-a": {
                "semantic_calls": [{"call": 1, "status": "PASS"}],
                "two_call_qualified": False,
                "gpu_active_started_ns": None,
                "gpu_active_closed_ns": None,
                "gpu_active_seconds": 0.0,
                "placement_submitted_ns": None,
                "strategy_receipt": None,
                "strategy_active_elapsed_ns": None,
                "strategy_accounting_failure": None,
                "byte_accounting_failures": {},
                "phase_bytes": {},
                "worker_started_ns": None,
                "t0_monotonic_ns": 500_000_000,
                "cohort": {},
            }
        }
        backend._last_billing_ns = None
        backend._setup_cost_charged = False
        backend._prepared = False
        backend._prepare_owned = set()
        backend._prepare_cleanup_failures = []
        backend._final_cleanup_receipt = None
        backend._port_forward = None
        backend._port = None
        backend.lease = {
            "state": "PLANNED", "node_ids": ["computeinstance-node-1"],
            "initial_state_receipt": {
                "schema": "archvteams.nebius.ai/k8s-initial-state/v2",
                "node_id": "computeinstance-node-1", "node_uid": "node-uid-1",
                "broker_node_id": "computeinstance-node-1", "occupant": None,
                "cache": {
                    "image": "local_verified", "artifact": "node_local_hit",
                    "checkpoint": "compatible_hit", "storage": "ready",
                },
                "cache_targets": [{
                    "model_id": "model-a", "model_version": "v1",
                    "artifact_id": "artifact-a", "artifact_version": "v1",
                    "artifact_sha256": "a" * 64, "artifact_bytes": 1024,
                    "image_digest": "registry.invalid/model-a@sha256:" + "b" * 64,
                    "image_bytes": 2048,
                    "checkpoint": {
                        "checkpoint_id": "model-a-checkpoint",
                        "checkpoint_sha256": "c" * 64, "checkpoint_bytes": 4096,
                    },
                }],
                "observed_at_utc": "2026-08-19T00:00:00Z",
                "evidence_path": "/tmp/initial.json", "evidence_sha256": "9" * 64,
            },
        }
        backend._active_occupant = Mock(return_value=None)
        backend.kube = Mock()
        backend.kube.get_json.return_value = {"spec": {"unschedulable": False}}
        return backend

    def request(self) -> dict:
        return {
            "attempt_id": "attempt-a",
            "scenario": "a_to_b_local",
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
            "artifact_id": model["artifact_id"],
            "artifact_version": model["artifact_version"],
            "artifact_sha256": model["artifact_sha256"],
            "artifact_bytes": model["artifact_bytes"],
            "image_digest": model["image_digest"],
            "image_bytes": model["image_bytes"],
            "checkpoint": model["checkpoint"],
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

    def test_environment_uses_exact_admitted_gpu_profile(self) -> None:
        backend = self.backend()
        backend.plan.update(
            {
                "backend": "kubernetes", "backend_version": "v1.31.8",
                "code_revision": "0" * 40, "experiment_id": "test",
                "_resolved": {"config_sha256": "1" * 64},
            }
        )
        value = backend.environment(self.request())
        self.assertEqual(value["gpu_type"], "NVIDIA-H100-80GB-HBM3")
        self.assertEqual(value["gpu_count"], 1)

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

    def test_second_call_duration_ends_after_semantic_validation(self) -> None:
        backend = self.backend()
        state = backend._attempt["attempt-a"]
        state["t0_monotonic_ns"] = 1_000_000_000
        backend._call_bundle = Mock(
            return_value=[
                {"input_id": "one", "payload": {}},
                {"input_id": "two", "payload": {}},
            ]
        )
        backend._http = Mock(return_value=b"{}")
        backend._validate_response = Mock()
        with patch(
            "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
            side_effect=[2_000_000_000, 3_000_000_000, 4_000_000_000, 5_000_000_000],
        ):
            backend.post_terminal(
                self.request(),
                TerminalResult(True, b"{}", "validator", "f" * 64),
            )
        call = state["semantic_calls"][1]
        self.assertEqual(call["response_received_monotonic_ns"], 3_000_000_000)
        self.assertEqual(call["validation_finished_monotonic_ns"], 4_000_000_000)
        self.assertEqual(call["t0_to_call2_validation_seconds"], 3.0)

    def test_active_occupant_uses_safe_label_and_full_digest_annotations(self) -> None:
        backend = self.backend()
        del backend._active_occupant
        model = backend.models[("model-a", "v1")]
        pod = {
            "metadata": {
                "name": "target", "labels": {
                    "mlsp.nebius.ai/role": "catalog-switch-target",
                    "mlsp.nebius.ai/task": "catalog-switch-k8s-baseline",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                    "mlsp.nebius.ai/model-id": "model-a",
                    "mlsp.nebius.ai/model-version-id": "v1",
                },
                "annotations": {
                    "mlsp.nebius.ai/model-version-full": "v1",
                    "mlsp.nebius.ai/artifact-id": model["artifact_id"],
                    "mlsp.nebius.ai/artifact-version": model["artifact_version"],
                    "mlsp.nebius.ai/artifact-sha256": model["artifact_sha256"],
                    "mlsp.nebius.ai/image-digest": model["image_digest"],
                    "mlsp.nebius.ai/strategy": "conventional",
                },
            },
            "spec": {
                "nodeName": "fresh-h100-node",
                "serviceAccountName": "catalog-switch-runtime",
                "containers": [{"name": "model-a", "image": model["image_digest"]}],
            },
            "status": {
                "phase": "Running",
                "containerStatuses": [{
                    "name": "model-a",
                    "imageID": "containerd://" + model["image_digest"].split("@", 1)[1],
                }],
            },
        }
        backend._pods = Mock(return_value=[pod])
        self.assertEqual(backend._active_occupant(), {"model_id": "model-a", "model_version": "v1"})
        pod["metadata"]["annotations"]["mlsp.nebius.ai/model-version-full"] = "forged"
        with self.assertRaisesRegex(BaselineError, "annotation receipt"):
            backend._active_occupant()
        pod["metadata"]["annotations"]["mlsp.nebius.ai/model-version-full"] = "v1"
        pod["spec"]["containers"][0]["image"] = "registry.invalid/foreign@sha256:" + "f" * 64
        with self.assertRaisesRegex(BaselineError, "runtime node/image identity"):
            backend._active_occupant()

    def test_partial_phase_failure_retains_bytes_and_closes_gpu_time(self) -> None:
        backend = self.backend()
        state = backend._attempt["attempt-a"]
        state["gpu_active_started_ns"] = 1_000_000_000
        backend._run_phase_inner = Mock(side_effect=BaselineError("localization fault"))
        backend._partial_phase_bytes = Mock(return_value=12345)
        with patch(
            "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
            return_value=3_000_000_000,
        ):
            with self.assertRaises(PhaseExecutionError) as raised:
                backend.run_phase(self.request(), "artifact_readiness")
        self.assertEqual(raised.exception.bytes_moved, 12345)
        self.assertEqual(state["gpu_active_seconds"], 2.0)

    def test_missing_or_malformed_progress_receipt_is_conservative_and_unpromotable(self) -> None:
        for response in (BaselineError("sentinel unavailable"), "{not-json"):
            with self.subTest(response=type(response).__name__):
                backend = self.backend()
                backend._run_phase_inner = Mock(side_effect=BaselineError("localization fault"))
                backend._sentinel = Mock(
                    side_effect=response if isinstance(response, Exception) else None,
                    return_value=response if isinstance(response, str) else None,
                )
                with self.assertRaises(PhaseExecutionError) as raised:
                    backend.run_phase(self.request(), "artifact_readiness")
                self.assertEqual(raised.exception.bytes_moved, 1024)
                self.assertIn(
                    "artifact_readiness",
                    backend._attempt["attempt-a"]["byte_accounting_failures"],
                )
                with self.assertRaisesRegex(BaselineError, "conservative bytes"):
                    backend.accounting(self.request(), 1.0, raised.exception.bytes_moved)

    def test_post_admission_template_bundle_and_validator_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "target.yaml"
            bundle = root / "bundle.json"
            validator = root / "validator.py"
            template.write_text("apiVersion: v1\nkind: Pod\n")
            bundle.write_text("{}\n")
            validator.write_text("def validate_response(*args): return None\n")
            backend = self.backend()
            model = backend.models[("model-a", "v1")]
            model.update(
                {
                    "target_templates": {
                        "conventional": {
                            "path": str(template),
                            "sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                        },
                        "snapshot": None,
                    },
                    "request_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
                    "validator_sha256": hashlib.sha256(validator.read_bytes()).hexdigest(),
                    "_paths": {
                        "conventional_template": str(template),
                        "snapshot_template": None,
                        "request_file": str(bundle),
                        "validator_path": str(validator),
                    },
                }
            )
            backend._attempt["attempt-a"]["pod_name"] = "target-a"

            template.write_text("apiVersion: v1\nkind: Pod\n# drift\n")
            with self.assertRaisesRegex(BaselineError, "template drifted"):
                backend._render_target(self.request())

            bundle.write_text('{"calls":[]}\n')
            with self.assertRaisesRegex(BaselineError, "bundle drifted"):
                backend._call_bundle(model)

            validator.write_text("def validate_response(*args): raise SystemExit\n")
            with self.assertRaisesRegex(BaselineError, "validator drifted"):
                backend._validate_response(model, {}, b"{}")

    def test_rendered_target_binds_safe_label_full_annotations_and_pinned_images(self) -> None:
        backend = self.backend()
        backend._attempt["attempt-a"]["pod_name"] = "target-a"
        model = backend.models[("model-a", "v1")]
        manifest = {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {
                "name": "target-a", "namespace": "mlsp-csw-k8s",
                "labels": {
                    "mlsp.nebius.ai/role": "catalog-switch-target",
                    "mlsp.nebius.ai/task": "catalog-switch-k8s-baseline",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                    "mlsp.nebius.ai/model-id": "model-a",
                    "mlsp.nebius.ai/model-version-id": "v1",
                },
                "annotations": {
                    "mlsp.nebius.ai/model-version-full": "v1",
                    "mlsp.nebius.ai/artifact-id": "artifact-a",
                    "mlsp.nebius.ai/artifact-version": "v1",
                    "mlsp.nebius.ai/artifact-sha256": "a" * 64,
                    "mlsp.nebius.ai/image-digest": model["image_digest"],
                    "mlsp.nebius.ai/strategy": "conventional",
                },
            },
            "spec": {
                "nodeName": "fresh-h100-node", "serviceAccountName": "catalog-switch-runtime",
                "imagePullSecrets": [{"name": "ngc-task-owned"}],
                "initContainers": [
                    {
                        "name": name,
                        "image": backend.plan["security"]["support_images"]["readiness_gate_digest"],
                    }
                    for name in ("artifact-gate", "cache-gate", "storage-gate")
                ],
                "containers": [{
                    "name": "model-a", "image": model["image_digest"],
                    "resources": {"limits": {"nvidia.com/gpu": 1}},
                }],
            },
        }
        backend._verify_rendered_target(manifest, self.request())
        manifest["metadata"]["labels"]["mlsp.nebius.ai/model-version-id"] = "forged"
        with self.assertRaisesRegex(BaselineError, "identity/ownership"):
            backend._verify_rendered_target(manifest, self.request())
        manifest["metadata"]["labels"]["mlsp.nebius.ai/model-version-id"] = "v1"
        manifest["spec"]["containers"].append(
            {
                "name": "attacker-sidecar",
                "image": "nvcr.io/attacker/sidecar@sha256:" + "9" * 64,
            }
        )
        with self.assertRaisesRegex(BaselineError, "container set"):
            backend._verify_rendered_target(manifest, self.request())

    def test_runtime_readiness_inference_faults_close_gpu_active_time(self) -> None:
        for phase in ("runtime_launch", "service_readiness", "inference"):
            with self.subTest(phase=phase):
                backend = self.backend()
                state = backend._attempt["attempt-a"]
                state["gpu_active_started_ns"] = 1_000_000_000
                backend._run_phase_inner = Mock(side_effect=BaselineError(f"{phase} fault"))
                backend._partial_phase_bytes = Mock(return_value=0)
                with patch(
                    "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
                    return_value=2_500_000_000,
                ):
                    with self.assertRaises(PhaseExecutionError):
                        backend.run_phase(self.request(), phase)
                self.assertEqual(state["gpu_active_seconds"], 1.5)

    def test_hot_service_or_inference_failure_counts_gpu_from_durable_t0(self) -> None:
        for phase in ("service_readiness", "inference"):
            with self.subTest(phase=phase):
                backend = self.backend()
                request = {**self.request(), "scenario": "same_model_hot"}
                backend.accepted(
                    request,
                    {
                        "observed_monotonic_ns": 1_000_000_000,
                        "observed_at_utc": "2026-08-19T00:00:00Z",
                    },
                )
                backend._run_phase_inner = Mock(side_effect=BaselineError(f"{phase} fault"))
                backend._partial_phase_bytes = Mock(return_value=0)
                with patch(
                    "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
                    return_value=2_500_000_000,
                ):
                    with self.assertRaises(PhaseExecutionError):
                        backend.run_phase(request, phase)
                self.assertEqual(
                    backend._attempt["attempt-a"]["gpu_active_seconds"], 1.5
                )

    def test_strategy_receipt_binds_snapshot_checkpoint_and_conventional_load(self) -> None:
        backend = self.backend()
        request = self.request()
        model = backend.models[("model-a", "v1")]
        backend.plan["scenario_strategies"]["a_to_b_local"] = "snapshot"
        receipt = {
            "schema": "archvteams.nebius.ai/k8s-strategy-receipt/v2",
            "attempt_id": "attempt-a", "model_id": "model-a", "model_version": "v1",
            "artifact_sha256": model["artifact_sha256"], "strategy": "snapshot",
            "checkpoint": model["checkpoint"], "status": "RESTORED",
            "node_clock_id": "CLOCK_MONOTONIC",
            "strategy_work_duration_ns": 1_000_000_000,
            "gpu_active_elapsed_ns": 1_100_000_000,
            "gpu_process_active": True,
            "observed_at_utc": "2026-08-19T00:00:01Z",
            "evidence_sha256": "e" * 64,
        }
        backend._attempt["attempt-a"]["pod_name"] = "target-a"
        backend._sentinel = Mock(return_value=json.dumps(receipt))
        backend._verify_strategy_receipt(request, model)
        self.assertEqual(backend._events[-1]["operation"], "strategy_receipt")

        forged = {**receipt, "checkpoint": {**receipt["checkpoint"], "checkpoint_sha256": "f" * 64}}
        backend._sentinel = Mock(return_value=json.dumps(forged))
        with self.assertRaisesRegex(BaselineError, "checkpoint receipt"):
            backend._verify_strategy_receipt(request, model)

        backend.plan["scenario_strategies"]["a_to_b_local"] = "conventional"
        backend._attempt["attempt-a"]["strategy_active_elapsed_ns"] = None
        conventional = {
            **receipt, "strategy": "conventional", "checkpoint": None, "status": "LOADED",
        }
        backend._sentinel = Mock(return_value=json.dumps(conventional))
        backend._verify_strategy_receipt(request, model)

    def test_success_accounting_refresh_preserves_load_and_later_inference_gpu_time(self) -> None:
        backend = self.backend()
        request = self.request()
        model = backend.models[("model-a", "v1")]
        state = backend._attempt["attempt-a"]
        state["pod_name"] = "target-a"
        state["placement_submitted_ns"] = 800_000_000
        backend._last_billing_ns = 1_000_000_000

        def receipt(active_ns: int) -> str:
            return json.dumps(
                {
                    "schema": "archvteams.nebius.ai/k8s-strategy-receipt/v2",
                    "attempt_id": "attempt-a", "model_id": "model-a", "model_version": "v1",
                    "artifact_sha256": model["artifact_sha256"], "strategy": "conventional",
                    "checkpoint": None, "status": "LOADED",
                    "node_clock_id": "CLOCK_MONOTONIC",
                    "strategy_work_duration_ns": 500_000_000,
                    "gpu_active_elapsed_ns": active_ns,
                    "gpu_process_active": True,
                    "observed_at_utc": "2026-08-19T00:00:01Z",
                    "evidence_sha256": "e" * 64,
                }
            )

        backend._sentinel = Mock(side_effect=[receipt(700_000_000), receipt(1_700_000_000)])
        backend._verify_strategy_receipt(request, model)
        with patch(
            "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
            return_value=4_000_000_000,
        ):
            accounting = backend.accounting(request, 3.0, 0)
        self.assertEqual(accounting.gpu_active_seconds, 1.7)
        self.assertEqual(accounting.gpu_idle_seconds, 1.3)

    def test_snapshot_restore_failure_before_runtime_launch_retains_gpu_time(self) -> None:
        backend = self.backend()
        request = self.request()
        model = backend.models[("model-a", "v1")]
        state = backend._attempt["attempt-a"]
        backend.plan["scenario_strategies"]["a_to_b_local"] = "snapshot"
        state["placement_submitted_ns"] = 900_000_000
        state["pod_name"] = "target-a"
        failed = {
            "schema": "archvteams.nebius.ai/k8s-strategy-receipt/v2",
            "attempt_id": "attempt-a", "model_id": "model-a", "model_version": "v1",
            "artifact_sha256": model["artifact_sha256"], "strategy": "snapshot",
            "checkpoint": model["checkpoint"], "status": "FAILED",
            "node_clock_id": "CLOCK_MONOTONIC",
            "strategy_work_duration_ns": 500_000_000,
            "gpu_active_elapsed_ns": 500_000_000,
            "gpu_process_active": False,
            "observed_at_utc": "2026-08-19T00:00:01Z",
            "evidence_sha256": "e" * 64,
        }
        backend._sentinel = Mock(return_value=json.dumps(failed))
        backend._run_phase_inner = Mock(side_effect=BaselineError("restore failed before runtime"))
        backend._partial_phase_bytes = Mock(return_value=0)
        with self.assertRaises(PhaseExecutionError):
            backend.run_phase(request, "artifact_readiness")
        self.assertEqual(state["gpu_active_seconds"], 0.5)

    def test_node_monotonic_origin_is_never_compared_with_controller_t0(self) -> None:
        backend = self.backend()
        request = self.request()
        model = backend.models[("model-a", "v1")]
        backend.plan["scenario_strategies"]["a_to_b_local"] = "snapshot"
        backend._attempt["attempt-a"]["pod_name"] = "target-a"
        backend._attempt["attempt-a"]["t0_monotonic_ns"] = 9_000_000_000_000_000
        receipt = {
            "schema": "archvteams.nebius.ai/k8s-strategy-receipt/v2",
            "attempt_id": "attempt-a", "model_id": "model-a", "model_version": "v1",
            "artifact_sha256": model["artifact_sha256"], "strategy": "snapshot",
            "checkpoint": model["checkpoint"], "status": "RESTORED",
            "node_clock_id": "CLOCK_MONOTONIC",
            "strategy_work_duration_ns": 400_000_000,
            "gpu_active_elapsed_ns": 700_000_000,
            "gpu_process_active": True,
            "observed_at_utc": "2026-08-19T00:00:01Z",
            "evidence_sha256": "e" * 64,
        }
        backend._sentinel = Mock(return_value=json.dumps(receipt))
        backend._verify_strategy_receipt(request, model)
        self.assertEqual(backend._attempt["attempt-a"]["gpu_active_seconds"], 0.7)

    def test_missing_restore_timing_after_pod_submission_is_conservative_and_unpromotable(self) -> None:
        backend = self.backend()
        request = self.request()
        state = backend._attempt["attempt-a"]
        backend.plan["scenario_strategies"]["a_to_b_local"] = "snapshot"
        state["placement_submitted_ns"] = 1_000_000_000
        state["pod_name"] = "target-a"
        backend._sentinel = Mock(side_effect=BaselineError("receipt unavailable"))
        backend._run_phase_inner = Mock(side_effect=BaselineError("restore fault"))
        backend._partial_phase_bytes = Mock(return_value=0)
        with patch(
            "performance.k8s_baseline.kubernetes_backend.time.monotonic_ns",
            return_value=3_000_000_000,
        ):
            with self.assertRaises(PhaseExecutionError):
                backend.run_phase(request, "artifact_readiness")
        self.assertEqual(state["gpu_active_seconds"], 2.0)
        with self.assertRaisesRegex(BaselineError, "timing receipt unavailable"):
            backend.accounting(request, 2.0, 0)

    def test_snapshot_manifest_requires_exact_checkpoint_annotations_and_gate(self) -> None:
        backend = self.backend()
        request = self.request()
        backend.plan["scenario_strategies"]["a_to_b_local"] = "snapshot"
        backend._attempt["attempt-a"]["pod_name"] = "target-a"
        model = backend.models[("model-a", "v1")]
        manifest = {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {
                "name": "target-a", "namespace": "mlsp-csw-k8s",
                "labels": {
                    "mlsp.nebius.ai/role": "catalog-switch-target",
                    "mlsp.nebius.ai/task": "catalog-switch-k8s-baseline",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                    "mlsp.nebius.ai/model-id": "model-a",
                    "mlsp.nebius.ai/model-version-id": "v1",
                },
                "annotations": {
                    "mlsp.nebius.ai/model-version-full": "v1",
                    "mlsp.nebius.ai/artifact-id": "artifact-a",
                    "mlsp.nebius.ai/artifact-version": "v1",
                    "mlsp.nebius.ai/artifact-sha256": "a" * 64,
                    "mlsp.nebius.ai/image-digest": model["image_digest"],
                    "mlsp.nebius.ai/strategy": "snapshot",
                    "mlsp.nebius.ai/checkpoint-id": model["checkpoint"]["checkpoint_id"],
                    "mlsp.nebius.ai/checkpoint-sha256": model["checkpoint"]["checkpoint_sha256"],
                    "mlsp.nebius.ai/checkpoint-bytes": "4096",
                },
            },
            "spec": {
                "nodeName": "fresh-h100-node", "serviceAccountName": "catalog-switch-runtime",
                "imagePullSecrets": [{"name": "ngc-task-owned"}],
                "initContainers": [
                    {
                        "name": name,
                        "image": backend.plan["security"]["support_images"]["readiness_gate_digest"],
                    }
                    for name in (
                        "artifact-gate", "cache-gate", "storage-gate",
                        "snapshot-restore-gate",
                    )
                ],
                "containers": [{
                    "name": "model-a", "image": model["image_digest"],
                    "resources": {"limits": {"nvidia.com/gpu": 1}},
                }],
            },
        }
        backend._verify_rendered_target(manifest, request)
        manifest["metadata"]["annotations"]["mlsp.nebius.ai/checkpoint-sha256"] = "f" * 64
        with self.assertRaisesRegex(BaselineError, "identity/ownership"):
            backend._verify_rendered_target(manifest, request)

    def test_prepare_failure_deletes_precreated_service(self) -> None:
        backend = self.backend()
        backend.plan.update(
            {
                "variant": "precreated_service",
                "kubernetes": {
                    **backend.plan["kubernetes"],
                    "context": "fresh-context", "expected_server": "https://cluster.invalid",
                },
            }
        )
        backend.kube.run.return_value = {
            "clusters": [{"cluster": {"server": "https://cluster.invalid"}}]
        }
        node = {
            "metadata": {
                "uid": "node-uid-1", "labels": {"nvidia.com/gpu.product": "NVIDIA-H100-80GB-HBM3"},
                "annotations": {
                    "mlsp.nebius.ai/broker-node-id": "computeinstance-node-1",
                    "mlsp.nebius.ai/broker-node-group-id": "mk8snodegroup-test",
                    "mlsp.nebius.ai/lease-id": "lease-1",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                    "mlsp.nebius.ai/preemptible": "true",
                },
            },
            "status": {
                "conditions": [{"type": "Ready", "status": "True"}],
                "allocatable": {"nvidia.com/gpu": "1"},
                "nodeInfo": {"kubeletVersion": "v1.31.8"},
            },
        }
        secret = {
            "type": "kubernetes.io/dockerconfigjson",
            "metadata": {
                "uid": "secret-uid-1", "labels": {"mlsp.nebius.ai/task": "catalog-switch-k8s-baseline"},
                "annotations": {
                    "mlsp.nebius.ai/scope-sha256": "c" * 64,
                    "mlsp.nebius.ai/scope-manifest-sha256": "8" * 64,
                    "mlsp.nebius.ai/receipt-sha256": "d" * 64,
                    "mlsp.nebius.ai/expires-at": "2026-08-20T00:00:00Z",
                    "mlsp.nebius.ai/revoke-by": "2026-08-20T01:00:00Z",
                },
            },
        }
        sentinel_digest = backend.plan["security"]["support_images"]["sentinel_digest"]
        sentinel = {
            "metadata": {
                "labels": {"mlsp.nebius.ai/task": "catalog-switch-k8s-baseline"},
                "annotations": {"mlsp.nebius.ai/broker-node-id": "computeinstance-node-1"},
            },
            "spec": {
                "nodeName": "fresh-h100-node", "imagePullSecrets": [{"name": "ngc-task-owned"}],
                "serviceAccountName": "catalog-switch-runtime",
                "containers": [{"image": sentinel_digest}],
            },
            "status": {"containerStatuses": [{"imageID": "containerd://" + sentinel_digest.split("@", 1)[1]}]},
        }
        namespace_obj = {
            "metadata": {
                "uid": "namespace-uid-1",
                "labels": {
                    "mlsp.nebius.ai/task": "catalog-switch-k8s-baseline",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                },
                "annotations": {
                    "mlsp.nebius.ai/lease-id": "lease-1",
                    "mlsp.nebius.ai/broker-resource-id": "namespace-test",
                },
            }
        }
        service_account = {
            "metadata": {
                "uid": "serviceaccount-uid-1",
                "labels": {
                    "mlsp.nebius.ai/task": "catalog-switch-k8s-baseline",
                    "mlsp.nebius.ai/resource-prefix": "mlsp-csw-test",
                },
                "annotations": {
                    "mlsp.nebius.ai/lease-id": "lease-1",
                    "mlsp.nebius.ai/broker-resource-id": "serviceaccount-test",
                },
            }
        }

        def get_json(kind, name=None, namespace=True):
            return {
                "namespace": namespace_obj, "serviceaccount": service_account,
                "node": node, "secret": secret, "pod": sentinel,
            }[kind]

        backend.kube.get_json.side_effect = get_json
        backend._sentinel = Mock(
            return_value=json.dumps(
                {
                    key: value
                    for key, value in backend.lease["initial_state_receipt"].items()
                    if key != "evidence_path"
                }
            )
        )
        backend._active_occupant = Mock(side_effect=BaselineError("occupant forged"))
        with self.assertRaisesRegex(BaselineError, "occupant forged"):
            backend.prepare()
        backend.kube.delete.assert_called_once_with("service", "catalog-switch-endpoint", 30)
        self.assertFalse(backend._prepare_owned)
        self.assertEqual(backend.final_cleanup()["status"], "NOT_RUN")

        backend.kube.reset_mock()
        node["metadata"]["annotations"]["mlsp.nebius.ai/preemptible"] = "false"
        with self.assertRaisesRegex(BaselineError, "broker-bound Ready preemptible"):
            backend.prepare()
        backend.kube.apply.assert_not_called()

        backend.kube.reset_mock()
        node["metadata"]["annotations"]["mlsp.nebius.ai/preemptible"] = "true"
        secret["metadata"]["annotations"]["mlsp.nebius.ai/scope-sha256"] = "f" * 64
        with self.assertRaisesRegex(BaselineError, "scoped registry credential"):
            backend.prepare()
        backend.kube.apply.assert_not_called()

        backend.kube.reset_mock()
        secret["metadata"]["annotations"]["mlsp.nebius.ai/scope-sha256"] = "c" * 64
        node["metadata"]["annotations"]["mlsp.nebius.ai/broker-node-group-id"] = "foreign-group"
        with self.assertRaisesRegex(BaselineError, "broker-bound Ready preemptible"):
            backend.prepare()
        backend.kube.apply.assert_not_called()

        backend.kube.reset_mock()
        node["metadata"]["annotations"]["mlsp.nebius.ai/broker-node-group-id"] = "mk8snodegroup-test"
        namespace_obj["metadata"]["uid"] = "foreign-namespace"
        with self.assertRaisesRegex(BaselineError, "namespace is not owned"):
            backend.prepare()
        backend.kube.apply.assert_not_called()

        backend.kube.reset_mock()
        namespace_obj["metadata"]["uid"] = "namespace-uid-1"
        service_account["metadata"]["uid"] = "foreign-serviceaccount"
        with self.assertRaisesRegex(BaselineError, "ServiceAccount is not owned"):
            backend.prepare()
        backend.kube.apply.assert_not_called()

        backend.kube.reset_mock()
        service_account["metadata"]["uid"] = "serviceaccount-uid-1"
        forged_initial = {
            key: value
            for key, value in backend.lease["initial_state_receipt"].items()
            if key != "evidence_path"
        }
        forged_initial = json.loads(json.dumps(forged_initial))
        forged_initial["cache_targets"][0]["artifact_sha256"] = "f" * 64
        backend._sentinel = Mock(return_value=json.dumps(forged_initial))
        with self.assertRaisesRegex(BaselineError, "live initial occupant/cache targets"):
            backend.prepare()
        backend.kube.apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
