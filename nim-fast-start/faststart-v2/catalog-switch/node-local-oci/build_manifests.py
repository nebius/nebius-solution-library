"""Regenerate SHARED_SOURCES.json and SOURCE_MANIFEST.json deterministically.

Run from anywhere; writes canonical JSON.  SHARED_SOURCES pins the exact
bytes of the reviewed shared sources this lane consumes; SOURCE_MANIFEST pins
this package's own production modules.  Both are verified fail-closed at CLI
startup by ``node_local_oci.binding``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

LANE_DIR = Path(__file__).resolve().parent
ROOT = LANE_DIR.parent.parent

REQUEST_SLO_COMMIT = "ba49c9e20f194e0f419d4209608904cc9335219d"
SECURITY_MODEL_COMMIT = "9cfbc1b1311a1f784a407889b215aaec5200fe0e"

PIN_SETS = [
    (REQUEST_SLO_COMMIT, "performance/request_slo"),
    (SECURITY_MODEL_COMMIT, "catalog-switch/security-reliability"),
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\x00".encode("ascii") + data).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def main() -> None:
    files = []
    for commit, rel_dir in PIN_SETS:
        base = ROOT / rel_dir
        for path in sorted(p for p in base.rglob("*") if p.is_file()
                           and "__pycache__" not in p.parts):
            data = path.read_bytes()
            files.append({
                "commit": commit,
                "path": str(path.relative_to(ROOT)),
                "git_blob_sha1": git_blob_sha1(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            })
    shared = {"schema": "catalog-switch/nlo-shared-sources/v1", "files": files}
    (LANE_DIR / "SHARED_SOURCES.json").write_text(canonical(shared) + "\n",
                                                  encoding="utf-8")

    package_files = {
        str(p.relative_to(LANE_DIR)): sha256_file(p)
        for p in sorted((LANE_DIR / "node_local_oci").glob("*.py"))
    }
    manifest = {"schema": "catalog-switch/nlo-source-manifest/v1",
                "files": package_files}
    (LANE_DIR / "SOURCE_MANIFEST.json").write_text(canonical(manifest) + "\n",
                                                   encoding="utf-8")
    print(f"pinned {len(files)} shared files, {len(package_files)} package files")


if __name__ == "__main__":
    main()
