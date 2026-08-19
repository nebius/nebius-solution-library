#!/usr/bin/env python3
"""Offline, fail-closed lifecycle tool for the Boltz2 external ``/tmp`` tree.

The tool never contacts Kubernetes.  A controller may mount the dedicated PVC
and invoke one action at a time.  Every copy is bracket-hashed and published by
one same-filesystem rename; every destructive action is confined to the exact
``runs/<run-id>`` directory selected by the reviewed contract.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import errno
import hashlib
import json
import math
import os
import posixpath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT_SCHEMA = "archvteams.nebius.ai/boltz2-external-tmp-contract/v1"
INITIALIZE_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-layout-initialization/v1"
COPY_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-seed-copy/v1"
SEAL_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-seed-seal/v1"
OBSERVATION_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-tree-observation/v1"
WRITER_EXCLUSION_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-writer-exclusion/v2"
CLONE_PREPARATION_SCHEMA = (
    "archvteams.nebius.ai/boltz2-tmp-run-clone-preparation/v1"
)
CLONE_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-run-clone/v1"
DELETE_AUTH_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-delete-authorization/v1"
DELETE_SCHEMA = "archvteams.nebius.ai/boltz2-tmp-run-clone-deletion/v1"
ARTIFACT_GATE_SCHEMA = "archvteams.nebius.ai/boltz2-external-tmp-artifact-gate/v2"
DONOR_POD_NAME = "boltz2-native-f7-external-tmp-donor"
HOLDER_POD_NAME = "boltz2-tmp-seed-holder-v2-t12"
HOLDER_NODE_NAME = "computeinstance-e00t12crqg6tw0kz65"
HOLDER_MOUNT_PATH = "/seed"
RUN_ID = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
OBSERVATION_PHASES = frozenset(
    {"pre-capture", "post-capture", "post-deletion", "post-cohort"}
)
WRITER_EXCLUSION_MAX_AGE_SECONDS = 300
TOOL_PATH = Path(__file__).resolve()
TOOL_DIR = TOOL_PATH.parent


class StateError(ValueError):
    """The requested filesystem transition is unsafe or does not match evidence."""


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise StateError(
            f"{label} keys do not match schema; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise StateError(f"{label} must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateError(f"cannot read {label}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{label} must be a JSON object")
    return value, raw


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_relative(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or posixpath.normpath(value) != value
        or value == ".."
        or value.startswith("../")
        or "//" in value
    ):
        raise StateError(f"{label} must be a normalized relative path")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise StateError(f"{label} must be a timestamp string")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise StateError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise StateError(f"{label} must carry a timezone")
    return parsed.astimezone(timezone.utc)


def _ordered_timestamps(
    earlier: Any, later: Any, earlier_label: str, later_label: str
) -> None:
    if _timestamp(earlier, earlier_label) > _timestamp(later, later_label):
        raise StateError(f"{later_label} is earlier than {earlier_label}")


def _require_fresh_timestamp(
    checked: Any, reference: Any, checked_label: str, reference_label: str
) -> None:
    checked_at = _timestamp(checked, checked_label)
    reference_at = _timestamp(reference, reference_label)
    age = (reference_at - checked_at).total_seconds()
    if age < 0 or age > WRITER_EXCLUSION_MAX_AGE_SECONDS:
        raise StateError(
            f"{checked_label} must be no more than "
            f"{WRITER_EXCLUSION_MAX_AGE_SECONDS}s before {reference_label}"
        )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise StateError(f"{label} must be a nonempty normalized string")
    return value


def _canonical_uuid(value: Any, label: str) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except ValueError as exc:
        raise StateError(f"{label} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise StateError(f"{label} must be a canonical lowercase UUID")
    return value


def _volume_handle(value: Any, contract: dict[str, Any], label: str) -> str:
    # One provider-identity grammar shared with render.py: exact prefix followed
    # by lowercase alphanumerics only, so both gates accept the same handles.
    prefix = contract["storage"]["volume_handle_prefix"]
    pattern = re.compile(r"^" + re.escape(prefix) + r"[a-z0-9]+$")
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise StateError(f"{label} is not an immutable provider volume handle")
    return value


def _strict_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StateError(f"{label} must be a nonnegative integer")
    return value


def _nonnegative_number(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise StateError(f"{label} must be a finite nonnegative number")
    return float(value)


def validate_contract(value: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(
        value,
        {
            "schema",
            "experiment_id",
            "tool",
            "artifact_validator",
            "images",
            "crit_decoder",
            "deleted_files_capture",
            "storage",
            "layout",
            "candidate",
            "baseline",
            "artifact_gates",
        },
        "contract",
    )
    if value["schema"] != CONTRACT_SCHEMA:
        raise StateError("contract schema is not supported")
    if value["experiment_id"] != "boltz2-external-tmp-v1":
        raise StateError("contract experiment_id changed")
    tool = value["tool"]
    if not isinstance(tool, dict):
        raise StateError("contract.tool must be an object")
    _exact_keys(tool, {"filename", "sha256"}, "contract.tool")
    if tool["filename"] != TOOL_PATH.name or not isinstance(tool["sha256"], str) or not SHA256.fullmatch(tool["sha256"]):
        raise StateError("contract.tool does not pin this tool by SHA-256")

    artifact_validator = value["artifact_validator"]
    if not isinstance(artifact_validator, dict):
        raise StateError("contract.artifact_validator must be an object")
    _exact_keys(
        artifact_validator, {"filename", "sha256"}, "contract.artifact_validator"
    )
    if (
        artifact_validator["filename"] != "validate_external_tmp_artifact.py"
        or not isinstance(artifact_validator["sha256"], str)
        or not SHA256.fullmatch(artifact_validator["sha256"])
    ):
        raise StateError("contract does not pin the artifact validator by SHA-256")

    images = value["images"]
    if not isinstance(images, dict):
        raise StateError("contract.images must be an object")
    _exact_keys(images, {"nim", "worker", "probe"}, "contract.images")
    expected_images = {
        "nim": "nvcr.io/nim/mit/boltz2@sha256:0788c95c8b5b6c1a73a62c656b298ecc353a8187dc22b794f496ae40672c4c98",
        "worker": "cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:31e1dacd18b99aec1ab7e8ec8c933f260c9dcec687938b40c44c61274f930d86",
        "probe": "docker.io/library/python@sha256:356b0d18f9385f4bdcc673af60e1e64c9d1504952e4ec36ee32044c722a6bc4e",
    }
    if images != expected_images:
        raise StateError("contract image set changed from the matched baseline")

    crit_decoder = value["crit_decoder"]
    if not isinstance(crit_decoder, dict):
        raise StateError("contract.crit_decoder must be an object")
    _exact_keys(
        crit_decoder,
        {
            "container_image",
            "criu_repository",
            "criu_commit",
            "source_archive_sha256",
            "source_bundle_filename",
            "source_bundle_sha256",
            "bundle_build_tool",
            "bundle_build_tool_sha256",
            "python_command",
            "pythonpath",
            "python_imports",
            "decode_argument_template",
        },
        "contract.crit_decoder",
    )
    if crit_decoder != {
        "container_image": expected_images["nim"],
        "criu_repository": "https://github.com/checkpoint-restore/criu",
        "criu_commit": "91d552257809d0e5c7148190e9aa0372f13b76a0",
        "source_archive_sha256": "1f2a5a3f3b393feb57f18331f4af1284ea3b7883fadc2f8b2da70291fc1e0040",
        "source_bundle_filename": "boltz2-crit-decoder-bundle.tar.gz",
        "source_bundle_sha256": "113b40250517c7bfe423eb12ed5612f68b7e07966de77f39603121bbd369b2c8",
        "bundle_build_tool": "build_crit_decoder_bundle.py",
        "bundle_build_tool_sha256": "1deff4847516e258dec43a123fccd7c102a6da582bbe24a0b5eb8f9eb3a12093",
        "python_command": "python3",
        "pythonpath": "/decoder",
        "python_imports": ["crit", "pycriu", "google.protobuf"],
        "decode_argument_template": [
            "-m",
            "crit",
            "decode",
            "-i",
            "{raw_image}",
            "-o",
            "{decoded_json}",
        ],
    }:
        raise StateError("contract CRIU crit decoder identity changed")

    deleted_capture = value["deleted_files_capture"]
    if not isinstance(deleted_capture, dict):
        raise StateError("contract.deleted_files_capture must be an object")
    _exact_keys(
        deleted_capture,
        {
            "container_image",
            "repository",
            "commit",
            "source_path",
            "source_sha256",
            "empty_inventory_encoding",
        },
        "contract.deleted_files_capture",
    )
    if deleted_capture != {
        "container_image": expected_images["worker"],
        "repository": "https://github.com/ai-dynamo/dynamo.git",
        "commit": "f7f37be174d252590c4b56e25ff4262dd82466fd",
        "source_path": "deploy/snapshot/internal/runtime/overlay.go",
        "source_sha256": "dfd89a85f2bc52f3699bfa494c204f69c86ca6229f3c6fdbbfe2fcd64e9cb0e2",
        "empty_inventory_encoding": "file-absent",
    }:
        raise StateError("contract deleted-files capture source changed")

    storage = value["storage"]
    if not isinstance(storage, dict):
        raise StateError("contract.storage must be an object")
    _exact_keys(
        storage,
        {
            "namespace",
            "pvc_name",
            "access_modes",
            "requested_storage",
            "storage_class",
            "csi_driver",
            "volume_handle_prefix",
        },
        "contract.storage",
    )
    if storage != {
        "namespace": "nim-fast-start",
        "pvc_name": "boltz2-tmp-state-native-f7-v2",
        "access_modes": ["ReadWriteOnce"],
        "requested_storage": "20Gi",
        "storage_class": "compute-csi-default-sc",
        "csi_driver": "compute.csi.nebius.com",
        "volume_handle_prefix": "computedisk-",
    }:
        raise StateError("contract storage identity changed")

    layout = value["layout"]
    if not isinstance(layout, dict):
        raise StateError("contract.layout must be an object")
    _exact_keys(
        layout,
        {
            "working_root",
            "seed_root",
            "run_root",
            "partial_root",
            "working_subpath",
            "seed_version",
            "seed_subpath",
            "max_published_run_clones",
            "container_mount_path",
            "temp_environment",
        },
        "contract.layout",
    )
    expected_layout = {
        "working_root": "working",
        "seed_root": "seeds",
        "run_root": "runs",
        "partial_root": ".partial",
        "working_subpath": "working/boltz2-native-f7-external-tmp-v2",
        "seed_version": "boltz2-native-f7-tmp-seed-v2",
        "seed_subpath": "seeds/boltz2-native-f7-tmp-seed-v2",
        "max_published_run_clones": 1,
        "container_mount_path": "/tmp",
        "temp_environment": {"TMPDIR": "/tmp", "TEMP": "/tmp", "TMP": "/tmp"},
    }
    if layout != expected_layout:
        raise StateError("contract layout changed")
    if isinstance(layout["max_published_run_clones"], bool):
        raise StateError("contract clone limit must be the integer one")
    for field in (
        "working_root",
        "seed_root",
        "run_root",
        "partial_root",
        "working_subpath",
        "seed_subpath",
    ):
        _normalized_relative(layout[field], f"contract.layout.{field}")

    candidate = value["candidate"]
    if not isinstance(candidate, dict):
        raise StateError("contract.candidate must be an object")
    _exact_keys(candidate, {"checkpoint_id", "artifact_version", "image_io_mode"}, "contract.candidate")
    if candidate != {
        "checkpoint_id": "boltz2-native-f7-external-tmp-v2",
        "artifact_version": "2",
        "image_io_mode": "direct",
    }:
        raise StateError("contract candidate identity changed")

    baseline = value["baseline"]
    if not isinstance(baseline, dict):
        raise StateError("contract.baseline must be an object")
    _exact_keys(
        baseline,
        {"checkpoint_id", "artifact_manifest_sha256", "rootfs_diff_bytes", "pages_bytes"},
        "contract.baseline",
    )
    if baseline != {
        "checkpoint_id": "boltz2-native-f7-v1",
        "artifact_manifest_sha256": "6539b9f50a71c9f5fb6a3fbacd44f5d5ea41003539b6563682a38600d1492456",
        "rootfs_diff_bytes": 1908910080,
        "pages_bytes": 14321520640,
    }:
        raise StateError("contract baseline changed")
    for field in ("rootfs_diff_bytes", "pages_bytes"):
        _strict_nonnegative_int(baseline[field], f"contract.baseline.{field}")

    gates = value["artifact_gates"]
    if not isinstance(gates, dict):
        raise StateError("contract.artifact_gates must be an object")
    _exact_keys(
        gates,
        {
            "rootfs_diff_max_bytes",
            "pages_growth_max_basis_points",
            "pages_growth_reviewed_max_basis_points",
            "forbidden_rootfs_prefixes",
            "required_external_mount",
            "tmpfs_images_max_total_bytes",
            "allowed_extra_files",
            "ext_mnt_exact",
            "bind_mount_dests_exact",
        },
        "contract.artifact_gates",
    )
    expected_simple_gates = {
        "rootfs_diff_max_bytes": 134217728,
        "pages_growth_max_basis_points": 200,
        "pages_growth_reviewed_max_basis_points": 500,
        "forbidden_rootfs_prefixes": ["tmp", "tmp/"],
        "required_external_mount": "/tmp",
        "tmpfs_images_max_total_bytes": 134217728,
        "allowed_extra_files": ["criu.conf", "dump.log", "stats-dump"],
    }
    for key, expected in expected_simple_gates.items():
        if gates[key] != expected:
            raise StateError(f"contract artifact gate {key} changed")
    # The full expected mount sets come from the measured baseline manifest
    # (SHA-256 6539b9f5...) plus exactly the new /tmp externalization; they
    # live in the contract JSON, whose digest every receipt binds.  The tool
    # pins the invariants no reviewed set may lose.
    ext_mnt = gates["ext_mnt_exact"]
    if (
        not isinstance(ext_mnt, dict)
        or ext_mnt.get("/") != "/"
        or ext_mnt.get("/tmp") != "/tmp"
        or any(
            not isinstance(key, str)
            or not key.startswith("/")
            or not isinstance(item, str)
            or not item.startswith("/")
            for key, item in ext_mnt.items()
        )
    ):
        raise StateError(
            "contract ext_mnt_exact must be a rooted mapping containing /:/ and /tmp:/tmp"
        )
    dests = gates["bind_mount_dests_exact"]
    if (
        not isinstance(dests, list)
        or dests != sorted(set(dests))
        or "/tmp" not in dests
        or "/opt/nim/.cache" not in dests
        or any(not isinstance(item, str) or not item.startswith("/") for item in dests)
    ):
        raise StateError(
            "contract bind_mount_dests_exact must be sorted, unique, rooted, and /tmp-inclusive"
        )
    for field in ("rootfs_diff_max_bytes", "pages_growth_max_basis_points", "tmpfs_images_max_total_bytes"):
        _strict_nonnegative_int(gates[field], f"contract artifact gate {field}")
    return value


def load_contract(path: Path, *, verify_tool: bool = True) -> tuple[dict[str, Any], str]:
    value, raw = _read_json(path, "external-tmp contract")
    validate_contract(value)
    if verify_tool:
        actual = _sha256_file(TOOL_PATH)
        if actual != value["tool"]["sha256"]:
            raise StateError("external-tmp tool source digest does not match the contract")
        pinned_files = (
            (
                TOOL_DIR / value["artifact_validator"]["filename"],
                value["artifact_validator"]["sha256"],
                "artifact validator",
            ),
            (
                TOOL_DIR / value["crit_decoder"]["bundle_build_tool"],
                value["crit_decoder"]["bundle_build_tool_sha256"],
                "CRIT bundle build tool",
            ),
            (
                TOOL_DIR / value["crit_decoder"]["source_bundle_filename"],
                value["crit_decoder"]["source_bundle_sha256"],
                "CRIT source bundle",
            ),
        )
        for pinned_path, expected, label in pinned_files:
            if (
                pinned_path.is_symlink()
                or not pinned_path.is_file()
                or _sha256_file(pinned_path) != expected
            ):
                raise StateError(f"{label} digest does not match the contract")
    return value, _sha256_bytes(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _elapsed(start_ns: int) -> float:
    return round((time.monotonic_ns() - start_ns) / 1_000_000_000, 9)


def _state_root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise StateError("state root must be an existing directory, not a symlink")
    resolved = path.resolve(strict=True)
    if resolved == Path("/"):
        raise StateError("state root must not be filesystem root")
    return resolved


def _layout_path(root: Path, relative: str) -> Path:
    relative = _normalized_relative(relative, "layout path")
    candidate = root.joinpath(*relative.split("/"))
    if candidate == root or candidate.parent == Path("/"):
        raise StateError("layout path escaped the dedicated state root")
    return candidate


def _mode(value: os.stat_result) -> str:
    return format(stat.S_IMODE(value.st_mode), "04o")


def _path_b64(relative: bytes) -> str:
    return base64.b64encode(relative).decode("ascii")


def _regular_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _safe_symlink_target(root: Path, path: Path, target: str) -> None:
    if os.path.isabs(target):
        raise StateError(f"absolute symlink is forbidden: {path}")
    try:
        resolved = (path.parent / target).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise StateError(f"dangling or cyclic symlink is forbidden: {path}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise StateError(f"symlink escapes the state tree: {path}") from exc


def _entry_record(root: Path, path: Path, relative: bytes, root_device: int) -> dict[str, Any]:
    info = path.lstat()
    if info.st_dev != root_device:
        raise StateError(f"nested mount/device boundary is forbidden: {path}")
    try:
        xattrs = os.listxattr(path, follow_symlinks=False)
    except OSError as exc:
        raise StateError(f"cannot prove extended-attribute absence: {path}") from exc
    if xattrs:
        raise StateError(f"extended attributes are not supported by the exact-copy layout: {path}")
    common = {
        "path_b64": _path_b64(relative),
        "mode": _mode(info),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mtime_ns": info.st_mtime_ns,
    }
    if stat.S_ISDIR(info.st_mode):
        return {**common, "type": "directory"}
    if stat.S_ISREG(info.st_mode):
        if info.st_nlink != 1:
            raise StateError(f"hard-linked regular file is ambiguous: {path}")
        if info.st_size > 0 and info.st_blocks * 512 < info.st_size:
            raise StateError(f"sparse regular file layout is not preserved: {path}")
        return {
            **common,
            "type": "regular",
            "size": info.st_size,
            "sha256": _regular_sha256(path),
        }
    if stat.S_ISLNK(info.st_mode):
        target = os.readlink(path)
        _safe_symlink_target(root, path, target)
        return {
            **common,
            "type": "symlink",
            "target_b64": base64.b64encode(os.fsencode(target)).decode("ascii"),
        }
    raise StateError(f"device, FIFO, socket, or unsupported entry is forbidden: {path}")


def fingerprint_tree(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_dir():
        raise StateError(f"tree root must be a directory, not a symlink: {path}")
    root = path.resolve(strict=True)
    root_info = root.lstat()
    records: list[dict[str, Any]] = [
        _entry_record(root, root, b"", root_info.st_dev)
    ]

    def visit(directory: Path, relative: bytes) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: os.fsencode(item.name))
        except OSError as exc:
            raise StateError(f"cannot scan state tree: {directory}: {exc}") from exc
        for entry in entries:
            name = os.fsencode(entry.name)
            child_relative = name if not relative else relative + b"/" + name
            child = directory / entry.name
            record = _entry_record(root, child, child_relative, root_info.st_dev)
            records.append(record)
            if record["type"] == "directory":
                visit(child, child_relative)

    visit(root, b"")
    lines = [
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        for record in records
    ]
    manifest = b"\n".join(lines) + b"\n"
    type_counts = {
        kind: sum(record["type"] == kind for record in records)
        for kind in ("directory", "regular", "symlink")
    }
    return {
        "tree_sha256": _sha256_bytes(manifest),
        "manifest_sha256": _sha256_bytes(manifest),
        "entry_count": len(records),
        "directory_count": type_counts["directory"],
        "regular_file_count": type_counts["regular"],
        "symlink_count": type_counts["symlink"],
        "payload_bytes": sum(
            int(record.get("size", 0)) for record in records if record["type"] == "regular"
        ),
        "records": records,
    }


def _summary(fingerprint: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fingerprint.items() if key != "records"}


def _validate_fingerprint_summary(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError(f"{label} must be an object")
    _exact_keys(
        value,
        {
            "tree_sha256",
            "manifest_sha256",
            "entry_count",
            "directory_count",
            "regular_file_count",
            "symlink_count",
            "payload_bytes",
        },
        label,
    )
    for field in ("tree_sha256", "manifest_sha256"):
        if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
            raise StateError(f"{label}.{field} must be one lowercase SHA-256")
    if value["tree_sha256"] != value["manifest_sha256"]:
        raise StateError(f"{label} tree and manifest digests differ")
    for field in (
        "entry_count",
        "directory_count",
        "regular_file_count",
        "symlink_count",
        "payload_bytes",
    ):
        _strict_nonnegative_int(value[field], f"{label}.{field}")
    if value["directory_count"] < 1 or value["entry_count"] != (
        value["directory_count"]
        + value["regular_file_count"]
        + value["symlink_count"]
    ):
        raise StateError(f"{label} entry counts are inconsistent")
    return value


def _same_tree(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["tree_sha256"] == right["tree_sha256"] and left == right


def _apply_metadata(path: Path, source: os.stat_result, *, follow_symlinks: bool) -> None:
    if follow_symlinks:
        os.chmod(path, stat.S_IMODE(source.st_mode), follow_symlinks=True)
    try:
        os.chown(path, source.st_uid, source.st_gid, follow_symlinks=follow_symlinks)
    except PermissionError as exc:
        raise StateError("copy process cannot preserve exact UID/GID metadata") from exc
    try:
        os.utime(
            path,
            ns=(source.st_atime_ns, source.st_mtime_ns),
            follow_symlinks=follow_symlinks,
        )
    except (NotImplementedError, PermissionError) as exc:
        raise StateError("copy process cannot preserve exact timestamps") from exc


def _copy_regular(source: Path, destination: Path, source_info: os.stat_result) -> None:
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, read_flags)
    destination_fd = os.open(destination, write_flags, 0o600)
    try:
        with os.fdopen(source_fd, "rb", closefd=False) as input_handle, os.fdopen(
            destination_fd, "wb", closefd=False
        ) as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(destination_fd)
        os.fchmod(destination_fd, stat.S_IMODE(source_info.st_mode))
        os.fchown(destination_fd, source_info.st_uid, source_info.st_gid)
        os.utime(destination_fd, ns=(source_info.st_atime_ns, source_info.st_mtime_ns))
        os.fsync(destination_fd)
    except PermissionError as exc:
        raise StateError("copy process cannot preserve exact regular-file metadata") from exc
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def _copy_directory_contents(source: Path, destination: Path, root: Path) -> None:
    for entry in sorted(os.scandir(source), key=lambda item: os.fsencode(item.name)):
        source_path = source / entry.name
        destination_path = destination / entry.name
        info = source_path.lstat()
        if info.st_dev != root.lstat().st_dev:
            raise StateError(f"nested mount/device boundary is forbidden: {source_path}")
        if stat.S_ISDIR(info.st_mode):
            os.mkdir(destination_path, 0o700)
            _copy_directory_contents(source_path, destination_path, root)
            _apply_metadata(destination_path, info, follow_symlinks=True)
            descriptor = os.open(destination_path, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise StateError(f"hard-linked regular file is ambiguous: {source_path}")
            _copy_regular(source_path, destination_path, info)
        elif stat.S_ISLNK(info.st_mode):
            target = os.readlink(source_path)
            _safe_symlink_target(root, source_path, target)
            os.symlink(target, destination_path)
            _apply_metadata(destination_path, info, follow_symlinks=False)
        else:
            raise StateError(
                f"device, FIFO, socket, or unsupported entry is forbidden: {source_path}"
            )


def _rename_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish a directory while refusing a racing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise StateError("renameat2(RENAME_NOREPLACE) is required for publication")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise StateError("published destination appeared during atomic copy")
        raise OSError(error, os.strerror(error), str(destination))


def _copy_tree_atomic(source: Path, partial: Path, destination: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], float]:
    if partial.exists() or partial.is_symlink() or destination.exists() or destination.is_symlink():
        raise StateError("partial or published destination already exists")
    before = fingerprint_tree(source)
    copy_start = time.monotonic_ns()
    try:
        os.mkdir(partial, 0o700)
        _copy_directory_contents(source, partial, source.resolve(strict=True))
        _apply_metadata(partial, source.lstat(), follow_symlinks=True)
        descriptor = os.open(partial, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        copied = fingerprint_tree(partial)
        after = fingerprint_tree(source)
        if not _same_tree(before, after):
            raise StateError("source tree changed while it was being copied")
        if not _same_tree(before, copied):
            raise StateError("copied tree does not exactly match its source")
        _rename_noreplace(partial, destination)
        parent_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        if partial.is_dir() and not partial.is_symlink():
            shutil.rmtree(partial)
        elif partial.exists() or partial.is_symlink():
            partial.unlink()
        raise
    return before, after, copied, _elapsed(copy_start)


def _common_receipt(
    schema: str,
    action: str,
    contract_sha256: str,
    tool_sha256: str,
    started_at: str,
    start_ns: int,
) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": "PASS",
        "action": action,
        "contract_sha256": contract_sha256,
        "tool_sha256": tool_sha256,
        "started_at": started_at,
        "completed_at": _now(),
        "elapsed_seconds": _elapsed(start_ns),
    }


def _validate_common_receipt(
    value: dict[str, Any],
    *,
    schema: str,
    action: str,
    contract: dict[str, Any],
    contract_sha256: str,
    label: str,
) -> tuple[datetime, datetime]:
    if (
        value.get("schema") != schema
        or value.get("status") != "PASS"
        or value.get("action") != action
        or value.get("contract_sha256") != contract_sha256
        or value.get("tool_sha256") != contract["tool"]["sha256"]
    ):
        raise StateError(f"{label} identity does not match the pinned contract")
    started = _timestamp(value.get("started_at"), f"{label} started_at")
    completed = _timestamp(value.get("completed_at"), f"{label} completed_at")
    if started > completed:
        raise StateError(f"{label} completed before it started")
    _nonnegative_number(value.get("elapsed_seconds"), f"{label} elapsed_seconds")
    return started, completed


def _layout_directories(root: Path, contract: dict[str, Any]) -> dict[str, Path]:
    layout = contract["layout"]
    return {
        name: _layout_path(root, layout[field])
        for name, field in (
            ("working_root", "working_root"),
            ("seed_root", "seed_root"),
            ("run_root", "run_root"),
            ("partial_root", "partial_root"),
            ("working", "working_subpath"),
            ("seed", "seed_subpath"),
        )
    }


def initialize_layout(root: Path, contract: dict[str, Any], contract_sha256: str) -> dict[str, Any]:
    start_ns = time.monotonic_ns()
    started_at = _now()
    root = _state_root(root)
    allowed_existing = {"lost+found"}
    unexpected = {entry.name for entry in os.scandir(root)} - allowed_existing
    if unexpected:
        raise StateError(f"state root is not pristine: {sorted(unexpected)}")
    paths = _layout_directories(root, contract)
    created: list[Path] = []
    try:
        for name in ("working_root", "seed_root", "run_root", "partial_root"):
            path = paths[name]
            path.mkdir(mode=0o700)
            created.append(path)
        paths["working"].mkdir(mode=0o1777)
        created.append(paths["working"])
        os.chmod(paths["working"], 0o1777)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
    except Exception:
        for path in reversed(created):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
    receipt = _common_receipt(
        INITIALIZE_SCHEMA,
        "initialize",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt["created_subpaths"] = [
        contract["layout"][field]
        for field in (
            "working_root",
            "seed_root",
            "run_root",
            "partial_root",
            "working_subpath",
        )
    ]
    receipt["working"] = _summary(fingerprint_tree(paths["working"]))
    receipt["donor_writes_directly_to_seed"] = False
    return receipt


def _require_layout(root: Path, contract: dict[str, Any]) -> dict[str, Path]:
    root = _state_root(root)
    paths = _layout_directories(root, contract)
    for name in ("working_root", "seed_root", "run_root", "partial_root", "working"):
        path = paths[name]
        if path.is_symlink() or not path.is_dir():
            raise StateError(f"required layout directory is missing or unsafe: {name}")
    return paths


def _directory_names(path: Path) -> list[str]:
    names: list[str] = []
    for entry in os.scandir(path):
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            raise StateError(f"published state root contains a non-directory entry: {entry.path}")
        names.append(entry.name)
    return sorted(names)


def copy_seed(
    root: Path, contract: dict[str, Any], contract_sha256: str
) -> dict[str, Any]:
    start_ns = time.monotonic_ns()
    started_at = _now()
    paths = _require_layout(root, contract)
    if _directory_names(paths["run_root"]):
        raise StateError("cannot copy the seed while run clones exist")
    if _directory_names(paths["partial_root"]):
        raise StateError("cannot copy the seed with dirty partial state")
    partial = paths["partial_root"] / f"seed-{contract['layout']['seed_version']}"
    before, after, copied, copy_elapsed = _copy_tree_atomic(
        paths["working"], partial, paths["seed"]
    )
    receipt = _common_receipt(
        COPY_SCHEMA,
        "copy-seed",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "working_subpath": contract["layout"]["working_subpath"],
            "seed_version": contract["layout"]["seed_version"],
            "seed_subpath": contract["layout"]["seed_subpath"],
            "working_before": _summary(before),
            "working_after": _summary(after),
            "seed": _summary(copied),
            "copy_elapsed_seconds": copy_elapsed,
            "published_atomically": True,
        }
    )
    return receipt


def _read_copy_receipt(
    path: Path, contract: dict[str, Any], contract_sha256: str
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "seed-copy receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "action",
            "contract_sha256",
            "tool_sha256",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "working_subpath",
            "seed_version",
            "seed_subpath",
            "working_before",
            "working_after",
            "seed",
            "copy_elapsed_seconds",
            "published_atomically",
        },
        "seed-copy receipt",
    )
    _validate_common_receipt(
        value,
        schema=COPY_SCHEMA,
        action="copy-seed",
        contract=contract,
        contract_sha256=contract_sha256,
        label="seed-copy receipt",
    )
    if (
        value["published_atomically"] is not True
        or value["working_subpath"] != contract["layout"]["working_subpath"]
        or value["seed_version"] != contract["layout"]["seed_version"]
        or value["seed_subpath"] != contract["layout"]["seed_subpath"]
        or value["working_before"] != value["working_after"]
        or value["working_before"] != value["seed"]
    ):
        raise StateError("seed-copy receipt does not prove one stable exact copy")
    for field in ("working_before", "working_after", "seed"):
        _validate_fingerprint_summary(value[field], f"seed-copy receipt {field}")
    _nonnegative_number(value["copy_elapsed_seconds"], "seed-copy copy elapsed")
    _nonnegative_number(value["elapsed_seconds"], "seed-copy elapsed")
    return value, raw


def _read_observation(
    path: Path,
    phase: str,
    contract: dict[str, Any],
    contract_sha256: str,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, f"{phase} observation")
    tree_keys = {"seed"}
    if phase in {"pre-capture", "post-capture"}:
        tree_keys.add("working")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "action",
            "contract_sha256",
            "tool_sha256",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "phase",
            "working_subpath",
            "seed_version",
            "seed_subpath",
        }
        | tree_keys,
        f"{phase} observation",
    )
    _validate_common_receipt(
        value,
        schema=OBSERVATION_SCHEMA,
        action="observe",
        contract=contract,
        contract_sha256=contract_sha256,
        label=f"{phase} observation",
    )
    if (
        value["phase"] != phase
        or value["working_subpath"] != contract["layout"]["working_subpath"]
        or value["seed_version"] != contract["layout"]["seed_version"]
        or value["seed_subpath"] != contract["layout"]["seed_subpath"]
    ):
        raise StateError(f"{phase} observation does not match the contract")
    seed = _validate_fingerprint_summary(
        value["seed"], f"{phase} observation seed fingerprint"
    )
    _nonnegative_number(value["elapsed_seconds"], f"{phase} observation elapsed")
    if phase in {"pre-capture", "post-capture"}:
        working = _validate_fingerprint_summary(
            value["working"], f"{phase} observation working fingerprint"
        )
        if working != seed:
            raise StateError(f"{phase} observation does not prove working equals seed")
    return value, raw


def _evidence_object(value: Any, kind: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("kind") != kind:
        raise StateError(f"{label} evidence must be a raw Kubernetes {kind} document")
    return value


def _pvc_users_from_pod_list(
    pod_list: dict[str, Any], pvc_name: str, namespace: str
) -> list[dict[str, Any]]:
    """Re-derive the PVC's active users from an embedded raw PodList."""

    items = pod_list.get("items")
    if not isinstance(items, list):
        raise StateError("writer-exclusion PodList evidence has no items array")
    users: list[dict[str, Any]] = []
    for pod in items:
        if not isinstance(pod, dict):
            raise StateError("writer-exclusion PodList evidence has a non-object pod")
        metadata = pod.get("metadata")
        spec = pod.get("spec")
        status = pod.get("status")
        if (
            not isinstance(metadata, dict)
            or not isinstance(spec, dict)
            or not isinstance(status, dict)
        ):
            raise StateError("writer-exclusion pod evidence is structurally incomplete")
        if metadata.get("namespace") != namespace:
            raise StateError("writer-exclusion PodList evidence crosses namespaces")
        if status.get("phase") in {"Succeeded", "Failed"}:
            continue
        for volume in spec.get("volumes") or []:
            if not isinstance(volume, dict):
                continue
            claim = volume.get("persistentVolumeClaim")
            if not isinstance(claim, dict) or claim.get("claimName") != pvc_name:
                continue
            users.append(
                {
                    "pod": pod,
                    "name": metadata.get("name"),
                    "uid": metadata.get("uid"),
                    "read_only": claim.get("readOnly") is True,
                    "terminating": "deletionTimestamp" in metadata,
                }
            )
    return users


