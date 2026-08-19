#!/usr/bin/env python3
"""Offline artifact gates for the Boltz2 external-``/tmp`` candidate.

This validator does not run CRIU and never contacts Kubernetes.  It consumes a
separately produced, source-pinned ``crit`` decode receipt and verifies every
referenced byte before inspecting decoded metadata.  A PASS remains explicitly
pending the mandatory live clone canary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import tarfile
from pathlib import Path
from typing import Any, Iterable

import yaml

import external_tmp_state as state


CRIT_RECEIPT_SCHEMA = "archvteams.nebius.ai/boltz2-pinned-crit-decode/v1"
VALIDATOR_PATH = Path(__file__).resolve()
PAGES = re.compile(r"^pages-[1-9][0-9]*\.img$")
OPAQUE_IMAGE = re.compile(r"^tmpfs-.+\.tar\.gz\.img$")
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
    if not isinstance(ext_mnt, dict) or ext_mnt.get("/tmp") != "/tmp":
        raise ArtifactError("manifest CRIU ExtMnt does not map exact /tmp to /tmp")
    overlay = manifest.get("overlay")
    destinations = overlay.get("bindMountDests") if isinstance(overlay, dict) else None
    if (
        not isinstance(destinations, list)
        or any(not isinstance(item, str) for item in destinations)
        or destinations.count("/tmp") != 1
    ):
        raise ArtifactError("manifest Overlay.BindMountDests must contain /tmp once")
    return manifest, {
        "path": "/tmp",
        "ext_mnt_value": "/tmp",
        "bind_mount_dest_count": 1,
    }, _sha256_bytes(raw)


def _inspect_rootfs(artifact: Path, contract: dict[str, Any]) -> dict[str, Any]:
    path = _regular(artifact / "rootfs-diff.tar", "rootfs diff")
    size = path.stat().st_size
    if size <= 0 or size > contract["artifact_gates"]["rootfs_diff_max_bytes"]:
        raise ArtifactError("rootfs diff exceeds 128 MiB or is empty")
    members: list[str] = []
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive:
                normalized = _normalized_artifact_path(
                    member.name, "rootfs tar member"
                )
                if normalized in members:
                    raise ArtifactError(
                        f"rootfs tar contains duplicate member: {normalized}"
                    )
                members.append(normalized)
                if _is_tmp_path(normalized):
                    raise ArtifactError(
                        f"rootfs tar still contains forbidden /tmp payload: {normalized}"
                    )
    except (tarfile.TarError, OSError) as exc:
        raise ArtifactError(f"cannot inspect rootfs diff: {exc}") from exc
    return {
        "path": "rootfs-diff.tar",
        "sha256": _sha256_file(path),
        "bytes": size,
        "member_count": len(members),
        "forbidden_tmp_member_count": 0,
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


def _inspect_pages(artifact: Path, contract: dict[str, Any]) -> dict[str, Any]:
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
    maximum = baseline * (10_000 + basis_points) // 10_000
    if total <= 0 or total > maximum:
        raise ArtifactError(
            f"CRIU pages grew above {basis_points} basis points: {total}>{maximum}"
        )
    growth = max(0.0, (total - baseline) * 10_000 / baseline)
    return {
        "file_count": len(pages),
        "bytes": total,
        "baseline_bytes": baseline,
        "growth_basis_points": round(growth, 9),
        "max_growth_basis_points": basis_points,
    }


def _metadata_image_names(artifact: Path) -> list[str]:
    names: list[str] = []
    for entry in os.scandir(artifact):
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


def _tmp_mount_ids(decoded: dict[str, Any]) -> set[int | str]:
    candidates: list[dict[str, Any]] = []
    for item in _dicts(decoded):
        strings = [value for value in item.values() if isinstance(value, str)]
        if "/tmp" in strings:
            if any(value.startswith("/tmp/") for value in strings):
                raise ArtifactError("mountpoints metadata names a /tmp descendant")
            candidates.append(item)
    if len(candidates) != 1:
        raise ArtifactError("decoded mountpoints must contain one exact /tmp entry")
    ids: set[int | str] = set()
    for key, value in candidates[0].items():
        normalized = key.lower().replace("-", "_")
        if "mnt" in normalized and "id" in normalized and type(value) in {int, str}:
            ids.add(value)
    if not ids:
        raise ArtifactError("decoded /tmp mount entry has no mount identity")
    return ids


def _inspect_crit(
    artifact: Path,
    decoded_dir: Path,
    receipt_path: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    decoded_dir = _directory(decoded_dir, "decoded CRIU directory")
    value, receipt_raw = _read_json(receipt_path, "pinned-crit decode receipt")
    if not isinstance(value, dict):
        raise ArtifactError("pinned-crit decode receipt must be an object")
    _exact_keys(
        value,
        {"schema", "status", "checkpoint_id", "generated_at", "decoder", "images"},
        "pinned-crit decode receipt",
    )
    if (
        value["schema"] != CRIT_RECEIPT_SCHEMA
        or value["status"] != "PASS"
        or value["checkpoint_id"] != contract["candidate"]["checkpoint_id"]
        or value["decoder"] != contract["crit_decoder"]
    ):
        raise ArtifactError("pinned-crit decode identity does not match the contract")
    state._timestamp(value["generated_at"], "pinned-crit generated_at")
    records = value["images"]
    if not isinstance(records, list):
        raise ArtifactError("pinned-crit images must be a list")
    expected_names = _metadata_image_names(artifact)
    observed_names: list[str] = []
    decoded_values: dict[str, Any] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ArtifactError("pinned-crit image record must be an object")
        _exact_keys(
            record,
            {
                "raw_name",
                "raw_sha256",
                "decoded_name",
                "decoded_sha256",
                "decode_argv",
            },
            "pinned-crit image record",
        )
        raw_name = record["raw_name"]
        if (
            not isinstance(raw_name, str)
            or Path(raw_name).name != raw_name
            or raw_name in observed_names
        ):
            raise ArtifactError("pinned-crit raw image name is unsafe or duplicated")
        decoded_name = f"{raw_name}.json"
        if record["decoded_name"] != decoded_name:
            raise ArtifactError("pinned-crit decoded filename is not deterministic")
        expected_argv = [
            contract["crit_decoder"]["python_command"],
            *[
                item.format(raw_image=raw_name, decoded_json=decoded_name)
                for item in contract["crit_decoder"]["decode_argument_template"]
            ],
        ]
        if record["decode_argv"] != expected_argv:
            raise ArtifactError("pinned-crit decode argv changed")
        raw_path = _regular(artifact / raw_name, f"raw CRIU image {raw_name}")
        decoded_path = _regular(
            decoded_dir / decoded_name, f"decoded CRIU image {decoded_name}"
        )
        if (
            record["raw_sha256"] != _sha256_file(raw_path)
            or record["decoded_sha256"] != _sha256_file(decoded_path)
        ):
            raise ArtifactError("pinned-crit raw or decoded digest mismatch")
        decoded, _ = _read_json(decoded_path, f"decoded CRIU image {decoded_name}")
        decoded_values[raw_name] = decoded
        observed_names.append(raw_name)
    if sorted(observed_names) != expected_names:
        raise ArtifactError("pinned-crit receipt does not decode every metadata image")

    mount_names = [name for name in expected_names if name.startswith("mountpoints-")]
    if len(mount_names) != 1:
        raise ArtifactError("artifact must have exactly one mountpoints metadata image")
    tmp_ids = _tmp_mount_ids(decoded_values[mount_names[0]])
    category_counts = {name: 0 for name in IDENTITY_CATEGORIES}
    for raw_name, decoded in decoded_values.items():
        if raw_name in mount_names:
            continue
        category = _category(raw_name)
        for json_path, item in _walk_json(decoded):
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
                    and item in tmp_ids
                ):
                    category_counts[category] += 1
    reference_count = sum(category_counts.values())
    if reference_count:
        nonzero = {key: value for key, value in category_counts.items() if value}
        raise ArtifactError(
            f"decoded CRIU retains /tmp identity-sensitive references: {nonzero}"
        )
    return {
        "decoder_receipt_sha256": _sha256_bytes(receipt_raw),
        "metadata_image_count": len(expected_names),
        "decoded_image_count": len(decoded_values),
        "tmp_identity_reference_count": 0,
        "category_counts": category_counts,
        "decoder": contract["crit_decoder"],
    }


def validate_artifact(
    artifact: Path,
    decoded_dir: Path,
    crit_receipt: Path,
    contract: dict[str, Any],
    contract_sha256: str,
) -> dict[str, Any]:
    artifact = _directory(artifact, "candidate artifact")
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
        "external_mount": external_mount,
        "rootfs": _inspect_rootfs(artifact, contract),
        "deleted_files": _inspect_deleted_files(artifact, contract),
        "pages": _inspect_pages(artifact, contract),
        "crit": _inspect_crit(artifact, decoded_dir, crit_receipt, contract),
        "live_clone_canary_required": True,
        "live_clone_canary_completed": False,
    }
    return receipt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--decoded-dir", type=Path, required=True)
    parser.add_argument("--crit-receipt", type=Path, required=True)
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
            args.crit_receipt,
            contract,
            contract_sha256,
        )
        state._write_receipt(args.receipt_output, receipt)
    except (ArtifactError, state.StateError, OSError) as exc:
        print(f"external-tmp-artifact: refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
