from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
MODULE_DIR = TEST_DIR.parent
sys.path.insert(0, str(MODULE_DIR))

import external_tmp_state as state  # noqa: E402


PVC_UID = "22222222-2222-4222-8222-222222222222"
PV_UID = "33333333-3333-4333-8333-333333333333"
DONOR_UID = "44444444-4444-4444-8444-444444444444"
HOLDER_UID = "55555555-5555-4555-8555-555555555555"
TARGET_UID = "66666666-6666-4666-8666-666666666666"


class ExternalTmpStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "state"
        self.receipts = self.base / "receipts"
        self.root.mkdir()
        self.receipts.mkdir()
        self.contract_path = MODULE_DIR / "external-tmp-contract.json"
        self.contract, self.contract_sha = state.load_contract(
            self.contract_path, verify_tool=False
        )

    def write_receipt(self, name: str, value: dict[str, object]) -> Path:
        path = self.receipts / name
        state._write_receipt(path, value)
        return path

    def initialize(self) -> dict[str, object]:
        return state.initialize_layout(self.root, self.contract, self.contract_sha)

    @property
    def working(self) -> Path:
        return self.root / self.contract["layout"]["working_subpath"]

    @property
    def seed(self) -> Path:
        return self.root / self.contract["layout"]["seed_subpath"]

    def populate(self) -> None:
        directory = self.working / "nested"
        directory.mkdir(mode=0o750)
        payload = directory / "payload.bin"
        payload.write_bytes(b"boltz-external-tmp\x00" * 7)
        payload.chmod(0o640)
        os.symlink("nested/payload.bin", self.working / "safe-relative-link")

    def pvc_identity(self) -> dict[str, object]:
        return {
            "name": self.contract["storage"]["pvc_name"],
            "uid": PVC_UID,
            "pv_name": "pvc-22222222-2222-4222-8222-222222222222",
            "pv_uid": PV_UID,
            "csi_driver": self.contract["storage"]["csi_driver"],
            "volume_handle": "computedisk-e00tmpstateidentity",
        }

    def holder_pod_evidence(self, pvc: dict[str, object]) -> dict[str, object]:
        return {
            "kind": "Pod",
            "metadata": {
                "name": state.HOLDER_POD_NAME,
                "namespace": self.contract["storage"]["namespace"],
                "uid": HOLDER_UID,
            },
            "spec": {
                "nodeName": state.HOLDER_NODE_NAME,
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "holder",
                        "image": self.contract["images"]["probe"],
                        "volumeMounts": [
                            {
                                "name": "tmp-state",
                                "mountPath": state.HOLDER_MOUNT_PATH,
                                "subPath": self.contract["layout"]["seed_subpath"],
                                "readOnly": True,
                            }
                        ],
                    }
                ],
                "volumes": [
                    {
                        "name": "tmp-state",
                        "persistentVolumeClaim": {
                            "claimName": pvc["name"],
                            "readOnly": True,
                        },
                    }
                ],
            },
            "status": {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        }

    def writer_evidence(
        self, pvc: dict[str, object], holder_pod: dict[str, object]
    ) -> dict[str, object]:
        namespace = self.contract["storage"]["namespace"]
        return {
            "pvc": {
                "kind": "PersistentVolumeClaim",
                "metadata": {
                    "name": pvc["name"],
                    "namespace": namespace,
                    "uid": pvc["uid"],
                },
                "spec": {
                    "volumeName": pvc["pv_name"],
                    "accessModes": ["ReadWriteOnce"],
                },
                "status": {"phase": "Bound"},
            },
            "pv": {
                "kind": "PersistentVolume",
                "metadata": {"name": pvc["pv_name"], "uid": pvc["pv_uid"]},
                "spec": {
                    "csi": {
                        "driver": pvc["csi_driver"],
                        "volumeHandle": pvc["volume_handle"],
                    },
                    "claimRef": {
                        "namespace": namespace,
                        "name": pvc["name"],
                        "uid": pvc["uid"],
                    },
                },
            },
            "pods": {
                "kind": "PodList",
                "items": [
                    holder_pod,
                    {
                        "kind": "Pod",
                        "metadata": {
                            "name": "unrelated-workload",
                            "namespace": namespace,
                            "uid": "99999999-9999-4999-8999-999999999999",
                        },
                        "spec": {"volumes": [{"name": "scratch", "emptyDir": {}}]},
                        "status": {"phase": "Running"},
                    },
                ],
            },
            "volumeattachments": {
                "kind": "VolumeAttachmentList",
                "items": [
                    {
                        "kind": "VolumeAttachment",
                        "spec": {
                            "nodeName": state.HOLDER_NODE_NAME,
                            "source": {"persistentVolumeName": pvc["pv_name"]},
                        },
                    }
                ],
            },
            "donor_get_attempt": {
                "argv": [
                    "kubectl",
                    "get",
                    "pod",
                    state.DONOR_POD_NAME,
                    "-n",
                    namespace,
                    "-o",
                    "json",
                ],
                "exit_code": 1,
                "stderr": (
                    'Error from server (NotFound): pods '
                    f'"{state.DONOR_POD_NAME}" not found'
                ),
            },
        }

    def writer_receipt(
        self,
        purpose: str,
        *,
        deleted_at: str,
        checked_at: str | None = None,
        volume_handle: str | None = None,
    ) -> dict[str, object]:
        pvc = self.pvc_identity()
        if volume_handle is not None:
            pvc["volume_handle"] = volume_handle
        holder_pod = self.holder_pod_evidence(pvc)
        return {
            "schema": state.WRITER_EXCLUSION_SCHEMA,
            "status": "PASS",
            "purpose": purpose,
            "checked_at": checked_at or state._now(),
            "namespace": self.contract["storage"]["namespace"],
            "pvc": pvc,
            "donor": {
                "name": state.DONOR_POD_NAME,
                "uid": DONOR_UID,
                "absent": True,
                "uid_preconditioned_delete": True,
                "deleted_at": deleted_at,
            },
            "holder": {
                "name": state.HOLDER_POD_NAME,
                "uid": HOLDER_UID,
                "node_name": state.HOLDER_NODE_NAME,
                "ready": True,
                "read_only": True,
                "seed_subpath": self.contract["layout"]["seed_subpath"],
                "mount_path": state.HOLDER_MOUNT_PATH,
                "image": self.contract["images"]["probe"],
                "restart_policy": "Never",
                "pvc_name": pvc["name"],
                "pvc_uid": pvc["uid"],
                "pv_name": pvc["pv_name"],
                "pv_uid": pvc["pv_uid"],
                "csi_driver": pvc["csi_driver"],
                "volume_handle": pvc["volume_handle"],
                "pod_spec_sha256": state._pod_spec_sha256(holder_pod),
            },
            "active_writer_count": 0,
            "active_read_write_users": [],
            "evidence": self.writer_evidence(pvc, holder_pod),
        }

    def artifact_gate(self, validated_at: str | None = None) -> dict[str, object]:
        categories = {
            key: 0
            for key in (
                "open_file",
                "mmap",
                "cwd_root",
                "socket",
                "watch",
                "ghost",
                "remap",
                "other_identity",
            )
        }
        decode_images = [
            {
                "raw_name": name,
                "raw_sha256": "c" * 64,
                "decoded_name": f"{name}.json",
                "decoded_sha256": "d" * 64,
                "decode_argv": ["python3", "-m", "crit", "decode"],
                "exit_code": 0,
            }
            for name in ("inventory.img", "pstree.img")
        ]
        return {
            "schema": state.ARTIFACT_GATE_SCHEMA,
            "status": "PASS",
            "qualification": "artifact-gates-pass-live-clone-canary-pending",
            "contract_sha256": self.contract_sha,
            "validator_sha256": self.contract["artifact_validator"]["sha256"],
            "checkpoint_id": self.contract["candidate"]["checkpoint_id"],
            "artifact_version": self.contract["candidate"]["artifact_version"],
            "artifact_manifest_sha256": "8" * 64,
            "validated_at": validated_at or state._now(),
            "artifact_entries": [
                "inventory.img",
                "manifest.yaml",
                "pages-1.img",
                "pstree.img",
                "rootfs-diff.tar",
            ],
            "external_mount": {
                "path": "/tmp",
                "ext_mnt": dict(self.contract["artifact_gates"]["ext_mnt_exact"]),
                "bind_mount_dests": sorted(
                    self.contract["artifact_gates"]["bind_mount_dests_exact"]
                ),
            },
            "rootfs": {
                "path": "rootfs-diff.tar",
                "sha256": "9" * 64,
                "bytes": 1024,
                "member_count": 2,
                "member_type_counts": {
                    "regular": 1,
                    "directory": 1,
                    "symlink": 0,
                    "hardlink": 0,
                },
                "forbidden_tmp_member_count": 0,
            },
            "tmpfs_images": {
                "file_count": 0,
                "total_bytes": 0,
                "max_total_bytes": self.contract["artifact_gates"][
                    "tmpfs_images_max_total_bytes"
                ],
                "images": [],
            },
            "deleted_files": {
                "path": "deleted-files.json",
                "present": False,
                "sha256": None,
                "entry_count": 0,
                "forbidden_tmp_path_count": 0,
                "capture_source_sha256": self.contract["deleted_files_capture"][
                    "source_sha256"
                ],
                "empty_inventory_encoding": "file-absent",
            },
            "pages": {
                "file_count": 12,
                "bytes": self.contract["baseline"]["pages_bytes"],
                "baseline_bytes": self.contract["baseline"]["pages_bytes"],
                "growth_basis_points": 0.0,
                "max_growth_basis_points": 200,
                "effective_max_growth_basis_points": 200,
                "growth_receipt_sha256": None,
            },
            "crit": {
                "bundle_sha256": self.contract["crit_decoder"]["source_bundle_sha256"],
                "python_executable": "python3",
                "imports_preflight_ok": True,
                "images": decode_images,
                "metadata_image_count": len(decode_images),
                "decoded_image_count": len(decode_images),
                "tmp_identity_reference_count": 0,
                "allowed_external_tmp_reg_count": 5,
                "category_counts": categories,
                "decoder": self.contract["crit_decoder"],
            },
            "live_clone_canary_required": True,
            "live_clone_canary_completed": False,
        }

    def sealed_layout(self) -> tuple[dict[str, object], Path, str]:
        self.initialize()
        self.populate()
        copied = state.copy_seed(self.root, self.contract, self.contract_sha)
        copy_path = self.write_receipt("copy.json", copied)
        pre = state.observe_bracket(
            self.root, self.contract, self.contract_sha, "pre-capture"
        )
        pre_path = self.write_receipt("pre.json", pre)
        post = state.observe_bracket(
            self.root, self.contract, self.contract_sha, "post-capture"
        )
        post_path = self.write_receipt("post.json", post)
        deleted_at = state._now()
        deleted = state.observe_bracket(
            self.root, self.contract, self.contract_sha, "post-deletion"
        )
        deleted_path = self.write_receipt("deleted.json", deleted)
        writer = self.writer_receipt(
            "post-deletion-seal", deleted_at=deleted_at
        )
        writer_path = self.write_receipt("writer-seal.json", writer)
        artifact_path = self.write_receipt(
            "artifact.json", self.artifact_gate(validated_at=state._now())
        )
        sealed = state.seal_seed(
            self.root,
            self.contract,
            self.contract_sha,
            copy_path,
            pre_path,
            post_path,
            deleted_path,
            writer_path,
            artifact_path,
        )
        seal_path = self.write_receipt("seal.json", sealed)
        return sealed, seal_path, deleted_at

    def prepared_clone(self) -> tuple[dict[str, object], Path]:
        sealed, seal_path, deleted_at = self.sealed_layout()
        writer = self.writer_receipt("pre-clone", deleted_at=deleted_at)
        writer_path = self.write_receipt("writer-clone.json", writer)
        preparation = state.prepare_clone(
            self.root,
            self.contract,
            self.contract_sha,
            "run-one",
            seal_path,
            writer_path,
        )
        preparation_path = self.write_receipt(
            "clone-preparation.json", preparation
        )
        post_writer = self.writer_receipt("post-clone", deleted_at=deleted_at)
        post_writer_path = self.write_receipt("writer-post-clone.json", post_writer)
        clone = state.admit_clone(
            self.root,
            self.contract,
            self.contract_sha,
            "run-one",
            preparation_path,
            post_writer_path,
        )
        clone_path = self.write_receipt("clone.json", clone)
        self.assertEqual(sealed["seed"], clone["clone"])
        return clone, clone_path

    def delete_authorization(
        self, clone: dict[str, object], clone_path: Path
    ) -> dict[str, object]:
        return {
            "schema": state.DELETE_AUTH_SCHEMA,
            "status": "PASS",
            "run_id": clone["run_id"],
            "authorized_at": state._now(),
            "target": {
                "namespace": "nim-fast-start",
                "name": "b2-target-run-one",
                "uid": TARGET_UID,
                "absent": True,
            },
            "active_tmp_mount_users": 0,
            "target_cleanup_receipt_sha256": "b" * 64,
            "clone_receipt_sha256": hashlib.sha256(clone_path.read_bytes()).hexdigest(),
            "pvc": {
                "name": clone["pvc_name"],
                "uid": clone["pvc_uid"],
                "pv_name": clone["pv_name"],
                "pv_uid": clone["pv_uid"],
                "csi_driver": clone["csi_driver"],
                "volume_handle": clone["volume_handle"],
            },
        }

    def test_exact_lifecycle_copy_seal_prepare_and_uid_cleanup(self) -> None:
        clone, clone_path = self.prepared_clone()
        self.assertGreaterEqual(clone["copy_elapsed_seconds"], 0)
        self.assertEqual(clone["seed"], clone["clone"])
        self.assertTrue(clone["writer_exclusion_bracketed"])
        authorization = self.delete_authorization(clone, clone_path)
        authorization_path = self.write_receipt("delete-auth.json", authorization)
        deleted = state.delete_clone(
            self.root,
            self.contract,
            self.contract_sha,
            "run-one",
            clone_path,
            authorization_path,
        )
        self.assertTrue(deleted["clone_absent"])
        self.assertEqual(TARGET_UID, deleted["target_uid"])
        self.assertEqual(0, deleted["published_clone_count"])

    def test_atomic_copy_failure_never_publishes_partial_seed(self) -> None:
        self.initialize()
        self.populate()
        with mock.patch.object(
            state, "_copy_directory_contents", side_effect=state.StateError("injected")
        ):
            with self.assertRaisesRegex(state.StateError, "injected"):
                state.copy_seed(self.root, self.contract, self.contract_sha)
        self.assertFalse(self.seed.exists())
        self.assertEqual([], list((self.root / ".partial").iterdir()))

        with mock.patch.object(
            state,
            "_rename_noreplace",
            side_effect=state.StateError("racing destination"),
        ):
            with self.assertRaisesRegex(state.StateError, "racing destination"):
                state.copy_seed(self.root, self.contract, self.contract_sha)
        self.assertFalse(self.seed.exists())
        self.assertEqual([], list((self.root / ".partial").iterdir()))

    def test_seed_digest_drift_and_second_clone_are_rejected(self) -> None:
        clone, clone_path = self.prepared_clone()
        with self.assertRaisesRegex(state.StateError, "existing run clone"):
            state.prepare_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-two",
                self.receipts / "seal.json",
                self.receipts / "writer-clone.json",
            )
        authorization_path = self.write_receipt(
            "delete-auth.json", self.delete_authorization(clone, clone_path)
        )
        state.delete_clone(
            self.root,
            self.contract,
            self.contract_sha,
            "run-one",
            clone_path,
            authorization_path,
        )
        (self.seed / "unexpected").write_text("dirty", encoding="utf-8")
        fresh_writer = self.write_receipt(
            "writer-clone-2.json",
            self.writer_receipt("pre-clone", deleted_at=state._now()),
        )
        with self.assertRaisesRegex(state.StateError, "seal receipt"):
            state.prepare_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-two",
                self.receipts / "seal.json",
                fresh_writer,
            )

    def test_unsafe_tree_entries_are_rejected(self) -> None:
        cases: list[tuple[str, object]] = []

        def escaping(root: Path) -> None:
            outside = root.parent / "outside"
            outside.write_text("outside", encoding="utf-8")
            os.symlink("../../outside", root / "escape")

        def fifo(root: Path) -> None:
            os.mkfifo(root / "fifo")

        def unix_socket(root: Path) -> None:
            sock = socket.socket(socket.AF_UNIX)
            self.addCleanup(sock.close)
            sock.bind(str(root / "socket"))

        def hardlink(root: Path) -> None:
            source = root / "source"
            source.write_text("same inode", encoding="utf-8")
            os.link(source, root / "alias")

        def sparse(root: Path) -> None:
            with (root / "sparse").open("wb") as handle:
                handle.seek(4 * 1024 * 1024)
                handle.write(b"x")

        def xattr(root: Path) -> None:
            path = root / "xattr"
            path.write_text("xattr", encoding="utf-8")
            try:
                os.setxattr(path, "user.external_tmp_test", b"1")
            except OSError as exc:
                self.skipTest(f"test filesystem has no user xattr support: {exc}")

        cases.extend(
            [
                ("escaping symlink", escaping),
                ("FIFO", fifo),
                ("socket", unix_socket),
                ("hardlink", hardlink),
                ("sparse", sparse),
                ("xattr", xattr),
            ]
        )
        for label, build in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                build(root)  # type: ignore[operator]
                with self.assertRaises(state.StateError):
                    state.fingerprint_tree(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "device-fixture"
            path.write_bytes(b"")
            real = path.lstat()
            fake = os.stat_result(
                (
                    stat.S_IFCHR | 0o600,
                    real.st_ino,
                    real.st_dev,
                    1,
                    real.st_uid,
                    real.st_gid,
                    0,
                    real.st_atime,
                    real.st_mtime,
                    real.st_ctime,
                )
            )
            with mock.patch.object(Path, "lstat", return_value=fake):
                with self.assertRaisesRegex(state.StateError, "device"):
                    state._entry_record(root, path, b"device-fixture", real.st_dev)

    def test_receipt_publication_is_atomic_no_overwrite(self) -> None:
        path = self.receipts / "atomic.json"
        state._write_receipt(path, {"status": "PASS"})
        before = path.read_bytes()
        with self.assertRaises(state.StateError):
            state._write_receipt(path, {"status": "REPLACED"})
        self.assertEqual(before, path.read_bytes())
        self.assertEqual([], list(self.receipts.glob("*.partial")))
        self.assertEqual([], list(self.receipts.glob(".*.partial")))

    def test_bool_counts_identity_drift_and_unsafe_delete_fail_closed(self) -> None:
        clone, clone_path = self.prepared_clone()
        writer = self.writer_receipt("pre-clone", deleted_at=state._now())
        writer["active_writer_count"] = True
        writer_path = self.write_receipt("writer-bool.json", writer)
        with self.assertRaisesRegex(state.StateError, "nonnegative integer"):
            state._read_writer_exclusion(writer_path, self.contract, "pre-clone")

        authorization = self.delete_authorization(clone, clone_path)
        authorization["active_tmp_mount_users"] = True
        authorization_path = self.write_receipt("delete-bool.json", authorization)
        with self.assertRaisesRegex(state.StateError, "nonnegative integer"):
            state.delete_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-one",
                clone_path,
                authorization_path,
            )

        clone_dir = self.root / "runs" / "run-one"
        source = clone_dir / "hardlink-source"
        source.write_text("unsafe", encoding="utf-8")
        os.link(source, clone_dir / "hardlink-alias")
        safe_authorization_path = self.write_receipt(
            "delete-hardlink.json", self.delete_authorization(clone, clone_path)
        )
        with self.assertRaisesRegex(state.StateError, "hard-link"):
            state.delete_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-one",
                clone_path,
                safe_authorization_path,
            )
        self.assertTrue(clone_dir.is_dir())
        self.assertTrue((clone_dir / "nested" / "payload.bin").is_file())

    def test_receipt_tool_time_and_storage_identity_drift_are_rejected(self) -> None:
        _sealed, seal_path, deleted_at = self.sealed_layout()
        copy_receipt = json.loads(
            (self.receipts / "copy.json").read_text(encoding="utf-8")
        )
        copy_receipt["tool_sha256"] = "f" * 64
        bad_copy = self.write_receipt("copy-bad-tool.json", copy_receipt)
        with self.assertRaisesRegex(state.StateError, "pinned contract"):
            state._read_copy_receipt(bad_copy, self.contract, self.contract_sha)

        post = json.loads((self.receipts / "post.json").read_text(encoding="utf-8"))
        post["started_at"] = "2000-01-01T00:00:00Z"
        post["completed_at"] = "2000-01-01T00:00:01Z"
        bad_post = self.write_receipt("post-reversed.json", post)
        with self.assertRaisesRegex(state.StateError, "earlier"):
            state.seal_seed(
                self.root,
                self.contract,
                self.contract_sha,
                self.receipts / "copy.json",
                self.receipts / "pre.json",
                bad_post,
                self.receipts / "deleted.json",
                self.receipts / "writer-seal.json",
                self.receipts / "artifact.json",
            )

        drifted = self.writer_receipt(
            "pre-clone",
            deleted_at=deleted_at,
            volume_handle="computedisk-otheridentity",
        )
        drifted_path = self.write_receipt("writer-drifted.json", drifted)
        with self.assertRaisesRegex(state.StateError, "storage identity drifted"):
            state.prepare_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-one",
                seal_path,
                drifted_path,
            )

        stale = self.writer_receipt(
            "pre-clone",
            deleted_at=deleted_at,
            checked_at="2000-01-01T00:00:00Z",
        )
        stale_path = self.write_receipt("writer-stale.json", stale)
        with self.assertRaises(state.StateError):
            state.prepare_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-one",
                seal_path,
                stale_path,
            )

    def test_writer_exclusion_declared_facts_must_be_evidence_derived(self) -> None:
        deleted_at = state._now()

        def receipt() -> dict[str, object]:
            return self.writer_receipt("pre-clone", deleted_at=deleted_at)

        def read(value: dict[str, object], name: str) -> None:
            path = self.write_receipt(name, value)
            state._read_writer_exclusion(path, self.contract, "pre-clone")

        forged = receipt()
        forged["evidence"]["pods"]["items"].append(  # type: ignore[index]
            {
                "kind": "Pod",
                "metadata": {
                    "name": "rogue-writer",
                    "namespace": self.contract["storage"]["namespace"],
                    "uid": "88888888-8888-4888-8888-888888888888",
                },
                "spec": {
                    "volumes": [
                        {
                            "name": "tmp-state",
                            "persistentVolumeClaim": {
                                "claimName": self.contract["storage"]["pvc_name"]
                            },
                        }
                    ]
                },
                "status": {"phase": "Running"},
            }
        )
        with self.assertRaisesRegex(state.StateError, "re-derivation contradicts"):
            read(forged, "writer-forged-count.json")

        forged = receipt()
        forged["evidence"]["pv"]["spec"]["csi"]["volumeHandle"] = (  # type: ignore[index]
            "computedisk-differenthandle"
        )
        with self.assertRaisesRegex(state.StateError, "PV evidence contradicts"):
            read(forged, "writer-forged-pv.json")

        forged = receipt()
        forged["evidence"]["pods"]["items"][0]["metadata"]["uid"] = (  # type: ignore[index]
            "12121212-1212-4212-8212-121212121212"
        )
        with self.assertRaisesRegex(state.StateError, "read-only holder"):
            read(forged, "writer-forged-holder.json")

        forged = receipt()
        forged["evidence"]["pods"]["items"].append(  # type: ignore[index]
            {
                "kind": "Pod",
                "metadata": {
                    "name": state.DONOR_POD_NAME,
                    "namespace": self.contract["storage"]["namespace"],
                    "uid": DONOR_UID,
                },
                "spec": {"volumes": []},
                "status": {"phase": "Running"},
            }
        )
        with self.assertRaisesRegex(state.StateError, "still contains the donor"):
            read(forged, "writer-forged-donor.json")

        forged = receipt()
        forged["evidence"]["volumeattachments"]["items"].append(  # type: ignore[index]
            {
                "kind": "VolumeAttachment",
                "spec": {
                    "nodeName": "computeinstance-foreignnode",
                    "source": {
                        "persistentVolumeName": self.pvc_identity()["pv_name"]
                    },
                },
            }
        )
        with self.assertRaisesRegex(state.StateError, "attached beyond the holder"):
            read(forged, "writer-forged-attachment.json")

        forged = receipt()
        forged["evidence"]["donor_get_attempt"]["exit_code"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(state.StateError, "NotFound donor"):
            read(forged, "writer-forged-attempt.json")

        forged = receipt()
        forged["evidence"]["donor_get_attempt"]["argv"] = [  # type: ignore[index]
            "kubectl",
            "get",
            "pod",
            state.DONOR_POD_NAME,
            "-n",
            "some-other-namespace",
            "-o",
            "json",
        ]
        with self.assertRaisesRegex(state.StateError, "NotFound donor"):
            read(forged, "writer-forged-argv-namespace.json")

        forged = receipt()
        forged["holder"]["pod_spec_sha256"] = "7" * 64  # type: ignore[index]
        with self.assertRaisesRegex(state.StateError, "holder evidence contradicts"):
            read(forged, "writer-forged-spec-hash.json")

        forged = receipt()
        del forged["evidence"]
        with self.assertRaisesRegex(state.StateError, "keys do not match"):
            read(forged, "writer-missing-evidence.json")

    def test_collect_writer_exclusion_runs_kubectl_and_fails_closed(self) -> None:
        deleted_at = state._now()
        reference = self.writer_receipt("pre-clone", deleted_at=deleted_at)
        evidence = reference["evidence"]
        stub = self.base / "kubectl-stub"
        responses = self.base / "kubectl-responses"
        responses.mkdir()
        for name, document in (
            ("pvc.json", evidence["pvc"]),  # type: ignore[index]
            ("pv.json", evidence["pv"]),  # type: ignore[index]
            ("pods.json", evidence["pods"]),  # type: ignore[index]
            ("volumeattachments.json", evidence["volumeattachments"]),  # type: ignore[index]
        ):
            (responses / name).write_text(json.dumps(document), encoding="utf-8")
        stub.write_text(
            "#!/bin/sh\n"
            f"root='{responses}'\n"
            'case "$*" in\n'
            '  *persistentvolumeclaim*) cat "$root/pvc.json" ;;\n'
            '  *persistentvolume*) cat "$root/pv.json" ;;\n'
            '  *volumeattachments*) cat "$root/volumeattachments.json" ;;\n'
            f'  *"pod {state.DONOR_POD_NAME}"*) echo \'Error from server (NotFound): pods "{state.DONOR_POD_NAME}" not found\' >&2; exit 1 ;;\n'
            '  *pods*) cat "$root/pods.json" ;;\n'
            "  *) exit 3 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        collected = state.collect_writer_exclusion(
            self.contract,
            "pre-clone",
            [str(stub)],
            DONOR_UID,
            deleted_at,
        )
        collected_path = self.write_receipt("writer-collected.json", collected)
        readback, _ = state._read_writer_exclusion(
            collected_path, self.contract, "pre-clone"
        )
        self.assertEqual(0, readback["active_writer_count"])
        self.assertEqual(HOLDER_UID, readback["holder"]["uid"])
        self.assertEqual(
            readback["holder"]["pod_spec_sha256"],
            state._pod_spec_sha256(evidence["pods"]["items"][0]),  # type: ignore[index]
        )

        rogue_pods = json.loads((responses / "pods.json").read_text(encoding="utf-8"))
        rogue_pods["items"].append(
            {
                "kind": "Pod",
                "metadata": {
                    "name": "rogue-writer",
                    "namespace": self.contract["storage"]["namespace"],
                    "uid": "88888888-8888-4888-8888-888888888888",
                },
                "spec": {
                    "volumes": [
                        {
                            "name": "tmp-state",
                            "persistentVolumeClaim": {
                                "claimName": self.contract["storage"]["pvc_name"]
                            },
                        }
                    ]
                },
                "status": {"phase": "Running"},
            }
        )
        (responses / "pods.json").write_text(json.dumps(rogue_pods), encoding="utf-8")
        with self.assertRaises(state.StateError):
            state.collect_writer_exclusion(
                self.contract,
                "pre-clone",
                [str(stub)],
                DONOR_UID,
                deleted_at,
            )

    def test_stale_delete_authorization_is_rejected(self) -> None:
        clone, clone_path = self.prepared_clone()
        stale = self.delete_authorization(clone, clone_path)
        stale["authorized_at"] = "2000-01-01T00:00:00Z"
        stale_path = self.write_receipt("delete-stale.json", stale)
        with self.assertRaisesRegex(state.StateError, "no more than"):
            state.delete_clone(
                self.root,
                self.contract,
                self.contract_sha,
                "run-one",
                clone_path,
                stale_path,
            )
        self.assertTrue((self.root / "runs" / "run-one").is_dir())

    def test_contract_pins_exact_tool_sources(self) -> None:
        expected = json.loads(self.contract_path.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256((MODULE_DIR / "external_tmp_state.py").read_bytes()).hexdigest(),
            expected["tool"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                (MODULE_DIR / "validate_external_tmp_artifact.py").read_bytes()
            ).hexdigest(),
            expected["artifact_validator"]["sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                (MODULE_DIR / expected["crit_decoder"]["bundle_build_tool"]).read_bytes()
            ).hexdigest(),
            expected["crit_decoder"]["bundle_build_tool_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                (MODULE_DIR / expected["crit_decoder"]["source_bundle_filename"]).read_bytes()
            ).hexdigest(),
            expected["crit_decoder"]["source_bundle_sha256"],
        )
        with tarfile.open(
            MODULE_DIR / expected["crit_decoder"]["source_bundle_filename"], "r:gz"
        ) as archive:
            names = archive.getnames()
            self.assertEqual(len(names), len(set(names)))
            self.assertIn("COPYING", names)
            self.assertIn("crit/__main__.py", names)
            self.assertIn("pycriu/images/images.py", names)
            self.assertTrue(all(member.isfile() for member in archive.getmembers()))


if __name__ == "__main__":
    unittest.main()
