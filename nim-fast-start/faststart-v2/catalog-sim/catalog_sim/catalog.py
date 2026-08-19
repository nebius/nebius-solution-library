"""Synthetic ~200-model catalog anchored on the ten measured lanes.

The ten measured anchors keep their exact measured distributions. The other
catalog entries are placeholder extrapolations: each synthetic model inherits
one anchor's shape and applies a bounded deterministic scale factor to its
timing distributions and artifact size. The scale factor range and every
fleet-level parameter are explicit ``PlaceholderQuantity`` values with
mandatory sensitivity ranges.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .measured import ModelAnchor, load_anchors
from .schema import EmpiricalDist, PlaceholderQuantity, SchemaError
from .units import gib_to_bytes, seconds_to_micros

CATALOG_SEED = 20260819

# --- Placeholder fleet/scenario parameters (all swept in sensitivity runs) ---

PLACEHOLDERS: Dict[str, PlaceholderQuantity] = {
    "synthetic_scale_min": PlaceholderQuantity(
        "synthetic_scale_min", 0.6, 0.7, 0.8, "ratio",
        "lower bound of per-model timing/size scale relative to its anchor; "
        "no catalog-wide measurement exists yet",
    ),
    "synthetic_scale_max": PlaceholderQuantity(
        "synthetic_scale_max", 1.3, 1.6, 2.2, "ratio",
        "upper bound of per-model timing/size scale relative to its anchor",
    ),
    "l2_fetch_bytes_per_s": PlaceholderQuantity(
        "l2_fetch_bytes_per_s", 300e6, 1000e6, 2400e6, "bytes/s",
        "remote artifact localization bandwidth per node; Phase 5 observed "
        "~483 MB/s single-stream and ~2356 MB/s 4-way parallel NRD reads, "
        "but no task-scoped L2 benchmark exists for this fleet",
    ),
    "l1_capacity_gib": PlaceholderQuantity(
        "l1_capacity_gib", 200.0, 400.0, 800.0, "GiB",
        "node-local NVMe budget reserved for the L1 artifact cache",
    ),
    "gpu_release_seconds": PlaceholderQuantity(
        "gpu_release_seconds", 0.5, 2.0, 5.0, "seconds",
        "drain/teardown time to release the GPU from model A before "
        "starting model B; not yet measured as an isolated phase",
    ),
    "conventional_init_seconds": PlaceholderQuantity(
        "conventional_init_seconds", 45.0, 90.0, 240.0, "seconds",
        "conventional (non-snapshot) NIM start time excluding artifact "
        "load I/O; only the MSA Search cached conventional route is measured",
    ),
    "conventional_load_bytes_per_s": PlaceholderQuantity(
        "conventional_load_bytes_per_s", 300e6, 700e6, 1500e6, "bytes/s",
        "effective artifact ingest bandwidth during a conventional load",
    ),
    "node_mtbf_hours": PlaceholderQuantity(
        "node_mtbf_hours", 2.0, 6.0, 24.0, "hours",
        "preemptible node mean time between preemptions",
    ),
    "node_reprovision_seconds": PlaceholderQuantity(
        "node_reprovision_seconds", 120.0, 300.0, 900.0, "seconds",
        "time from preemption to a replacement node Ready with empty caches",
    ),
    "gpu_hour_usd": PlaceholderQuantity(
        "gpu_hour_usd", 1.9, 2.95, 4.2, "USD/GPU-hour",
        "H100-class hourly price used for reserved GPU-hour cost",
    ),
    "l2_egress_usd_per_gib": PlaceholderQuantity(
        "l2_egress_usd_per_gib", 0.0, 0.02, 0.09, "USD/GiB",
        "remote artifact read/egress cost per GiB fetched into L1",
    ),
}


@dataclass(frozen=True)
class CatalogModel:
    """One catalog entry with provenance-labeled timing inputs."""

    model_id: str
    family: str
    provenance: str  # "measured" or "placeholder-scaled"
    evidence_class: str
    strategy_default: str  # "snapshot" or "conventional"
    ready_dist: EmpiricalDist
    call1_dist: EmpiricalDist
    call2_dist: EmpiricalDist
    artifact_bytes: int
    artifact_digest: str
    local_full_read_micros: int
    conventional_ready_micros: int
    group: int  # correlation/pipeline group index
    scale: float = 1.0


def _conventional_ready_micros(
    artifact_bytes: int, level: str, anchor: ModelAnchor
) -> int:
    """Conventional-load readiness estimate for one model.

    MSA-family models are measured conventional starts; everything else is
    placeholder init + artifact ingest at placeholder bandwidth.
    """
    if anchor.strategy == "conventional":
        return anchor.ready_dist.median_micros()
    init = PLACEHOLDERS["conventional_init_seconds"].at(level)
    bw = PLACEHOLDERS["conventional_load_bytes_per_s"].at(level)
    return seconds_to_micros(init + artifact_bytes / bw)


def build_catalog(
    n_models: int = 200,
    sensitivity: str = "base",
    seed: int = CATALOG_SEED,
) -> Tuple[Dict[str, CatalogModel], Dict[str, ModelAnchor]]:
    """Deterministically build the catalog for one sensitivity level."""
    if n_models < 10:
        raise SchemaError("catalog needs at least the 10 measured anchors")
    anchors = load_anchors()
    anchor_names = sorted(anchors)
    rng = random.Random((seed, sensitivity, n_models).__repr__())

    scale_min = PLACEHOLDERS["synthetic_scale_min"].at(sensitivity)
    scale_max = PLACEHOLDERS["synthetic_scale_max"].at(sensitivity)

    catalog: Dict[str, CatalogModel] = {}
    ordered_ids = []

    # The ten measured anchors enter the catalog unscaled.
    for idx, name in enumerate(anchor_names):
        anchor = anchors[name]
        model_id = f"m{idx:03d}-{name}"
        full_read = (
            seconds_to_micros(anchor.local_full_read_seconds.value)
            if anchor.local_full_read_seconds is not None
            else 0
        )
        catalog[model_id] = CatalogModel(
            model_id=model_id,
            family=name,
            provenance="measured",
            evidence_class=anchor.evidence_class,
            strategy_default=anchor.strategy,
            ready_dist=anchor.ready_dist,
            call1_dist=anchor.call1_dist,
            call2_dist=anchor.call2_dist,
            artifact_bytes=int(anchor.artifact_bytes.value),
            artifact_digest=f"sha256-fixture-{name}-v1",
            local_full_read_micros=full_read,
            conventional_ready_micros=_conventional_ready_micros(
                int(anchor.artifact_bytes.value), sensitivity, anchor
            ),
            group=idx % 5,
            scale=1.0,
        )
        ordered_ids.append(model_id)

    # Synthetic models: deterministic anchor assignment and bounded scaling.
    for idx in range(len(anchor_names), n_models):
        family = anchor_names[idx % len(anchor_names)]
        anchor = anchors[family]
        scale = rng.uniform(scale_min, scale_max)
        model_id = f"m{idx:03d}-{family}-syn"
        artifact_bytes = int(anchor.artifact_bytes.value * scale)
        full_read = (
            int(seconds_to_micros(anchor.local_full_read_seconds.value) * scale)
            if anchor.local_full_read_seconds is not None
            else 0
        )
        catalog[model_id] = CatalogModel(
            model_id=model_id,
            family=family,
            provenance="placeholder-scaled",
            evidence_class=f"placeholder scaled x{scale:.4f} from "
            f"{anchor.evidence_class}",
            strategy_default=anchor.strategy,
            ready_dist=EmpiricalDist.scaled(
                anchor.ready_dist, scale, f"{model_id}-ready"
            ),
            call1_dist=EmpiricalDist.scaled(
                anchor.call1_dist, scale, f"{model_id}-call1"
            ),
            call2_dist=EmpiricalDist.scaled(
                anchor.call2_dist, scale, f"{model_id}-call2"
            ),
            artifact_bytes=artifact_bytes,
            artifact_digest=f"sha256-fixture-{model_id}-v1",
            local_full_read_micros=full_read,
            conventional_ready_micros=_conventional_ready_micros(
                artifact_bytes, sensitivity, anchor
            ),
            group=idx % 5 if idx % 4 else (idx // 4) % 40,
            scale=scale,
        )
        ordered_ids.append(model_id)

    # Correlation groups: fixed-size pipelines of four consecutive models so
    # correlated traces and prefetch policies share a deterministic notion of
    # "next stage".
    for pos, model_id in enumerate(ordered_ids):
        object.__setattr__(catalog[model_id], "group", pos // 4)

    return catalog, anchors


def pipeline_successor(catalog: Dict[str, CatalogModel], model_id: str) -> Optional[str]:
    """The next model in the same pipeline group, if any."""
    members = sorted(m for m, c in catalog.items() if c.group == catalog[model_id].group)
    pos = members.index(model_id)
    if pos + 1 < len(members):
        return members[pos + 1]
    return None


def scenario_placeholders_json(sensitivity: str) -> dict:
    return {
        name: {**q.to_json(), "selected_level": sensitivity, "selected": q.at(sensitivity)}
        for name, q in sorted(PLACEHOLDERS.items())
    }


def fleet_parameters(sensitivity: str) -> dict:
    """Resolve placeholder fleet parameters at one sensitivity level."""
    p = PLACEHOLDERS
    return {
        "l2_fetch_bytes_per_s": int(p["l2_fetch_bytes_per_s"].at(sensitivity)),
        "l1_capacity_bytes": gib_to_bytes(p["l1_capacity_gib"].at(sensitivity)),
        "gpu_release_micros": seconds_to_micros(p["gpu_release_seconds"].at(sensitivity)),
        "node_mtbf_micros": seconds_to_micros(p["node_mtbf_hours"].at(sensitivity) * 3600),
        "node_reprovision_micros": seconds_to_micros(
            p["node_reprovision_seconds"].at(sensitivity)
        ),
        "gpu_hour_usd": p["gpu_hour_usd"].at(sensitivity),
        "l2_egress_usd_per_gib": p["l2_egress_usd_per_gib"].at(sensitivity),
    }