def _pod_spec_sha256(pod: dict[str, Any]) -> str:
    return _sha256_bytes(
        (
            json.dumps(
                pod["spec"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
            + "\n"
        ).encode("ascii")
    )


def _pod_is_ready(pod: dict[str, Any]) -> bool:
    for condition in (pod.get("status") or {}).get("conditions") or []:
        if (
            isinstance(condition, dict)
            and condition.get("type") == "Ready"
            and condition.get("status") == "True"
        ):
            return True
    return False


def _verify_writer_exclusion_evidence(
    value: dict[str, Any], contract: dict[str, Any]
) -> None:
    """Re-derive every declared writer-exclusion fact from raw evidence.

    Declared booleans and counts are never trusted on their own: each one must
    be recomputable from the embedded raw Kubernetes documents, so a forged
    receipt needs a complete, internally consistent forged cluster snapshot
    that the live replay can still disprove against the real cluster.
    """

    evidence = value["evidence"]
    if not isinstance(evidence, dict):
        raise StateError("writer-exclusion evidence must be an object")
    _exact_keys(
        evidence,
        {"pvc", "pv", "pods", "volumeattachments", "donor_get_attempt"},
        "writer-exclusion evidence",
    )
    declared_pvc = value["pvc"]
    namespace = contract["storage"]["namespace"]

    pvc_doc = _evidence_object(evidence["pvc"], "PersistentVolumeClaim", "PVC")
    pvc_meta = pvc_doc.get("metadata") or {}
    pvc_spec = pvc_doc.get("spec") or {}
    pvc_status = pvc_doc.get("status") or {}
    if (
        pvc_meta.get("name") != declared_pvc["name"]
        or pvc_meta.get("namespace") != namespace
        or pvc_meta.get("uid") != declared_pvc["uid"]
        or pvc_spec.get("volumeName") != declared_pvc["pv_name"]
        or pvc_spec.get("accessModes") != contract["storage"]["access_modes"]
        or pvc_status.get("phase") != "Bound"
    ):
        raise StateError("writer-exclusion PVC evidence contradicts the declared identity")

    pv_doc = _evidence_object(evidence["pv"], "PersistentVolume", "PV")
    pv_meta = pv_doc.get("metadata") or {}
    pv_spec = pv_doc.get("spec") or {}
    pv_csi = pv_spec.get("csi") or {}
    pv_claim_ref = pv_spec.get("claimRef") or {}
    if (
        pv_meta.get("name") != declared_pvc["pv_name"]
        or pv_meta.get("uid") != declared_pvc["pv_uid"]
        or pv_csi.get("driver") != declared_pvc["csi_driver"]
        or pv_csi.get("volumeHandle") != declared_pvc["volume_handle"]
        or pv_claim_ref.get("namespace") != namespace
        or pv_claim_ref.get("name") != declared_pvc["name"]
        or pv_claim_ref.get("uid") != declared_pvc["uid"]
    ):
        raise StateError("writer-exclusion PV evidence contradicts the declared identity")

    pod_list = _evidence_object(evidence["pods"], "PodList", "pod inventory")
    users = _pvc_users_from_pod_list(pod_list, declared_pvc["name"], namespace)
    derived_rw_users = sorted(
        {user["name"] for user in users if not user["read_only"] or user["terminating"]}
    )
    if derived_rw_users != value["active_read_write_users"]:
        raise StateError(
            "writer-exclusion evidence re-derivation contradicts the declared "
            f"read-write users: {derived_rw_users}"
        )
    if len(derived_rw_users) != value["active_writer_count"]:
        raise StateError("writer-exclusion declared writer count is not evidence-derived")
    holder = value["holder"]
    holder_users = [user for user in users if user["read_only"] and not user["terminating"]]
    if (
        len(users) != len(holder_users) + len(derived_rw_users)
        or len(holder_users) != 1
        or holder_users[0]["name"] != holder["name"]
        or holder_users[0]["uid"] != holder["uid"]
    ):
        raise StateError(
            "writer-exclusion evidence must show exactly the read-only holder using the claim"
        )
    holder_pod = holder_users[0]["pod"]
    holder_spec = holder_pod.get("spec") or {}
    containers = holder_spec.get("containers")
    if not isinstance(containers, list) or len(containers) != 1:
        raise StateError("writer-exclusion holder evidence must have one container")
    container = containers[0]
    holder_mounts = [
        mount
        for mount in container.get("volumeMounts") or []
        if isinstance(mount, dict) and mount.get("mountPath") == holder["mount_path"]
    ]
    if (
        holder_spec.get("nodeName") != holder["node_name"]
        or holder_spec.get("restartPolicy") != holder["restart_policy"]
        or container.get("image") != holder["image"]
        or len(holder_mounts) != 1
        or holder_mounts[0].get("subPath") != holder["seed_subpath"]
        or holder_mounts[0].get("readOnly") is not True
        or _pod_is_ready(holder_pod) is not (holder["ready"] is True)
        or _pod_spec_sha256(holder_pod) != holder["pod_spec_sha256"]
    ):
        raise StateError("writer-exclusion holder evidence contradicts the declared holder")

    attachments_doc = _evidence_object(
        evidence["volumeattachments"], "VolumeAttachmentList", "volume attachments"
    )
    attachment_items = attachments_doc.get("items")
    if not isinstance(attachment_items, list):
        raise StateError("writer-exclusion VolumeAttachmentList evidence has no items")
    attached_nodes = []
    for attachment in attachment_items:
        if not isinstance(attachment, dict):
            raise StateError("writer-exclusion volume attachment is not an object")
        spec = attachment.get("spec") or {}
        source = spec.get("source") or {}
        if source.get("persistentVolumeName") != declared_pvc["pv_name"]:
            continue
        attached_nodes.append(spec.get("nodeName"))
    if attached_nodes not in ([], [holder["node_name"]]):
        raise StateError(
            "writer-exclusion evidence shows the volume attached beyond the holder node: "
            f"{attached_nodes}"
        )

    donor = value["donor"]
    donor_names = {
        (pod.get("metadata") or {}).get("name")
        for pod in pod_list.get("items", [])
        if isinstance(pod, dict)
    }
    if donor["name"] in donor_names:
        raise StateError("writer-exclusion PodList evidence still contains the donor pod")
    attempt = evidence["donor_get_attempt"]
    if not isinstance(attempt, dict):
        raise StateError("writer-exclusion donor get attempt must be an object")
    _exact_keys(attempt, {"argv", "exit_code", "stderr"}, "donor get attempt")
    canonical_suffix = [
        "get",
        "pod",
        donor["name"],
        "-n",
        namespace,
        "-o",
        "json",
    ]
    argv = attempt["argv"]
    if (
        not isinstance(argv, list)
        or not all(isinstance(item, str) for item in argv)
        or len(argv) <= len(canonical_suffix)
        or argv[-len(canonical_suffix):] != canonical_suffix
        or _strict_nonnegative_int(attempt["exit_code"], "donor get exit code") == 0
        or not isinstance(attempt["stderr"], str)
        or "NotFound" not in attempt["stderr"]
    ):
        raise StateError(
            "writer-exclusion donor get attempt does not prove a NotFound donor"
        )


def _read_writer_exclusion(
    path: Path, contract: dict[str, Any], purpose: str
) -> tuple[dict[str, Any], bytes]:
    if purpose not in {"post-deletion-seal", "pre-clone", "post-clone"}:
        raise StateError("writer-exclusion purpose is unsupported")
    value, raw = _read_json(path, "writer-exclusion receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "purpose",
            "checked_at",
            "namespace",
            "pvc",
            "donor",
            "holder",
            "active_writer_count",
            "active_read_write_users",
            "evidence",
        },
        "writer-exclusion receipt",
    )
    if (
        value["schema"] != WRITER_EXCLUSION_SCHEMA
        or value["status"] != "PASS"
        or value["purpose"] != purpose
        or value["namespace"] != contract["storage"]["namespace"]
        or _strict_nonnegative_int(
            value["active_writer_count"], "writer-exclusion active writer count"
        )
        != 0
    ):
        raise StateError("writer-exclusion receipt is not an exact PASS")
    _timestamp(value["checked_at"], "writer-exclusion checked_at")
    if value["active_read_write_users"] != []:
        raise StateError("writer-exclusion receipt does not prove all RW users absent")
    pvc = value["pvc"]
    if not isinstance(pvc, dict):
        raise StateError("writer-exclusion PVC identity must be an object")
    _exact_keys(
        pvc,
        {"name", "uid", "pv_name", "pv_uid", "csi_driver", "volume_handle"},
        "writer-exclusion PVC",
    )
    if pvc["name"] != contract["storage"]["pvc_name"]:
        raise StateError("writer-exclusion receipt names the wrong PVC")
    _canonical_uuid(pvc["uid"], "writer-exclusion PVC UID")
    _canonical_uuid(pvc["pv_uid"], "writer-exclusion PV UID")
    if not isinstance(pvc["pv_name"], str) or not pvc["pv_name"]:
        raise StateError("writer-exclusion PV name is missing")
    if pvc["csi_driver"] != contract["storage"]["csi_driver"]:
        raise StateError("writer-exclusion CSI driver changed")
    _volume_handle(pvc["volume_handle"], contract, "writer-exclusion CSI volume handle")
    donor = value["donor"]
    if not isinstance(donor, dict):
        raise StateError("writer-exclusion donor identity must be an object")
    _exact_keys(
        donor,
        {"name", "uid", "absent", "uid_preconditioned_delete", "deleted_at"},
        "writer-exclusion donor",
    )
    if (
        donor["name"] != DONOR_POD_NAME
        or donor["absent"] is not True
        or donor["uid_preconditioned_delete"] is not True
    ):
        raise StateError("writer-exclusion receipt does not prove exact donor deletion")
    _canonical_uuid(donor["uid"], "writer-exclusion donor UID")
    _timestamp(donor["deleted_at"], "writer-exclusion donor deleted_at")
    holder = value["holder"]
    if not isinstance(holder, dict):
        raise StateError("writer-exclusion holder identity must be an object")
    _exact_keys(
        holder,
        {
            "name",
            "uid",
            "node_name",
            "ready",
            "read_only",
            "seed_subpath",
            "mount_path",
            "image",
            "restart_policy",
            "pvc_name",
            "pvc_uid",
            "pv_name",
            "pv_uid",
            "csi_driver",
            "volume_handle",
            "pod_spec_sha256",
        },
        "writer-exclusion holder",
    )
    if (
        holder["name"] != HOLDER_POD_NAME
        or holder["node_name"] != HOLDER_NODE_NAME
        or holder["ready"] is not True
        or holder["read_only"] is not True
        or holder["seed_subpath"] != contract["layout"]["seed_subpath"]
        or holder["mount_path"] != HOLDER_MOUNT_PATH
        or holder["image"] != contract["images"]["probe"]
        or holder["restart_policy"] != "Never"
        or holder["pvc_name"] != pvc["name"]
        or holder["pvc_uid"] != pvc["uid"]
        or holder["pv_name"] != pvc["pv_name"]
        or holder["pv_uid"] != pvc["pv_uid"]
        or holder["csi_driver"] != pvc["csi_driver"]
        or holder["volume_handle"] != pvc["volume_handle"]
    ):
        raise StateError("writer-exclusion holder does not protect the exact seed read-only")
    _canonical_uuid(holder["uid"], "writer-exclusion holder UID")
    if holder["uid"] == donor["uid"]:
        raise StateError("writer-exclusion donor and holder UIDs must differ")
    if not isinstance(holder["pod_spec_sha256"], str) or not SHA256.fullmatch(
        holder["pod_spec_sha256"]
    ):
        raise StateError("writer-exclusion holder PodSpec SHA-256 is malformed")
    _verify_writer_exclusion_evidence(value, contract)
    return value, raw


def _run_kubectl_json(
    kubectl: list[str], arguments: list[str], label: str
) -> dict[str, Any]:
    argv = [*kubectl, *arguments]
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StateError(f"cannot collect {label}: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        raise StateError(
            f"kubectl failed collecting {label} (exit {completed.returncode}): "
            f"{completed.stderr.strip()[:400]}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise StateError(f"{label} kubectl output is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{label} kubectl output is not a JSON object")
    return value


def collect_writer_exclusion(
    contract: dict[str, Any],
    purpose: str,
    kubectl: list[str],
    donor_uid: str,
    donor_deleted_at: str,
) -> dict[str, Any]:
    """Collect a writer-exclusion receipt from the live cluster.

    Every declared field is computed from raw kubectl documents that are then
    embedded verbatim in the receipt, so the reader can re-derive each claim
    and an auditor can replay the same queries against the cluster.
    """

    if purpose not in {"post-deletion-seal", "pre-clone", "post-clone"}:
        raise StateError("writer-exclusion purpose is unsupported")
    _canonical_uuid(donor_uid, "collector donor UID")
    _timestamp(donor_deleted_at, "collector donor deleted_at")
    namespace = contract["storage"]["namespace"]
    pvc_name = contract["storage"]["pvc_name"]
    checked_at = _now()
    pvc_doc = _run_kubectl_json(
        kubectl,
        ["get", "persistentvolumeclaim", pvc_name, "-n", namespace, "-o", "json"],
        "PVC evidence",
    )
    pv_name = ((pvc_doc.get("spec") or {}).get("volumeName")) or ""
    if not pv_name:
        raise StateError("collector PVC evidence is not bound to a PV")
    pv_doc = _run_kubectl_json(
        kubectl, ["get", "persistentvolume", pv_name, "-o", "json"], "PV evidence"
    )
    pods_doc = _run_kubectl_json(
        kubectl, ["get", "pods", "-n", namespace, "-o", "json"], "pod inventory"
    )
    attachments_doc = _run_kubectl_json(
        kubectl, ["get", "volumeattachments", "-o", "json"], "volume attachments"
    )
    donor_argv = [*kubectl, "get", "pod", DONOR_POD_NAME, "-n", namespace, "-o", "json"]
    try:
        donor_attempt = subprocess.run(
            donor_argv, capture_output=True, text=True, timeout=120, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise StateError(f"cannot attempt donor lookup: {exc}") from exc

    pv_csi = (pv_doc.get("spec") or {}).get("csi") or {}
    declared_pvc = {
        "name": pvc_name,
        "uid": (pvc_doc.get("metadata") or {}).get("uid"),
        "pv_name": pv_name,
        "pv_uid": (pv_doc.get("metadata") or {}).get("uid"),
        "csi_driver": pv_csi.get("driver"),
        "volume_handle": pv_csi.get("volumeHandle"),
    }
    users = _pvc_users_from_pod_list(pods_doc, pvc_name, namespace)
    rw_users = sorted(
        {user["name"] for user in users if not user["read_only"] or user["terminating"]}
    )
    holder_users = [user for user in users if user["read_only"] and not user["terminating"]]
    if len(holder_users) != 1:
        raise StateError(
            "collector requires exactly one read-only holder using the claim; "
            f"observed {len(holder_users)}"
        )
    holder_pod = holder_users[0]["pod"]
    holder_spec = holder_pod.get("spec") or {}
    containers = holder_spec.get("containers") or [{}]
    container = containers[0] if isinstance(containers, list) and containers else {}
    holder_mounts = [
        mount
        for mount in container.get("volumeMounts") or []
        if isinstance(mount, dict) and mount.get("mountPath") == HOLDER_MOUNT_PATH
    ]
    receipt = {
        "schema": WRITER_EXCLUSION_SCHEMA,
        "status": "PASS",
        "purpose": purpose,
        "checked_at": checked_at,
        "namespace": namespace,
        "pvc": declared_pvc,
        "donor": {
            "name": DONOR_POD_NAME,
            "uid": donor_uid,
            "absent": True,
            "uid_preconditioned_delete": True,
            "deleted_at": donor_deleted_at,
        },
        "holder": {
            "name": holder_users[0]["name"],
            "uid": holder_users[0]["uid"],
            "node_name": holder_spec.get("nodeName"),
            "ready": _pod_is_ready(holder_pod),
            "read_only": True,
            "seed_subpath": holder_mounts[0].get("subPath") if holder_mounts else None,
            "mount_path": HOLDER_MOUNT_PATH,
            "image": container.get("image"),
            "restart_policy": holder_spec.get("restartPolicy"),
            "pvc_name": declared_pvc["name"],
            "pvc_uid": declared_pvc["uid"],
            "pv_name": declared_pvc["pv_name"],
            "pv_uid": declared_pvc["pv_uid"],
            "csi_driver": declared_pvc["csi_driver"],
            "volume_handle": declared_pvc["volume_handle"],
            "pod_spec_sha256": _pod_spec_sha256(holder_pod),
        },
        "active_writer_count": len(rw_users),
        "active_read_write_users": rw_users,
        "evidence": {
            "pvc": pvc_doc,
            "pv": pv_doc,
            "pods": pods_doc,
            "volumeattachments": attachments_doc,
            "donor_get_attempt": {
                "argv": donor_argv,
                "exit_code": donor_attempt.returncode,
                "stderr": donor_attempt.stderr.strip()[:400],
            },
        },
    }
    # Fail closed at collection time exactly as the reader would.
    with tempfile.TemporaryDirectory() as scratch:
        probe_path = Path(scratch) / "writer-exclusion-probe.json"
        _write_receipt(probe_path, receipt)
        _read_writer_exclusion(probe_path, contract, purpose)
    return receipt


def _read_artifact_gate(
    path: Path, contract: dict[str, Any], contract_sha256: str
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "artifact-gate receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "qualification",
            "contract_sha256",
            "validator_sha256",
            "checkpoint_id",
            "artifact_version",
            "artifact_manifest_sha256",
            "validated_at",
            "artifact_entries",
            "external_mount",
            "rootfs",
            "deleted_files",
            "pages",
            "tmpfs_images",
            "crit",
            "live_clone_canary_required",
            "live_clone_canary_completed",
        },
        "artifact-gate receipt",
    )
    if (
        value["schema"] != ARTIFACT_GATE_SCHEMA
        or value["status"] != "PASS"
        or value["qualification"]
        != "artifact-gates-pass-live-clone-canary-pending"
        or value["contract_sha256"] != contract_sha256
        or value["validator_sha256"]
        != contract["artifact_validator"]["sha256"]
        or value["checkpoint_id"] != contract["candidate"]["checkpoint_id"]
        or value["artifact_version"] != contract["candidate"]["artifact_version"]
        or value["live_clone_canary_required"] is not True
        or value["live_clone_canary_completed"] is not False
    ):
        raise StateError("artifact-gate receipt is not the exact pending-canary PASS")
    _timestamp(value["validated_at"], "artifact-gate validated_at")
    for field in ("artifact_manifest_sha256",):
        if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
            raise StateError(f"artifact-gate {field} is malformed")

    entries = value["artifact_entries"]
    if (
        not isinstance(entries, list)
        or not entries
        or any(not isinstance(item, str) or not item for item in entries)
        or entries != sorted(entries)
        or len(entries) != len(set(entries))
    ):
        raise StateError("artifact-gate artifact_entries must be a sorted unique list")

    external = value["external_mount"]
    if not isinstance(external, dict):
        raise StateError("artifact-gate external_mount must be an object")
    _exact_keys(
        external,
        {"path", "ext_mnt", "bind_mount_dests"},
        "artifact-gate external_mount",
    )
    if (
        external["path"] != "/tmp"
        or external["ext_mnt"] != contract["artifact_gates"]["ext_mnt_exact"]
        or external["bind_mount_dests"]
        != sorted(contract["artifact_gates"]["bind_mount_dests_exact"])
    ):
        raise StateError("artifact-gate does not prove the exact mount allowlist")

    rootfs = value["rootfs"]
    if not isinstance(rootfs, dict):
        raise StateError("artifact-gate rootfs must be an object")
    _exact_keys(
        rootfs,
        {
            "path",
            "sha256",
            "bytes",
            "member_count",
            "member_type_counts",
            "forbidden_tmp_member_count",
        },
        "artifact-gate rootfs",
    )
    if (
        rootfs["path"] != "rootfs-diff.tar"
        or not isinstance(rootfs["sha256"], str)
        or not SHA256.fullmatch(rootfs["sha256"])
        or _strict_nonnegative_int(rootfs["bytes"], "artifact rootfs bytes")
        > contract["artifact_gates"]["rootfs_diff_max_bytes"]
        or _strict_nonnegative_int(
            rootfs["forbidden_tmp_member_count"], "forbidden tmp rootfs members"
        )
        != 0
    ):
        raise StateError("artifact rootfs gates are not exact PASS values")
    _strict_nonnegative_int(rootfs["member_count"], "artifact rootfs member count")
    type_counts = rootfs["member_type_counts"]
    if not isinstance(type_counts, dict):
        raise StateError("artifact rootfs member type counts must be an object")
    _exact_keys(
        type_counts,
        {"regular", "directory", "symlink", "hardlink"},
        "artifact rootfs member type counts",
    )
    if sum(
        _strict_nonnegative_int(count, f"rootfs {name} member count")
        for name, count in type_counts.items()
    ) != rootfs["member_count"]:
        raise StateError("artifact rootfs member type counts do not total member_count")

    tmpfs = value["tmpfs_images"]
    if not isinstance(tmpfs, dict):
        raise StateError("artifact-gate tmpfs_images must be an object")
    _exact_keys(
        tmpfs,
        {"file_count", "total_bytes", "max_total_bytes", "images"},
        "artifact-gate tmpfs_images",
    )
    if (
        tmpfs["max_total_bytes"]
        != contract["artifact_gates"]["tmpfs_images_max_total_bytes"]
        or _strict_nonnegative_int(tmpfs["total_bytes"], "tmpfs images total bytes")
        > tmpfs["max_total_bytes"]
        or not isinstance(tmpfs["images"], list)
        or _strict_nonnegative_int(tmpfs["file_count"], "tmpfs image count")
        != len(tmpfs["images"])
    ):
        raise StateError("artifact tmpfs-images gate is not an exact PASS")
    for image in tmpfs["images"]:
        if not isinstance(image, dict):
            raise StateError("artifact tmpfs image record must be an object")
        _exact_keys(
            image, {"name", "sha256", "bytes", "member_count"}, "tmpfs image record"
        )
        if (
            not isinstance(image["name"], str)
            or not image["name"]
            or not isinstance(image["sha256"], str)
            or not SHA256.fullmatch(image["sha256"])
        ):
            raise StateError("artifact tmpfs image record is malformed")
        _strict_nonnegative_int(image["bytes"], "tmpfs image bytes")
        _strict_nonnegative_int(image["member_count"], "tmpfs image member count")

    deleted = value["deleted_files"]
    if not isinstance(deleted, dict):
        raise StateError("artifact-gate deleted_files must be an object")
    _exact_keys(
        deleted,
        {
            "path",
            "present",
            "sha256",
            "entry_count",
            "forbidden_tmp_path_count",
            "capture_source_sha256",
            "empty_inventory_encoding",
        },
        "artifact-gate deleted_files",
    )
    if (
        deleted["path"] != "deleted-files.json"
        or type(deleted["present"]) is not bool
        or _strict_nonnegative_int(
            deleted["forbidden_tmp_path_count"], "forbidden deleted tmp paths"
        )
        != 0
        or deleted["capture_source_sha256"]
        != contract["deleted_files_capture"]["source_sha256"]
        or deleted["empty_inventory_encoding"]
        != contract["deleted_files_capture"]["empty_inventory_encoding"]
    ):
        raise StateError("artifact deleted-files gate is not an exact PASS")
    _strict_nonnegative_int(deleted["entry_count"], "deleted-files entry count")
    if deleted["present"] is True:
        if not isinstance(deleted["sha256"], str) or not SHA256.fullmatch(
            deleted["sha256"]
        ):
            raise StateError("present deleted-files inventory lacks a SHA-256")
    elif deleted["sha256"] is not None or deleted["entry_count"] != 0:
        raise StateError("absent deleted-files inventory is not empty")

    pages = value["pages"]
    if not isinstance(pages, dict):
        raise StateError("artifact-gate pages must be an object")
    _exact_keys(
        pages,
        {
            "file_count",
            "bytes",
            "baseline_bytes",
            "growth_basis_points",
            "max_growth_basis_points",
            "effective_max_growth_basis_points",
            "growth_receipt_sha256",
        },
        "artifact-gate pages",
    )
    effective = _strict_nonnegative_int(
        pages["effective_max_growth_basis_points"], "pages effective growth cap"
    )
    if (
        _strict_nonnegative_int(pages["file_count"], "pages file count") < 1
        or _strict_nonnegative_int(pages["bytes"], "pages bytes") < 1
        or pages["baseline_bytes"] != contract["baseline"]["pages_bytes"]
        or pages["max_growth_basis_points"]
        != contract["artifact_gates"]["pages_growth_max_basis_points"]
        or effective
        > contract["artifact_gates"]["pages_growth_reviewed_max_basis_points"]
        or _nonnegative_number(
            pages["growth_basis_points"], "pages growth basis points"
        )
        > effective
    ):
        raise StateError("artifact pages gate is not an exact PASS")
    if pages["growth_basis_points"] > pages["max_growth_basis_points"]:
        if not isinstance(pages["growth_receipt_sha256"], str) or not SHA256.fullmatch(
            pages["growth_receipt_sha256"]
        ):
            raise StateError(
                "over-base pages growth requires a bound reviewed growth receipt"
            )
    elif pages["growth_receipt_sha256"] is not None and (
        not isinstance(pages["growth_receipt_sha256"], str)
        or not SHA256.fullmatch(pages["growth_receipt_sha256"])
    ):
        raise StateError("artifact pages growth receipt digest is malformed")

    crit = value["crit"]
    if not isinstance(crit, dict):
        raise StateError("artifact-gate crit must be an object")
    _exact_keys(
        crit,
        {
            "bundle_sha256",
            "python_executable",
            "imports_preflight_ok",
            "images",
            "metadata_image_count",
            "decoded_image_count",
            "tmp_identity_reference_count",
            "allowed_external_tmp_reg_count",
            "category_counts",
            "decoder",
        },
        "artifact-gate crit",
    )
    _strict_nonnegative_int(
        crit["allowed_external_tmp_reg_count"],
        "allowed external /tmp REG entry count",
    )
    if (
        crit["bundle_sha256"] != contract["crit_decoder"]["source_bundle_sha256"]
        or crit["imports_preflight_ok"] is not True
        or not isinstance(crit["python_executable"], str)
        or not crit["python_executable"]
        or not isinstance(crit["images"], list)
        or _strict_nonnegative_int(
            crit["metadata_image_count"], "CRIT metadata image count"
        )
        < 1
        or _strict_nonnegative_int(
            crit["decoded_image_count"], "CRIT decoded image count"
        )
        != crit["metadata_image_count"]
        or len(crit["images"]) != crit["metadata_image_count"]
        or _strict_nonnegative_int(
            crit["tmp_identity_reference_count"], "CRIT tmp identity references"
        )
        != 0
        or crit["decoder"] != contract["crit_decoder"]
    ):
        raise StateError("artifact pinned-CRIT gate is not an exact PASS")
    for record in crit["images"]:
        if not isinstance(record, dict):
            raise StateError("artifact CRIT image record must be an object")
        _exact_keys(
            record,
            {
                "raw_name",
                "raw_sha256",
                "decoded_name",
                "decoded_sha256",
                "decode_argv",
                "exit_code",
            },
            "artifact CRIT image record",
        )
        if (
            not isinstance(record["raw_name"], str)
            or not record["raw_name"]
            or not isinstance(record["raw_sha256"], str)
            or not SHA256.fullmatch(record["raw_sha256"])
            or record["decoded_name"] != f"{record['raw_name']}.json"
            or not isinstance(record["decoded_sha256"], str)
            or not SHA256.fullmatch(record["decoded_sha256"])
            or not isinstance(record["decode_argv"], list)
            or not all(isinstance(item, str) for item in record["decode_argv"])
            or _strict_nonnegative_int(record["exit_code"], "CRIT decode exit code")
            != 0
        ):
            raise StateError("artifact CRIT image record is not an executed-decode PASS")
    expected_categories = {
        "open_file",
        "mmap",
        "cwd_root",
        "socket",
        "watch",
        "ghost",
        "remap",
        "other_identity",
    }
    if not isinstance(crit["category_counts"], dict):
        raise StateError("artifact CRIT category counts must be an object")
    _exact_keys(
        crit["category_counts"], expected_categories, "artifact CRIT category counts"
    )
    for category, count in crit["category_counts"].items():
        if _strict_nonnegative_int(count, f"CRIT {category} count") != 0:
            raise StateError("artifact CRIT category contains a /tmp identity reference")
    return value, raw


def seal_seed(
    root: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    copy_receipt_path: Path,
    pre_capture_path: Path,
    post_capture_path: Path,
    post_deletion_path: Path,
    writer_exclusion_path: Path,
    artifact_gate_path: Path,
) -> dict[str, Any]:
    start_ns = time.monotonic_ns()
    started_at = _now()
    paths = _require_layout(root, contract)
    if _directory_names(paths["run_root"]):
        raise StateError("cannot seal the seed while run clones exist")
    if _directory_names(paths["partial_root"]):
        raise StateError("cannot seal the seed with dirty partial state")
    copied, copied_raw = _read_copy_receipt(
        copy_receipt_path, contract, contract_sha256
    )
    pre, pre_raw = _read_observation(
        pre_capture_path, "pre-capture", contract, contract_sha256
    )
    post, post_raw = _read_observation(
        post_capture_path, "post-capture", contract, contract_sha256
    )
    deleted, deleted_raw = _read_observation(
        post_deletion_path, "post-deletion", contract, contract_sha256
    )
    writer, writer_raw = _read_writer_exclusion(
        writer_exclusion_path, contract, "post-deletion-seal"
    )
    artifact, artifact_raw = _read_artifact_gate(
        artifact_gate_path, contract, contract_sha256
    )
    _ordered_timestamps(
        copied["completed_at"],
        pre["started_at"],
        "seed-copy completed_at",
        "pre-capture started_at",
    )
    _ordered_timestamps(
        pre["completed_at"],
        post["started_at"],
        "pre-capture completed_at",
        "post-capture started_at",
    )
    _ordered_timestamps(
        post["completed_at"],
        writer["donor"]["deleted_at"],
        "post-capture completed_at",
        "donor deleted_at",
    )
    _ordered_timestamps(
        writer["donor"]["deleted_at"],
        deleted["started_at"],
        "donor deleted_at",
        "post-deletion observation started_at",
    )
    _ordered_timestamps(
        deleted["completed_at"],
        writer["checked_at"],
        "post-deletion observation completed_at",
        "writer-exclusion checked_at",
    )
    _ordered_timestamps(
        post["completed_at"],
        artifact["validated_at"],
        "post-capture completed_at",
        "artifact-gate validated_at",
    )
    _ordered_timestamps(
        writer["checked_at"],
        started_at,
        "writer-exclusion checked_at",
        "seal started_at",
    )
    _require_fresh_timestamp(
        writer["checked_at"],
        started_at,
        "writer-exclusion checked_at",
        "seal started_at",
    )
    _ordered_timestamps(
        artifact["validated_at"],
        started_at,
        "artifact-gate validated_at",
        "seal started_at",
    )
    if not (copied["seed"] == pre["seed"] == post["seed"] == deleted["seed"]):
        raise StateError("seed changed across copy, capture, or donor deletion")
    current = _summary(fingerprint_tree(paths["seed"]))
    if current != deleted["seed"]:
        raise StateError("seed changed after the post-deletion observation")
    receipt = _common_receipt(
        SEAL_SCHEMA,
        "seal",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "seed_version": contract["layout"]["seed_version"],
            "seed_subpath": contract["layout"]["seed_subpath"],
            "seed": current,
            "copy_receipt_sha256": _sha256_bytes(copied_raw),
            "pre_capture_observation_sha256": _sha256_bytes(pre_raw),
            "post_capture_observation_sha256": _sha256_bytes(post_raw),
            "post_deletion_observation_sha256": _sha256_bytes(deleted_raw),
            "writer_exclusion_receipt_sha256": _sha256_bytes(writer_raw),
            "artifact_gate_receipt_sha256": _sha256_bytes(artifact_raw),
            "artifact_manifest_sha256": artifact["artifact_manifest_sha256"],
            "donor_uid": writer["donor"]["uid"],
            "holder_uid": writer["holder"]["uid"],
            "holder_pod_spec_sha256": writer["holder"]["pod_spec_sha256"],
            "writer_exclusion_checked_at": writer["checked_at"],
            "pvc_name": writer["pvc"]["name"],
            "pvc_uid": writer["pvc"]["uid"],
            "pv_name": writer["pvc"]["pv_name"],
            "pv_uid": writer["pvc"]["pv_uid"],
            "csi_driver": writer["pvc"]["csi_driver"],
            "volume_handle": writer["pvc"]["volume_handle"],
            "donor_wrote_directly_to_seed": False,
            "working_seed_inode_identity_claimed": False,
            "metadata_changed_after_capture": False,
            "all_read_write_users_absent_at_seal": True,
            "logical_immutability_scope": (
                "valid-only-while-exact-holder-and-zero-read-write-users-remain"
            ),
            "live_clone_canary_required": True,
            "live_clone_canary_completed": False,
        }
    )
    return receipt


def _read_seal_receipt(
    path: Path, contract: dict[str, Any], contract_sha256: str
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "seed-seal receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "action",
            "contract_sha256",
            "tool_sha256",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "seed_version",
            "seed_subpath",
            "seed",
            "copy_receipt_sha256",
            "pre_capture_observation_sha256",
            "post_capture_observation_sha256",
            "post_deletion_observation_sha256",
            "writer_exclusion_receipt_sha256",
            "artifact_gate_receipt_sha256",
            "artifact_manifest_sha256",
            "donor_uid",
            "holder_uid",
            "holder_pod_spec_sha256",
            "writer_exclusion_checked_at",
            "pvc_name",
            "pvc_uid",
            "pv_name",
            "pv_uid",
            "csi_driver",
            "volume_handle",
            "donor_wrote_directly_to_seed",
            "working_seed_inode_identity_claimed",
            "metadata_changed_after_capture",
            "all_read_write_users_absent_at_seal",
            "logical_immutability_scope",
            "live_clone_canary_required",
            "live_clone_canary_completed",
        },
        "seed-seal receipt",
    )
    _validate_common_receipt(
        value,
        schema=SEAL_SCHEMA,
        action="seal",
        contract=contract,
        contract_sha256=contract_sha256,
        label="seed-seal receipt",
    )
    if (
        value["seed_version"] != contract["layout"]["seed_version"]
        or value["seed_subpath"] != contract["layout"]["seed_subpath"]
        or value["pvc_name"] != contract["storage"]["pvc_name"]
        or value["csi_driver"] != contract["storage"]["csi_driver"]
        or value["volume_handle"]
        != _volume_handle(value["volume_handle"], contract, "seed-seal volume handle")
        or value["donor_wrote_directly_to_seed"] is not False
        or value["working_seed_inode_identity_claimed"] is not False
        or value["metadata_changed_after_capture"] is not False
        or value["all_read_write_users_absent_at_seal"] is not True
        or value["logical_immutability_scope"]
        != "valid-only-while-exact-holder-and-zero-read-write-users-remain"
        or value["live_clone_canary_required"] is not True
        or value["live_clone_canary_completed"] is not False
    ):
        raise StateError("seed-seal receipt does not match the scoped immutable contract")
    _validate_fingerprint_summary(value["seed"], "seed-seal seed fingerprint")
    for field in (
        "copy_receipt_sha256",
        "pre_capture_observation_sha256",
        "post_capture_observation_sha256",
        "post_deletion_observation_sha256",
        "writer_exclusion_receipt_sha256",
        "artifact_gate_receipt_sha256",
        "artifact_manifest_sha256",
        "holder_pod_spec_sha256",
    ):
        if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
            raise StateError(f"seed-seal {field} is malformed")
    for field in ("donor_uid", "holder_uid", "pvc_uid", "pv_uid"):
        _canonical_uuid(value[field], f"seed-seal {field}")
    if value["donor_uid"] == value["holder_uid"]:
        raise StateError("seed-seal donor and holder UIDs collide")
    _nonempty_string(value["pv_name"], "seed-seal PV name")
    _timestamp(value["writer_exclusion_checked_at"], "seed-seal writer check")
    return value, raw


