from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.vendor_skills import TOOL_MAP, transform_skill

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "nvidia-bionemo"


def test_transform_replaces_execution_and_preserves_trigger_frontmatter() -> None:
    source = """---
name: boltz2-nim
description: Use the hosted NVIDIA API or local Docker for Boltz2.
license: Apache-2.0 AND CC-BY-4.0
allowed-tools: Bash, Read
---

# Boltz2 NIM

Predict structures. Read `references/api.md`.

## Choose Mode

Run curl against http://localhost:8000.
"""
    transformed = transform_skill(source, "boltz2-nim", ["api.md"])
    assert "name: boltz2-nim" in transformed
    assert "boltz2_predict" in transformed
    assert "allowed-tools: Bash" not in transformed
    assert "localhost:8000" not in transformed
    assert "Run curl" not in transformed


def test_vendored_manifest_proves_references_and_evals_are_unmodified() -> None:
    manifest = json.loads((VENDOR / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert manifest["requested_sha"] == "4e8fda769bd773538cb7168c849bd712c1b51b7b"
    assert set(item["mcp_tool"] for item in manifest["transformed_skills"].values()) == set(TOOL_MAP.values())
    preserved = manifest["preserved_files"]
    assert any(path.endswith("evals/evals.json") for path in preserved)
    assert any(path.endswith("evals/trigger_evals.json") for path in preserved)
    assert any("/references/" in path for path in preserved)
    for relative, expected in preserved.items():
        actual = hashlib.sha256((VENDOR / relative).read_bytes()).hexdigest()
        assert actual == expected


@pytest.mark.parametrize("relative", sorted(TOOL_MAP))
def test_every_transformed_skill_uses_only_its_mcp_execution(relative: str) -> None:
    candidates = list((VENDOR / "nim-skills").glob(f"**/{relative}/SKILL.md"))
    assert len(candidates) == 1
    text = candidates[0].read_text(encoding="utf-8")
    assert TOOL_MAP[relative] in text
    for obsolete in ("health.api.nvidia.com", "localhost:8000", "docker run", "curl -"):
        assert obsolete not in text.lower()
