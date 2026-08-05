#!/usr/bin/env python3
"""Vendor NVIDIA BioNeMo NIM skills and replace shell execution with MCP calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

UPSTREAM_REPOSITORY = "https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit.git"
PINNED_SHA = "4e8fda769bd773538cb7168c849bd712c1b51b7b"

TOOL_MAP = {
    "boltz2-nim": "boltz2_predict",
    "diffdock-nim": "diffdock_dock",
    "evo2-nim": "evo2_run",
    "genmol-nim": "genmol_generate",
    "molmim-nim": "molmim_run",
    "msa-search-nim": "msa_search",
    "openfold2-nim": "openfold2_predict",
    "openfold3-nim": "openfold3_predict",
    "proteinmpnn-nim": "proteinmpnn_design",
    "rfdiffusion-nim": "rfdiffusion_generate",
    "drug-discovery-pipeline": "drug_discovery_pipeline",
    "msa-structure-prediction-pipeline": "msa_structure_prediction_pipeline",
}

MODEL_NOTES = {
    "boltz2-nim": "Supply polymers, optional ligands, constraints, and sampling controls in the typed request object.",
    "diffdock-nim": "Supply ATOM-only PDB text, ligand text, its file type, and docking controls.",
    "evo2-nim": "Choose the generate or forward operation in the typed request.",
    "genmol-nim": "The `smiles` field carries SAFE notation; temperature and noise remain strings as required by NIM.",
    "molmim-nim": "Choose generate, embedding, hidden, decode, or sampling in the discriminated request.",
    "msa-search-nim": "Choose standard, paired, or templates and provide the corresponding typed fields.",
    "openfold2-nim": "Supply a protein sequence and optional A3M alignments or mmCIF templates.",
    "openfold3-nim": "Supply exactly one typed input containing protein, nucleic-acid, or ligand molecules.",
    "proteinmpnn-nim": "Supply inline PDB text or an asset reference and sequence-design controls.",
    "rfdiffusion-nim": "Supply a contig specification and inline PDB text or an asset reference.",
    "drug-discovery-pipeline": "Supply the target sequence and PDB plus generation, docking, and affinity limits.",
    "msa-structure-prediction-pipeline": "Supply the sequence, database choices, MSA depth, and structure format.",
}

LICENSE_FILES = ("LICENSE", "LICENSE-APACHE-2.0", "LICENSE-CC-BY-4.0", "NOTICE")


def _run(*command: str, cwd: Path | None = None) -> str:
    result = subprocess.run(  # noqa: S603 - argv is passed directly to git without a shell
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checkout(source: str, sha: str, target: Path) -> str:
    _run("git", "clone", "--filter=blob:none", "--no-checkout", source, str(target))
    _run("git", "fetch", "--depth=1", "origin", sha, cwd=target)
    _run("git", "checkout", "--detach", "FETCH_HEAD", cwd=target)
    resolved = _run("git", "rev-parse", "HEAD", cwd=target)
    if resolved != sha:
        raise RuntimeError(f"requested {sha}, but git resolved {resolved}")
    return resolved


def _frontmatter_and_intro(source: str) -> tuple[str, str, str]:
    if not source.startswith("---\n"):
        raise ValueError("SKILL.md has no YAML frontmatter")
    closing = source.find("\n---\n", 4)
    if closing < 0:
        raise ValueError("SKILL.md frontmatter is not terminated")
    frontmatter = source[4:closing]
    body = source[closing + 5 :]
    first_h2 = re.search(r"^##\s+", body, flags=re.MULTILINE)
    intro = body[: first_h2.start() if first_h2 else len(body)].rstrip()
    title = next((line for line in intro.splitlines() if line.startswith("# ")), "# NVIDIA BioNeMo skill")
    return frontmatter, intro, title


def _rewrite_frontmatter(frontmatter: str) -> str:
    lines = [line for line in frontmatter.splitlines() if not line.startswith("allowed-tools:")]
    text = "\n".join(lines)
    replacements = {
        "hosted NVIDIA API": "Nebius-hosted MCP",
        "hosted API": "Nebius-hosted MCP",
        "local Docker": "Nebius-hosted MCP",
        "Docker deployment": "MCP execution",
        "Docker setup": "MCP execution",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    compatibility = 'compatibility: "Requires nebius-bionemo-mcp >=0.1"'
    if re.search(r"^compatibility:", text, flags=re.MULTILINE):
        text = re.sub(r"^compatibility:.*$", compatibility, text, flags=re.MULTILINE)
    else:
        text += f"\n{compatibility}"
    return text


def transform_skill(source: str, skill_name: str, reference_names: list[str]) -> str:
    if skill_name not in TOOL_MAP:
        raise ValueError(f"no MCP tool mapping for {skill_name}")
    frontmatter, intro, title = _frontmatter_and_intro(source)
    tool = TOOL_MAP[skill_name]
    references = "\n".join(f"- `references/{name}`" for name in reference_names)
    if not references:
        references = "- This pipeline composes the individually vendored NIM references."

    return f"""---
{_rewrite_frontmatter(frontmatter)}
---

