from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml


TEST_DIR = Path(__file__).resolve().parent
MODULE_DIR = TEST_DIR.parent
sys.path.insert(0, str(MODULE_DIR))

import external_tmp_state as state  # noqa: E402
import validate_external_tmp_artifact as artifact_validator  # noqa: E402


METADATA_IMAGES = (
    "files.img",
    "fs-1.img",
    "inventory.img",
    "mm-1.img",
    "mountpoints-1.img",
    "pstree.img",
)


class ExternalTmpArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.artifact = self.root / "artifact"
        self.decoded = self.root / "decoded"
        self.artifact.mkdir()
        self.decoded.mkdir()
        self.contract_path = MODULE_DIR / "external-tmp-contract.json"
        self.contract, self.contract_sha = state.load_contract(
            self.contract_path, verify_tool=False
        )
        self.write_manifest()
        self.write_rootfs(["./", "./opt/", "./opt/nim-marker"])
        page = self.artifact / "pages-1.img"
        with page.open("wb") as handle:
            handle.truncate(self.contract["baseline"]["pages_bytes"])
        self.decoded_values: dict[str, Any] = {
            name: {"entries": []} for name in METADATA_IMAGES
        }
        self.decoded_values["mountpoints-1.img"] = {
            "entries": [{"mnt_id": 42, "mountpoint": "/tmp", "root": "/"}]
        }
        for index, name in enumerate(METADATA_IMAGES):
            (self.artifact / name).write_bytes(f"raw-{index}-{name}".encode("ascii"))
        self.crit_receipt_path = self.root / "crit-receipt.json"
        self.write_crit_receipt()

    def write_manifest(self, *, ext_tmp: bool = True, bind_tmp_count: int = 1) -> None:
        ext_mnt = {"/": "/"}
        if ext_tmp:
            ext_mnt["/tmp"] = "/tmp"
        manifest = {
            "checkpointId": self.contract["candidate"]["checkpoint_id"],
            "criuDump": {
                "criu": {"imageIoMode": "direct", "leaveRunning": True},
                "extMnt": ext_mnt,
            },
            "overlay": {
                "bindMountDests": ["/tmp"] * bind_tmp_count + ["/opt/nim/.cache"]
            },
        }
        (self.artifact / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

    def write_rootfs(self, names: list[str]) -> None:
        with tarfile.open(self.artifact / "rootfs-diff.tar", mode="w") as archive:
            for name in names:
                info = tarfile.TarInfo(name)
                if name.endswith("/"):
                    info.type = tarfile.DIRTYPE
                    info.size = 0
                    archive.addfile(info)
                else:
                    payload = b"fixture"
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

    def write_crit_receipt(self) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        for name in sorted(METADATA_IMAGES):
            decoded_name = f"{name}.json"
            decoded_path = self.decoded / decoded_name
            decoded_path.write_text(
                json.dumps(
                    self.decoded_values[name],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="ascii",
            )
            template = self.contract["crit_decoder"]["decode_argument_template"]
            records.append(
                {
                    "raw_name": name,
                    "raw_sha256": hashlib.sha256(
                        (self.artifact / name).read_bytes()
                    ).hexdigest(),
                    "decoded_name": decoded_name,
                    "decoded_sha256": hashlib.sha256(
                        decoded_path.read_bytes()
                    ).hexdigest(),
                    "decode_argv": [
                        self.contract["crit_decoder"]["python_command"],
                        *[
                            item.format(raw_image=name, decoded_json=decoded_name)
                            for item in template
                        ],
                    ],
                }
            )
        receipt = {
            "schema": artifact_validator.CRIT_RECEIPT_SCHEMA,
            "status": "PASS",
            "checkpoint_id": self.contract["candidate"]["checkpoint_id"],
            "generated_at": state._now(),
            "decoder": copy.deepcopy(self.contract["crit_decoder"]),
            "images": records,
        }
        self.crit_receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="ascii",
        )
        return receipt

    def validate(self) -> dict[str, Any]:
        return artifact_validator.validate_artifact(
            self.artifact,
            self.decoded,
            self.crit_receipt_path,
            self.contract,
            self.contract_sha,
        )

    def test_all_artifact_gates_pass_but_live_canary_remains_pending(self) -> None:
        receipt = self.validate()
        self.assertEqual("PASS", receipt["status"])
        self.assertEqual(
            "artifact-gates-pass-live-clone-canary-pending",
            receipt["qualification"],
        )
        self.assertTrue(receipt["live_clone_canary_required"])
        self.assertFalse(receipt["live_clone_canary_completed"])
        self.assertEqual(0, receipt["rootfs"]["forbidden_tmp_member_count"])
        self.assertEqual(0, receipt["crit"]["tmp_identity_reference_count"])
        path = self.root / "artifact-gate.json"
        state._write_receipt(path, receipt)
        state._read_artifact_gate(path, self.contract, self.contract_sha)

    def test_manifest_requires_direct_exact_extmnt_and_single_bind_destination(self) -> None:
        for ext_tmp, bind_count, message in (
            (False, 1, "ExtMnt"),
            (True, 0, "BindMountDests"),
            (True, 2, "BindMountDests"),
        ):
            with self.subTest(ext_tmp=ext_tmp, bind_count=bind_count):
                self.write_manifest(ext_tmp=ext_tmp, bind_tmp_count=bind_count)
                with self.assertRaisesRegex(
                    artifact_validator.ArtifactError, message
                ):
                    self.validate()

        self.write_manifest()
        manifest = yaml.safe_load(
            (self.artifact / "manifest.yaml").read_text(encoding="utf-8")
        )
        manifest["criuDump"]["criu"]["imageIoMode"] = "buffered"
        (self.artifact / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "direct"):
            self.validate()

    def test_rootfs_rejects_tmp_traversal_and_oversize(self) -> None:
        for member in ("./tmp/model.bin", "tmp", "../tmp/escape", "/tmp/absolute"):
            with self.subTest(member=member):
                self.write_rootfs([member])
                with self.assertRaises(artifact_validator.ArtifactError):
                    self.validate()
        rootfs = self.artifact / "rootfs-diff.tar"
        with rootfs.open("wb") as handle:
            handle.truncate(
                self.contract["artifact_gates"]["rootfs_diff_max_bytes"] + 1
            )
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "128 MiB"):
            self.validate()

    def test_deleted_files_reject_tmp_and_malformed_inventory(self) -> None:
        deleted = self.artifact / "deleted-files.json"
        for value in (["tmp/prediction"], ["../tmp/prediction"], {"tmp": True}):
            with self.subTest(value=value):
                deleted.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(artifact_validator.ArtifactError):
                    self.validate()

    def test_pages_growth_gate_is_exactly_two_percent(self) -> None:
        maximum = (
            self.contract["baseline"]["pages_bytes"]
            * (10_000 + self.contract["artifact_gates"]["pages_growth_max_basis_points"])
            // 10_000
        )
        with (self.artifact / "pages-1.img").open("wb") as handle:
            handle.truncate(maximum)
        self.assertLessEqual(self.validate()["pages"]["growth_basis_points"], 200)
        with (self.artifact / "pages-1.img").open("wb") as handle:
            handle.truncate(maximum + 1)
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "grew above"):
            self.validate()

    def test_pinned_crit_rejects_direct_tmp_references_by_category(self) -> None:
        cases = {
            "files.img": {"entries": [{"name": "/tmp/open"}]},
            "mm-1.img": {"entries": [{"mnt_id": 42}]},
            "fs-1.img": {"entries": [{"cwd": "/tmp"}]},
        }
        for name, decoded in cases.items():
            with self.subTest(name=name):
                original = self.decoded_values[name]
                self.decoded_values[name] = decoded
                self.write_crit_receipt()
                with self.assertRaisesRegex(
                    artifact_validator.ArtifactError, "identity-sensitive"
                ):
                    self.validate()
                self.decoded_values[name] = original
        self.write_crit_receipt()

    def test_pinned_crit_rejects_digest_decoder_and_coverage_drift(self) -> None:
        receipt = self.write_crit_receipt()
        receipt["images"][0]["raw_sha256"] = "0" * 64
        self.crit_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "digest"):
            self.validate()

        receipt = self.write_crit_receipt()
        receipt["decoder"]["criu_commit"] = "0" * 40
        self.crit_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "identity"):
            self.validate()

        receipt = self.write_crit_receipt()
        receipt["images"].pop()
        self.crit_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "every metadata"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