def observe_bracket(
    root: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    phase: str,
) -> dict[str, Any]:
    if phase not in OBSERVATION_PHASES:
        raise StateError("observation phase is not supported")
    start_ns = time.monotonic_ns()
    started_at = _now()
    paths = _require_layout(root, contract)
    if paths["seed"].is_symlink() or not paths["seed"].is_dir():
        raise StateError("versioned seed is missing or unsafe")
    seed = fingerprint_tree(paths["seed"])
    working: dict[str, Any] | None = None
    if phase in {"pre-capture", "post-capture"}:
        working = fingerprint_tree(paths["working"])
        if not _same_tree(working, seed):
            raise StateError("working tree and seed differ at the capture bracket")
    receipt = _common_receipt(
        OBSERVATION_SCHEMA,
        "observe",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "phase": phase,
            "working_subpath": contract["layout"]["working_subpath"],
            "seed_version": contract["layout"]["seed_version"],
            "seed_subpath": contract["layout"]["seed_subpath"],
            "seed": _summary(seed),
        }
    )
    if working is not None:
        receipt["working"] = _summary(working)
    return receipt


def _validate_run_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > 32 or not RUN_ID.fullmatch(value):
        raise StateError("run_id must be a lowercase DNS label of at most 32 characters")
    return value


def prepare_clone(
    root: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    run_id: str,
    seal_receipt_path: Path,
    writer_exclusion_path: Path,
) -> dict[str, Any]:
    run_id = _validate_run_id(run_id)
    start_ns = time.monotonic_ns()
    started_at = _now()
    sealed, sealed_raw = _read_seal_receipt(
        seal_receipt_path, contract, contract_sha256
    )
    writer, writer_raw = _read_writer_exclusion(
        writer_exclusion_path, contract, "pre-clone"
    )
    _ordered_timestamps(
        sealed["completed_at"],
        writer["checked_at"],
        "seed-seal completed_at",
        "pre-clone writer-exclusion checked_at",
    )
    _require_fresh_timestamp(
        writer["checked_at"],
        started_at,
        "pre-clone writer-exclusion checked_at",
        "clone preparation started_at",
    )
    identity_pairs = (
        ("pvc_name", "name"),
        ("pvc_uid", "uid"),
        ("pv_name", "pv_name"),
        ("pv_uid", "pv_uid"),
        ("csi_driver", "csi_driver"),
        ("volume_handle", "volume_handle"),
    )
    for seal_field, writer_field in identity_pairs:
        if sealed[seal_field] != writer["pvc"][writer_field]:
            raise StateError(
                f"pre-clone storage identity drifted at {seal_field}"
            )
    if (
        sealed["donor_uid"] != writer["donor"]["uid"]
        or sealed["holder_uid"] != writer["holder"]["uid"]
        or sealed["holder_pod_spec_sha256"]
        != writer["holder"]["pod_spec_sha256"]
    ):
        raise StateError("pre-clone donor or holder identity drifted since seal")
    paths = _require_layout(root, contract)
    published = _directory_names(paths["run_root"])
    if published:
        raise StateError(
            "serial clone contract permits no existing run clone before preparation: "
            + ",".join(published)
        )
    if _directory_names(paths["partial_root"]):
        raise StateError("cannot prepare a clone with dirty partial state")
    seed_before = fingerprint_tree(paths["seed"])
    expected_seed_sha256 = sealed["seed"]["tree_sha256"]
    if _summary(seed_before) != sealed["seed"]:
        raise StateError("seed tree no longer matches the exact seal receipt")
    partial = paths["partial_root"] / f"run-{run_id}"
    destination = paths["run_root"] / run_id
    before, after, copied, copy_elapsed = _copy_tree_atomic(
        paths["seed"], partial, destination
    )
    if before["tree_sha256"] != expected_seed_sha256:
        raise StateError("immutable seed changed before clone publication")
    receipt = _common_receipt(
        CLONE_PREPARATION_SCHEMA,
        "prepare",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "run_id": run_id,
            "seed_version": contract["layout"]["seed_version"],
            "seed_subpath": contract["layout"]["seed_subpath"],
            "clone_subpath": f"{contract['layout']['run_root']}/{run_id}",
            "seal_receipt_sha256": _sha256_bytes(sealed_raw),
            "writer_exclusion_receipt_sha256": _sha256_bytes(writer_raw),
            "writer_exclusion_checked_at": writer["checked_at"],
            "pvc_name": sealed["pvc_name"],
            "pvc_uid": sealed["pvc_uid"],
            "pv_name": sealed["pv_name"],
            "pv_uid": sealed["pv_uid"],
            "csi_driver": sealed["csi_driver"],
            "volume_handle": sealed["volume_handle"],
            "donor_uid": sealed["donor_uid"],
            "holder_uid": sealed["holder_uid"],
            "holder_pod_spec_sha256": sealed["holder_pod_spec_sha256"],
            "seed_before": _summary(before),
            "seed_after": _summary(after),
            "clone": _summary(copied),
            "copy_elapsed_seconds": copy_elapsed,
            "published_atomically": True,
            "published_clone_count": 1,
        }
    )
    return receipt


