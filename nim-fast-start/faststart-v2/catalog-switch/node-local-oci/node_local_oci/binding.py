"""Exact-byte binding to the reviewed shared sources.

The adapter consumes two reviewed source trees that were checked out from
exact commits onto this branch:

- request-SLO harness  ``performance/request_slo``           @ ba49c9e20f194e0f419d4209608904cc9335219d
- security threat model ``catalog-switch/security-reliability`` @ 9cfbc1b1311a1f784a407889b215aaec5200fe0e

``SHARED_SOURCES.json`` records commit, path, git blob SHA-1, SHA-256 and byte
count for every pinned file.  ``verify_shared_sources()`` recomputes both
digests from the bytes on disk and refuses when anything drifted; the
production CLI calls it before importing the shared validator, so a mutated
copy of the harness can never silently replace the reviewed one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .errors import Refusal, require

PACKAGE_DIR = Path(__file__).resolve().parent
LANE_DIR = PACKAGE_DIR.parent
FASTSTART_ROOT = LANE_DIR.parent.parent
SHARED_SOURCES_PATH = LANE_DIR / "SHARED_SOURCES.json"
SOURCE_MANIFEST_PATH = LANE_DIR / "SOURCE_MANIFEST.json"

REQUEST_SLO_COMMIT = "ba49c9e20f194e0f419d4209608904cc9335219d"
SECURITY_MODEL_COMMIT = "9cfbc1b1311a1f784a407889b215aaec5200fe0e"


def _sha256_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            hasher.update(chunk)
    return hasher.hexdigest(), size


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\x00".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _load_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise Refusal("binding.manifest-unreadable", f"{path}: {error}") from error
    value = json.loads(text)
    require(isinstance(value, dict), "binding.manifest-shape", f"{path} is not an object")
    return value


def verify_shared_sources(root: Path | None = None) -> dict:
    """Verify every pinned shared-source file byte-for-byte. Returns the pin set."""
    base = Path(root) if root is not None else FASTSTART_ROOT
    pins = _load_json(SHARED_SOURCES_PATH)
    require(pins.get("schema") == "catalog-switch/nlo-shared-sources/v1",
            "binding.manifest-schema", "SHARED_SOURCES.json schema mismatch")
    files = pins.get("files")
    require(isinstance(files, list) and len(files) > 0,
            "binding.manifest-empty", "SHARED_SOURCES.json has no pinned files")
    for entry in files:
        require(isinstance(entry, dict), "binding.pin-shape", "pin entry is not an object")
        require(set(entry) == {"commit", "path", "git_blob_sha1", "sha256", "bytes"},
                "binding.pin-keys", f"pin entry keys wrong: {sorted(entry)}")
        target = base / entry["path"]
        require(target.is_file() and not target.is_symlink(),
                "binding.pin-missing", f"pinned file absent or symlink: {target}")
        sha256, size = _sha256_file(target)
        require(sha256 == entry["sha256"],
                "binding.pin-sha256", f"{entry['path']}: sha256 drifted")
        require(size == entry["bytes"],
                "binding.pin-bytes", f"{entry['path']}: byte count drifted")
        require(_git_blob_sha1(target) == entry["git_blob_sha1"],
                "binding.pin-blob", f"{entry['path']}: git blob drifted")
    return pins


def verify_source_manifest() -> dict:
    """Verify this package's own production sources against SOURCE_MANIFEST.json."""
    manifest = _load_json(SOURCE_MANIFEST_PATH)
    require(manifest.get("schema") == "catalog-switch/nlo-source-manifest/v1",
            "binding.self-manifest-schema", "SOURCE_MANIFEST.json schema mismatch")
    files = manifest.get("files")
    require(isinstance(files, dict) and len(files) > 0,
            "binding.self-manifest-empty", "SOURCE_MANIFEST.json has no files")
    listed = set(files)
    actual = {
        str(p.relative_to(LANE_DIR))
        for p in sorted(PACKAGE_DIR.glob("*.py"))
    }
    require(actual == listed,
            "binding.self-manifest-coverage",
            f"manifest files {sorted(listed)} != package files {sorted(actual)}")
    for rel, expected in files.items():
        sha256, _ = _sha256_file(LANE_DIR / rel)
        require(sha256 == expected,
                "binding.self-manifest-sha256", f"{rel}: source drifted from manifest")
    return manifest


def import_shared_harness():
    """Import the pinned request-SLO harness after byte verification."""
    verify_shared_sources()
    import sys
    root = str(FASTSTART_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from performance.request_slo import harness  # noqa: PLC0415

    return harness
