#!/usr/bin/env python3
"""Cross-file contract tests for the MSA Search native capture lane."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
IMAGE = (
    "nvcr.io/nim/colabfold/msa-search@sha256:"
    "944f3cf845761be8e42b33147ae08b68c61eca7cad67bf5251e1708d03c0165c"
)
VALIDATOR_SHA256 = "4ac58960c881f748dd1340288d1fa97f6d722a1be26c71c321f681a2c252bdee"
FIXTURE_SHA256 = "874b0e5e3be9776ea289fb46444032e04b63875d9d4110f1560e5435de72686a"
PIPE_VALIDATOR_SHA256 = "29f45a3c0d7197b5ad0757174666b1f6a8e11f2e3dd7cc54d63fc71fb030ad23"
WORKER_IMAGE = (
    "cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/"
    "snapshot-agent@sha256:"
    "25d195c97ee2e62577475d5a97d3de8c9f694c3e2a7bcc06d3b5c48d88549a24"
)


def documents(name: str) -> list[dict]:
    with (ROOT / name).open(encoding="utf-8") as source:
        return list(yaml.safe_load_all(source))


class CaptureManifestTests(unittest.TestCase):
    def test_input_digests_and_donor_warmup_are_exact(self) -> None:
        validator = (ROOT / "validate_msa_search.py").read_bytes()
        fixture = (ROOT / "fixtures" / "request-pdb70.json").read_bytes()
        pipe_validator = (ROOT / "verify_mmseqs_pipe.py").read_bytes()
        self.assertEqual(hashlib.sha256(validator).hexdigest(), VALIDATOR_SHA256)
        self.assertEqual(hashlib.sha256(fixture).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(
            hashlib.sha256(pipe_validator).hexdigest(), PIPE_VALIDATOR_SHA256
        )

        donor = documents("donor-job.yaml")[0]
        self.assertEqual(donor["metadata"]["annotations"]["archvteams.nebius.ai/validator-sha256"], VALIDATOR_SHA256)
        self.assertEqual(donor["metadata"]["annotations"]["archvteams.nebius.ai/fixture-sha256"], FIXTURE_SHA256)
        container = donor["spec"]["template"]["spec"]["containers"][0]
        script = container["args"][0]
        self.assertEqual(container["image"], IMAGE)
        self.assertIn("python3 -m pip uninstall -y uvloop", script)
        self.assertEqual(script.count("--run-id native-f7-donor-"), 2)
        self.assertEqual(
            container["resources"],
            {
                "requests": {"cpu": "14", "memory": "128Gi", "nvidia.com/gpu": "1"},
                "limits": {"cpu": "15", "memory": "180Gi", "nvidia.com/gpu": "1"},
            },
        )
        env = {item["name"]: item.get("value") for item in container["env"]}
        self.assertEqual(
            env["NIM_MODEL_PROFILE"],
            "ad5086cc67393792e71fa57444f13eaff8425658e8fb5feea07070ca3b2d34bb",
        )
        self.assertEqual(env["NIM_GLOBAL_MAX_MSA_DEPTH"], "500")
        volumes = {item["name"]: item for item in donor["spec"]["template"]["spec"]["volumes"]}
        self.assertEqual(volumes["dshm"]["emptyDir"], {"medium": "Memory", "sizeLimit": "16Gi"})
        runner = (ROOT / "dynamo" / "run_provisioned_trial.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(PIPE_VALIDATOR_SHA256, runner)
        self.assertIn("mmseqs-pipe-receipt.json", runner)

    def test_storage_and_artifact_modes_are_isolated(self) -> None:
        storage = documents("storage.yaml")
        self.assertEqual(len(storage), 2)
        claims = {item["metadata"]["name"]: item for item in storage}
        self.assertEqual(
            claims["msa-search-native-f7-artifacts"]["spec"]["resources"]["requests"]["storage"],
            "93Gi",
        )
        self.assertEqual(
            claims["msa-search-native-f7-artifacts"]["spec"]["storageClassName"],
            "mlspec-archvteams-2407-io-m3",
        )
        self.assertEqual(
            claims["msa-search-native-f7-cache"]["spec"]["resources"]["requests"]["storage"],
            "50Gi",
        )
        self.assertEqual(
            claims["msa-search-native-f7-cache"]["spec"]["storageClassName"],
            "compute-csi-default-sc",
        )

        direct = documents("artifact-holder.yaml")[0]
        buffered = documents("artifact-holder-buffered.yaml")[0]
        direct_script = direct["spec"]["containers"][0]["args"][0]
        buffered_script = buffered["spec"]["containers"][0]["args"][0]
        self.assertIn('"checkpoint_id": "msa-search-native-f7-v1"', direct_script)
        self.assertIn('"image_io_mode": "direct"', direct_script)
        self.assertIn('"checkpoint_id": "msa-search-native-f7-v2-buffered"', buffered_script)
        self.assertIn('"image_io_mode": "buffered"', buffered_script)
        self.assertNotEqual(direct["metadata"]["name"], buffered["metadata"]["name"])

    def test_worker_image_has_one_release_contract_source(self) -> None:
        contract = json.loads((ROOT / "dynamo" / "restore-interface.live.json").read_text())
        template = (ROOT / "snapshot-agent.yaml.tmpl").read_text()
        self.assertEqual(template.count("@@WORKER_IMAGE@@"), 1)
        self.assertNotIn(contract["worker_image"], template)
        self.assertEqual(contract["worker_image"], WORKER_IMAGE)
        self.assertEqual(
            contract["worker_executable_sha256"],
            "941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651",
        )
        self.assertFalse(contract["release_ready"])
        self.assertEqual(contract["worker_classification"], "performance-validation-only")
        self.assertEqual(
            contract["supported_image_io_modes"],
            ["direct", "writeback", "buffered"],
        )
        self.assertEqual(
            contract["source"]["materialized_tree_sha256"],
            "ffa53eadaf37b40b260766e6a33c07268b76c8ee7f3a045db1e6327a0ca671b4",
        )
        self.assertEqual(len(contract["source"]["patch_inputs"]), 7)
        self.assertEqual(
            contract["tool_bundle"]["content_sha256"],
            "c0d638100c03fa35973e82859d15b9c8dd1bcbf0fe9cb185b58cc21fae7ead1e",
        )
        self.assertEqual(contract["tool_bundle"]["regular_files"], 34)
        self.assertEqual(
            contract["tool_bundle"]["glibc_compatibility_sha256"],
            "f7af5b214cb963c4cf64910dfafe16987f0c5ec886af5d0e5d7aab5b634f6950",
        )
        self.assertNotEqual(contract["release_blocker"], "")


if __name__ == "__main__":
    unittest.main()