def _read_clone_preparation_receipt(
    path: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    run_id: str,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "run-clone preparation receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "action",
            "contract_sha256",
            "tool_sha256",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "run_id",
            "seed_version",
            "seed_subpath",
            "clone_subpath",
            "seal_receipt_sha256",
            "writer_exclusion_receipt_sha256",
            "writer_exclusion_checked_at",
            "pvc_name",
            "pvc_uid",
            "pv_name",
            "pv_uid",
            "csi_driver",
            "volume_handle",
            "donor_uid",
            "holder_uid",
            "holder_pod_spec_sha256",
            "seed_before",
            "seed_after",
            "clone",
            "copy_elapsed_seconds",
            "published_atomically",
            "published_clone_count",
        },
        "run-clone preparation receipt",
    )
    _validate_common_receipt(
        value,
        schema=CLONE_PREPARATION_SCHEMA,
        action="prepare",
        contract=contract,
        contract_sha256=contract_sha256,
        label="run-clone preparation receipt",
    )
    if (
        value["run_id"] != run_id
        or value["seed_version"] != contract["layout"]["seed_version"]
        or value["seed_subpath"] != contract["layout"]["seed_subpath"]
        or value["clone_subpath"] != f"{contract['layout']['run_root']}/{run_id}"
        or value["pvc_name"] != contract["storage"]["pvc_name"]
        or value["csi_driver"] != contract["storage"]["csi_driver"]
        or value["volume_handle"]
        != _volume_handle(
            value["volume_handle"], contract, "run-clone preparation volume handle"
        )
        or value["published_atomically"] is not True
        or _strict_nonnegative_int(
            value["published_clone_count"], "published clone count"
        )
        != 1
    ):
        raise StateError("run-clone preparation is not the exact copied clone")
    for field in ("seed_before", "seed_after", "clone"):
        _validate_fingerprint_summary(value[field], f"run-clone preparation {field}")
    if not (value["seed_before"] == value["seed_after"] == value["clone"]):
        raise StateError("run-clone preparation does not prove exact seed equality")
    for field in ("seal_receipt_sha256", "writer_exclusion_receipt_sha256"):
        if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
            raise StateError(f"run-clone preparation {field} is malformed")
    for field in ("pvc_uid", "pv_uid", "donor_uid", "holder_uid"):
        _canonical_uuid(value[field], f"run-clone preparation {field}")
    if value["donor_uid"] == value["holder_uid"]:
        raise StateError("run-clone preparation donor and holder UIDs collide")
    if not isinstance(value["holder_pod_spec_sha256"], str) or not SHA256.fullmatch(
        value["holder_pod_spec_sha256"]
    ):
        raise StateError("run-clone preparation holder PodSpec SHA is malformed")
    _nonempty_string(value["pv_name"], "run-clone preparation PV name")
    _timestamp(
        value["writer_exclusion_checked_at"], "run-clone preparation writer check"
    )
    _nonnegative_number(
        value["copy_elapsed_seconds"], "run-clone preparation copy elapsed"
    )
    return value, raw


