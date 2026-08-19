"""Measured phase distributions from the faststart-v2 evidence.

Two kinds of measured input feed the simulator:

1. Fresh fail-closed n=20 cohorts (OpenFold2, Boltz2) are loaded directly
   from their checked-in per-run TSVs, using the conservative CLOCK_BOOTTIME
   upper-bound readiness clock and the exact response-boundary call timers.
2. The nine production-shaped n=3 lanes from
   ``performance/COLD_START_METRICS.md`` publish ``median [minimum-maximum]``;
   with n=3 that triple *is* the complete sample set, so the exact three-run
   arrays are embedded here with their source rows.

Evo2-40B is carried as ``manual/provisional`` evidence and is never used as a
production-shaped anchor without that label. Anything not listed here is a
placeholder and must go through ``schema.PlaceholderQuantity``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schema import EmpiricalDist, MeasuredQuantity, SchemaError

FASTSTART_V2_ROOT = Path(__file__).resolve().parents[2]

N20_COHORTS = {
    "openfold2": "performance/openfold2/fresh-cohort-n20-results.tsv",
    "boltz2": "boltz2-native/fresh-cohort-n20-results.tsv",
}

METRICS_SOURCE = "nim-fast-start/faststart-v2/performance/COLD_START_METRICS.md"


@dataclass(frozen=True)
class ModelAnchor:
    """One measured model lane usable as a catalog anchor.

    ``ready_dist`` is T0 (target create) to first HTTP readiness for the
    selected lane strategy (native snapshot restore for all lanes except MSA
    Search, whose selected route is a conventional cached start).
    ``call1_dist`` is the first post-readiness semantic request (includes
    deferred per-shape init); ``call2_dist`` is the warm request path.
    ``local_full_read_seconds`` is the measured pre-T0 full artifact/cache
    read excluded from T0, i.e. the cost to move a node-local artifact from
    cold to page-resident for lanes whose selected state requires prewarm.
    """

    name: str
    strategy: str  # "snapshot" or "conventional"
    evidence_class: str
    ready_dist: EmpiricalDist
    call1_dist: EmpiricalDist
    call2_dist: EmpiricalDist
    artifact_bytes: MeasuredQuantity
    local_full_read_seconds: Optional[MeasuredQuantity]
    gpu: str = "H100"


def _n3(name: str, row: str, median: float, low: float, high: float) -> EmpiricalDist:
    """Reconstruct an exact n=3 sample set from median [min-max]."""
    if not (low <= median <= high):
        raise SchemaError(f"{name}: median must lie inside [min, max]")
    return EmpiricalDist.from_seconds(
        name, (low, median, high), f"{METRICS_SOURCE} ({row}, n=3 exact)"
    )


def load_n20_dists(model: str, root: Path = FASTSTART_V2_ROOT) -> dict:
    """Load the fresh fail-closed n=20 cohort arrays for a model."""
    rel = N20_COHORTS[model]
    path = root / rel
    ready, call1, call2 = [], [], []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if row["record_type"] != "sample":
                continue
            ready.append(float(row["demand_to_http_ready_boottime_upper_seconds"]))
            call1.append(float(row["semantic_request_1_seconds"]))
            call2.append(float(row["semantic_request_2_seconds"]))
    if len(ready) != 20:
        raise SchemaError(f"{rel}: expected 20 sample rows, got {len(ready)}")
    src = f"nim-fast-start/faststart-v2/{rel} (fresh fail-closed n=20)"
    return {
        "ready": EmpiricalDist.from_seconds(f"{model}-ready-boottime-upper", ready, src),
        "call1": EmpiricalDist.from_seconds(f"{model}-call1", call1, src),
        "call2": EmpiricalDist.from_seconds(f"{model}-call2", call2, src),
    }


def _bytes(name: str, value: int, source_row: str) -> MeasuredQuantity:
    return MeasuredQuantity(
        name=name, value=float(value), unit="bytes",
        source=f"{METRICS_SOURCE} ({source_row})",
    )


def _read(name: str, seconds: float, source_row: str) -> MeasuredQuantity:
    return MeasuredQuantity(
        name=name, value=seconds, unit="seconds",
        source=f"{METRICS_SOURCE} ({source_row})",
    )


def load_anchors(root: Path = FASTSTART_V2_ROOT) -> dict:
    """Return the ten measured model anchors keyed by lane name."""
    of2 = load_n20_dists("openfold2", root)
    b2 = load_n20_dists("boltz2", root)

    anchors = {}

    anchors["openfold2"] = ModelAnchor(
        name="openfold2",
        strategy="snapshot",
        evidence_class="fresh fail-closed n=20",
        ready_dist=of2["ready"],
        call1_dist=of2["call1"],
        call2_dist=of2["call2"],
        artifact_bytes=MeasuredQuantity(
            "openfold2-native-artifact-bytes", 7_290_652_785.0, "bytes",
            "nim-fast-start/faststart-v2/native-capture/README.md "
            "(202 files, native artifact)",
        ),
        # Selected lane uses direct/O_DIRECT artifact reads with no page-cache
        # prewarm claim, so cold->warm local prewarm cost is zero by contract.
        local_full_read_seconds=None,
    )

    anchors["boltz2"] = ModelAnchor(
        name="boltz2",
        strategy="snapshot",
        evidence_class="fresh fail-closed n=20",
        ready_dist=b2["ready"],
        call1_dist=b2["call1"],
        call2_dist=b2["call2"],
        artifact_bytes=_bytes(
            "boltz2-artifact-plus-cache-bytes",
            16_241_056_616 + 13_341_111_872,
            "pre-T0 audit: 16,241,056,616-byte M3 artifact + 13,341,111,872 "
            "payload bytes attached cache",
        ),
        local_full_read_seconds=_read(
            "boltz2-cache-full-read", 422.854590,
            "pre-T0 audit: cache full read 422.854590 s; artifact direct",
        ),
    )

    anchors["proteinmpnn"] = ModelAnchor(
        name="proteinmpnn",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3("proteinmpnn-ready", "ProteinMPNN", 9.460347, 9.401879, 9.494261),
        call1_dist=_n3("proteinmpnn-call1", "ProteinMPNN", 0.589204, 0.390123, 0.597313),
        call2_dist=_n3("proteinmpnn-call2", "ProteinMPNN", 0.248845, 0.244145, 0.255925),
        artifact_bytes=_bytes(
            "proteinmpnn-artifact-bytes", 1_867_046_505,
            "pre-T0 audit: 1,867,046,505 bytes, 57 files",
        ),
        local_full_read_seconds=_read(
            "proteinmpnn-full-read", 3.586695, "pre-T0 audit: in-holder reader"
        ),
    )

    anchors["diffdock"] = ModelAnchor(
        name="diffdock",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3("diffdock-ready", "DiffDock", 12.127239, 12.057153, 12.181481),
        call1_dist=_n3("diffdock-call1", "DiffDock", 1.456961, 1.456592, 1.462333),
        call2_dist=_n3("diffdock-call2", "DiffDock", 0.588161, 0.578353, 0.599702),
        artifact_bytes=_bytes(
            "diffdock-artifact-bytes", 7_516_058_314,
            "pre-T0 audit: 7,516,058,314 bytes, 122 files",
        ),
        local_full_read_seconds=_read(
            "diffdock-full-read", 5.931160, "pre-T0 audit"
        ),
    )

    anchors["openfold3"] = ModelAnchor(
        name="openfold3",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3("openfold3-ready", "OpenFold3", 12.271182, 12.088885, 12.369170),
        call1_dist=_n3("openfold3-call1", "OpenFold3", 9.098247, 9.070079, 9.180301),
        call2_dist=_n3("openfold3-call2", "OpenFold3", 9.166892, 9.112610, 9.174043),
        artifact_bytes=_bytes(
            "openfold3-artifact-bytes", 9_263_246_107,
            "pre-T0 audit: 9,263,246,107 bytes, 148 files",
        ),
        local_full_read_seconds=_read(
            "openfold3-full-read", 7.386615, "pre-T0 audit: in-holder reader"
        ),
    )

    anchors["msa-search"] = ModelAnchor(
        name="msa-search",
        strategy="conventional",
        evidence_class="exact response-boundary conventional n=3",
        ready_dist=_n3("msa-ready", "MSA Search PDB70", 4.872400, 4.830585, 4.962104),
        call1_dist=_n3("msa-call1", "MSA Search PDB70", 0.040644, 0.039441, 0.041808),
        call2_dist=_n3("msa-call2", "MSA Search PDB70", 0.029920, 0.028986, 0.030188),
        artifact_bytes=_bytes(
            "msa-artifact-bytes", 112_682_799,
            "pre-T0 audit: 112,682,799 bytes across 13 unique inodes",
        ),
        local_full_read_seconds=_read(
            "msa-full-read", 0.104987, "pre-T0 audit"
        ),
    )

    anchors["genmol"] = ModelAnchor(
        name="genmol",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3("genmol-ready", "GenMol", 10.400351, 10.217778, 10.478343),
        call1_dist=_n3("genmol-call1", "GenMol", 1.198462, 1.186065, 1.205458),
        call2_dist=_n3("genmol-call2", "GenMol", 0.575554, 0.574723, 0.585800),
        artifact_bytes=_bytes(
            "genmol-artifact-bytes", 4_781_347_930,
            "pre-T0 audit: 4,781,347,930 bytes, 114 files",
        ),
        local_full_read_seconds=_read(
            "genmol-full-read", 6.328907, "pre-T0 audit"
        ),
    )

    anchors["rfdiffusion"] = ModelAnchor(
        name="rfdiffusion",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3(
            "rfdiffusion-ready", "RFdiffusion", 17.662044, 17.456876, 17.965447
        ),
        call1_dist=_n3(
            "rfdiffusion-call1", "RFdiffusion", 7.892573, 7.792848, 7.980680
        ),
        call2_dist=_n3(
            "rfdiffusion-call2", "RFdiffusion", 5.584081, 5.552619, 5.726694
        ),
        artifact_bytes=_bytes(
            "rfdiffusion-artifact-plus-cache-bytes",
            22_087_352_229 + 2_590_162_178,
            "pre-T0 audit: artifact 22,087,352,229 + cache 2,590,162,178 bytes",
        ),
        local_full_read_seconds=_read(
            "rfdiffusion-full-read", 48.965637,
            "pre-T0 audit: artifact 16.332096 + cache 32.633541",
        ),
    )

    anchors["molmim"] = ModelAnchor(
        name="molmim",
        strategy="snapshot",
        evidence_class="exact response-boundary n=3",
        ready_dist=_n3("molmim-ready", "MolMIM", 10.520799, 10.446875, 10.522802),
        call1_dist=_n3("molmim-call1", "MolMIM", 2.839590, 2.812727, 2.854831),
        call2_dist=_n3("molmim-call2", "MolMIM", 2.099549, 2.082203, 2.109474),
        artifact_bytes=_bytes(
            "molmim-artifact-plus-cache-bytes",
            5_220_755_473 + 284_497_920,
            "pre-T0 audit: artifact 5,220,755,473 + cache 284,497,920 bytes",
        ),
        local_full_read_seconds=_read(
            "molmim-full-read", 4.194605 + 17.524894,
            "pre-T0 audit: artifact 4.194605 + cache 17.524894",
        ),
    )

    anchors["evo2-40b"] = ModelAnchor(
        name="evo2-40b",
        strategy="snapshot",
        evidence_class="manual/provisional (restore-trigger clock, not T0)",
        ready_dist=_n3("evo2-ready", "Evo2-40B manual", 65.377, 63.052, 65.696),
        call1_dist=_n3("evo2-call1", "Evo2-40B manual", 1.181, 1.163, 1.213),
        call2_dist=_n3("evo2-call2", "Evo2-40B manual", 0.796, 0.795, 0.819),
        artifact_bytes=_bytes(
            "evo2-artifact-bytes", 99_959_572_798,
            "pre-T0 audit: legacy direct 99,959,572,798-byte checkpoint",
        ),
        local_full_read_seconds=None,
        gpu="H200",
    )

    return anchors


# Measured direct-I/O (artifact not page-resident) readiness canaries retained
# as bounding cross-checks for the cold-local-artifact path; they are not used
# as selected anchors. Values are seconds to HTTP readiness.
DIRECT_READINESS_CANARIES = {
    "openfold3": MeasuredQuantity(
        "openfold3-direct-ready", 87.284431, "seconds",
        f"{METRICS_SOURCE} (storage sensitivity, n=1 canary)",
    ),
    "proteinmpnn": MeasuredQuantity(
        "proteinmpnn-direct-ready", 23.763, "seconds",
        f"{METRICS_SOURCE} (storage sensitivity, n=3 direct)",
    ),
    "diffdock": MeasuredQuantity(
        "diffdock-direct-ready", 72.594545, "seconds",
        f"{METRICS_SOURCE} (storage sensitivity, n=1 canary)",
    ),
    "genmol": MeasuredQuantity(
        "genmol-direct-ready", 48.738868, "seconds",
        f"{METRICS_SOURCE} (storage sensitivity, n=3 direct)",
    ),
    "rfdiffusion": MeasuredQuantity(
        "rfdiffusion-direct-ready", 199.036267, "seconds",
        f"{METRICS_SOURCE} (storage sensitivity, exact direct canary)",
    ),
}
