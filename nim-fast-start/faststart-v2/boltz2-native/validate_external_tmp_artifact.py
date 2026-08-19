#!/usr/bin/env python3
"""Offline artifact gates for the Boltz2 external-``/tmp`` candidate.

This validator does not run CRIU and never contacts Kubernetes, but it does
execute the source-pinned ``crit`` decoder itself: the reviewed bundle bytes
are hash-verified, safely extracted, and every CRIU metadata image is decoded
by a subprocess this validator launches.  No pre-decoded JSON and no
separately produced decode receipt is ever trusted as input.  A PASS remains
explicitly pending the mandatory live clone canary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Iterable

import yaml

import external_tmp_state as state


VALIDATOR_PATH = Path(__file__).resolve()
PAGES = re.compile(r"^pages-[1-9][0-9]*\.img$")
OPAQUE_IMAGE = re.compile(r"^tmpfs-.+\.tar\.gz\.img$")
ROOT_ARTIFACT_FILES = frozenset(
    {"manifest.yaml", "rootfs-diff.tar", "deleted-files.json"}
)
_ALLOWED_TAR_TYPES = frozenset(
    {
        tarfile.REGTYPE,
        tarfile.AREGTYPE,
        tarfile.DIRTYPE,
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
    }
)
CRITICAL_IMAGE_PATTERNS = (
    re.compile(r"^inventory\.img$"),
    re.compile(r"^pstree\.img$"),
    re.compile(r"^files\.img$"),
    re.compile(r"^fs-[1-9][0-9]*\.img$"),
    re.compile(r"^mm-[1-9][0-9]*\.img$"),
    re.compile(r"^mountpoints-[1-9][0-9]*\.img$"),
)
IDENTITY_CATEGORIES = (
    "open_file",
    "mmap",
    "cwd_root",
    "socket",
    "watch",
    "ghost",
    "remap",
    "other_identity",
)


class ArtifactError(ValueError):
    """The candidate artifact does not prove the external-state contract."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ArtifactError(f"manifest contains duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ArtifactError(f"{label} must be a regular non-symlink file")
    return path


def _directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ArtifactError(f"{label} must be a directory, not a symlink")
    return path.resolve(strict=True)


def _read_json(path: Path, label: str) -> tuple[Any, bytes]:
    raw = _regular(path, label).read_bytes()
    try:
        return json.loads(raw), raw
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"{label} is not strict JSON: {exc}") from exc


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ArtifactError(
            f"{label} keys differ; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )


def _normalized_artifact_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ArtifactError(f"{label} is not a path string")
    candidate = value
    while candidate.startswith("./"):
        candidate = candidate[2:]
    candidate = candidate.rstrip("/")
    if not candidate:
        return "."
    normalized = posixpath.normpath(candidate)
    if (
        candidate.startswith("/")
        or normalized != candidate
        or normalized == ".."
        or normalized.startswith("../")
        or "//" in candidate
    ):
        raise ArtifactError(f"{label} is not canonical and root-confined: {value!r}")
    return normalized


def _is_tmp_path(value: str) -> bool:
    return value == "tmp" or value.startswith("tmp/")


def _read_manifest(
    artifact: Path, contract: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], str]:
    path = _regular(artifact / "manifest.yaml", "candidate manifest")
    raw = path.read_bytes()
    try:
        manifest = yaml.load(raw, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ArtifactError(f"candidate manifest is invalid YAML: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ArtifactError("candidate manifest must be an object")
    if manifest.get("checkpointId") != contract["candidate"]["checkpoint_id"]:
        raise ArtifactError("manifest checkpointId is not the candidate identity")
    criu_dump = manifest.get("criuDump")
    if not isinstance(criu_dump, dict):
        raise ArtifactError("manifest lacks criuDump")
    criu = criu_dump.get("criu")
    if (
        not isinstance(criu, dict)
        or criu.get("imageIoMode") != contract["candidate"]["image_io_mode"]
    ):
        raise ArtifactError("manifest does not retain direct CRIU image I/O")
    ext_mnt = criu_dump.get("extMnt")
    expected_ext_mnt = contract["artifact_gates"]["ext_mnt_exact"]
    if not isinstance(ext_mnt, dict) or ext_mnt != expected_ext_mnt:
        raise ArtifactError(
            "manifest CRIU ExtMnt is not exactly the reviewed mapping set: "
            f"observed {sorted(ext_mnt) if isinstance(ext_mnt, dict) else ext_mnt!r}"
        )
    overlay = manifest.get("overlay")
    destinations = overlay.get("bindMountDests") if isinstance(overlay, dict) else None
    expected_dests = sorted(contract["artifact_gates"]["bind_mount_dests_exact"])
    if (
        not isinstance(destinations, list)
        or any(not isinstance(item, str) for item in destinations)
        or len(destinations) != len(set(destinations))
        or sorted(destinations) != expected_dests
    ):
        raise ArtifactError(
            "manifest Overlay.BindMountDests is not exactly the reviewed destination "
            f"set: observed {destinations!r}"
        )
    return manifest, {
        "path": "/tmp",
        "ext_mnt": dict(expected_ext_mnt),
        "bind_mount_dests": expected_dests,
    }, _sha256_bytes(raw)


def _symlink_target_forbidden(normalized: str, linkname: str) -> str | None:
    if not linkname or "\x00" in linkname:
        return "empty or unsafe symlink target"
    if linkname.startswith("/"):
        collapsed = posixpath.normpath(linkname)
        if collapsed == "/tmp" or collapsed.startswith("/tmp/"):
            return f"absolute symlink into /tmp: {linkname!r}"
        return None
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(normalized), linkname)
    )
    if resolved == ".." or resolved.startswith("../"):
        return f"symlink escapes the archive root: {linkname!r}"
    if _is_tmp_path(resolved):
        return f"relative symlink into tmp: {linkname!r}"
    return None