def admit_clone(
    root: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    run_id: str,
    preparation_receipt_path: Path,
    post_writer_exclusion_path: Path,
) -> dict[str, Any]:
    run_id = _validate_run_id(run_id)
    start_ns = time.monotonic_ns()
    started_at = _now()
    prepared, prepared_raw = _read_clone_preparation_receipt(
        preparation_receipt_path, contract, contract_sha256, run_id
    )
    writer, writer_raw = _read_writer_exclusion(
        post_writer_exclusion_path, contract, "post-clone"
    )
    _ordered_timestamps(
        prepared["completed_at"],
        writer["checked_at"],
        "clone preparation completed_at",
        "post-clone writer-exclusion checked_at",
    )
    _require_fresh_timestamp(
        writer["checked_at"],
        started_at,
        "post-clone writer-exclusion checked_at",
        "clone admission started_at",
    )
    for prepared_field, writer_field in (
        ("pvc_name", "name"),
        ("pvc_uid", "uid"),
        ("pv_name", "pv_name"),
        ("pv_uid", "pv_uid"),
        ("csi_driver", "csi_driver"),
        ("volume_handle", "volume_handle"),
    ):
        if prepared[prepared_field] != writer["pvc"][writer_field]:
            raise StateError(
                f"post-clone storage identity drifted at {prepared_field}"
            )
    if (
        prepared["donor_uid"] != writer["donor"]["uid"]
        or prepared["holder_uid"] != writer["holder"]["uid"]
        or prepared["holder_pod_spec_sha256"]
        != writer["holder"]["pod_spec_sha256"]
    ):
        raise StateError("post-clone donor or holder identity drifted")
    paths = _require_layout(root, contract)
    if _directory_names(paths["run_root"]) != [run_id]:
        raise StateError("clone admission requires exactly the prepared run clone")
    if _directory_names(paths["partial_root"]):
        raise StateError("clone admission refuses dirty partial state")
    seed = _summary(fingerprint_tree(paths["seed"]))
    clone = _summary(fingerprint_tree(paths["run_root"] / run_id))
    if seed != prepared["seed_after"] or clone != prepared["clone"] or seed != clone:
        raise StateError("seed or clone changed before post-copy admission")
    receipt = _common_receipt(
        CLONE_SCHEMA,
        "admit",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "run_id": run_id,
            "seed_version": prepared["seed_version"],
            "seed_subpath": prepared["seed_subpath"],
            "clone_subpath": prepared["clone_subpath"],
            "preparation_receipt_sha256": _sha256_bytes(prepared_raw),
            "seal_receipt_sha256": prepared["seal_receipt_sha256"],
            "pre_writer_exclusion_receipt_sha256": prepared[
                "writer_exclusion_receipt_sha256"
            ],
            "post_writer_exclusion_receipt_sha256": _sha256_bytes(writer_raw),
            "pre_writer_exclusion_checked_at": prepared[
                "writer_exclusion_checked_at"
            ],
            "post_writer_exclusion_checked_at": writer["checked_at"],
            "pvc_name": prepared["pvc_name"],
            "pvc_uid": prepared["pvc_uid"],
            "pv_name": prepared["pv_name"],
            "pv_uid": prepared["pv_uid"],
            "csi_driver": prepared["csi_driver"],
            "volume_handle": prepared["volume_handle"],
            "donor_uid": prepared["donor_uid"],
            "holder_uid": prepared["holder_uid"],
            "holder_pod_spec_sha256": prepared["holder_pod_spec_sha256"],
            "seed": seed,
            "clone": clone,
            "copy_elapsed_seconds": prepared["copy_elapsed_seconds"],
            "preparation_elapsed_seconds": prepared["elapsed_seconds"],
            "published_atomically": True,
            "writer_exclusion_bracketed": True,
            "published_clone_count": 1,
        }
    )
    return receipt


