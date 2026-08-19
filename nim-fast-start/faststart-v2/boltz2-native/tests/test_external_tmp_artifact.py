from __future__ import annotations

import gzip
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

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


def _tar_bytes(builders: list[tuple[tarfile.TarInfo, bytes | None]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for info, payload in builders:
            if payload is None:
                archive.addfile(info)
            else:
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


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

    def fake_decoder_run(
        self, argv: list[str], cwd: Path, decoder_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        # Stand-in for the pinned-crit subprocess only: bundle hashing, safe
        # extraction, argv construction, and output hashing all stay real, and
        # the true subprocess mechanics are exercised separately below.
        self.assertTrue(decoder_dir.is_dir())
        self.assertTrue((decoder_dir / "crit" / "__main__.py").is_file())
        if argv[1] == "-c":
            return subprocess.CompletedProcess(argv, 0, "", "")
        raw = Path(argv[argv.index("-i") + 1])
        out = Path(argv[argv.index("-o") + 1])
        out.write_text(
            json.dumps(
                self.decoded_values[raw.name], sort_keys=True, separators=(",", ":")
            )
            + "\n",
            encoding="ascii",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    def write_manifest(
        self,
        *,
        ext_tmp: bool = True,
        drop_tmp_dest: bool = False,
        extra_dest: str | None = None,
    ) -> None:
        ext_mnt = dict(self.contract["artifact_gates"]["ext_mnt_exact"])
        if not ext_tmp:
            del ext_mnt["/tmp"]
        destinations = list(self.contract["artifact_gates"]["bind_mount_dests_exact"])
        if drop_tmp_dest:
            destinations.remove("/tmp")
        if extra_dest is not None:
            destinations.append(extra_dest)
        manifest = {
            "checkpointId": self.contract["candidate"]["checkpoint_id"],
            "criuDump": {
                "criu": {"imageIoMode": "direct", "leaveRunning": True},
                "extMnt": ext_mnt,
            },
            "overlay": {"bindMountDests": destinations},
        }
        (self.artifact / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )

    def write_rootfs(self, names: list[str]) -> None:
        builders: list[tuple[tarfile.TarInfo, bytes | None]] = []
        for name in names:
            info = tarfile.TarInfo(name)
            if name.endswith("/"):
                info.type = tarfile.DIRTYPE
                builders.append((info, None))
            else:
                builders.append((info, b"fixture"))
        (self.artifact / "rootfs-diff.tar").write_bytes(_tar_bytes(builders))

    def write_rootfs_members(
        self, builders: list[tuple[tarfile.TarInfo, bytes | None]]
    ) -> None:
        (self.artifact / "rootfs-diff.tar").write_bytes(_tar_bytes(builders))

    def validate(self, **overrides: Any) -> dict[str, Any]:
        if self.decoded.exists():
            shutil.rmtree(self.decoded)
        self.decoded.mkdir()
        with mock.patch.object(
            artifact_validator, "_run_decoder_subprocess", self.fake_decoder_run
        ):
            return artifact_validator.validate_artifact(
                self.artifact,
                self.decoded,
                self.contract,
                self.contract_sha,
                **overrides,
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
        self.assertEqual(
            {"regular": 1, "directory": 2, "symlink": 0, "hardlink": 0},
            receipt["rootfs"]["member_type_counts"],
        )
        self.assertEqual(0, receipt["crit"]["tmp_identity_reference_count"])
        self.assertEqual(
            self.contract["crit_decoder"]["source_bundle_sha256"],
            receipt["crit"]["bundle_sha256"],
        )
        self.assertTrue(receipt["crit"]["imports_preflight_ok"])
        self.assertEqual(
            len(METADATA_IMAGES), len(receipt["crit"]["images"])
        )
        for record in receipt["crit"]["images"]:
            self.assertEqual(0, record["exit_code"])
            decoded_path = self.decoded / record["decoded_name"]
            self.assertTrue(decoded_path.is_file())
            self.assertEqual(
                record["decoded_sha256"],
                artifact_validator._sha256_file(decoded_path),
            )
        self.assertEqual(0, receipt["tmpfs_images"]["file_count"])
        self.assertIn("manifest.yaml", receipt["artifact_entries"])
        self.assertEqual(
            sorted(receipt["artifact_entries"]), receipt["artifact_entries"]
        )
        path = self.root / "artifact-gate.json"
        state._write_receipt(path, receipt)
        state._read_artifact_gate(path, self.contract, self.contract_sha)

    def test_manifest_requires_exact_mount_sets_and_direct_io(self) -> None:
        for kwargs, message in (
            ({"ext_tmp": False}, "ExtMnt"),
            ({"drop_tmp_dest": True}, "BindMountDests"),
            ({"extra_dest": "/data"}, "BindMountDests"),
            ({"extra_dest": "/tmp"}, "BindMountDests"),
        ):
            with self.subTest(kwargs=kwargs):
                self.write_manifest(**kwargs)
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

    def test_rootfs_rejects_unsafe_member_types_and_linknames(self) -> None:
        def symlink(name: str, target: str) -> tarfile.TarInfo:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            return info

        def hardlink(name: str, target: str) -> tarfile.TarInfo:
            info = tarfile.TarInfo(name)
            info.type = tarfile.LNKTYPE
            info.linkname = target
            return info

        def device(name: str) -> tarfile.TarInfo:
            info = tarfile.TarInfo(name)
            info.type = tarfile.CHRTYPE
            info.devmajor = 1
            info.devminor = 3
            return info

        def fifo(name: str) -> tarfile.TarInfo:
            info = tarfile.TarInfo(name)
            info.type = tarfile.FIFOTYPE
            return info

        adversaries: list[tuple[str, list[tuple[tarfile.TarInfo, bytes | None]]]] = [
            (
                "absolute symlink into /tmp",
                [(symlink("opt/sneaky-link", "/tmp/mols_tar_actual_dir"), None)],
            ),
            (
                "relative symlink into tmp",
                [(symlink("opt/rel-link", "../tmp/payload"), None)],
            ),
            (
                "symlink escaping the root",
                [(symlink("opt/escape", "../../etc/shadow"), None)],
            ),
            (
                "hardlink into tmp",
                [(hardlink("opt/hardlink-tmp", "tmp/data"), None)],
            ),
            (
                "hardlink with traversal target",
                [(hardlink("opt/hardlink-escape", "../../../etc/shadow"), None)],
            ),
            (
                "hardlink to a missing member",
                [(hardlink("opt/dangling-hardlink", "opt/nonexistent"), None)],
            ),
            ("character device", [(device("opt/null"), None)]),
            ("FIFO", [(fifo("opt/pipe"), None)]),
            (
                "member routed through a symlinked directory",
                [
                    (symlink("opt/link", "elsewhere"), None),
                    (tarfile.TarInfo("opt/link/planted"), b"escape"),
                ],
            ),
        ]
        for label, builders in adversaries:
            with self.subTest(label=label):
                self.write_rootfs_members(builders)
                with self.assertRaises(artifact_validator.ArtifactError):
                    self.validate()

        self.write_rootfs_members(
            [
                (tarfile.TarInfo("opt/real-file"), b"payload"),
                (symlink("opt/benign-link", "real-file"), None),
                (hardlink("opt/benign-hardlink", "opt/real-file"), None),
            ]
        )
        receipt = self.validate()
        self.assertEqual(
            {"regular": 1, "directory": 0, "symlink": 1, "hardlink": 1},
            receipt["rootfs"]["member_type_counts"],
        )

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

    def test_tmpfs_images_are_inspected_and_capped(self) -> None:
        clean = _tar_bytes([(tarfile.TarInfo("torch_shm_segment"), b"shm-bytes")])
        (self.artifact / "tmpfs-2.tar.gz.img").write_bytes(gzip.compress(clean))
        receipt = self.validate()
        self.assertEqual(1, receipt["tmpfs_images"]["file_count"])
        self.assertEqual(
            "tmpfs-2.tar.gz.img", receipt["tmpfs_images"]["images"][0]["name"]
        )
        self.assertEqual(
            1, receipt["tmpfs_images"]["images"][0]["member_count"]
        )

        info = tarfile.TarInfo("shm-link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/tmp/mols_tar_hidden"
        malicious = _tar_bytes([(info, None)])
        (self.artifact / "tmpfs-2.tar.gz.img").write_bytes(gzip.compress(malicious))
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "/tmp"):
            self.validate()

        (self.artifact / "tmpfs-2.tar.gz.img").write_bytes(b"not-a-gzip-tar")
        with self.assertRaisesRegex(
            artifact_validator.ArtifactError, "inspectable gzip tar"
        ):
            self.validate()

        with (self.artifact / "tmpfs-2.tar.gz.img").open("wb") as handle:
            handle.truncate(
                self.contract["artifact_gates"]["tmpfs_images_max_total_bytes"] + 1
            )
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "byte cap"):
            self.validate()
        (self.artifact / "tmpfs-2.tar.gz.img").unlink()

    def test_unknown_artifact_entries_are_rejected(self) -> None:
        (self.artifact / "evil.bin").write_bytes(b"unaccounted")
        with self.assertRaisesRegex(
            artifact_validator.ArtifactError, "unreviewed entry"
        ):
            self.validate()
        (self.artifact / "evil.bin").unlink()

        (self.artifact / "stats-dump").write_bytes(b"criu statistics")
        receipt = self.validate()
        self.assertIn("stats-dump", receipt["artifact_entries"])
        (self.artifact / "stats-dump").unlink()

        nested = self.artifact / "subdir"
        nested.mkdir()
        with self.assertRaisesRegex(
            artifact_validator.ArtifactError, "non-regular entry"
        ):
            self.validate()
        nested.rmdir()

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
                with self.assertRaisesRegex(
                    artifact_validator.ArtifactError, "identity-sensitive"
                ):
                    self.validate()
                self.decoded_values[name] = original

    def test_decode_is_executed_not_trusted(self) -> None:
        # A tampered bundle must be refused before anything is decoded.
        tampered = self.root / "tampered-bundle.tar.gz"
        bundle_bytes = bytearray(
            (
                MODULE_DIR
                / self.contract["crit_decoder"]["source_bundle_filename"]
            ).read_bytes()
        )
        bundle_bytes[-1] ^= 0x01
        tampered.write_bytes(bytes(bundle_bytes))
        with self.assertRaisesRegex(artifact_validator.ArtifactError, "bundle digest"):
            self.validate(bundle_path=tampered)

        # A failing decoder subprocess must fail the gate, not be skipped.
        def failing_run(
            argv: list[str], cwd: Path, decoder_dir: Path
        ) -> subprocess.CompletedProcess[str]:
            if argv[1] == "-c":
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 1, "", "decode exploded")

        if self.decoded.exists():
            shutil.rmtree(self.decoded)
        self.decoded.mkdir()
        with mock.patch.object(
            artifact_validator, "_run_decoder_subprocess", failing_run
        ):
            with self.assertRaisesRegex(
                artifact_validator.ArtifactError, "pinned decoder failed"
            ):
                artifact_validator.validate_artifact(
                    self.artifact, self.decoded, self.contract, self.contract_sha
                )

        # A failing import preflight must also fail closed.
        def failing_preflight(
            argv: list[str], cwd: Path, decoder_dir: Path
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv, 1, "", "ModuleNotFoundError: google"
            )

        if self.decoded.exists():
            shutil.rmtree(self.decoded)
        self.decoded.mkdir()
        with mock.patch.object(
            artifact_validator, "_run_decoder_subprocess", failing_preflight
        ):
            with self.assertRaisesRegex(
                artifact_validator.ArtifactError, "import preflight"
            ):
                artifact_validator.validate_artifact(
                    self.artifact, self.decoded, self.contract, self.contract_sha
                )

        # Pre-existing decoded output is never accepted as input.
        if self.decoded.exists():
            shutil.rmtree(self.decoded)
        self.decoded.mkdir()
        (self.decoded / "stale.json").write_text("{}", encoding="ascii")
        with mock.patch.object(
            artifact_validator, "_run_decoder_subprocess", self.fake_decoder_run
        ):
            with self.assertRaisesRegex(
                artifact_validator.ArtifactError, "start empty"
            ):
                artifact_validator.validate_artifact(
                    self.artifact, self.decoded, self.contract, self.contract_sha
                )

    def test_bundle_extraction_and_subprocess_mechanics_are_real(self) -> None:
        # The real pinned bundle safely extracts to regular files only.
        with tempfile.TemporaryDirectory() as scratch:
            destination = Path(scratch)
            count = artifact_validator._safe_extract_bundle(
                MODULE_DIR / self.contract["crit_decoder"]["source_bundle_filename"],
                destination,
            )
            self.assertGreater(count, 0)
            self.assertTrue((destination / "crit" / "__main__.py").is_file())
            self.assertTrue((destination / "COPYING").is_file())

        # A bundle containing a symlink member is refused at extraction.
        malicious = self.root / "malicious-bundle.tar.gz"
        info = tarfile.TarInfo("crit/__init__.py")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        malicious.write_bytes(gzip.compress(_tar_bytes([(info, None)])))
        with tempfile.TemporaryDirectory() as scratch:
            with self.assertRaisesRegex(
                artifact_validator.ArtifactError, "regular file"
            ):
                artifact_validator._safe_extract_bundle(malicious, Path(scratch))

        # The genuine subprocess path executes a decoder package end-to-end.
        with tempfile.TemporaryDirectory() as scratch:
            scratch_path = Path(scratch)
            decoder_dir = scratch_path / "decoder"
            package = decoder_dir / "crit"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("", encoding="ascii")
            (package / "__main__.py").write_text(
                "import json, sys\n"
                "argv = sys.argv[1:]\n"
                "assert argv[0] == 'decode'\n"
                "raw = argv[argv.index('-i') + 1]\n"
                "out = argv[argv.index('-o') + 1]\n"
                "with open(raw, 'rb') as handle:\n"
                "    payload = handle.read()\n"
                "with open(out, 'w') as handle:\n"
                "    json.dump({'raw_bytes': len(payload)}, handle)\n",
                encoding="ascii",
            )
            raw_path = scratch_path / "inventory.img"
            raw_path.write_bytes(b"raw-image-bytes")
            out_path = scratch_path / "inventory.img.json"
            completed = artifact_validator._run_decoder_subprocess(
                [
                    sys.executable,
                    "-m",
                    "crit",
                    "decode",
                    "-i",
                    str(raw_path),
                    "-o",
                    str(out_path),
                ],
                scratch_path,
                decoder_dir,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(
                {"raw_bytes": len(b"raw-image-bytes")},
                json.loads(out_path.read_text(encoding="ascii")),
            )


if __name__ == "__main__":
    unittest.main()