{title}

{intro.split(title, 1)[-1].strip()}

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `{tool}` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `{tool}`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

{MODEL_NOTES[skill_name]}

If the tool is absent, call `fleet_health` and report the disabled or unready
catalog model. Do not fall back to NVIDIA-hosted inference or a workstation
container. The customer-owned Nebius fleet is the only execution target.

## Scientific references

The NVIDIA-authored reference and evaluation files below are preserved byte for
byte. Use the references for model selection, scientific limitations, parameter
interpretation, and output validation; use MCP for all execution.

{references}

## Upstream evaluation intent

The unmodified upstream eval prompts may mention NVIDIA-hosted endpoints or
local containers. Preserve their scientific request and validation criteria,
but execute the request with `{tool}` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
"""


def _copy_tree(checkout: Path, stage: Path, source_url: str, resolved_sha: str) -> None:
    source_root = checkout / "nim-skills"
    if not source_root.is_dir():
        raise RuntimeError("upstream checkout has no nim-skills directory")
    shutil.copytree(source_root, stage / "nim-skills")
    for name in LICENSE_FILES:
        shutil.copy2(checkout / name, stage / name)

    preserved: dict[str, str] = {}
    transformed: dict[str, dict[str, str]] = {}
    skill_files = sorted((stage / "nim-skills").glob("**/SKILL.md"))
    for skill_file in skill_files:
        skill_name = skill_file.parent.name
        if skill_name not in TOOL_MAP:
            raise RuntimeError(f"unexpected NIM skill without a tool mapping: {skill_name}")
        source_text = skill_file.read_text(encoding="utf-8")
        source_hash = hashlib.sha256(source_text.encode()).hexdigest()
        reference_dir = skill_file.parent / "references"
        references = sorted(path.name for path in reference_dir.glob("*.md")) if reference_dir.exists() else []
        output = transform_skill(source_text, skill_name, references)
        skill_file.write_text(output, encoding="utf-8", newline="\n")
        transformed[str(skill_file.relative_to(stage))] = {
            "source_sha256": source_hash,
            "vendored_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "mcp_tool": TOOL_MAP[skill_name],
        }

    for path in sorted((stage / "nim-skills").glob("**/*")):
        if path.is_file() and path.name != "SKILL.md":
            preserved[str(path.relative_to(stage))] = _sha256(path)

    manifest: dict[str, Any] = {
        "upstream_repository": source_url,
        "requested_sha": resolved_sha,
        "resolved_sha": resolved_sha,
        "source_subdirectory": "nim-skills",
        "license": "Apache-2.0 OR CC-BY-4.0",
        "preserved_files": preserved,
        "transformed_skills": transformed,
    }
    (stage / "UPSTREAM.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (stage / "MODIFICATIONS.md").write_text(
        """# Modifications

Nebius mechanically replaced every vendored `SKILL.md` execution body with a
typed `nebius-bionemo-mcp` workflow. YAML trigger descriptions and introductory
model context were retained with hosted/Docker wording normalized to Nebius MCP.
All `references/`, `evals/`, and other non-`SKILL.md` files are copied without
modification; their SHA-256 hashes are recorded in `UPSTREAM.json`.

The adaptation does not add scientific claims or alter NVIDIA's reference and
evaluation content. It changes only how an agent executes the documented model.
""",
        encoding="utf-8",
    )


def _files(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): _sha256(path) for path in sorted(root.glob("**/*")) if path.is_file()}


def vendor(source: str, sha: str, output: Path, *, check: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="nebius-bionemo-vendor-") as temporary:
        temporary_root = Path(temporary)
        checkout = temporary_root / "checkout"
        stage = temporary_root / "stage"
        stage.mkdir()
        resolved = _checkout(source, sha, checkout)
        _copy_tree(checkout, stage, source, resolved)

        if check:
            if not output.is_dir() or _files(output) != _files(stage):
                raise SystemExit("vendored skill tree differs from deterministic output")
            return

        output.parent.mkdir(parents=True, exist_ok=True)
        replacement = output.parent / f".{output.name}.replacement"
        if replacement.exists():
            shutil.rmtree(replacement)
        shutil.copytree(stage, replacement)
        if output.exists():
            shutil.rmtree(output)
        replacement.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=UPSTREAM_REPOSITORY)
    parser.add_argument("--sha", default=PINNED_SHA)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "vendor" / "nvidia-bionemo",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    vendor(args.source, args.sha, args.output.resolve(), check=args.check)


if __name__ == "__main__":
    main()