def _read_clone_receipt(
    path: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    run_id: str,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "admitted run-clone receipt")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "action",
            "contract_sha256",
            "tool_sha256",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "run_id",
            "seed_version",
            "seed_subpath",
            "clone_subpath",
            "preparation_receipt_sha256",
            "seal_receipt_sha256",
            "pre_writer_exclusion_receipt_sha256",
            "post_writer_exclusion_receipt_sha256",
            "pre_writer_exclusion_checked_at",
            "post_writer_exclusion_checked_at",
            "pvc_name",
            "pvc_uid",
            "pv_name",
            "pv_uid",
            "csi_driver",
            "volume_handle",
            "donor_uid",
            "holder_uid",
            "holder_pod_spec_sha256",
            "seed",
            "clone",
            "copy_elapsed_seconds",
            "preparation_elapsed_seconds",
            "published_atomically",
            "writer_exclusion_bracketed",
            "published_clone_count",
        },
        "admitted run-clone receipt",
    )
    _validate_common_receipt(
        value,
        schema=CLONE_SCHEMA,
        action="admit",
        contract=contract,
        contract_sha256=contract_sha256,
        label="admitted run-clone receipt",
    )
    if (
        value["run_id"] != run_id
        or value["seed_version"] != contract["layout"]["seed_version"]
        or value["seed_subpath"] != contract["layout"]["seed_subpath"]
        or value["clone_subpath"] != f"{contract['layout']['run_root']}/{run_id}"
        or value["pvc_name"] != contract["storage"]["pvc_name"]
        or value["csi_driver"] != contract["storage"]["csi_driver"]
        or value["volume_handle"]
        != _volume_handle(
            value["volume_handle"], contract, "admitted run-clone volume handle"
        )
        or value["published_atomically"] is not True
        or value["writer_exclusion_bracketed"] is not True
        or _strict_nonnegative_int(
            value["published_clone_count"], "admitted published clone count"
        )
        != 1
    ):
        raise StateError("admitted run-clone receipt does not match the contract")
    for field in ("seed", "clone"):
        _validate_fingerprint_summary(value[field], f"admitted run-clone {field}")
    if value["seed"] != value["clone"]:
        raise StateError("admitted run-clone differs from its seed")
    for field in (
        "preparation_receipt_sha256",
        "seal_receipt_sha256",
        "pre_writer_exclusion_receipt_sha256",
        "post_writer_exclusion_receipt_sha256",
        "holder_pod_spec_sha256",
    ):
        if not isinstance(value[field], str) or not SHA256.fullmatch(value[field]):
            raise StateError(f"admitted run-clone {field} is malformed")
    for field in ("pvc_uid", "pv_uid", "donor_uid", "holder_uid"):
        _canonical_uuid(value[field], f"admitted run-clone {field}")
    if value["donor_uid"] == value["holder_uid"]:
        raise StateError("admitted clone donor and holder UIDs collide")
    pre_checked = _timestamp(
        value["pre_writer_exclusion_checked_at"], "pre-clone writer check"
    )
    post_checked = _timestamp(
        value["post_writer_exclusion_checked_at"], "post-clone writer check"
    )
    if pre_checked > post_checked:
        raise StateError("clone writer-exclusion bracket is reversed")
    _nonempty_string(value["pv_name"], "admitted run-clone PV name")
    _nonnegative_number(value["copy_elapsed_seconds"], "clone copy elapsed")
    _nonnegative_number(
        value["preparation_elapsed_seconds"], "clone preparation elapsed"
    )
    return value, raw


