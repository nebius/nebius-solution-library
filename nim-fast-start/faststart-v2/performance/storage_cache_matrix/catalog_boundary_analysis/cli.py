#!/usr/bin/env python3
"""CLI for the offline catalog-boundary storage/cache package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from performance.request_slo.harness import canonical_json
from performance.storage_cache_matrix.catalog_boundary_analysis.analysis import (
    AnalysisError,
    analyze_capacity,
    load_attempts,
    load_canonical_json,
    validate_attempts,
    verify_pinned_sources,
)


PACKAGE = Path(__file__).resolve().parent


def _write(path: Path | None, value: object) -> None:
    rendered = canonical_json(value) + "\n"
    if path is None:
        print(rendered, end="")
        return
    if path.exists() and path.is_symlink():
        raise AnalysisError("output cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify-sources")
    verify.add_argument("--manifest", type=Path, default=PACKAGE / "source_manifest.json")
    verify.add_argument("--repo-root", type=Path, required=True)
    verify.add_argument("--task-deck-root", type=Path)
    verify.add_argument("--output", type=Path)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--manifest", type=Path, default=PACKAGE / "source_manifest.json")
    analyze.add_argument("--config", type=Path, default=PACKAGE / "analysis_config.json")
    analyze.add_argument("--output", type=Path)

    attempts = subparsers.add_parser("validate-attempts")
    attempts.add_argument("--manifest", type=Path, default=PACKAGE / "source_manifest.json")
    attempts.add_argument("--attempts", type=Path, required=True)
    attempts.add_argument("--evidence-root", type=Path, required=True)
    attempts.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_canonical_json(args.manifest)
        if args.command == "verify-sources":
            result = verify_pinned_sources(
                manifest, args.repo_root, args.task_deck_root
            )
        elif args.command == "analyze":
            result = analyze_capacity(manifest, load_canonical_json(args.config))
        else:
            shaped = validate_attempts(
                manifest, load_attempts(args.attempts), args.evidence_root
            )
            result = {
                "schema": "archvteams.nebius.ai/catalog-boundary-attempt-validation/v1",
                "attempt_count": len(shaped),
                "cache_states": sorted(
                    {item["raw"]["cache_state"] for item in shaped}
                ),
                "evidence_classifications": sorted(
                    {item["raw"]["evidence_classification"] for item in shaped}
                ),
            }
        _write(args.output, result)
    except (AnalysisError, OSError, json.JSONDecodeError) as exc:
        parser = build_parser()
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
