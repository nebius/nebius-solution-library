#!/usr/bin/env python3
"""Extract a sanitized Forge model-manifest snapshot for the switch catalog.

Reads every model manifest from a local Forge checkout and emits
``sources/forge-models.json`` containing only the whitelisted,
credential-free fields the catalog builder consumes. Private Nebius
registry paths, organization identifiers, container environment blocks,
and free-text onboarding blockers never enter the output; extraction
fails closed if a forbidden pattern survives sanitization.

Usage:
    python3 extract_forge_source.py --forge-repo /path/to/forge \
        [--output sources/forge-models.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys

PRIVATE_REGISTRY_RE = re.compile(r"^cr\.([a-z0-9-]+)\.nebius\.cloud/")
DIGEST_RE = re.compile(r"@(sha256:[0-9a-f]{64})$")

# Patterns that must never appear in the sanitized output. Candidate
# Nebius-style identifiers that are pure hexadecimal are allowed because
# they are substrings of content digests, not resource identifiers.
FORBIDDEN_PATTERNS = [
    re.compile(r"cr\.[a-z0-9-]+\.nebius\.cloud"),
    re.compile(
        r"\b(?:tenant|project|registry|computeinstance|mk8scluster|"
        r"mk8snodegroup|vpcsubnet|vpcnetwork)-[a-z0-9]{8,}\b"
    ),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?<!@sha256)"),
]
# Standalone Nebius org/resource ids such as "e00h91c5sa606xfwpj": start
# with a known prefix letter + two digits and contain at least one
# non-hex letter (so digest fragments never match).
ORG_ID_CANDIDATE_RE = re.compile(r"\b[eiu]\d{2}[a-z0-9]{12,}\b")
NON_HEX_RE = re.compile(r"[g-z]")


def find_forbidden(text: str) -> list[str]:
    """Return forbidden substrings found in ``text``."""
    hits = [m.group(0) for pat in FORBIDDEN_PATTERNS for m in pat.finditer(text)]
    for m in ORG_ID_CANDIDATE_RE.finditer(text):
        if NON_HEX_RE.search(m.group(0)):
            hits.append(m.group(0))
    return hits


def sanitize_image(ref: str | None) -> dict:
    """Split an image reference into a publishable form."""
    if not ref:
        return {
            "public_ref": None,
            "digest": None,
            "registry_visibility": "unknown",
        }
    digest = None
    m = DIGEST_RE.search(ref)
    if m:
        digest = m.group(1)
        ref = ref[: m.start()]
    if PRIVATE_REGISTRY_RE.match(ref):
        return {
            "public_ref": None,
            "digest": digest,
            "registry_visibility": "private-mirror",
        }
    if ref.startswith("forge-local") or ref.startswith("pending-build"):
        return {
            "public_ref": None,
            "digest": digest,
            "registry_visibility": "local-build",
        }
    return {
        "public_ref": ref,
        "digest": digest,
        "registry_visibility": "public",
    }


def tri_state(value: object) -> bool | None:
    """Coerce manifest tri-state flags (true/false/"auto"/absent) honestly."""
    if isinstance(value, bool):
        return value
    return None


def extract_model(path: str, repo: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        m = json.load(fh)
    gpu_req = m.get("gpu_requirements") or {}
    bench = m.get("benchmark_scores") or {}
    image = sanitize_image(m.get("container_image"))
    mirrors = m.get("regional_container_images") or {}
    mirror_digests = set()
    for ref in mirrors.values():
        dm = DIGEST_RE.search(ref or "")
        if dm:
            mirror_digests.add(dm.group(1))
    blockers = bench.get("blockers") or []
    return {
        "slug": m["slug"],
        "name": m.get("name"),
        "model_family": m.get("model_family"),
        "version": m.get("version"),
        "version_key": m.get("version_key"),
        "status": m.get("status"),
        "stability": m.get("stability"),
        "default_eligible": m.get("default_eligible"),
        "is_latest": m.get("is_latest"),
        "category": (m.get("category") or "").replace("_", "-") or None,
        "tags": sorted(m.get("tags") or []),
        "modality_input": sorted(m.get("modality_input") or []),
        "modality_output": sorted(m.get("modality_output") or []),
        "parameter_count": m.get("parameter_count"),
        "quantization": m.get("quantization"),
        "context_window": m.get("context_window"),
        "license": m.get("license"),
        "requires_hf_token": bool(m.get("requires_hf_token")),
        "endpoint_path": (m.get("endpoint_schema") or {}).get("path"),
        "endpoint_method": (m.get("endpoint_schema") or {}).get("method"),
        "min_gpus": m.get("min_gpus") or gpu_req.get("min_gpus"),
        "min_vram_gb": m.get("min_vram_gb") or gpu_req.get("min_vram_gb"),
        "gpu_compatibility": m.get("gpu_compatibility") or {},
        "container_image": image,
        "container_image_size_bytes": m.get("container_image_size_bytes")
        or bench.get("container_image_size_bytes"),
        "mirror_regions": sorted(mirrors.keys()),
        "mirror_digests": sorted(mirror_digests),
        "artifact": {
            "size_bytes": bench.get("artifact_size_bytes"),
            "gated": tri_state(bench.get("artifact_gated")),
            "private": tri_state(bench.get("artifact_private")),
            "revision": bench.get("artifact_revision"),
            "license": bench.get("artifact_license"),
        },
        "runtime": bench.get("runtime"),
        "onboarding_state": bench.get("onboarding_state"),
        "blocker_count": len(blockers) if isinstance(blockers, list) else 1,
        "has_playground_example": bool(
            (m.get("playground_config") or {}).get("input_fields")
        ),
        "source_url": m.get("source_url"),
        "source_file": os.path.relpath(path, repo),
    }


def git_provenance(repo: str) -> dict:
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", repo, *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    commit = run("rev-parse", "HEAD")
    commit_date = run("log", "-1", "--format=%cI")
    dirty = run("status", "--short", "--", "manifests/models")
    return {
        "repo_kind": "local-forge-checkout",
        "commit": commit,
        "commit_date": commit_date,
        "manifests_dirty": bool(dirty),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-repo", required=True)
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "sources", "forge-models.json"),
    )
    args = parser.parse_args()

    pattern = os.path.join(args.forge_repo, "manifests", "models", "**", "*.json")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        print(f"no model manifests under {args.forge_repo}", file=sys.stderr)
        return 1

    models = [extract_model(f, args.forge_repo) for f in files]
    models.sort(key=lambda m: m["slug"])
    doc = {
        "meta": {
            "source": "forge-manifests",
            "provenance": git_provenance(args.forge_repo),
            "manifest_count": len(models),
            "sanitization": "whitelisted fields only; private registry paths, "
            "container env, and free-text blockers removed",
        },
        "models": models,
    }
    serialized = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False)
    leaks = find_forbidden(serialized)
    if leaks:
        print("sanitization failed; forbidden content:", sorted(set(leaks))[:10],
              file=sys.stderr)
        return 2
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(serialized + "\n")
    print(f"wrote {args.output}: {len(models)} models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
