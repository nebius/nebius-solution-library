from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import qualification_receipt as qualification


UID = "11111111-1111-4111-8111-111111111111"
IMAGE = "registry.example/openfold2@sha256:" + "a" * 64
POD_SPEC = "b" * 64


def target() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "of2-target-fresh-001",
            "namespace": "nim-fast-start",
            "uid": UID,
            "creationTimestamp": "2026-08-18T00:00:00Z",
            "annotations": {
                "archvteams.nebius.ai/target-pod-spec-sha256": POD_SPEC
            },
        },
        "spec": {"nodeName": "qualified-h100"},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "openfold2",
                    "restartCount": 0,
                    "state": {
                        "running": {"startedAt": "2026-08-18T00:00:01Z"}
                    },
                    "lastState": {},
                }
            ],
        },
    }


def create_response() -> dict:
    value = target()
    value["status"] = {}
    return value


def job_pod(container: str) -> dict:
    return {
        "spec": {"nodeName": "qualified-h100"},
        "status": {
            "phase": "Succeeded",
            "containerStatuses": [
                {
                    "name": container,
                    "restartCount": 0,
                    "state": {
                        "terminated": {
                            "exitCode": 0,
                            "reason": "Completed",
                            "startedAt": "2026-08-18T00:00:01Z",
                            "finishedAt": "2026-08-18T00:00:02Z",
                        }
                    },
                    "lastState": {},
                }
            ],
        }
    }


def events() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "EventList",
        "items": [
            {
                "type": "Normal",
                "reason": "Scheduled",
                "message": "Successfully assigned",
                "involvedObject": {"uid": UID},
            },
            {
                "type": "Normal",
                "reason": "Pulled",
                "message": f'Container image "{IMAGE}" already present on machine',
                "involvedObject": {"uid": UID},
            },
        ],
    }


GPU_XML = b"""<?xml version="1.0" ?>
<nvidia_smi_log>
  <attached_gpus>1</attached_gpus>
  <gpu id="00000000:01:00.0">
    <product_name>NVIDIA H100 80GB HBM3</product_name>
    <uuid>GPU-11111111-2222-3333-4444-555555555555</uuid>
  </gpu>
</nvidia_smi_log>
"""


def clock_sample(phase: str) -> dict:
    if phase == "before-semantic":
        before, observed, after = (
            "2026-08-18T00:00:01.000000Z",
            "2026-08-18T00:00:01.050000Z",
            "2026-08-18T00:00:01.100000Z",
        )
    else:
        before, observed, after = (
            "2026-08-18T00:00:12.000000Z",
            "2026-08-18T00:00:12.050000Z",
            "2026-08-18T00:00:12.100000Z",
        )
    return {
        "schema": qualification.CLOCK_SAMPLE_SCHEMA,
        "phase": phase,
        "sampled_pod_name": (
            "artifact-holder" if phase == "before-semantic" else "of2-target-fresh-001"
        ),
        "sampled_pod_uid": (
            "99999999-9999-4999-8999-999999999999"
            if phase == "before-semantic"
            else UID
        ),
        "target_node": "qualified-h100",
        "sampled_container": "" if phase == "before-semantic" else "openfold2",
        "controller_before": before,
        "node_observed": observed,
        "controller_after": after,
    }


class QualificationReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.gpu_xml = Path(self.temporary.name) / "nvidia-smi.xml"
        self.gpu_xml.write_bytes(GPU_XML)
        self.gpu_stderr = Path(self.temporary.name) / "nvidia-smi.stderr"
        self.gpu_stderr.write_bytes(b"")

    def build(self, **changes: object) -> dict:
        values = {
            "model": "openfold2",
            "run_id": "fresh-001",
            "namespace": "nim-fast-start",
            "target_name": "of2-target-fresh-001",
            "target_container": "openfold2",
            "expected_image": IMAGE,
            "target_submit_at": "2026-08-18T00:00:00.100000Z",
            "target_create_response_at": "2026-08-18T00:00:00.400000Z",
            "target_create_response": create_response(),
            "target": target(),
            "target_events": events(),
            "worker_pod": job_pod("restore-worker"),
            "worker_container": "restore-worker",
            "probe_pod": job_pod("semantic-probe"),
            "probe_container": "semantic-probe",
            "gpu_health_xml": self.gpu_xml,
            "gpu_health_stderr": self.gpu_stderr,
            "clock_sample_start": clock_sample("before-semantic"),
            "clock_sample_end": clock_sample("after-semantic"),
        }
        values.update(changes)
        return qualification.build_receipt(**values)  # type: ignore[arg-type]

    def test_builds_cached_image_zero_restart_bounded_gpu_receipt(self) -> None:
        receipt = self.build()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(
            receipt["timing_boundaries"]["acceptance_response_proxy"][
                "client_observed_api_round_trip_seconds"
            ],
            0.3,
        )
        self.assertFalse(
            receipt["timing_boundaries"]["acceptance_response_proxy"][
                "is_exact_server_acceptance"
            ]
        )
        self.assertEqual(receipt["pod_health"]["target"]["restart_count"], 0)
        self.assertEqual(receipt["gpu_health"]["attached_gpu_count"], 1)
        self.assertEqual(
            receipt["gpu_health"]["host_xid_check"]["status"], "unavailable"
        )
        self.assertEqual(receipt["clock_alignment"]["status"], "PASS")
        self.assertLessEqual(
            receipt["clock_alignment"]["absolute_offset_upper_bound_seconds"],
            1.0,
        )

    def test_rejects_image_pull_or_non_cached_pulled_event(self) -> None:
        for reason, message in (
            ("Pulling", f'Pulling image "{IMAGE}"'),
            ("Pulled", f'Successfully pulled image "{IMAGE}"'),
        ):
            with self.subTest(reason=reason):
                changed = events()
                changed["items"][1].update({"reason": reason, "message": message})
                with self.assertRaises(qualification.QualificationError):
                    self.build(target_events=changed)

    def test_rejects_warning_event(self) -> None:
        changed = events()
        changed["items"].append(
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "mount failed",
                "involvedObject": {"uid": UID},
            }
        )
        with self.assertRaisesRegex(qualification.QualificationError, "Warning"):
            self.build(target_events=changed)

    def test_rejects_restart_oom_eviction_and_nonzero_termination(self) -> None:
        mutations = []
        restarted = target()
        restarted["status"]["containerStatuses"][0]["restartCount"] = 1
        mutations.append(restarted)
        oom = target()
        oom["status"]["containerStatuses"][0]["lastState"] = {
            "terminated": {"exitCode": 137, "reason": "OOMKilled"}
        }
        mutations.append(oom)
        evicted = target()
        evicted["status"].update({"reason": "Evicted", "message": "node pressure"})
        mutations.append(evicted)
        for changed in mutations:
            with self.subTest(status=changed["status"]):
                with self.assertRaises(qualification.QualificationError):
                    self.build(target=changed)

        worker = job_pod("restore-worker")
        worker["status"]["containerStatuses"][0]["state"]["terminated"][
            "exitCode"
        ] = 2
        with self.assertRaises(qualification.QualificationError):
            self.build(worker_pod=worker)

    def test_rejects_invalid_nvidia_smi_or_create_response_bracket(self) -> None:
        self.gpu_xml.write_text("not xml", encoding="utf-8")
        with self.assertRaisesRegex(qualification.QualificationError, "valid XML"):
            self.build()
        self.gpu_xml.write_bytes(GPU_XML)
        self.gpu_stderr.write_text("driver warning", encoding="utf-8")
        with self.assertRaisesRegex(qualification.QualificationError, "stderr"):
            self.build()
        self.gpu_stderr.write_bytes(b"")
        with self.assertRaisesRegex(qualification.QualificationError, "precedes"):
            self.build(target_create_response_at="2026-08-17T23:59:59Z")

    def test_rejects_cross_node_or_unbounded_clock_sample(self) -> None:
        probe = job_pod("semantic-probe")
        probe["spec"]["nodeName"] = "other-node"
        with self.assertRaisesRegex(qualification.QualificationError, "one node clock"):
            self.build(probe_pod=probe)
        changed = clock_sample("before-semantic")
        changed["node_observed"] = "2026-08-18T00:00:04Z"
        with self.assertRaisesRegex(qualification.QualificationError, "uncertainty"):
            self.build(clock_sample_start=changed)


if __name__ == "__main__":
    unittest.main()