def validate_delete_authorization(
    value: dict[str, Any],
    run_id: str,
    clone: dict[str, Any],
    clone_sha256: str,
    reference_at: str,
) -> dict[str, Any]:
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "run_id",
            "authorized_at",
            "target",
            "active_tmp_mount_users",
            "target_cleanup_receipt_sha256",
            "clone_receipt_sha256",
            "pvc",
        },
        "delete authorization",
    )
    if value["schema"] != DELETE_AUTH_SCHEMA or value["status"] != "PASS":
        raise StateError("delete authorization is not a PASS receipt")
    if value["run_id"] != run_id:
        raise StateError("delete authorization run_id does not match")
    # A stale target-absence authorization must not be replayable arbitrarily
    # late: absence has to be re-proven within the same freshness window every
    # other cross-receipt check in this state machine enforces.
    _require_fresh_timestamp(
        value["authorized_at"],
        reference_at,
        "delete authorization authorized_at",
        "clone deletion started_at",
    )
    if _strict_nonnegative_int(
        value["active_tmp_mount_users"], "active_tmp_mount_users"
    ) != 0:
        raise StateError("run clone still has an active mount user")
    digest = value["target_cleanup_receipt_sha256"]
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise StateError("target cleanup receipt digest is malformed")
    if value["clone_receipt_sha256"] != clone_sha256:
        raise StateError("delete authorization does not bind the exact clone receipt")
    pvc = value["pvc"]
    if not isinstance(pvc, dict):
        raise StateError("delete authorization PVC identity must be an object")
    _exact_keys(
        pvc,
        {"name", "uid", "pv_name", "pv_uid", "csi_driver", "volume_handle"},
        "delete authorization PVC",
    )
    for authorization_field, clone_field in (
        ("name", "pvc_name"),
        ("uid", "pvc_uid"),
        ("pv_name", "pv_name"),
        ("pv_uid", "pv_uid"),
        ("csi_driver", "csi_driver"),
        ("volume_handle", "volume_handle"),
    ):
        if pvc[authorization_field] != clone[clone_field]:
            raise StateError("delete authorization PVC/PV/CSI identity drifted")
    target = value["target"]
    if not isinstance(target, dict):
        raise StateError("delete authorization target must be an object")
    _exact_keys(target, {"namespace", "name", "uid", "absent"}, "delete authorization target")
    if target["namespace"] != "nim-fast-start" or target["name"] != f"b2-target-{run_id}" or target["absent"] is not True:
        raise StateError("delete authorization does not prove the exact target absent")
    _canonical_uuid(target["uid"], "delete authorization target UID")
    return value