def _inspect_tar_members(
    archive: tarfile.TarFile, label: str
) -> dict[str, Any]:
    """Fail-closed structural inspection of every tar member.

    Beyond name normalization and /tmp exclusion, each member's *type* and
    *linkname* are gated: devices, FIFOs, sockets, and sparse members are
    rejected; symlink and hardlink targets must not couple back into /tmp,
    escape the archive root, or route later members through a symlink.
    """

    seen: dict[str, bytes] = {}
    counts = {"regular": 0, "directory": 0, "symlink": 0, "hardlink": 0}
    for member in archive:
        normalized = _normalized_artifact_path(member.name, f"{label} member")
        if normalized in seen:
            raise ArtifactError(f"{label} contains duplicate member: {normalized}")
        parts = normalized.split("/")
        for index in range(1, len(parts)):
            ancestor_type = seen.get("/".join(parts[:index]))
            if ancestor_type is not None and ancestor_type != tarfile.DIRTYPE:
                raise ArtifactError(
                    f"{label} member routes through a non-directory member: {normalized}"
                )
        if member.type not in _ALLOWED_TAR_TYPES:
            raise ArtifactError(
                f"{label} member {normalized} has forbidden type {member.type!r} "
                "(devices, FIFOs, and specials are rejected)"
            )
        if member.issparse():
            raise ArtifactError(f"{label} member is sparse: {normalized}")
        if _is_tmp_path(normalized):
            raise ArtifactError(
                f"{label} still contains forbidden /tmp payload: {normalized}"
            )
        if member.type == tarfile.SYMTYPE:
            reason = _symlink_target_forbidden(normalized, member.linkname)
            if reason is not None:
                raise ArtifactError(f"{label} member {normalized}: {reason}")
            counts["symlink"] += 1
        elif member.type == tarfile.LNKTYPE:
            target = _normalized_artifact_path(
                member.linkname, f"{label} hardlink target"
            )
            if _is_tmp_path(target):
                raise ArtifactError(
                    f"{label} hardlink couples into tmp: {normalized} -> {target}"
                )
            if seen.get(target) not in {tarfile.REGTYPE, tarfile.AREGTYPE}:
                raise ArtifactError(
                    f"{label} hardlink target is not an earlier regular member: "
                    f"{normalized} -> {target}"
                )
            counts["hardlink"] += 1
        elif member.type == tarfile.DIRTYPE:
            counts["directory"] += 1
        else:
            counts["regular"] += 1
        seen[normalized] = member.type
    return {"member_count": len(seen), "member_type_counts": counts}


