from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "campaign"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CampaignFreezeTests(unittest.TestCase):
    def test_first_campaign_is_planned_and_mutation_is_not_admitted(self) -> None:
        value = json.loads((CAMPAIGN / "arm-a-first-campaign.json").read_text())
        self.assertEqual(value["status"], "PLANNED")
        self.assertFalse(value["mutation_admitted"])
        self.assertEqual(value["campaign_arm"], "A_prepared_node")
        self.assertEqual(value["models"], ["boltz2", "openfold2"])
        self.assertEqual(value["repetitions_per_model"], 30)
        self.assertEqual(value["total_attempts"], 60)
        self.assertEqual(value["product_boundary"]["semantic_calls_per_attempt"], 2)
        self.assertEqual(
            sha256(CAMPAIGN / value["trace_path"]), value["trace_file_sha256"]
        )
        self.assertEqual(
            sha256(CAMPAIGN / value["request_slo_freeze_path"]),
            value["request_slo_freeze_sha256"],
        )
        self.assertIsNone(value["resource_request_path"])
        self.assertIsNone(value["resource_lease_path"])

    def test_metric_freeze_hashes_every_shared_contract_file(self) -> None:
        value = json.loads((CAMPAIGN / "request-slo-freeze.json").read_text())
        repository = ROOT.parents[1]
        for relative, expected in value["files"].items():
            self.assertEqual(sha256(repository / relative), expected, relative)

    def test_arm_b_interface_places_node_and_model_work_after_t0(self) -> None:
        value = json.loads(
            (CAMPAIGN / "broker-cluster-interface-required.json").read_text()
        )
        arm_b = value["arm_b_new_preemptible_node"]
        self.assertEqual(arm_b["state_before_request_t0"], "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP")
        self.assertIn("GPU node-group demand or create", arm_b["forbidden_before_request_t0"])
        self.assertIn("artifact localization", arm_b["forbidden_before_request_t0"])
        self.assertIn("model image pull", arm_b["forbidden_before_request_t0"])
        self.assertEqual(
            arm_b["demand_call"]["must_follow"], "durable request.accepted event"
        )
        self.assertTrue(value["arm_separation"]["lease_ids_must_differ"])
        self.assertTrue(value["arm_separation"]["evidence_denominators_must_not_mix"])
        self.assertIn(
            "runtime_sources_sha256", value["common"]["immutable_request_fields"]
        )
        handoff = value["common"]["paired_variant_handoff"]
        self.assertEqual(
            handoff["status"], "BLOCKED_PENDING_VERSIONED_BROKER_BACKEND"
        )
        self.assertIn("pair-handoff/rearm", handoff["consumer_state"])

    def test_wave_one_catalog_pins_two_distinct_semantic_calls(self) -> None:
        catalog = json.loads((ROOT / "experiment-catalog.json").read_text())
        self.assertEqual(
            [item["model_id"] for item in catalog["models"]],
            ["boltz2", "openfold2"],
        )
        fixtures = {
            "boltz2": ROOT / "fixtures/boltz2-two-call-bundle.json",
            "openfold2": ROOT / "fixtures/openfold2-two-call-bundle.json",
        }
        artifact_digests = {
            "boltz2": "6539b9f50a71c9f5fb6a3fbacd44f5d5ea41003539b6563682a38600d1492456",
            "openfold2": "78368af3e6f143d7dc681632c4150b29f6354717103638b56e776244d9631b04",
        }
        for model in catalog["models"]:
            self.assertEqual(model["artifact_sha256"], artifact_digests[model["model_id"]])
            self.assertEqual(model["artifact_version"], "1")
            bundle_path = fixtures[model["model_id"]]
            self.assertEqual(sha256(bundle_path), model["input"]["payload_sha256"])
            self.assertEqual(bundle_path.stat().st_size, model["input"]["input_bytes"])
            bundle = json.loads(bundle_path.read_text())
            self.assertEqual(len(bundle["calls"]), 2)
            self.assertNotEqual(bundle["calls"][0]["input_id"], bundle["calls"][1]["input_id"])
            for call in bundle["calls"]:
                payload = (bundle_path.parent / call["payload_path"]).resolve()
                self.assertTrue(payload.is_file())
                self.assertEqual(sha256(payload), call["payload_sha256"])


if __name__ == "__main__":
    unittest.main()
