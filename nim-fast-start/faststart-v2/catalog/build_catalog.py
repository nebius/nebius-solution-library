#!/usr/bin/env python3
"""Build the catalog-switch model inventory from checked-in sources.

Deterministically reconciles four source snapshots into one
machine-readable catalog:

- ``sources/forge-models.json``      (sanitized Forge manifest snapshot)
- ``sources/faststart-lanes.json``   (measured faststart-v2 lane evidence)
- ``sources/nims-terraform.json``    (modules/nims Terraform catalog)
- ``sources/documented-candidates.json`` (doc-referenced candidates)

Outputs ``catalog.json``, ``catalog.tsv``, and ``GAP_REPORT.md`` next to
this script. The build is a pure function of the source files: no
timestamps, no environment reads, rows sorted by id. Rerunning must
reproduce the committed outputs byte for byte.

Classification rules (documented in README.md):

- availability class: ``hypothetical`` when the row exists only as a
  documentation reference; otherwise ``gated`` when a gate that this
  program cannot satisfy from the catalog alone is recorded (credential,
  license acceptance, disabled listing, private-only image, or a hardware
  release decision); otherwise ``verified`` when an authorized source
  records that this exact profile served real requests; otherwise
  ``discoverable``.
- evidence tier: ``measured-local`` (faststart lane evidence in this
  repository), ``measured-source`` (Forge ``status=active`` live-serving
  records), ``catalog-listed`` (listed without run evidence), or
  ``referenced-only``.
- snapshot eligibility is evidence-based for faststart lanes and
  heuristic elsewhere: same canonical model as a proven lane gives
  ``candidate-family-proven``; single-GPU rows are
  ``candidate-unproven``; multi-GPU rows are ``unproven-multi-gpu``.
- pilots: the three program-mandated classes are selected by fixed
  arithmetic rules over the row set, never by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from extract_forge_source import find_forbidden  # noqa: E402

SOURCES_DIR = os.path.join(HERE, "sources")

NONCOMMERCIAL_LICENSE_TOKENS = ("non-commercial", "noncommercial")
WORKLOAD_TAG_PRECEDENCE = [
    "chat",
    "code",
    "embedding",
    "rerank",
    "retrieval",
    "vision",
    "image-generation",
    "video-world",
    "physical-ai",
    "molecular-dynamics",
    "document-parse",
    "safety",
]
RUNTIME_SLUG_TOKENS = {
    "vllm": "vllm",
    "tei": "tei",
    "sglang": "sglang",
    "nim": "nim",
    "diffusers": "diffusers",
    "wrapper": "custom-wrapper",
}
EVIDENCE_RANK = {
    "measured-local": 0,
    "measured-source": 1,
    "catalog-listed": 2,
    "referenced-only": 3,
}


def load(name: str) -> dict:
    with open(os.path.join(SOURCES_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def hf_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    marker = "huggingface.co/"
    if marker not in url:
        return None
    tail = url.split(marker, 1)[1].strip("/")
    parts = tail.split("/")
    if len(parts) >= 2:
        return f"hf:{parts[0]}/{parts[1]}"
    return None


def forge_runtime_family(model: dict) -> str:
    tokens = set(model["slug"].split("-"))
    for token, family in RUNTIME_SLUG_TOKENS.items():
        if token in tokens:
            return family
    ref = (model["container_image"].get("public_ref") or "")
    if ref.startswith("nvcr.io/nim/"):
        return "nim"
    return "custom"


def forge_workload_class(model: dict) -> str:
    tags = set(model.get("tags") or [])
    for tag in WORKLOAD_TAG_PRECEDENCE:
        if tag in tags:
            return tag
    return model.get("category") or "other"


def api_style(endpoint_path: str | None, runtime_family: str) -> str:
    if not endpoint_path:
        return "unknown"
    if endpoint_path.startswith(
        ("/v1/chat/completions", "/v1/completions", "/v1/embeddings")
    ):
        return "openai-compatible"
    if runtime_family == "nim":
        return "nim-native-http"
    return "custom-http"


def availability_class(evidence_tier: str, gates: list[str]) -> str:
    if evidence_tier == "referenced-only":
        return "hypothetical"
    if gates:
        return "gated"
    if evidence_tier in ("measured-local", "measured-source"):
        return "verified"
    return "discoverable"


def confidence_for(evidence_tier: str, gates: list[str]) -> str:
    if "catalog-disabled" in gates:
        return "low"
    if evidence_tier in ("measured-local", "measured-source"):
        return "high"
    if evidence_tier == "catalog-listed":
        return "medium"
    return "low"


def build_forge_rows(forge: dict) -> list[dict]:
    rows = []
    for m in forge["models"]:
        runtime_family = forge_runtime_family(m)
        image = m["container_image"]
        gates: list[str] = []
        if m.get("requires_hf_token"):
            gates.append("hf-token-required")
        if m["artifact"].get("gated"):
            gates.append("artifact-gated-upstream")
        license_id = m.get("license") or ""
        if any(t in license_id.lower() for t in NONCOMMERCIAL_LICENSE_TOKENS):
            gates.append("license-noncommercial")
        if m["status"] == "disabled":
            gates.append("catalog-disabled")
        if image["registry_visibility"] in ("private-mirror", "local-build") and not image["public_ref"]:
            gates.append("no-public-image-reference")
        gates = sorted(set(gates))

        evidence_tier = "measured-source" if m["status"] == "active" else "catalog-listed"
        cls = availability_class(evidence_tier, gates)

        canonical = (
            hf_id_from_url(m.get("source_url"))
            or (image["public_ref"] or "").split(":")[0]
            or f"forge-family:{m['model_family']}"
        )
        version_id = str(m.get("version_key") or m.get("version") or "unversioned")
        min_gpus = m.get("min_gpus")
        row = {
            "id": f"forge:{m['slug']}@{version_id}",
            "canonical_key": canonical,
            "name": m.get("name") or m["slug"],
            "version_id": version_id,
            "source": "forge-manifests",
            "provenance": [
                {
                    "source": "forge-manifests",
                    "path": m["source_file"],
                    "ref": forge["meta"]["provenance"]["commit"],
                    "detail": f"status={m['status']}; onboarding_state={m.get('onboarding_state')}",
                }
            ],
            "availability": {
                "class": cls,
                "evidence_tier": evidence_tier,
                "confidence": confidence_for(evidence_tier, gates),
                "gates": gates,
                "evidence": (
                    "Forge catalog records this profile as live-serving (status=active)"
                    if m["status"] == "active"
                    else f"Forge catalog listing with status={m['status']}"
                ),
            },
            "workload": {
                "workload_class": forge_workload_class(m),
                "category": m.get("category"),
                "tags": m.get("tags") or [],
                "modality_input": m.get("modality_input") or [],
                "modality_output": m.get("modality_output") or [],
                "parameter_count": m.get("parameter_count"),
            },
            "api": {
                "style": api_style(m.get("endpoint_path"), runtime_family),
                "endpoint_path": m.get("endpoint_path"),
                "method": m.get("endpoint_method"),
                "context_window": m.get("context_window"),
            },
            "gpu": {
                "min_gpus": min_gpus,
                "min_vram_gb": m.get("min_vram_gb"),
                "sku_compatibility": m.get("gpu_compatibility") or None,
                "sku_evidence": "per-SKU support matrix recorded in the Forge manifest",
                "multi_gpu_required": (min_gpus or 1) > 1 if min_gpus is not None else None,
            },
            "image": {
                "upstream_ref": image["public_ref"],
                "digest": image["digest"] or (m.get("mirror_digests") or [None])[0],
                "size_bytes": m.get("container_image_size_bytes"),
                "registry_visibility": image["registry_visibility"],
                "mirror_regions": m.get("mirror_regions") or [],
                "tag_pinned": bool(image["digest"]),
            },
            "artifact": {
                "size_bytes": m["artifact"].get("size_bytes"),
                "cache_bytes": None,
                "gated": m["artifact"].get("gated"),
                "private": m["artifact"].get("private"),
                "requires_hf_token": bool(m.get("requires_hf_token")),
                "revision": m["artifact"].get("revision"),
                "artifact_id": canonical if canonical.startswith("hf:") else None,
                "note": None,
            },
            "startup": {
                "path": "conventional-pull-and-load",
                "runtime_family": runtime_family,
                "writable_state": None,
                "external_mounts": [],
                "measured": None,
            },
            "snapshot": None,  # filled after canonical linking
            "license": {
                "id": m.get("license"),
                "caveats": (
                    ["NGC/NIM container terms apply"]
                    if (image["public_ref"] or "").startswith("nvcr.io/nim/")
                    else []
                ),
            },
            "fixtures": {
                "status": "example-only" if m.get("has_playground_example") else "missing",
                "validator_path": None,
                "fixture_paths": [],
            },
            "storage": None,  # filled later
            "related_ids": [],
            "notes": m.get("description_short"),
        }
        rows.append(row)
    return rows


def build_faststart_rows(lanes: dict) -> list[dict]:
    rows = []
    root = lanes["meta"]["provenance"]["root"]
    for lane in lanes["lanes"]:
        gates = []
        if lane["key"] == "evo2-40b":
            gates.append("hardware-h200-release-required")
        evidence_tier = "measured-local"
        cls = availability_class(evidence_tier, gates)
        measured = lane["measured"]
        row = {
            "id": f"faststart:{lane['key']}@{lane['image_digest']}",
            "canonical_key": lane["image_repo"],
            "name": lane["name"],
            "version_id": lane.get("nim_version") or lane["image_digest"],
            "source": "faststart-v2-lanes",
            "provenance": [
                {
                    "source": "faststart-v2-lanes",
                    "path": f"{root}/{p}",
                    "ref": None,
                    "detail": None,
                }
                for p in lane["evidence_paths"]
            ],
            "availability": {
                "class": cls,
                "evidence_tier": evidence_tier,
                "confidence": "high" if not gates else "medium",
                "gates": gates,
                "evidence": lane["snapshot_evidence"],
            },
            "workload": {
                "workload_class": lane["workload"],
                "category": "life-science",
                "tags": [],
                "modality_input": [],
                "modality_output": [],
                "parameter_count": 40000000000 if lane["key"] == "evo2-40b" else None,
            },
            "api": {
                "style": "nim-native-http",
                "endpoint_path": lane["endpoint_path"],
                "method": "POST",
                "context_window": None,
            },
            "gpu": {
                "min_gpus": lane["gpu_count"],
                "min_vram_gb": None,
                "sku_compatibility": None,
                "sku_evidence": lane["gpu_sku_evidence"],
                "multi_gpu_required": lane["gpu_count"] > 1,
            },
            "image": {
                "upstream_ref": lane["image_repo"],
                "digest": lane["image_digest"],
                "size_bytes": None,
                "registry_visibility": "public",
                "mirror_regions": [],
                "tag_pinned": True,
            },
            "artifact": {
                "size_bytes": lane["artifact_bytes"],
                "cache_bytes": lane["cache_bytes"],
                "gated": False,
                "private": False,
                "requires_hf_token": False,
                "revision": None,
                "artifact_id": None,
                "note": lane.get("artifact_note"),
            },
            "startup": {
                "path": lane["startup_path"],
                "runtime_family": "nim",
                "writable_state": lane["writable_state"],
                "external_mounts": lane["external_mounts"],
                "measured": measured,
            },
            "snapshot": {
                "eligibility": lane["snapshot_eligibility"],
                "confidence": "high",
                "evidence": lane["snapshot_evidence"],
            },
            "license": {"id": None, "caveats": ["NGC/NIM container terms apply"]},
            "fixtures": {
                "status": "linked-strict-validator",
                "validator_path": f"{root}/{lane['validator']}",
                "fixture_paths": [f"{root}/{p}" for p in lane["fixtures"]],
            },
            "storage": None,
            "related_ids": [],
            "notes": None,
        }
        rows.append(row)
    return rows


def build_nims_rows(nims: dict) -> list[dict]:
    rows = []
    path = nims["meta"]["provenance"]["path"]
    for e in nims["entries"]:
        is_notebook = e["kind"] == "bionemo_notebook"
        evidence_tier = "catalog-listed"
        gates: list[str] = []
        cls = availability_class(evidence_tier, gates)
        row = {
            "id": f"nims-terraform:{e['key'].replace('_', '-')}@{e['version']}",
            "canonical_key": e["image"],
            "name": e["display_name"],
            "version_id": e["version"],
            "source": "nims-terraform-catalog",
            "provenance": [
                {
                    "source": "nims-terraform-catalog",
                    "path": path,
                    "ref": None,
                    "detail": f"local.default_model_catalog key {e['key']}",
                }
            ],
            "availability": {
                "class": cls,
                "evidence_tier": evidence_tier,
                "confidence": "medium",
                "gates": gates,
                "evidence": "deployable Terraform catalog entry; no run evidence recorded in this repository",
            },
            "workload": {
                "workload_class": e["workload"],
                "category": None,
                "tags": [],
                "modality_input": [],
                "modality_output": [],
                "parameter_count": None,
            },
            "api": {
                "style": "notebook" if is_notebook else "nim-native-http",
                "endpoint_path": None,
                "method": None,
                "context_window": None,
            },
            "gpu": {
                "min_gpus": e["gpu_count"],
                "min_vram_gb": None,
                "sku_compatibility": None,
                "sku_evidence": "module requests nvidia.com/gpu counts only; no GPU SKU is bound anywhere in modules/nims",
                "multi_gpu_required": e["gpu_count"] > 1,
                "cpu": e["cpu"],
                "memory_gi": e["memory_gi"],
                "shm_gi": e["shm_gi"],
            },
            "image": {
                "upstream_ref": e["image"],
                "digest": None,
                "size_bytes": None,
                "registry_visibility": "public",
                "mirror_regions": [],
                "tag_pinned": e["version"] not in ("latest", "nightly"),
            },
            "artifact": {
                "size_bytes": None,
                "cache_bytes": None,
                "gated": None,
                "private": None,
                "requires_hf_token": False,
                "revision": None,
                "artifact_id": None,
                "note": None,
            },
            "startup": {
                "path": "notebook" if is_notebook else "conventional-pull-and-load",
                "runtime_family": "notebook" if is_notebook else "nim",
                "writable_state": None,
                "external_mounts": ["/opt/nim/.cache shared cache volume"] if not is_notebook else ["/workspace/bionemo cache volume"],
                "measured": None,
            },
            "snapshot": {"eligibility": "not-applicable", "confidence": "high", "evidence": "notebook environment"} if is_notebook else None,
            "license": {"id": None, "caveats": ["NGC/NIM container terms apply"] if not is_notebook else []},
            "fixtures": {"status": "missing", "validator_path": None, "fixture_paths": []},
            "storage": None,
            "related_ids": [],
            "notes": e.get("notes"),
        }
        rows.append(row)
    return rows


def build_documented_rows(doc: dict) -> list[dict]:
    rows = []
    for e in doc["entries"]:
        gates = ["hf-license-acceptance-required"] if e.get("license_gate") else []
        row = {
            "id": f"documented:{e['key']}@unversioned",
            "canonical_key": f"hf:{e['artifact_id']}",
            "name": e["name"],
            "version_id": "unversioned",
            "source": "documented-candidates",
            "provenance": [
                {"source": "documented-candidates", "path": p, "ref": None, "detail": e["evidence"]}
                for p in e["paths"]
            ],
            "availability": {
                "class": "hypothetical",
                "evidence_tier": "referenced-only",
                "confidence": "low",
                "gates": gates,
                "evidence": e["evidence"],
            },
            "workload": {
                "workload_class": e["workload"],
                "category": "general",
                "tags": [],
                "modality_input": ["text"],
                "modality_output": ["text"],
                "parameter_count": 7000000000,
            },
            "api": {"style": "openai-compatible", "endpoint_path": "/v1/completions", "method": "POST", "context_window": 4096},
            "gpu": {
                "min_gpus": 1,
                "min_vram_gb": None,
                "sku_compatibility": None,
                "sku_evidence": e["gpu_note"],
                "multi_gpu_required": False,
            },
            "image": {"upstream_ref": None, "digest": None, "size_bytes": None, "registry_visibility": "unknown", "mirror_regions": [], "tag_pinned": None},
            "artifact": {
                "size_bytes": None,
                "cache_bytes": None,
                "gated": True,
                "private": False,
                "requires_hf_token": True,
                "revision": None,
                "artifact_id": e["artifact_id"],
                "note": e.get("license_gate"),
            },
            "startup": {"path": "conventional-pull-and-load", "runtime_family": e["runtime"], "writable_state": None, "external_mounts": [], "measured": None},
            "snapshot": None,
            "license": {"id": "llama2", "caveats": [e["license_gate"]] if e.get("license_gate") else []},
            "fixtures": {"status": "missing", "validator_path": None, "fixture_paths": []},
            "storage": None,
            "related_ids": [],
            "notes": e["evidence"],
        }
        rows.append(row)
    return rows


def link_and_fill(rows: list[dict]) -> None:
    """Fill related_ids, heuristic snapshot fields, and storage totals."""
    by_canonical: dict[str, list[dict]] = {}
    for row in rows:
        by_canonical.setdefault(row["canonical_key"], []).append(row)
    proven_canonicals = {
        r["canonical_key"]
        for r in rows
        if r["snapshot"] and r["snapshot"]["eligibility"] == "proven"
    }
    for row in rows:
        siblings = by_canonical[row["canonical_key"]]
        row["related_ids"] = sorted(r["id"] for r in siblings if r["id"] != row["id"])
        if row["snapshot"] is None:
            if row["canonical_key"] in proven_canonicals:
                row["snapshot"] = {
                    "eligibility": "candidate-family-proven",
                    "confidence": "medium",
                    "evidence": "same canonical model as a faststart lane with a proven native-snapshot restore; this exact image/version is unproven",
                }
            elif (row["gpu"]["min_gpus"] or 1) > 1:
                row["snapshot"] = {
                    "eligibility": "unproven-multi-gpu",
                    "confidence": "low",
                    "evidence": "multi-GPU serving; no multi-GPU native-snapshot restore has been qualified in this program",
                }
            else:
                row["snapshot"] = {
                    "eligibility": "candidate-unproven",
                    "confidence": "low",
                    "evidence": "single-GPU HTTP server; heuristic eligibility only, no capture attempted",
                }
        unknown = []
        total = 0
        img = row["image"]["size_bytes"]
        if img:
            total += img
        else:
            unknown.append("container-image-size")
        art = row["artifact"]["size_bytes"]
        if art:
            total += art
        else:
            unknown.append("artifact-size")
        cache = row["artifact"]["cache_bytes"]
        if cache:
            total += cache
        row["storage"] = {"local_bytes_known": total, "unknown_components": unknown}


def percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    rank = max(1, int(-(-pct * len(sorted_values) // 1)))  # ceil, nearest-rank
    return sorted_values[min(rank, len(sorted_values)) - 1]


def storage_feasibility(rows: list[dict]) -> dict:
    image_sizes = sorted(r["image"]["size_bytes"] for r in rows if r["image"]["size_bytes"])
    artifact_sizes = sorted(r["artifact"]["size_bytes"] for r in rows if r["artifact"]["size_bytes"])
    p90_image = percentile(image_sizes, 0.9)
    p90_artifact = percentile(artifact_sizes, 0.9)
    known_total = sum(r["storage"]["local_bytes_known"] for r in rows)
    fully = partially = unsized = 0
    missing_image = missing_artifact = 0
    for r in rows:
        unknown = r["storage"]["unknown_components"]
        if not unknown:
            fully += 1
        elif len(unknown) == 2:
            unsized += 1
        else:
            partially += 1
        missing_image += "container-image-size" in unknown
        missing_artifact += "artifact-size" in unknown
    high = known_total + missing_image * p90_image + missing_artifact * p90_artifact
    return {
        "known_local_bytes_total": known_total,
        "rows_fully_sized": fully,
        "rows_partially_sized": partially,
        "rows_unsized": unsized,
        "estimated_total_bytes_low": known_total,
        "estimated_total_bytes_high": high,
        "method": (
            "low bound sums only source-recorded image/artifact/cache bytes; "
            "high bound adds the observed nearest-rank p90 image size "
            f"({p90_image} B) per missing image size and p90 artifact size "
            f"({p90_artifact} B) per missing artifact size. Artifact sizes are "
            "unknown for most Forge rows because manifests record them only "
            "when onboarding measured them; treat the high bound as a "
            "planning ceiling, not a measurement."
        ),
    }


def select_pilots(rows: list[dict]) -> list[dict]:
    proven_verified = [
        r
        for r in rows
        if r["availability"]["class"] == "verified"
        and r["snapshot"]["eligibility"] == "proven"
        and r["storage"]["local_bytes_known"] > 0
    ]

    def by_bytes(r: dict) -> tuple:
        return (r["storage"]["local_bytes_known"], r["id"])

    small_pool = sorted(proven_verified, key=by_bytes)
    heavy_pool = sorted(proven_verified, key=by_bytes, reverse=True)

    def size_metric(r: dict) -> int:
        return max(
            r["artifact"]["size_bytes"] or 0,
            r["workload"].get("parameter_count") or 0,
        )

    large_pool = sorted(
        (
            r
            for r in rows
            if (r["gpu"]["min_gpus"] or 1) >= 2
            or (r["artifact"]["size_bytes"] or 0) >= 50_000_000_000
            or (r["workload"].get("parameter_count") or 0) >= 20_000_000_000
        ),
        key=lambda r: (
            EVIDENCE_RANK[r["availability"]["evidence_tier"]],
            -size_metric(r),
            r["id"],
        ),
    )

    def alternate(pool: list[dict], selected: dict) -> str | None:
        for r in pool:
            if r["canonical_key"] != selected["canonical_key"]:
                return r["id"]
        return None

    pilots = []
    for pilot_class, pool, rule in (
        (
            "small-snapshot-friendly",
            small_pool,
            "among verified rows with a proven native-snapshot restore and a nonzero known footprint, minimize known local bytes",
        ),
        (
            "storage-heavy",
            heavy_pool,
            "among verified rows with a proven native-snapshot restore and a nonzero known footprint, maximize known local bytes",
        ),
        (
            "large-or-multi-gpu",
            large_pool,
            "among rows requiring >=2 GPUs or holding >=50 GB artifacts or >=20B parameters, prefer the strongest evidence tier, then the largest artifact/parameter size",
        ),
    ):
        selected = pool[0]
        caveats = []
        if selected["availability"]["gates"]:
            caveats.append(
                "selected pilot is gated: " + "; ".join(selected["availability"]["gates"])
            )
        pilots.append(
            {
                "pilot_class": pilot_class,
                "selection_rule": rule,
                "selected_id": selected["id"],
                "alternate_id": alternate(pool[1:], selected),
                "caveats": caveats,
            }
        )
    return pilots


def family_taxonomy(rows: list[dict]) -> list[dict]:
    counts: dict[tuple, int] = {}
    for r in rows:
        key = (r["workload"]["workload_class"], r["startup"]["runtime_family"])
        counts[key] = counts.get(key, 0) + 1
    return [
        {"workload_class": w, "runtime_family": rt, "row_count": c}
        for (w, rt), c in sorted(counts.items())
    ]


TSV_COLUMNS = [
    "id",
    "canonical_key",
    "name",
    "source",
    "availability_class",
    "evidence_tier",
    "gates",
    "workload_class",
    "runtime_family",
    "api_style",
    "endpoint_path",
    "min_gpus",
    "min_vram_gb",
    "gpu_sku_compat_true",
    "image_upstream_ref",
    "image_digest",
    "image_size_bytes",
    "artifact_size_bytes",
    "cache_bytes",
    "snapshot_eligibility",
    "startup_path",
    "t0_to_call2_p50_s",
    "license",
    "fixtures_status",
    "local_bytes_known",
]


def tsv_row(r: dict) -> list[str]:
    measured = r["startup"]["measured"] or {}
    compat = r["gpu"]["sku_compatibility"] or {}
    values = [
        r["id"],
        r["canonical_key"],
        r["name"],
        r["source"],
        r["availability"]["class"],
        r["availability"]["evidence_tier"],
        "|".join(r["availability"]["gates"]),
        r["workload"]["workload_class"],
        r["startup"]["runtime_family"],
        r["api"]["style"],
        r["api"]["endpoint_path"],
        r["gpu"]["min_gpus"],
        r["gpu"]["min_vram_gb"],
        "|".join(sorted(k for k, v in compat.items() if v)),
        r["image"]["upstream_ref"],
        r["image"]["digest"],
        r["image"]["size_bytes"],
        r["artifact"]["size_bytes"],
        r["artifact"]["cache_bytes"],
        r["snapshot"]["eligibility"],
        r["startup"]["path"],
        measured.get("t0_to_call2_p50_s"),
        r["license"]["id"],
        r["fixtures"]["status"],
        r["storage"]["local_bytes_known"],
    ]
    return ["" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in values]


def gap_report(rows: list[dict], meta: dict) -> str:
    by_class = meta["row_counts"]["by_availability"]
    feas = meta["storage_feasibility"]
    missing_fixture = sum(1 for r in rows if r["fixtures"]["status"] == "missing")
    example_only = sum(1 for r in rows if r["fixtures"]["status"] == "example-only")
    unpinned = sum(1 for r in rows if r["image"]["tag_pinned"] is False)
    no_sku = sum(1 for r in rows if not r["gpu"]["sku_compatibility"] and r["source"] != "forge-manifests")
    lines = [
        "# Catalog gap report",
        "",
        "Generated by `build_catalog.py`; regenerating must reproduce this file.",
        "",
        "## Row inventory",
        "",
        f"- Total rows: {meta['row_counts']['total']} "
        f"({meta['row_counts']['unique_canonical_models']} unique canonical models).",
        f"- Availability: {json.dumps(by_class, sort_keys=True)}.",
        "- The often-quoted \"approximately 200 models\" is real but heterogeneous: "
        "only the availability classes above are defensible today. No rows were "
        "invented to reach a round number.",
        "",
        "## Named reconciliation gaps",
        "",
        "- OpenFold2 and MSA Search have measured faststart lanes and Terraform "
        "catalog entries but **no manifest in the live Forge checkout** (they were "
        "present in an older Forge snapshot and later removed). The Forge and "
        "Terraform catalogs have drifted from each other.",
        "- Evo2-40B GPU shape conflicts across sources: the faststart lane pins a "
        "single-H200 profile while `modules/nims/catalog.tf` requests 2 GPUs for "
        "the same image. Unresolved; both values are carried with provenance.",
        "- `modules/nims/catalog.tf` sets `container_name = \"evo2-40b\"` on the "
        "`msa_search` entry — a likely copy-paste bug in the source catalog.",
        "- Most `modules/nims` entries deploy unpinned `latest`/`nightly` tags "
        f"({unpinned} rows without a pinned tag catalog-wide); the faststart lanes "
        "are digest-pinned and should be treated as the reproducible identities.",
        "- No GPU SKU is bound to any model outside the Forge manifests and the "
        f"faststart measurement notes ({no_sku} non-Forge rows lack a SKU matrix); "
        "`modules/nims` only requests GPU counts.",
        "",
        "## Missing per-row data",
        "",
        f"- Correctness fixtures: {missing_fixture} rows have none linked; "
        f"{example_only} rows have only a playground example request, which is not "
        "a semantic validator. Only the ten faststart lanes have strict validators.",
        f"- Storage: {feas['rows_fully_sized']} rows fully sized, "
        f"{feas['rows_partially_sized']} partially sized, {feas['rows_unsized']} "
        "with no size data. Known local footprint "
        f"{feas['known_local_bytes_total']} bytes; high-bound estimate "
        f"{feas['estimated_total_bytes_high']} bytes (see method in catalog.json).",
        "- OpenFold2's native-snapshot artifact byte count and Evo2-40B's "
        "manifest-bound artifact are not published in the metric contract; their "
        "artifact sizes are null rather than guessed.",
        "- Snapshot eligibility outside the ten faststart lanes is heuristic "
        "(`candidate-*`/`unproven-multi-gpu`), never proven.",
        "",
        "## Known evidence caveats inherited from sources",
        "",
        "- The fresh n=20 cohorts record privileged host-driver Xid absence as "
        "unavailable/unproven, and the 80 raw response bodies referenced by the "
        "two-call semantic summaries were not retained controller-side.",
        "- Forge `status=active` is treated as source-recorded serving evidence "
        "(`measured-source`), not as evidence measured by this program.",
        "- Boltz2's n=20 conservative-upper p95 (30.310246 s) fails the <30 s "
        "target; it is carried as verified inventory with a failing SLO result, "
        "not hidden.",
        "",
        "## Pilot selection",
        "",
    ]
    for p in meta["pilots"]:
        lines.append(
            f"- **{p['pilot_class']}** → `{p['selected_id']}` "
            f"(alternate `{p['alternate_id']}`). Rule: {p['selection_rule']}."
            + (f" Caveats: {'; '.join(p['caveats'])}." if p["caveats"] else "")
        )
    lines.append("")
    return "\n".join(lines)


def validate(doc: dict) -> None:
    schema_path = os.path.join(HERE, "schema", "catalog.schema.json")
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    try:
        import jsonschema
    except ImportError:  # minimal structural fallback
        for row in doc["rows"]:
            for field in schema["$defs"]["row"]["required"]:
                if field not in row:
                    raise SystemExit(f"row {row.get('id')} missing {field}")
        return
    jsonschema.validate(doc, schema)


def build() -> tuple[dict, str, str, str]:
    """Return (doc, catalog_json, catalog_tsv, gap_report) deterministically."""
    forge = load("forge-models.json")
    lanes = load("faststart-lanes.json")
    nims = load("nims-terraform.json")
    documented = load("documented-candidates.json")

    rows = (
        build_forge_rows(forge)
        + build_faststart_rows(lanes)
        + build_nims_rows(nims)
        + build_documented_rows(documented)
    )
    rows.sort(key=lambda r: r["id"])
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate row ids")
    link_and_fill(rows)

    by_availability: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rows:
        by_availability[r["availability"]["class"]] = by_availability.get(r["availability"]["class"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1

    canonical_serialization = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    meta = {
        "catalog_version": "sha256:" + hashlib.sha256(canonical_serialization.encode()).hexdigest(),
        "sources": [forge["meta"], lanes["meta"], nims["meta"], documented["meta"]],
        "row_counts": {
            "total": len(rows),
            "by_availability": by_availability,
            "by_source": by_source,
            "unique_canonical_models": len({r["canonical_key"] for r in rows}),
        },
        "family_taxonomy": family_taxonomy(rows),
        "pilots": select_pilots(rows),
        "storage_feasibility": storage_feasibility(rows),
    }
    doc = {"meta": meta, "rows": rows}
    validate(doc)

    catalog_json = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    tsv_lines = ["\t".join(TSV_COLUMNS)] + ["\t".join(tsv_row(r)) for r in rows]
    catalog_tsv = "\n".join(tsv_lines) + "\n"
    report = gap_report(rows, meta)
    return doc, catalog_json, catalog_tsv, report


def main() -> int:
    doc, catalog_json, catalog_tsv, report = build()
    meta = doc["meta"]
    by_availability = meta["row_counts"]["by_availability"]

    for name, text in (
        ("catalog.json", catalog_json),
        ("catalog.tsv", catalog_tsv),
        ("GAP_REPORT.md", report),
    ):
        leaks = find_forbidden(text) + (["/home/ path"] if "/home/" in text else [])
        if leaks:
            raise SystemExit(f"{name}: forbidden content: {sorted(set(leaks))[:10]}")
        with open(os.path.join(HERE, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(
        f"catalog: {len(doc['rows'])} rows, "
        f"{meta['row_counts']['unique_canonical_models']} canonical models; "
        f"availability {json.dumps(by_availability, sort_keys=True)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