def _inspect_rootfs(artifact: Path, contract: dict[str, Any]) -> dict[str, Any]:
    path = _regular(artifact / "rootfs-diff.tar", "rootfs diff")
    size = path.stat().st_size
    if size <= 0 or size > contract["artifact_gates"]["rootfs_diff_max_bytes"]:
        raise ArtifactError("rootfs diff exceeds 128 MiB or is empty")
    try:
        with tarfile.open(path, mode="r:*") as archive:
            inspected = _inspect_tar_members(archive, "rootfs tar")
    except (tarfile.TarError, OSError) as exc:
        raise ArtifactError(f"cannot inspect rootfs diff: {exc}") from exc
    return {
        "path": "rootfs-diff.tar",
        "sha256": _sha256_file(path),
        "bytes": size,
        "member_count": inspected["member_count"],
        "member_type_counts": inspected["member_type_counts"],
        "forbidden_tmp_member_count": 0,
    }


def _inspect_artifact_entries(
    artifact: Path, contract: dict[str, Any]
) -> list[str]:
    """Reject any artifact-directory entry no gate accounts for."""

    allowed_extra = set(contract["artifact_gates"]["allowed_extra_files"])
    names: list[str] = []
    with os.scandir(artifact) as entries:
        for entry in entries:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                raise ArtifactError(
                    f"artifact contains a non-regular entry: {entry.name}"
                )
            name = entry.name
            if (
                name in ROOT_ARTIFACT_FILES
                or name in allowed_extra
                or PAGES.fullmatch(name)
                or OPAQUE_IMAGE.fullmatch(name)
                or name.endswith(".img")
            ):
                names.append(name)
                continue
            raise ArtifactError(
                f"artifact contains an unreviewed entry outside every gate: {name}"
            )
    names.sort()
    return names


def _inspect_tmpfs_images(artifact: Path, contract: dict[str, Any]) -> dict[str, Any]:
    """Gate the previously opaque tmpfs payload images byte-for-byte.

    Every ``tmpfs-*.tar.gz.img`` must be a well-formed gzip tar whose members
    pass the same type/linkname/tmp gates as the rootfs diff, and the total
    byte count is capped so no payload can hide there uninspected.
    """

    maximum = contract["artifact_gates"]["tmpfs_images_max_total_bytes"]
    entries = sorted(
        (entry for entry in os.scandir(artifact) if OPAQUE_IMAGE.fullmatch(entry.name)),
        key=lambda item: item.name,
    )
    sizes: dict[str, int] = {}
    for entry in entries:
        path = _regular(Path(entry.path), f"tmpfs image {entry.name}")
        sizes[entry.name] = path.stat().st_size
    total = sum(sizes.values())
    if total > maximum:
        raise ArtifactError(
            f"tmpfs images exceed the reviewed total byte cap: {total}>{maximum}"
        )
    images: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(entry.path)
        try:
            with tarfile.open(path, mode="r:gz") as archive:
                inspected = _inspect_tar_members(archive, f"tmpfs image {entry.name}")
        except (tarfile.TarError, OSError) as exc:
            raise ArtifactError(
                f"tmpfs image {entry.name} is not an inspectable gzip tar: {exc}"
            ) from exc
        images.append(
            {
                "name": entry.name,
                "sha256": _sha256_file(path),
                "bytes": sizes[entry.name],
                "member_count": inspected["member_count"],
            }
        )
    return {
        "file_count": len(images),
        "total_bytes": total,
        "max_total_bytes": maximum,
        "images": images,
    }


def _inspect_deleted_files(
    artifact: Path, contract: dict[str, Any]
) -> dict[str, Any]:
    path = artifact / "deleted-files.json"
    if not os.path.lexists(path):
        return {
            "path": "deleted-files.json",
            "present": False,
            "sha256": None,
            "entry_count": 0,
            "forbidden_tmp_path_count": 0,
            "capture_source_sha256": contract["deleted_files_capture"][
                "source_sha256"
            ],
            "empty_inventory_encoding": contract["deleted_files_capture"][
                "empty_inventory_encoding"
            ],
        }
    value, raw = _read_json(path, "deleted-files inventory")
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ArtifactError("deleted-files inventory must be a JSON string array")
    normalized: list[str] = []
    for item in value:
        candidate = _normalized_artifact_path(item, "deleted-files entry")
        if candidate == "." or _is_tmp_path(candidate):
            raise ArtifactError(
                f"deleted-files inventory contains forbidden /tmp identity: {item!r}"
            )
        normalized.append(candidate)
    if len(normalized) != len(set(normalized)):
        raise ArtifactError("deleted-files inventory contains duplicates")
    return {
        "path": "deleted-files.json",
        "present": True,
        "sha256": _sha256_bytes(raw),
        "entry_count": len(normalized),
        "forbidden_tmp_path_count": 0,
        "capture_source_sha256": contract["deleted_files_capture"]["source_sha256"],
        "empty_inventory_encoding": contract["deleted_files_capture"][
            "empty_inventory_encoding"
        ],
    }