def _safe_remove_directory(path: Path, expected_parent: Path) -> dict[str, int]:
    if path.parent != expected_parent or path.is_symlink() or not path.is_dir():
        raise StateError("clone deletion target is not the exact run directory")
    # Complete the fail-closed structural preflight before unlinking the first
    # byte.  The fd-relative pass below repeats type/device/link checks to catch
    # a race between inspection and deletion.
    fingerprint_tree(path)
    root_device = path.lstat().st_dev
    counts = {"directories": 1, "regular_files": 0, "symlinks": 0}

    def remove_contents(directory_fd: int, directory_path: Path) -> None:
        with os.scandir(directory_fd) as entries:
            names = sorted((entry.name for entry in entries), key=os.fsencode)
        for name in names:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if info.st_dev != root_device:
                raise StateError("clone contains a nested mount/device boundary")
            if stat.S_ISDIR(info.st_mode):
                flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
                child_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    remove_contents(child_fd, directory_path / name)
                finally:
                    os.close(child_fd)
                os.rmdir(name, dir_fd=directory_fd)
                counts["directories"] += 1
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    raise StateError("clone deletion refuses hard-link ambiguity")
                os.unlink(name, dir_fd=directory_fd)
                counts["regular_files"] += 1
            elif stat.S_ISLNK(info.st_mode):
                os.unlink(name, dir_fd=directory_fd)
                counts["symlinks"] += 1
            else:
                raise StateError("clone deletion refuses device, FIFO, or socket entries")

    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(path, flags)
    try:
        remove_contents(root_fd, path)
    finally:
        os.close(root_fd)
    path.rmdir()
    parent_fd = os.open(expected_parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return counts


def delete_clone(
    root: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    run_id: str,
    clone_receipt_path: Path,
    authorization_path: Path,
) -> dict[str, Any]:
    run_id = _validate_run_id(run_id)
    start_ns = time.monotonic_ns()
    started_at = _now()
    clone_receipt, clone_receipt_raw = _read_clone_receipt(
        clone_receipt_path, contract, contract_sha256, run_id
    )
    authorization, authorization_raw = _read_json(
        authorization_path, "clone delete authorization"
    )
    validate_delete_authorization(
        authorization,
        run_id,
        clone_receipt,
        _sha256_bytes(clone_receipt_raw),
        started_at,
    )
    paths = _require_layout(root, contract)
    published = _directory_names(paths["run_root"])
    if published != [run_id]:
        raise StateError("published clone set does not equal the exact authorized run")
    clone = paths["run_root"] / run_id
    delete_start = time.monotonic_ns()
    removed = _safe_remove_directory(clone, paths["run_root"])
    delete_elapsed = _elapsed(delete_start)
    if clone.exists() or clone.is_symlink() or _directory_names(paths["run_root"]):
        raise StateError("clone deletion did not reach an exact absent state")
    receipt = _common_receipt(
        DELETE_SCHEMA,
        "delete",
        contract_sha256,
        contract["tool"]["sha256"],
        started_at,
        start_ns,
    )
    receipt.update(
        {
            "run_id": run_id,
            "clone_subpath": f"{contract['layout']['run_root']}/{run_id}",
            "authorization_sha256": _sha256_bytes(authorization_raw),
            "clone_receipt_sha256": _sha256_bytes(clone_receipt_raw),
            "target_uid": authorization["target"]["uid"],
            "removed": removed,
            "delete_elapsed_seconds": delete_elapsed,
            "clone_absent": True,
            "published_clone_count": 0,
        }
    )
    return receipt


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    payload = (
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    if str(path) == "-":
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir() or path.is_symlink() or os.path.lexists(path):
        raise StateError("receipt output must be a new file in an existing directory")
    partial = parent / f".{path.name}.{uuid.uuid4().hex}.partial"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(partial, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(descriptor)
        # link(2) is an atomic, no-overwrite publication primitive on the same
        # filesystem.  A racing target creation fails instead of being replaced.
        os.link(partial, parent / path.name, follow_symlinks=False)
        partial.unlink()
        parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("initialize")
    subparsers.add_parser("copy-seed")
    seal = subparsers.add_parser("seal")
    seal.add_argument("--copy-receipt", type=Path, required=True)
    seal.add_argument("--pre-capture-observation", type=Path, required=True)
    seal.add_argument("--post-capture-observation", type=Path, required=True)
    seal.add_argument("--post-deletion-observation", type=Path, required=True)
    seal.add_argument("--writer-exclusion-receipt", type=Path, required=True)
    seal.add_argument("--artifact-gate-receipt", type=Path, required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--phase", choices=sorted(OBSERVATION_PHASES), required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--seal-receipt", type=Path, required=True)
    prepare.add_argument("--writer-exclusion-receipt", type=Path, required=True)
    admit = subparsers.add_parser("admit")
    admit.add_argument("--run-id", required=True)
    admit.add_argument("--preparation-receipt", type=Path, required=True)
    admit.add_argument("--writer-exclusion-receipt", type=Path, required=True)
    delete = subparsers.add_parser("delete")
    delete.add_argument("--run-id", required=True)
    delete.add_argument("--clone-receipt", type=Path, required=True)
    delete.add_argument("--cleanup-authorization", type=Path, required=True)
    collect = subparsers.add_parser("collect-writer-exclusion")
    collect.add_argument(
        "--purpose",
        choices=["post-deletion-seal", "pre-clone", "post-clone"],
        required=True,
    )
    collect.add_argument("--kubectl", default="kubectl")
    collect.add_argument("--donor-uid", required=True)
    collect.add_argument("--donor-deleted-at", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        contract, contract_sha256 = load_contract(args.contract)
        if args.action == "initialize":
            receipt = initialize_layout(args.state_root, contract, contract_sha256)
        elif args.action == "copy-seed":
            receipt = copy_seed(args.state_root, contract, contract_sha256)
        elif args.action == "seal":
            receipt = seal_seed(
                args.state_root,
                contract,
                contract_sha256,
                args.copy_receipt,
                args.pre_capture_observation,
                args.post_capture_observation,
                args.post_deletion_observation,
                args.writer_exclusion_receipt,
                args.artifact_gate_receipt,
            )
        elif args.action == "observe":
            receipt = observe_bracket(
                args.state_root, contract, contract_sha256, args.phase
            )
        elif args.action == "prepare":
            receipt = prepare_clone(
                args.state_root,
                contract,
                contract_sha256,
                args.run_id,
                args.seal_receipt,
                args.writer_exclusion_receipt,
            )
        elif args.action == "admit":
            receipt = admit_clone(
                args.state_root,
                contract,
                contract_sha256,
                args.run_id,
                args.preparation_receipt,
                args.writer_exclusion_receipt,
            )
        elif args.action == "collect-writer-exclusion":
            receipt = collect_writer_exclusion(
                contract,
                args.purpose,
                shlex.split(args.kubectl),
                args.donor_uid,
                args.donor_deleted_at,
            )
        else:
            receipt = delete_clone(
                args.state_root,
                contract,
                contract_sha256,
                args.run_id,
                args.clone_receipt,
                args.cleanup_authorization,
            )
        _write_receipt(args.receipt_output, receipt)
    except (StateError, OSError) as exc:
        print(f"external-tmp-state: refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