PAGES_GROWTH_RECEIPT_SCHEMA = "archvteams.nebius.ai/boltz2-pages-growth-review/v1"


def _read_pages_growth_receipt(
    path: Path, contract: dict[str, Any], observed_total: int
) -> tuple[dict[str, Any], bytes]:
    value, raw = _read_json(path, "pages-growth review receipt")
    if not isinstance(value, dict):
        raise ArtifactError("pages-growth review receipt must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "status",
            "checkpoint_id",
            "baseline_pages_bytes",
            "observed_pages_bytes",
            "max_allowed_basis_points",
            "tmp_backed_vma_bytes",
            "tmp_backed_vma_count",
            "analysis",
            "reviewed_at",
        },
        "pages-growth review receipt",
    )
    reviewed_cap = contract["artifact_gates"]["pages_growth_reviewed_max_basis_points"]
    if (
        value["schema"] != PAGES_GROWTH_RECEIPT_SCHEMA
        or value["status"] != "REVIEWED"
        or value["checkpoint_id"] != contract["candidate"]["checkpoint_id"]
        or value["baseline_pages_bytes"] != contract["baseline"]["pages_bytes"]
        or value["observed_pages_bytes"] != observed_total
        or isinstance(value["max_allowed_basis_points"], bool)
        or not isinstance(value["max_allowed_basis_points"], int)
        or value["max_allowed_basis_points"] > reviewed_cap
        or isinstance(value["tmp_backed_vma_bytes"], bool)
        or not isinstance(value["tmp_backed_vma_bytes"], int)
        or value["tmp_backed_vma_bytes"] < 0
        or isinstance(value["tmp_backed_vma_count"], bool)
        or not isinstance(value["tmp_backed_vma_count"], int)
        or value["tmp_backed_vma_count"] < 0
        or not isinstance(value["analysis"], str)
        or len(value["analysis"].strip()) < 40
    ):
        raise ArtifactError(
            "pages-growth review receipt does not exactly cover the observed artifact"
        )
    state._timestamp(value["reviewed_at"], "pages-growth reviewed_at")
    return value, raw


def _inspect_pages(
    artifact: Path,
    contract: dict[str, Any],
    growth_receipt_path: Path | None = None,
) -> dict[str, Any]:
    pages = sorted(
        (entry for entry in os.scandir(artifact) if PAGES.fullmatch(entry.name)),
        key=lambda item: item.name,
    )
    if not pages:
        raise ArtifactError("artifact contains no pages-N.img files")
    total = 0
    for entry in pages:
        path = Path(entry.path)
        _regular(path, f"page image {entry.name}")
        total += path.stat().st_size
    baseline = contract["baseline"]["pages_bytes"]
    basis_points = contract["artifact_gates"]["pages_growth_max_basis_points"]
    reviewed_cap = contract["artifact_gates"]["pages_growth_reviewed_max_basis_points"]
    maximum = baseline * (10_000 + basis_points) // 10_000
    growth_receipt_sha256: str | None = None
    effective_max = basis_points
    if total <= 0:
        raise ArtifactError("CRIU pages total is empty")
    if total > maximum:
        if growth_receipt_path is None:
            raise ArtifactError(
                f"CRIU pages grew above {basis_points} basis points: {total}>{maximum} "
                "and no reviewed growth receipt was provided"
            )
        receipt, raw = _read_pages_growth_receipt(growth_receipt_path, contract, total)
        effective_max = receipt["max_allowed_basis_points"]
        reviewed_maximum = baseline * (10_000 + effective_max) // 10_000
        if total > reviewed_maximum or effective_max > reviewed_cap:
            raise ArtifactError(
                f"CRIU pages exceed even the reviewed growth ceiling: {total}>{reviewed_maximum}"
            )
        growth_receipt_sha256 = _sha256_bytes(raw)
    growth = max(0.0, (total - baseline) * 10_000 / baseline)
    return {
        "file_count": len(pages),
        "bytes": total,
        "baseline_bytes": baseline,
        "growth_basis_points": round(growth, 9),
        "max_growth_basis_points": basis_points,
        "effective_max_growth_basis_points": effective_max,
        "growth_receipt_sha256": growth_receipt_sha256,
    }


def _metadata_image_names(artifact: Path) -> list[str]:
    names: list[str] = []
    with os.scandir(artifact) as entries:
        for entry in entries:
            if not entry.name.endswith(".img") or PAGES.fullmatch(entry.name):
                continue
            if OPAQUE_IMAGE.fullmatch(entry.name):
                _regular(Path(entry.path), f"opaque CRIU payload {entry.name}")
                continue
            _regular(Path(entry.path), f"CRIU metadata image {entry.name}")
            names.append(entry.name)
    names.sort()
    for pattern in CRITICAL_IMAGE_PATTERNS:
        if not any(pattern.fullmatch(name) for name in names):
            raise ArtifactError(
                f"artifact lacks required CRIU metadata image pattern {pattern.pattern}"
            )
    return names


def _category(name: str) -> str:
    if name == "files.img" or name.startswith("fdinfo-"):
        return "open_file"
    if name.startswith("mm-") or name.startswith("pagemap-"):
        return "mmap"
    if name.startswith("fs-"):
        return "cwd_root"
    if any(token in name for token in ("unixsk", "tcp", "udp", "packetsk")):
        return "socket"
    if any(token in name for token in ("inotify", "fanotify")):
        return "watch"
    if name.startswith("ghost-file-"):
        return "ghost"
    if name.startswith("remap-"):
        return "remap"
    return "other_identity"


def _walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk_json(item, path + (str(key),))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_json(item, path + (str(index),))


def _dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from _dicts(item)


def _tmp_mount_identity(decoded: dict[str, Any]) -> int | str:
    """Locate the single external /tmp mount entry and return its own mnt_id.

    Only the entry's exact ``mnt_id`` identifies the /tmp mount: parent,
    master, and shared ids belong to *other* mounts (the first live capture
    proved counting ``parent_mnt_id`` misattributes every root-mount file to
    /tmp).  The entry must also prove external binding via ``ext_key``.
    """

    candidates: list[dict[str, Any]] = []
    for item in _dicts(decoded):
        if item.get("mountpoint") == "/tmp":
            candidates.append(item)
        else:
            strings = [value for value in item.values() if isinstance(value, str)]
            if any(value == "/tmp" or value.startswith("/tmp/") for value in strings):
                if item.get("ext_key") == "/tmp" or item.get("mountpoint", "").startswith("/tmp/"):
                    raise ArtifactError(
                        "mountpoints metadata names an unexpected /tmp entry"
                    )
    if len(candidates) != 1:
        raise ArtifactError("decoded mountpoints must contain one exact /tmp entry")
    entry = candidates[0]
    if entry.get("ext_key") != "/tmp":
        raise ArtifactError(
            "decoded /tmp mount entry is not externally bound (ext_key != /tmp)"
        )
    mnt_id = entry.get("mnt_id")
    if isinstance(mnt_id, bool) or not isinstance(mnt_id, (int, str)):
        raise ArtifactError("decoded /tmp mount entry has no mount identity")
    return mnt_id


def _is_allowed_external_reg_entry(entry: dict[str, Any], tmp_mnt_id: int | str) -> bool:
    """A files.img REG entry pointing into the external /tmp mount.

    Such entries are pointers CRIU resolves inside the external volume at
    restore (e.g. mmapped Triton launcher shared objects); they carry no
    captured /tmp bytes and are the designed coupling to the seed clone.
    """

    if entry.get("type") != "REG":
        return False
    reg = entry.get("reg")
    if not isinstance(reg, dict):
        return False
    name = reg.get("name")
    return (
        reg.get("mnt_id") == tmp_mnt_id
        and isinstance(name, str)
        and name.startswith("/tmp/")
    )


def _safe_extract_bundle(bundle: Path, destination: Path) -> int:
    """Extract the hash-verified decoder bundle without trusting its members.

    Only regular files at normalized, root-confined paths are written; any
    symlink, hardlink, device, or traversal member fails the extraction.
    """

    count = 0
    try:
        with tarfile.open(bundle, mode="r:gz") as archive:
            for member in archive:
                normalized = _normalized_artifact_path(
                    member.name, "decoder bundle member"
                )
                if member.type == tarfile.DIRTYPE:
                    (destination / normalized).mkdir(parents=True, exist_ok=True)
                    continue
                if member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}:
                    raise ArtifactError(
                        f"decoder bundle member is not a regular file: {normalized}"
                    )
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ArtifactError(
                        f"decoder bundle member is unreadable: {normalized}"
                    )
                target = destination / normalized
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(extracted.read())
                count += 1
    except (tarfile.TarError, OSError) as exc:
        raise ArtifactError(f"cannot extract decoder bundle: {exc}") from exc
    if count == 0:
        raise ArtifactError("decoder bundle extracted zero files")
    return count


def _run_decoder_subprocess(
    argv: list[str], cwd: Path, decoder_dir: Path
) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONPATH": str(decoder_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C.UTF-8",
        "HOME": str(cwd),
    }
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArtifactError(
            f"pinned decoder subprocess failed to run: {type(exc).__name__}: {exc}"
        ) from exc


def _inspect_crit(
    artifact: Path,
    decoded_dir: Path,
    contract: dict[str, Any],
    bundle_path: Path,
    python_executable: str,
) -> dict[str, Any]:
    decoded_dir = _directory(decoded_dir, "decoded CRIU output directory")
    if os.listdir(decoded_dir):
        raise ArtifactError("decoded CRIU output directory must start empty")
    bundle_path = _regular(bundle_path, "pinned decoder bundle")
    expected_bundle_sha256 = contract["crit_decoder"]["source_bundle_sha256"]
    if _sha256_file(bundle_path) != expected_bundle_sha256:
        raise ArtifactError("pinned decoder bundle digest does not match the contract")
    expected_names = _metadata_image_names(artifact)
    records: list[dict[str, Any]] = []
    decoded_values: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="boltz2-crit-decoder-") as scratch:
        scratch_path = Path(scratch)
        decoder_dir = scratch_path / "decoder"
        decoder_dir.mkdir()
        _safe_extract_bundle(bundle_path, decoder_dir)
        preflight_argv = [
            python_executable,
            "-c",
            "import " + ", ".join(contract["crit_decoder"]["python_imports"]),
        ]
        preflight = _run_decoder_subprocess(preflight_argv, scratch_path, decoder_dir)
        if preflight.returncode != 0:
            raise ArtifactError(
                "pinned decoder import preflight failed: "
                f"{preflight.stderr.strip()[:400]}"
            )
        template = contract["crit_decoder"]["decode_argument_template"]
        for raw_name in expected_names:
            decoded_name = f"{raw_name}.json"
            raw_path = _regular(artifact / raw_name, f"raw CRIU image {raw_name}")
            decoded_path = decoded_dir / decoded_name
            argv = [
                python_executable,
                *[
                    item.format(
                        raw_image=str(raw_path), decoded_json=str(decoded_path)
                    )
                    for item in template
                ],
            ]
            completed = _run_decoder_subprocess(argv, scratch_path, decoder_dir)
            if completed.returncode != 0:
                raise ArtifactError(
                    f"pinned decoder failed on {raw_name} "
                    f"(exit {completed.returncode}): {completed.stderr.strip()[:400]}"
                )
            decoded_path = _regular(
                decoded_path, f"decoded CRIU image {decoded_name}"
            )
            decoded, _ = _read_json(decoded_path, f"decoded CRIU image {decoded_name}")
            decoded_values[raw_name] = decoded
            records.append(
                {
                    "raw_name": raw_name,
                    "raw_sha256": _sha256_file(raw_path),
                    "decoded_name": decoded_name,
                    "decoded_sha256": _sha256_file(decoded_path),
                    "decode_argv": argv,
                    "exit_code": 0,
                }
            )

    mount_names = [name for name in expected_names if name.startswith("mountpoints-")]
    if len(mount_names) != 1:
        raise ArtifactError("artifact must have exactly one mountpoints metadata image")
    tmp_mnt_id = _tmp_mount_identity(decoded_values[mount_names[0]])

    def _scan(category: str, value: Any) -> None:
        for json_path, item in _walk_json(value):
            if isinstance(item, str):
                stripped = item[1:] if item.startswith("/") else item
                if _is_tmp_path(stripped):
                    category_counts[category] += 1
            if json_path:
                key = json_path[-1].lower().replace("-", "_")
                if (
                    "mnt" in key
                    and "id" in key
                    and type(item) in {int, str}
                    and item == tmp_mnt_id
                ):
                    category_counts[category] += 1

    category_counts = {name: 0 for name in IDENTITY_CATEGORIES}
    allowed_external_reg = 0
    for raw_name, decoded in decoded_values.items():
        if raw_name in mount_names:
            continue
        category = _category(raw_name)
        entries = decoded.get("entries") if isinstance(decoded, dict) else None
        if raw_name == "files.img" and isinstance(entries, list):
            # REG entries resolved through the external /tmp mount are the
            # designed pointers into the immutable seed clone; everything
            # else in the file table must stay /tmp-free.
            remainder = {
                key: value for key, value in decoded.items() if key != "entries"
            }
            _scan(category, remainder)
            for entry in entries:
                if isinstance(entry, dict) and _is_allowed_external_reg_entry(
                    entry, tmp_mnt_id
                ):
                    allowed_external_reg += 1
                    continue
                _scan(category, entry)
        else:
            _scan(category, decoded)
    reference_count = sum(category_counts.values())
    if reference_count:
        nonzero = {key: value for key, value in category_counts.items() if value}
        raise ArtifactError(
            f"decoded CRIU retains /tmp identity-sensitive references: {nonzero}"
        )
    return {
        "bundle_sha256": expected_bundle_sha256,
        "python_executable": python_executable,
        "imports_preflight_ok": True,
        "images": records,
        "metadata_image_count": len(expected_names),
        "decoded_image_count": len(decoded_values),
        "tmp_identity_reference_count": 0,
        "allowed_external_tmp_reg_count": allowed_external_reg,
        "category_counts": category_counts,
        "decoder": contract["crit_decoder"],
    }


def validate_artifact(
    artifact: Path,
    decoded_dir: Path,
    contract: dict[str, Any],
    contract_sha256: str,
    *,
    bundle_path: Path | None = None,
    python_executable: str | None = None,
    pages_growth_receipt: Path | None = None,
) -> dict[str, Any]:
    artifact = _directory(artifact, "candidate artifact")
    if bundle_path is None:
        bundle_path = (
            VALIDATOR_PATH.parent / contract["crit_decoder"]["source_bundle_filename"]
        )
    if python_executable is None:
        python_executable = contract["crit_decoder"]["python_command"]
    _, external_mount, manifest_sha256 = _read_manifest(artifact, contract)
    receipt = {
        "schema": state.ARTIFACT_GATE_SCHEMA,
        "status": "PASS",
        "qualification": "artifact-gates-pass-live-clone-canary-pending",
        "contract_sha256": contract_sha256,
        "validator_sha256": contract["artifact_validator"]["sha256"],
        "checkpoint_id": contract["candidate"]["checkpoint_id"],
        "artifact_version": contract["candidate"]["artifact_version"],
        "artifact_manifest_sha256": manifest_sha256,
        "validated_at": state._now(),
        "artifact_entries": _inspect_artifact_entries(artifact, contract),
        "external_mount": external_mount,
        "rootfs": _inspect_rootfs(artifact, contract),
        "deleted_files": _inspect_deleted_files(artifact, contract),
        "pages": _inspect_pages(artifact, contract, pages_growth_receipt),
        "tmpfs_images": _inspect_tmpfs_images(artifact, contract),
        "crit": _inspect_crit(
            artifact, decoded_dir, contract, bundle_path, python_executable
        ),
        "live_clone_canary_required": True,
        "live_clone_canary_completed": False,
    }
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument(
        "--decoded-dir",
        type=Path,
        required=True,
        help="empty directory this validator fills with its own decoded JSON",
    )
    parser.add_argument(
        "--decoder-python",
        default=None,
        help="python interpreter with google.protobuf (default: contract value)",
    )
    parser.add_argument(
        "--pages-growth-receipt",
        type=Path,
        default=None,
        help="reviewed growth receipt admitting pages growth above the base gate",
    )
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        contract, contract_sha256 = state.load_contract(args.contract)
        actual_validator_sha256 = _sha256_file(VALIDATOR_PATH)
        if actual_validator_sha256 != contract["artifact_validator"]["sha256"]:
            raise ArtifactError("artifact validator source digest does not match contract")
        receipt = validate_artifact(
            args.artifact,
            args.decoded_dir,
            contract,
            contract_sha256,
            python_executable=args.decoder_python,
            pages_growth_receipt=args.pages_growth_receipt,
        )
        state._write_receipt(args.receipt_output, receipt)
    except (ArtifactError, state.StateError, OSError) as exc:
        print(f"external-tmp-artifact: refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
