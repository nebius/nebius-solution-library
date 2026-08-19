#!/usr/bin/env python3
"""Deterministic snapshot-eligibility classifier for the model catalog.

Consumes the vendored, commit-pinned catalog inventory (agent/
catalog-switch-model-inventory @ 9abd4920) plus hand-encoded lane
evidence, and classifies every catalog row into exactly one of four
snapshot classes:

- ``direct-snapshot-safe``
- ``snapshot-after-state-externalization``
- ``conventional-only``
- ``unresolved``

Every decision is rule-based (first matching rule wins), carries the
evidence tier and refs inherited from the catalog row, and every
non-direct active row routes to an explicit conventional fallback whose
measurement status is stated honestly. All outputs are deterministic:
rebuilding must byte-match the committed artifacts.

The BioNeMo NIM section is evidence-derived, not hand-asserted: cohort
statuses map deterministically from the vendored catalog's measured
evidence class, every evidence ref is resolved to committed bytes and
SHA-256 bound, n=20 cohorts are re-counted and their nearest-rank
percentiles recomputed from the committed TSVs, n=3 results files must
contain the exact published medians, digests, and response-timing
contract, and the zero-current-contract new-node state is proven from
the committed new-node audit. Threat-model gate bindings resolve
against the vendored reviewed threat model, and the requested_via
interfaces resolve against in-ancestry reviewed contracts.

Offline only: no network, credentials, clusters, or GPUs are touched.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
FASTSTART_ROOT = os.path.dirname(os.path.dirname(HERE))
FS_PREFIX = "nim-fast-start/faststart-v2/"

PINS = {
    "catalog_commit": "9abd49204e7dbfb9be17ebf6c3f213227a88e5ca",
    "catalog_branch": "agent/catalog-switch-model-inventory",
    "catalog_path": "nim-fast-start/faststart-v2/catalog/catalog.json",
    "catalog_sha256": "sha256:831c0517c0df3c92e3b8e802b609c08dbc5f2c0eb945fc0d21830e457a71d6ce",
    "catalog_schema_sha256": "sha256:c1d979b6ab62ed6e54edd2e1657e7aae4d557514638d726ba99ff7766e9ad56c",
    "threat_model_commit": "9cfbc1b1311a1f784a407889b215aaec5200fe0e",
    "threat_model_branch": "agent/catalog-switch-security-reliability",
    "threat_model_path": (
        "nim-fast-start/faststart-v2/catalog-switch/security-reliability/threat_model.json"
    ),
    "threat_model_sha256": "sha256:a9bfccaf2425b75beb40ed6265736aa1d97b3a26327ac37db3a9b92877bbb765",
    "threat_model_vendored": "inputs/threat_model.json",
    "resource_broker_commit": "229101bb5430143e78c4bc796b30715a2a0a14df",
    "resource_broker_branch": "agent/catalog-switch-resource-broker",
    "request_slo_commit": "ba49c9e20f194e0f419d4209608904cc9335219d",
    "request_slo_branch": "agent/catalog-switch-request-slo-harness",
}

CLASSES = {
    "direct-snapshot-safe": (
        "A native snapshot capture/restore of this exact image digest and "
        "artifact revision is proven by measured-local evidence with strict "
        "semantic validation; the restored route needs no state change."
    ),
    "snapshot-after-state-externalization": (
        "Snapshot restore is safe only after an explicit, verified "
        "externalization of mutable state (writable files, scratch dirs, "
        "sockets) out of the captured process image; the externalized "
        "variant must be qualified on its own digest-bound evidence."
    ),
    "conventional-only": (
        "On current evidence, snapshot capture/restore is rejected for this "
        "row (for example a capture whose artifact topology mismatches the "
        "restore target) or the row is non-serving; the only permitted "
        "startup path today is a conventional start. Reclassification is "
        "possible and requires new exact capture and qualification "
        "evidence through the shared canary process."
    ),
    "unresolved": (
        "Insufficient evidence to admit any snapshot path; fail-closed to "
        "the conventional fallback until the named blockers are resolved "
        "through the shared canary process."
    ),
}

# Snapshot-path promotion gates. Bindings cite the vendored reviewed
# threat model (invariants INV-*, controls CTL-*) and are resolved
# against its exact content at build time.
GATES = [
    {
        "id": "G-DIGEST",
        "title": "Digest-bound promotion",
        "requirement": (
            "A checkpoint is promoted only bound to the exact tuple "
            "{checkpoint sha256, image digest, artifact digest/revision, "
            "runtime version, driver/CUDA version, kernel version, GPU "
            "topology id}. Restore admission recomputes the tuple and "
            "refuses on any mismatch. Family-, tag-, or name-level reuse "
            "of a checkpoint across digests is forbidden."
        ),
        "bindings": ["INV-02", "CTL-01", "CTL-02", "CTL-03"],
    },
    {
        "id": "G-TOPOLOGY",
        "title": "Capture/restore topology identity",
        "requirement": (
            "Restore is refused when GPU SKU, GPU count, MIG layout, "
            "driver, kernel, mounts, canonical artifact paths, or "
            "shared-memory identity differ between the captured artifact "
            "and the restore target. A row whose only capture evidence is "
            "topology-mismatched is conventional-only until a topology-"
            "aligned recapture is qualified on exact evidence."
        ),
        "bindings": ["INV-02", "CTL-19"],
    },
    {
        "id": "G-CORRUPT",
        "title": "Corruption rejection",
        "requirement": (
            "Checkpoint and artifact content hashes are verified at write "
            "time and again at use time (verify-on-read). Archive member "
            "types are gated; truncated, mismatched, or partially written "
            "checkpoints are quarantined, never retried in place."
        ),
        "bindings": ["INV-07", "CTL-11", "CTL-16"],
    },
    {
        "id": "G-SEMEQ",
        "title": "Semantic equivalence",
        "requirement": (
            "A restored instance is accepted only after passing the row's "
            "strict semantic validator on a fresh input. HTTP readiness or "
            "health is never sufficient. A row without a linked strict "
            "validator cannot satisfy this gate, so its snapshot path is "
            "blocked until a validator exists."
        ),
        "bindings": ["INV-05", "INV-06"],
    },
    {
        "id": "G-ROLLBACK",
        "title": "Fail-closed fallback ladder",
        "requirement": (
            "Any gate failure quarantines the checkpoint (single strike), "
            "routes the request to the row's conventional fallback, and "
            "requires positively verified cleanup before the node is "
            "reused; absence of cleanup evidence quarantines the node."
        ),
        "bindings": ["INV-03", "CTL-15", "CTL-18"],
    },
    {
        "id": "G-STORAGE",
        "title": "Storage-bound restore qualification",
        "requirement": (
            "Rows with >= 50 GB known local bytes or direct-I/O artifact/"
            "checkpoint volumes must verify the attached volume's content "
            "identity against the promotion tuple before restore, and must "
            "have a measured restore on the exact target storage tier with "
            "the page-cache state named before promotion."
        ),
        "bindings": ["INV-07", "CTL-11"],
    },
]

BLOCKERS = [
    {
        "id": "multi-gpu-restore-unqualified",
        "rule": (
            "No multi-GPU native snapshot capture/restore has been "
            "qualified in this program."
        ),
        "fail_closed_behavior": (
            "Snapshot admission is refused for any row with min_gpus > 1 "
            "or multi_gpu_required; only the conventional fallback may "
            "serve it."
        ),
        "resolution_path": (
            "A dedicated multi-GPU qualification canary through the shared "
            "resource-broker/request-SLO process."
        ),
    },
    {
        "id": "no-digest-binding",
        "rule": (
            "The row records no image digest, or its registry visibility "
            "is unknown, so the G-DIGEST promotion tuple cannot be built."
        ),
        "fail_closed_behavior": (
            "Switch-fleet admission is blocked entirely - snapshot AND "
            "conventional - until a pinned digest is recorded."
        ),
        "resolution_path": (
            "Record a pinned digest and registry provenance in the "
            "catalog, then reclassify."
        ),
    },
    {
        "id": "digest-rebind-required",
        "rule": (
            "A different version/digest of the same canonical model has a "
            "proven lane, but proof does not transfer across digests."
        ),
        "fail_closed_behavior": (
            "The proven family checkpoint must never be restored onto this "
            "row; this row needs its own digest-bound capture "
            "qualification."
        ),
        "resolution_path": (
            "Highest-priority capture canary: family runtime behavior is "
            "already understood."
        ),
    },
    {
        "id": "no-capture-evidence",
        "rule": "No capture/restore evidence exists for this row.",
        "fail_closed_behavior": "Snapshot admission refused.",
        "resolution_path": (
            "Capture qualification canary after the state audit passes."
        ),
    },
    {
        "id": "state-audit-pending",
        "rule": (
            "Sockets, mutable files, external mounts, and process topology "
            "are unknown for this runtime; capture safety cannot be "
            "assessed."
        ),
        "fail_closed_behavior": (
            "No capture may be attempted before an explicit state-"
            "externalization audit; the audit routes the row to direct-"
            "snapshot-safe, snapshot-after-state-externalization, or "
            "conventional-only."
        ),
        "resolution_path": (
            "Runtime-family state audit through the shared canary process."
        ),
    },
    {
        "id": "hardware-gate-h200",
        "rule": (
            "Production-shaped capture requires the only allowed H200, "
            "whose release is an explicit owner decision."
        ),
        "fail_closed_behavior": "Capture deferred; conventional fallback only.",
        "resolution_path": "Owner decision to release the H200, then capture.",
    },
    {
        "id": "production-capture-missing",
        "rule": (
            "Only manual/provisional restore evidence exists; the "
            "production-shaped clock was never measured."
        ),
        "fail_closed_behavior": "Snapshot admission refused.",
        "resolution_path": "Production-shaped capture qualification.",
    },
    {
        "id": "unsealed-evidence-receipts",
        "rule": (
            "The cited cohort evidence is not sealed: published aggregates "
            "exist in a committed document, but the per-run result receipts "
            "live only in uncommitted external state."
        ),
        "fail_closed_behavior": (
            "Snapshot promotion is refused; the row cannot be classified "
            "snapshot-safe on unsealed evidence, regardless of the "
            "published aggregate."
        ),
        "resolution_path": (
            "Commit a replayable per-run result artifact to reseal the "
            "cohort, or run a fresh sealed cohort through the shared canary "
            "process."
        ),
    },
    {
        "id": "non-serving-row",
        "rule": "Notebook/dev image with no request-serving path.",
        "fail_closed_behavior": (
            "Excluded from the switch fleet entirely; no startup path is "
            "admissible."
        ),
        "resolution_path": "None; not a serving row.",
    },
    {
        "id": "referenced-only",
        "rule": (
            "The row exists only as a documentation reference with no "
            "pinned image or artifact."
        ),
        "fail_closed_behavior": "Excluded from the switch fleet entirely.",
        "resolution_path": (
            "Onboard the model through an authorized source, then "
            "reclassify."
        ),
    },
    {
        "id": "access-gate",
        "rule": (
            "Prefix pattern 'access-gate:<gate>': the catalog records an "
            "upstream access gate (HF token, license acceptance, private "
            "mirror, artifact gating, hardware decision) this program "
            "cannot satisfy alone."
        ),
        "fail_closed_behavior": (
            "No canary may run against this row until the named gate is "
            "satisfied."
        ),
        "resolution_path": "Satisfy the named access gate, then canary.",
    },
]

RULES = [
    {
        "id": "R01-lane-evidence",
        "order": 1,
        "condition": (
            "Row id has a hand-encoded disposition in inputs/"
            "lane_evidence.json (the ten measured faststart-v2 lanes)."
        ),
        "class": "per lane disposition",
    },
    {
        "id": "R02-non-serving",
        "order": 2,
        "condition": "startup.path == 'notebook' (no request-serving path).",
        "class": "conventional-only",
    },
    {
        "id": "R03-hypothetical",
        "order": 3,
        "condition": "availability.class == 'hypothetical' (referenced-only).",
        "class": "unresolved",
    },
    {
        "id": "R04-multi-gpu",
        "order": 4,
        "condition": "gpu.multi_gpu_required is true.",
        "class": "unresolved",
    },
    {
        "id": "R05-closed-image",
        "order": 5,
        "condition": (
            "image.digest is null or image.registry_visibility == 'unknown'."
        ),
        "class": "unresolved",
    },
    {
        "id": "R06-family-proven",
        "order": 6,
        "condition": (
            "snapshot.eligibility == 'candidate-family-proven' (same "
            "canonical model has a proven lane on a different digest)."
        ),
        "class": "unresolved",
    },
    {
        "id": "R07-unassessed",
        "order": 7,
        "condition": "Default: no capture evidence and no state audit.",
        "class": "unresolved",
    },
]

SNAPSHOT_GATE_SET = ["G-DIGEST", "G-TOPOLOGY", "G-CORRUPT", "G-SEMEQ", "G-ROLLBACK"]
CONVENTIONAL_GATE_SET = ["G-DIGEST", "G-SEMEQ", "G-ROLLBACK"]
STORAGE_BOUND_BYTES = 50_000_000_000

MEASUREMENT_OWNER = (
    "shared request-SLO harness (nim-fast-start/faststart-v2/performance/"
    "request_slo) via the resource broker (nim-fast-start/faststart-v2/"
    "resource-broker); Kubernetes conventional baselines are owned by the "
    "catalog-switch-k8s-baseline lane"
)

REQUESTED_VIA = {
    "resource_broker": (
        "nim-fast-start/faststart-v2/resource-broker (in-ancestry reviewed "
        "contract; catalog-switch-resource-lease-v1; immutable lease plan, "
        "unique prefix, TTL, exact-ID cleanup; preemptible profile for "
        "new-node cohorts)"
    ),
    "request_slo_harness": (
        "nim-fast-start/faststart-v2/performance/request_slo (in-ancestry "
        "reviewed contract; catalog-switch-ledger-event-v1 and "
        "catalog-switch-trace-v1; external T0, semantic completion, full "
        "denominator)"
    ),
}

# In-ancestry interface contracts that requested_via/measurement text
# points at. The builder refuses to emit output when a path or schema id
# is missing or drifted.
INTERFACE_CONTRACTS = [
    {
        "path": "resource-broker/lease.schema.json",
        "schema_id": "https://nebius.example/catalog-switch-resource-lease-v1.schema.json",
        "commit": PINS["resource_broker_commit"],
        "sha256": "sha256:6639e1cc759ecd7728f901aa9f2397752548f60b220cfaecb613996b7dd12b29",
    },
    {
        "path": "performance/request_slo/event.schema.json",
        "schema_id": "https://nebius.ai/schemas/catalog-switch-ledger-event-v1.json",
        "commit": PINS["request_slo_commit"],
        "sha256": "sha256:a8371e8f0e3713ccbf3db8658ae144e2c62b2ace223dbfd6ae7761d1a2cf3a52",
    },
    {
        "path": "performance/request_slo/trace.schema.json",
        "schema_id": "https://nebius.ai/schemas/catalog-switch-trace-v1.json",
        "commit": PINS["request_slo_commit"],
        "sha256": "sha256:b25b9fdc1caacbf173e6575f687899f20c8ca8ad0d6701b1d656105182ec5c3a",
    },
]

BIONEMO_NIMS = frozenset(
    [
        "boltz2",
        "openfold2",
        "diffdock",
        "evo2-40b",
        "genmol",
        "molmim",
        "msa-search",
        "openfold3",
        "proteinmpnn",
        "rfdiffusion",
    ]
)

EVIDENCE_CLASS_TO_STATUS = {
    "fresh fail-closed n=20": "complete-fresh-fail-closed-n20",
    "exact response-boundary n=3": "complete-n3",
    "exact response-boundary conventional n=3": "complete-n3-conventional",
    "manual/provisional": "missing-production-shaped",
}

RESPONSE_CONTRACT = "request-dispatch-to-complete-http-body/v1"
NEWNODE_AUDIT_PATH = "openfold2-newnode/CURRENT_STATUS.json"
METRICS_DOC_PATH = "performance/COLD_START_METRICS.md"

XID_GAP = (
    "host-driver Xid absence is recorded as unavailable/unproven for all 40 "
    "selected qualification receipts (no task-scoped privileged node-log "
    "collector existed)"
)
RAWBODY_GAP = (
    "the 80 raw response bodies referenced by the 40 two-call semantic "
    "summaries were not retained; response SHA-256, byte counts, "
    "complete-body timestamps, and strict semantic receipts are retained"
)
MOLMIM_SEAL_GAP = (
    "provenance cites a harness tree without committed per-run result "
    "receipts; the published medians appear in the committed metrics "
    "document while raw receipts live in uncommitted external state, so "
    "this cohort's evidence is not sealed pending a committed replayable "
    "result artifact"
)


def read_json(name: str):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def read_bytes(name: str) -> bytes:
    with open(os.path.join(HERE, name), "rb") as fh:
        return fh.read()


def repo_rel(catalog_path: str) -> str:
    if not catalog_path.startswith(FS_PREFIX):
        raise SystemExit(f"provenance path outside faststart-v2: {catalog_path}")
    return catalog_path[len(FS_PREFIX):]


def repo_read_bytes(rel: str) -> bytes:
    path = os.path.join(FASTSTART_ROOT, rel)
    if not os.path.isfile(path):
        raise SystemExit(f"authoritative source missing from tree: {rel}")
    with open(path, "rb") as fh:
        return fh.read()


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def verify_pins() -> None:
    for fname, key in (
        ("inputs/catalog.json", "catalog_sha256"),
        ("inputs/catalog.schema.json", "catalog_schema_sha256"),
        ("inputs/threat_model.json", "threat_model_sha256"),
    ):
        digest = sha256_hex(read_bytes(fname))
        if digest != PINS[key]:
            raise SystemExit(f"pinned input mismatch: {fname} is {digest}")


def load_threat_model_ids() -> set[str]:
    doc = json.loads(read_bytes("inputs/threat_model.json"))
    if doc.get("status") != "reviewed":
        raise SystemExit("vendored threat model is not in reviewed status")
    ids = {i["id"] for i in doc["invariants"]} | {c["id"] for c in doc["controls"]}
    if not ids:
        raise SystemExit("vendored threat model defines no invariants/controls")
    return ids


def validate_gate_bindings(gates: list[dict], threat_ids: set[str]) -> None:
    for gate in gates:
        for binding in gate["bindings"]:
            if binding == "CTL-17":
                raise SystemExit(
                    "gates must not bind the Modal-specific control CTL-17"
                )
            if binding not in threat_ids:
                raise SystemExit(
                    f"gate {gate['id']} binds unknown/renamed/drifted "
                    f"threat-model ref {binding}"
                )


def check_interface_bytes(data: bytes, contract: dict) -> None:
    digest = sha256_hex(data)
    if digest != contract["sha256"]:
        raise SystemExit(
            f"interface drift: {contract['path']} is {digest}, pinned "
            f"{contract['sha256']}"
        )
    doc = json.loads(data)
    if doc.get("$id") != contract["schema_id"]:
        raise SystemExit(
            f"interface drift: {contract['path']} $id is "
            f"{doc.get('$id')!r}, expected {contract['schema_id']!r}"
        )


def verify_interfaces() -> list[dict]:
    out = []
    for contract in INTERFACE_CONTRACTS:
        check_interface_bytes(repo_read_bytes(contract["path"]), contract)
        out.append(
            {
                "path": FS_PREFIX + contract["path"],
                "schema_id": contract["schema_id"],
                "commit": contract["commit"],
                "sha256": contract["sha256"],
            }
        )
    return out


# --- BioNeMo evidence verification (pure, unit-testable) ----------------


def nearest_rank(sorted_values: list[float], quantile: float) -> float:
    rank = math.ceil(quantile * len(sorted_values))
    return sorted_values[rank - 1]


SLO_THRESHOLD_S = 30.0

# Per-lane cohort binding for the two fresh fail-closed n=20 TSVs: the
# cohort id prefix binds the file to the NIM, and every sample must be a
# uniquely identified, qualified, cleaned, semantically exercised run.
N20_SPECS = {
    "boltz2": {"cohort_prefix": "b2-n20-"},
    "openfold2": {"cohort_prefix": "of2-n20-"},
}


def check_n20_tsv(
    tsv_text: str, expected_p50: float, expected_p95: float, cohort_prefix: str
) -> dict:
    rows = list(csv.DictReader(io.StringIO(tsv_text), delimiter="\t"))
    samples = [r for r in rows if r["record_type"] == "sample"]
    if len(samples) != 20:
        raise SystemExit(f"n20 cohort has {len(samples)} sample rows, not 20")
    cohort_ids = {r["cohort_id"] for r in rows}
    if len(cohort_ids) != 1:
        raise SystemExit(f"n20 file mixes cohorts: {sorted(cohort_ids)}")
    cohort_id = cohort_ids.pop()
    if not cohort_id.startswith(cohort_prefix):
        raise SystemExit(
            f"n20 cohort id {cohort_id!r} is not bound to this NIM "
            f"(expected prefix {cohort_prefix!r})"
        )
    if len({r["run_id"] for r in samples}) != 20:
        raise SystemExit("n20 cohort run ids are not unique")
    if {r["runner_qualification"] for r in samples} != {"PASS"}:
        raise SystemExit("n20 cohort contains non-PASS runner qualifications")
    if {r["cleanup"] for r in samples} != {"PASS"}:
        raise SystemExit("n20 cohort contains non-PASS cleanup records")
    if {r["failed_attempt_denominator"] for r in samples} != {"0/20"}:
        raise SystemExit("n20 cohort failed denominators unexpected")
    for col in ("semantic_request_1_seconds", "semantic_request_2_seconds"):
        if not all(float(r[col]) > 0 for r in samples):
            raise SystemExit(f"n20 cohort has a non-positive {col}; semantic "
                             "exercise unproven")
    summaries = {r["record"] for r in rows if r["record_type"] == "summary"}
    if not {"p50", "p95-nearest-rank", "max"} <= summaries:
        raise SystemExit("n20 cohort summary records incomplete")
    observed = sorted(float(r["demand_to_two_semantic_seconds"]) for r in samples)
    upper = sorted(
        float(r["demand_to_two_semantic_boottime_upper_seconds"]) for r in samples
    )
    got_p50 = nearest_rank(observed, 0.5)
    got_p95 = nearest_rank(observed, 0.95)
    if got_p50 != expected_p50 or got_p95 != expected_p95:
        raise SystemExit(
            "n20 recomputed percentiles "
            f"({got_p50}, {got_p95}) do not match the catalog "
            f"({expected_p50}, {expected_p95})"
        )
    upper_p95 = nearest_rank(upper, 0.95)
    slo_pass = upper_p95 < SLO_THRESHOLD_S
    outcomes = {r["cohort_outcome"] for r in samples}
    if outcomes != ({"PASS"} if slo_pass else {"SLO_FAIL"}):
        raise SystemExit(
            f"n20 cohort_outcome column {sorted(outcomes)} contradicts the "
            f"recomputed SLO (upper p95 {upper_p95})"
        )
    return {
        "sample_count": len(samples),
        "failed_attempt_denominator": "0/20",
        "boottime_upper_p50_s": nearest_rank(upper, 0.5),
        "boottime_upper_p95_s": upper_p95,
        "slo_pass_recomputed": slo_pass,
    }


# Structural extraction specs for the n=3 results files. Every field is
# addressed by exact path; token presence is never sufficient.
N3_SPECS = {
    "diffdock": {
        "status_path": ["response_boundary_requalification", "status"],
        "values_path": [
            "selected_response_boundary_n3",
            "demand_to_two_semantic_responses_seconds",
            "values",
        ],
        "median_path": [
            "selected_response_boundary_n3",
            "demand_to_two_semantic_responses_seconds",
            "median",
        ],
        "image_path": ["nim_image"],
        "contract_path": ["timing_correction", "response_timing_contract"],
    },
    "genmol": {
        "status_path": ["status"],
        "values_path": ["buffered", "demand_to_two_semantic_seconds"],
        "median_path": ["buffered", "median_seconds", "demand_to_two_semantic"],
        "image_path": ["image"],
        "contract_path": ["timing_measurement", "response_timing_contract"],
    },
    "openfold3": {
        "status_path": ["status"],
        "values_path": ["selected", "demand_to_two_semantic_responses_seconds"],
        "median_path": [
            "selected",
            "medians_seconds",
            "demand_to_two_semantic_responses",
        ],
        "image_path": None,  # file records no image ref; disclosed per entry
        "contract_path": [
            "response_boundary_requalification",
            "response_timing_contract",
        ],
    },
    "rfdiffusion": {
        "status_path": ["status"],
        "values_path": ["selected_n3", "demand_to_two_semantic_seconds", "values"],
        "median_path": ["selected_n3", "demand_to_two_semantic_seconds", "median"],
        "image_path": ["image"],
        "contract_path": ["metric_contract", "response_timing_contract"],
    },
    "proteinmpnn": {
        "status_path": ["status"],
        "values_path": [
            "selected_n3",
            "demand_to_two_semantic_responses_seconds",
            "values",
        ],
        "median_path": [
            "selected_n3",
            "demand_to_two_semantic_responses_seconds",
            "median",
        ],
        "image_path": ["image"],
        "contract_path": ["metric_contract", "response_timing_contract"],
    },
}


def get_path(doc, path: list[str]):
    node = doc
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise SystemExit(f"evidence file lacks required field {'/'.join(path)}")
        node = node[key]
    return node


# Selected-cohort binding tables: every promoted n=3 row's own selected
# result, semantic pass counts, qualification, and cleanup record are
# asserted by exact path and exact value (types included). A mutation of
# any of these fields refuses the build.
LANE_BINDINGS = {
    "diffdock": {
        "bindings": [
            (["selected_response_boundary_n3", "status"], "PASS"),
            (["selected_response_boundary_n3", "semantic_requests"], 6),
            (["selected_response_boundary_n3", "semantic_passes"], 6),
            (["response_boundary_requalification", "status"], "PASS"),
            (["response_boundary_requalification", "trial_count"], 3),
            (["response_boundary_requalification", "semantic_request_count"], 6),
            (["cleanup", "measured_run_objects_remaining"], 0),
            (["cleanup", "uid_preconditions_enforced"], True),
            (["cleanup", "active_gpu_requests_final"], 0),
        ],
        "unique_run_ids": ["selected_response_boundary_n3", "runs"],
    },
    "genmol": {
        "bindings": [
            (["response_boundary_requalification", "status"], "PASS"),
            (["response_boundary_requalification", "semantic_pass_count"], 6),
            (
                [
                    "response_boundary_requalification",
                    "cleanup_commands_succeeded_after_each_trial",
                ],
                True,
            ),
            (
                [
                    "response_boundary_requalification",
                    "target_image_and_worker_image_resident_before_t0",
                ],
                True,
            ),
            (["buffered", "trial_count"], 3),
            (["buffered", "request_count"], 6),
        ],
        "unique_run_ids": ["response_boundary_requalification", "selected_run_ids"],
    },
    "openfold3": {
        "bindings": [
            (["response_boundary_requalification", "status"], "PASS"),
            (["response_boundary_requalification", "trial_count"], 3),
            (["response_boundary_requalification", "semantic_call_count"], 6),
            (["selected", "trial_count"], 3),
            (["selected", "semantic_call_count"], 6),
        ],
        "unique_run_ids": None,
    },
    "rfdiffusion": {
        "bindings": [
            (["selected_n3", "status"], "PASS"),
            (["selected_n3", "semantic_pass_count"], 6),
        ],
        "unique_run_ids": ["selected_n3", "run_ids"],
    },
    "proteinmpnn": {
        "bindings": [
            (["selected_n3", "status"], "PASS"),
            (["selected_n3", "trial_count"], 3),
            (["selected_n3", "semantic_pass_count"], 6),
            (
                [
                    "cleanup",
                    "run_id_scoped_exact_manifest_cleanup_succeeded_after_each_trial",
                ],
                True,
            ),
            (["cleanup", "counted_run_resources_remaining"], 0),
        ],
        "unique_run_ids": ["selected_n3", "run_ids"],
    },
    "msa-search": {
        "bindings": [
            (["response_boundary_requalification", "status"], "PASS"),
            (
                ["response_boundary_requalification", "response_timing_contract"],
                RESPONSE_CONTRACT,
            ),
            (["conventional_cached_n3", "semantic_call_count"], 6),
            (["conventional_cached_n3", "strict_semantic_calls_per_trial"], 2),
            (
                ["conventional_cached_n3", "target_image_residency", "preloaded_outside_t0"],
                True,
            ),
            (
                [
                    "conventional_cached_n3",
                    "target_image_residency",
                    "target_event_pulling_count",
                ],
                0,
            ),
            (["cleanup", "counted_run_jobs_remaining"], 0),
            (["cleanup", "counted_run_pods_remaining"], 0),
            (["cleanup", "active_gpu_request_total_on_node"], 0),
            (["cleanup", "per_trial_cleanup_receipt_count"], 3),
        ],
        "unique_run_ids": None,
    },
}


def assert_lane_bindings(nim: str, doc: dict) -> None:
    table = LANE_BINDINGS[nim]
    for path, expected in table["bindings"]:
        actual = get_path(doc, path)
        if actual is not expected and actual != expected:
            raise SystemExit(
                f"{nim} evidence binding {'/'.join(path)} is {actual!r}, "
                f"expected {expected!r}"
            )
        if type(actual) is not type(expected):
            raise SystemExit(
                f"{nim} evidence binding {'/'.join(path)} has type "
                f"{type(actual).__name__}, expected {type(expected).__name__}"
            )
    if table["unique_run_ids"] is not None:
        run_ids = get_path(doc, table["unique_run_ids"])
        if not isinstance(run_ids, list) or len(run_ids) != 3 or len(set(run_ids)) != 3:
            raise SystemExit(f"{nim} evidence run ids are not 3 unique runs")


def check_of3_digest_join(results_doc: dict, prior_doc: dict, image_ref: str) -> None:
    """OpenFold3's results file records no image; the digest binds through
    the checkpoint identity shared with the prior-evidence file."""
    if get_path(prior_doc, ["status"]) != "PASS":
        raise SystemExit("openfold3 prior-evidence status is not PASS")
    if get_path(prior_doc, ["execution_identity", "image"]) != image_ref:
        raise SystemExit(
            "openfold3 prior-evidence image does not equal the row's pinned "
            "image reference"
        )
    sel = results_doc["selected"]
    ckpt = prior_doc["checkpoint"]
    for key in ("checkpoint_id", "manifest_sha256"):
        if sel.get(key) != ckpt.get(key):
            raise SystemExit(
                f"openfold3 checkpoint join broken on {key}: "
                f"{sel.get(key)!r} != {ckpt.get(key)!r}"
            )
    if str(sel.get("artifact_version")) != str(ckpt.get("artifact_version")):
        raise SystemExit("openfold3 checkpoint join broken on artifact_version")


# Evidence files verified in addition to the catalog row's provenance:
# ProteinMPNN's digest-bearing results file and OpenFold3's digest-join
# prior-evidence file. Cited explicitly so promotion never rests on
# image-free evidence alone.
SUPPLEMENTARY_EVIDENCE = {
    "proteinmpnn": ["proteinmpnn-native/results.json"],
    "openfold3": ["openfold3-native/prior-evidence.json"],
}

# Lanes whose committed results file records no cleanup block; disclosed
# as an outstanding evidence gap instead of being silently assumed.
NO_CLEANUP_RECORD = frozenset(["openfold3", "rfdiffusion"])

# How each promoted cohort's exact image digest is bound to its evidence.
IMAGE_BINDING = {
    "boltz2": "cohort-bound-n20",
    "openfold2": "cohort-bound-n20",
    "diffdock": "in-file",
    "genmol": "in-file",
    "rfdiffusion": "in-file",
    "proteinmpnn": "in-file",
    "msa-search": "in-file",
    "evo2-40b": "in-file",
    "openfold3": "checkpoint-join",
    "molmim": "none",
}


def check_n3_results(
    doc: dict, spec: dict, expected_p50: float, expected_image: str | None
) -> list[float]:
    if get_path(doc, spec["status_path"]) != "PASS":
        raise SystemExit("n3 results file status is not PASS")
    values = get_path(doc, spec["values_path"])
    if (
        not isinstance(values, list)
        or len(values) != 3
        or not all(isinstance(v, float) for v in values)
    ):
        raise SystemExit("n3 results file does not carry exactly 3 float samples")
    median = get_path(doc, spec["median_path"])
    if sorted(values)[1] != median or median != expected_p50:
        raise SystemExit(
            f"n3 median inconsistent: samples give {sorted(values)[1]}, file "
            f"says {median}, catalog says {expected_p50}"
        )
    if get_path(doc, spec["contract_path"]) != RESPONSE_CONTRACT:
        raise SystemExit("n3 results file uses a different response-timing contract")
    if spec["image_path"] is not None:
        if get_path(doc, spec["image_path"]) != expected_image:
            raise SystemExit(
                "n3 results file image ref does not equal the row's pinned "
                "image reference"
            )
    elif expected_image is not None:
        raise SystemExit("image binding requested but spec records no image field")
    return values


def check_pmpnn_tsv(tsv_text: str, expected_p50: float) -> list[float]:
    rows = list(csv.DictReader(io.StringIO(tsv_text), delimiter="\t"))
    if len(rows) != 3:
        raise SystemExit(f"proteinmpnn cohort has {len(rows)} rows, not 3")
    if {r["status"] for r in rows} != {"PASS"}:
        raise SystemExit("proteinmpnn cohort contains non-PASS rows")
    if len({r["run_id"] for r in rows}) != 3:
        raise SystemExit("proteinmpnn run ids are not unique")
    vals = sorted(float(r["demand_to_two_semantic_responses_seconds"]) for r in rows)
    if vals[1] != expected_p50:
        raise SystemExit(
            f"proteinmpnn median {vals[1]} does not match catalog {expected_p50}"
        )
    return vals


def check_msa_results(doc: dict, expected_p50: float) -> list[float]:
    conv = doc["conventional_cached_n3"]
    if conv["status"] != "PASS" or conv["trial_count"] != 3:
        raise SystemExit("msa conventional n3 cohort is not a 3-trial PASS")
    if conv["mmseqs_pipe_pass_count"] != 3:
        raise SystemExit("msa MMseqs pipe validation did not pass 3/3")
    stats = conv["demand_to_call2_response_seconds"]
    values = stats["values"]
    if len(values) != 3 or sorted(values)[1] != stats["median"]:
        raise SystemExit("msa conventional sample/median aggregate inconsistent")
    if stats["median"] != expected_p50:
        raise SystemExit("msa conventional median does not match the catalog")
    native = doc["native_checkpoint"]
    if native["status"] != "EXCLUDED_NON_PROMOTABLE" or native["counted_trials"] != 0:
        raise SystemExit("msa native exclusion state drifted")
    reason = native["reason"]
    if "emptyDir" not in reason or "cache PVC" not in reason:
        raise SystemExit("msa exclusion reason drifted from donor/target mismatch")
    fix = native["required_fix"]
    if "fresh checkpoint" not in fix or "/opt/nim/.cache" not in fix:
        raise SystemExit("msa prescribed aligned-recapture fix drifted")
    return values


def assert_slo_consistent(recomputed: bool, catalog_flag, source: str) -> None:
    if catalog_flag is None or bool(catalog_flag) != recomputed:
        raise SystemExit(
            f"catalog slo_under_30s {catalog_flag!r} contradicts the "
            f"recomputed SLO {recomputed} from {source}"
        )


def check_evo2_profile(doc: dict, digest: str) -> None:
    if digest not in doc["model"]["image"]:
        raise SystemExit("evo2 profile does not pin the row's image digest")


def check_metrics_doc(text: str) -> None:
    normalized = " ".join(text.split())
    for phrase in (
        "Xid absence as unavailable/unproven",
        "80 raw response bodies",
        "15.431630",
    ):
        if phrase not in normalized:
            raise SystemExit(f"metrics document drifted: missing {phrase!r}")


def check_zero_newnode_samples(doc: dict) -> dict:
    contract = doc["current_contract"]
    if contract["sample_count"] != 0:
        raise SystemExit("new-node current-contract sample count is not zero")
    if contract["poolable_run_ids"] != []:
        raise SystemExit("new-node audit lists poolable runs; zero-sample proof fails")
    if contract["classification"] != "NO_CURRENT_CONTRACT_EVIDENCE":
        raise SystemExit("new-node audit classification drifted")
    blockers = doc["v1_blockers"]["missing_current_contract_evidence"]
    if "n>=20 cohort aggregator" not in blockers:
        raise SystemExit("authoritative n>=20 cohort aggregator requirement missing")
    if not any("at least 20 accepted samples" in step for step in doc["newnode_v2_plan"]):
        raise SystemExit("authoritative >=20 accepted-samples plan step missing")
    return {
        "sample_count": 0,
        "poolable_run_ids": [],
        "classification": contract["classification"],
        "future_execution_path": contract["future_execution_path"],
        "historical_run_ids": sorted(r["run_id"] for r in doc["historical_runs"]),
    }


def check_no_other_newnode_dirs(names: list[str]) -> None:
    newnode = {n for n in names if n.endswith("-newnode")}
    if newnode != {"openfold2-newnode"}:
        raise SystemExit(
            f"unexpected new-node evidence directories {sorted(newnode)}; "
            "reclassification required before build"
        )


def derive_provisioned_status(evidence_class: str | None, sealed: bool = True) -> str:
    if evidence_class not in EVIDENCE_CLASS_TO_STATUS:
        raise SystemExit(
            f"unmapped measured evidence class {evidence_class!r}; refusing "
            "to assert a cohort status without evidence"
        )
    status = EVIDENCE_CLASS_TO_STATUS[evidence_class]
    if not sealed:
        if status != "complete-n3":
            raise SystemExit(
                f"unsealed evidence is only modeled for n=3 cohorts, got {status}"
            )
        return "complete-n3-unsealed"
    return status


def derive_newnode_status(row_blockers: list[str]) -> str:
    if "hardware-gate-h200" in row_blockers:
        return "blocked-hardware-gate-h200"
    return "required-not-run"


def check_min_samples(
    min_samples: int, required_text: str, per_scenario: bool = True
) -> None:
    if per_scenario is not True:
        raise SystemExit("new-node cohort requirement must be per-scenario")
    if min_samples < 20:
        raise SystemExit(
            f"new-node minimum accepted samples {min_samples} weakens the "
            "authoritative n>=20 contract"
        )
    if "at least 20 accepted samples per scenario" not in required_text:
        raise SystemExit(
            "new-node required text lost the exact per-scenario >=20 "
            "accepted-samples term"
        )
    lowered = required_text.lower()
    for weakener in (
        "across scenarios",
        "across all scenarios",
        "total across",
        "in total",
        "combined across",
        "summed across",
    ):
        if weakener in lowered:
            raise SystemExit(
                f"new-node required text weakens per-scenario counting: "
                f"{weakener!r}"
            )
    for match in re.finditer(r"n\s*>=\s*(\d+)", required_text):
        if int(match.group(1)) < 20:
            raise SystemExit(
                f"new-node required text contains weakened term {match.group(0)!r}"
            )


# --- classification ------------------------------------------------------


def is_storage_bound(row: dict) -> bool:
    if row["storage"]["local_bytes_known"] >= STORAGE_BOUND_BYTES:
        return True
    for mount in row["startup"].get("external_mounts") or []:
        if "direct I/O" in mount or "checkpoint volume" in mount:
            return True
    return False


def evidence_refs(row: dict) -> list[str]:
    return sorted({p["path"] for p in row["provenance"]})


def promotion_gates(snapshot_class: str, storage_bound: bool) -> list[str]:
    if snapshot_class == "conventional-only":
        return list(CONVENTIONAL_GATE_SET)
    gates = list(SNAPSHOT_GATE_SET)
    if storage_bound:
        gates.append("G-STORAGE")
    return gates


def classify_row(row: dict, lanes: dict) -> dict:
    rid = row["id"]
    avail = row["availability"]
    storage_bound = is_storage_bound(row)
    blockers: list[str] = []
    fleet_status = "active"
    canonical_fallback_path = (
        "conventional-cached-start"
        if row["startup"]["path"] == "conventional-cached-start"
        else "conventional-pull-and-load"
    )
    fallback = {
        "path": canonical_fallback_path,
        "admission": "measurement-required",
        "measured": False,
        "measurement_refs": [],
        "measurement_owner": MEASUREMENT_OWNER,
    }

    if rid in lanes:
        lane = lanes[rid]
        rule = "R01-lane-evidence"
        snapshot_class = lane["disposition"]
        confidence = lane.get("confidence", "high")
        detail = lane["basis"]
        if lane.get("caveats"):
            detail += " Caveats: " + " ".join(lane["caveats"])
        blockers.extend(lane.get("extra_blockers", []))
        if snapshot_class == "unresolved" and not blockers:
            raise SystemExit(f"lane {rid} is unresolved without named blockers")
        if snapshot_class == "conventional-only" and lane.get("fallback_measured"):
            fallback["admission"] = "measured"
            fallback["measured"] = True
            fallback["measurement_refs"] = evidence_refs(row)
    elif row["startup"]["path"] == "notebook":
        rule = "R02-non-serving"
        snapshot_class = "conventional-only"
        confidence = "high"
        detail = (
            "Notebook/dev image with no request-serving path; excluded "
            "from the switch fleet, so no startup path is admissible."
        )
        fleet_status = "excluded-non-serving"
        blockers.append("non-serving-row")
        fallback["admission"] = "excluded"
    elif avail["class"] == "hypothetical":
        rule = "R03-hypothetical"
        snapshot_class = "unresolved"
        confidence = "high"
        detail = (
            "Documentation reference only; no pinned image or artifact "
            "exists to classify or serve."
        )
        fleet_status = "excluded-hypothetical"
        blockers.append("referenced-only")
        fallback["admission"] = "excluded"
    elif row["gpu"]["multi_gpu_required"]:
        rule = "R04-multi-gpu"
        snapshot_class = "unresolved"
        confidence = "high"
        detail = (
            "Multi-GPU serving; no multi-GPU native snapshot restore has "
            "been qualified in this program, so the snapshot path is "
            "refused fail-closed."
        )
        blockers.extend(["multi-gpu-restore-unqualified", "no-capture-evidence"])
    elif row["image"]["digest"] is None or row["image"]["registry_visibility"] == "unknown":
        rule = "R05-closed-image"
        snapshot_class = "unresolved"
        confidence = "high"
        detail = (
            "Closed or unpinned image: no digest binding is possible, so "
            "neither snapshot nor conventional switch-fleet admission can "
            "pass the digest-bound promotion gate."
        )
        blockers.extend(
            ["no-digest-binding", "no-capture-evidence", "state-audit-pending"]
        )
        fallback["admission"] = "blocked-until-digest-bound"
    elif row["snapshot"]["eligibility"] == "candidate-family-proven":
        rule = "R06-family-proven"
        snapshot_class = "unresolved"
        confidence = "medium"
        detail = (
            "Same canonical model has a proven faststart lane on a "
            "different digest; proof does not transfer across digests "
            "(INV-02), so this row needs its own digest-bound capture "
            "qualification."
        )
        blockers.append("digest-rebind-required")
    else:
        rule = "R07-unassessed"
        snapshot_class = "unresolved"
        confidence = "low"
        detail = (
            "No capture/restore evidence and no state audit for this "
            "runtime; fail-closed to the conventional fallback."
        )
        blockers.extend(["no-capture-evidence", "state-audit-pending"])

    if (
        snapshot_class == "unresolved"
        and row["snapshot"]["eligibility"] == "candidate-family-proven"
    ):
        blockers.append("digest-rebind-required")
    for gate in avail.get("gates", []):
        blockers.append(f"access-gate:{gate}")
    blockers = sorted(set(blockers))

    return {
        "id": rid,
        "canonical_key": row["canonical_key"],
        "name": row["name"],
        "source": row["source"],
        "catalog": {
            "availability_class": avail["class"],
            "availability_gates": sorted(avail.get("gates", [])),
            "snapshot_eligibility": row["snapshot"]["eligibility"],
            "startup_path": row["startup"]["path"],
            "runtime_family": row["startup"]["runtime_family"],
            "multi_gpu_required": row["gpu"]["multi_gpu_required"],
            "min_gpus": row["gpu"]["min_gpus"],
            "image_digest": row["image"]["digest"],
            "registry_visibility": row["image"]["registry_visibility"],
            "tag_pinned": row["image"]["tag_pinned"],
            "local_bytes_known": row["storage"]["local_bytes_known"],
            "validator": row["fixtures"].get("validator_path"),
        },
        "fleet_status": fleet_status,
        "snapshot_class": snapshot_class,
        "decision_rule": rule,
        "confidence": confidence,
        "evidence": {
            "tier": avail["evidence_tier"],
            "refs": evidence_refs(row),
            "detail": detail,
        },
        "storage_bound": storage_bound,
        "blockers": blockers,
        "promotion_gates": promotion_gates(snapshot_class, storage_bound),
        "fallback": fallback,
        "canary_ids": [],
    }


def eligible_for_canary(out_row: dict) -> bool:
    return (
        out_row["fleet_status"] == "active"
        and not out_row["catalog"]["availability_gates"]
        and out_row["catalog"]["image_digest"] is not None
    )


def pick(pool: list[dict], key) -> dict:
    if not pool:
        raise SystemExit("canary pool unexpectedly empty; refusing to build")
    return sorted(pool, key=key)[0]


def build_canary_plan(out_rows: list[dict], lanes: dict) -> dict:
    by_rule = lambda r: [x for x in out_rows if x["decision_rule"] == r]  # noqa: E731
    direct = [
        x
        for x in out_rows
        if x["snapshot_class"] == "direct-snapshot-safe" and eligible_for_canary(x)
    ]
    entries = []

    c1 = pick(
        [x for x in direct if x["catalog"]["local_bytes_known"] > 0],
        key=lambda x: (x["catalog"]["local_bytes_known"], x["id"]),
    )
    entries.append(
        {
            "canary_id": "canary-direct-min-bytes",
            "purpose": (
                "Re-prove the smallest direct-snapshot-safe lane end to end "
                "under the shared external-T0 request-SLO contract."
            ),
            "row_id": c1["id"],
            "snapshot_attempt_allowed": True,
        }
    )

    c2 = pick(
        [x for x in direct if x["storage_bound"]],
        key=lambda x: (-x["catalog"]["local_bytes_known"], x["id"]),
    )
    entries.append(
        {
            "canary_id": "canary-direct-storage-heavy",
            "purpose": (
                "Qualify the storage-bound gate (G-STORAGE): restore the "
                "heaviest direct lane on the exact target storage tier with "
                "the page-cache state named."
            ),
            "row_id": c2["id"],
            "snapshot_attempt_allowed": True,
        }
    )

    c3 = pick(
        [
            x
            for x in by_rule("R06-family-proven")
            if eligible_for_canary(x) and not x["catalog"]["multi_gpu_required"]
        ],
        key=lambda x: x["id"],
    )
    entries.append(
        {
            "canary_id": "canary-family-proven-rebind",
            "purpose": (
                "Prove digest rebinding: the family checkpoint must be "
                "refused for this digest (G-DIGEST), and a fresh capture "
                "qualification must succeed or fail on its own evidence."
            ),
            "row_id": c3["id"],
            "snapshot_attempt_allowed": True,
        }
    )

    for family, cid in (("vllm", "canary-vllm-state-audit"), ("tei", "canary-tei-state-audit")):
        cand = pick(
            [
                x
                for x in by_rule("R07-unassessed")
                if eligible_for_canary(x)
                and x["catalog"]["runtime_family"] == family
                and x["catalog"]["availability_class"] == "verified"
                and x["catalog"]["local_bytes_known"] > 0
            ],
            key=lambda x: (x["catalog"]["local_bytes_known"], x["id"]),
        )
        entries.append(
            {
                "canary_id": cid,
                "purpose": (
                    f"State-externalization audit for the {family} runtime "
                    "family (sockets, mutable files, external mounts, process "
                    "topology) plus a measured conventional baseline."
                ),
                "row_id": cand["id"],
                "snapshot_attempt_allowed": False,
            }
        )

    c6 = pick(
        [x for x in by_rule("R04-multi-gpu") if eligible_for_canary(x)],
        key=lambda x: (x["catalog"]["min_gpus"], x["id"]),
    )
    entries.append(
        {
            "canary_id": "canary-multi-gpu-conventional",
            "purpose": (
                "Measured conventional baseline for a multi-GPU row; any "
                "snapshot attempt is forbidden (multi-gpu-restore-"
                "unqualified is fail-closed)."
            ),
            "row_id": c6["id"],
            "snapshot_attempt_allowed": False,
        }
    )

    for entry in entries:
        entry["requested_via"] = dict(REQUESTED_VIA)
        entry["status"] = "requested-not-run"

    evo2_id = next(
        rid for rid, lane in lanes.items() if "hardware-gate-h200" in lane.get("extra_blockers", [])
    )
    return {
        "process": (
            "Canaries are requests to the shared resource/harness process, "
            "never independent runs by this task. Each canary requires an "
            "approved broker lease plan and must report through the shared "
            "request-SLO event schema with all attempts in the denominator, "
            "explicit cost accounting, and exact-ID cleanup receipts."
        ),
        "entries": entries,
        "deferred": [
            {
                "row_id": evo2_id,
                "reason": (
                    "hardware-gate-h200: production-shaped capture is "
                    "deferred pending the explicit owner decision to release "
                    "the only allowed H200; no canary is requested."
                ),
                "status": "deferred-not-requested",
            }
        ],
    }


# --- BioNeMo section ------------------------------------------------------


def verify_lane_evidence(nim: str, cat_row: dict, refs: list[str]) -> dict:
    """Resolve and verify the committed evidence behind one NIM lane.
    Returns bound refs (path+sha256), recomputed cohort figures, the
    sealing state, and the SLO recomputed from verified samples (never
    from the catalog boolean)."""
    measured = cat_row["startup"].get("measured") or {}
    p50 = measured.get("t0_to_call2_p50_s")
    p95 = measured.get("t0_to_call2_p95_s")
    digest = cat_row["image"]["digest"]
    image_ref = f"{cat_row['image']['upstream_ref']}@{digest}"
    bound_refs = []
    recomputed = {}
    sealed = True
    values: list[float] | None = None
    image_verified = False
    of3_results_doc = None
    of3_prior_doc = None
    for ref in refs:
        rel = repo_rel(ref)
        if ref.endswith("/"):
            # Directory citation (MolMIM): a harness tree is not a sealed
            # per-run result artifact and cannot be hash-bound as one.
            if not os.path.isdir(os.path.join(FASTSTART_ROOT, rel)):
                raise SystemExit(f"cited evidence directory missing: {ref}")
            bound_refs.append({"path": ref, "sha256": None})
            sealed = False
            continue
        data = repo_read_bytes(rel)
        bound_refs.append({"path": ref, "sha256": sha256_hex(data)})
        text = data.decode("utf-8")
        if rel == METRICS_DOC_PATH:
            check_metrics_doc(text)
        elif nim in N20_SPECS and rel.endswith(".tsv"):
            recomputed = check_n20_tsv(
                text, p50, p95, N20_SPECS[nim]["cohort_prefix"]
            )
            image_verified = True  # cohort id is NIM-bound; digest from row id
        elif nim == "proteinmpnn" and rel.endswith(".tsv"):
            tsv_values = check_pmpnn_tsv(text, p50)
            if values is not None and sorted(tsv_values)[1] != sorted(values)[1]:
                raise SystemExit("proteinmpnn TSV and results medians diverge")
        elif nim == "msa-search" and rel.endswith("results.json"):
            doc = json.loads(text)
            values = check_msa_results(doc, p50)
            if get_path(doc, ["nim_image"]) != image_ref:
                raise SystemExit(
                    "msa results file image ref does not equal the row's "
                    "pinned image reference"
                )
            assert_lane_bindings(nim, doc)
            image_verified = True
        elif nim == "evo2-40b" and rel.endswith("profile.json"):
            check_evo2_profile(json.loads(text), digest)
            image_verified = True
        elif nim == "openfold3" and rel.endswith("prior-evidence.json"):
            of3_prior_doc = json.loads(text)
        elif nim in N3_SPECS and rel.endswith("results.json"):
            spec = N3_SPECS[nim]
            doc = json.loads(text)
            values = check_n3_results(
                doc,
                spec,
                p50,
                image_ref if spec["image_path"] is not None else None,
            )
            assert_lane_bindings(nim, doc)
            if spec["image_path"] is not None:
                image_verified = True
            if nim == "openfold3":
                of3_results_doc = doc
        else:
            raise SystemExit(f"unrecognized evidence ref for {nim}: {ref}")
    if nim == "openfold3":
        if of3_results_doc is None or of3_prior_doc is None:
            raise SystemExit(
                "openfold3 requires both results.json and prior-evidence.json "
                "to close the digest join"
            )
        check_of3_digest_join(of3_results_doc, of3_prior_doc, image_ref)
        image_verified = True
    expected_binding = IMAGE_BINDING[nim]
    if expected_binding != "none" and not image_verified:
        raise SystemExit(
            f"{nim}: image binding {expected_binding!r} was not verified by "
            "any cited evidence"
        )
    # SLO is recomputed from verified evidence only; the catalog boolean is
    # cross-checked, never trusted.
    slo_recomputed: bool | None = None
    if "slo_pass_recomputed" in recomputed:
        slo_recomputed = recomputed["slo_pass_recomputed"]
    elif sealed and values is not None:
        slo_recomputed = sorted(values)[1] < SLO_THRESHOLD_S
    if slo_recomputed is not None:
        assert_slo_consistent(
            slo_recomputed, measured.get("slo_under_30s"), f"{nim} lane evidence"
        )
    return {
        "refs": bound_refs,
        "recomputed": recomputed,
        "sealed": sealed,
        "slo_recomputed": slo_recomputed,
        "image_binding": expected_binding,
    }


def provisioned_outcome(
    nim: str, status: str, measured: dict, verified: dict
) -> dict | None:
    if status == "missing-production-shaped":
        return None
    recomputed = verified["recomputed"]
    outcome = {
        "slo_threshold_s": SLO_THRESHOLD_S,
        "slo_pass": verified["slo_recomputed"],
        "t0_to_call2_p50_s": measured.get("t0_to_call2_p50_s"),
        "t0_to_call2_p95_s": measured.get("t0_to_call2_p95_s"),
        "boottime_upper_p50_s": recomputed.get("boottime_upper_p50_s"),
        "boottime_upper_p95_s": recomputed.get("boottime_upper_p95_s"),
        "note": None,
    }
    if status == "complete-fresh-fail-closed-n20":
        if outcome["slo_pass"]:
            outcome["note"] = (
                "SLO PASS on the conservative BOOTTIME upper bound, "
                "recomputed from the committed cohort TSV; cohort evidence "
                "closure does not close the outstanding evidence gaps "
                "listed separately."
            )
        else:
            outcome["note"] = (
                "SLO FAIL is a latency result, not an execution failure: "
                "all 20 samples were semantically valid with clean cleanup "
                "and a 0/20 failed denominator (recomputed from the "
                "committed cohort TSV)."
            )
    elif outcome["slo_pass"] is None:
        outcome["note"] = (
            "SLO not asserted: the cohort evidence is not sealed, so no "
            "per-run samples exist in committed bytes to recompute it; the "
            "published median appears only in the committed metrics "
            "document."
        )
    return outcome


def provisioned_further_required(nim: str, status: str, outcome: dict | None) -> str | None:
    if status == "complete-fresh-fail-closed-n20":
        gaps = (
            "outstanding evidence gaps (host-driver Xid proof, raw "
            "response-body retention) remain open"
        )
        if outcome and outcome["slo_pass"]:
            return (
                "no further provisioned-node cohort samples required; "
                + gaps
                + " and are not closed by the SLO pass"
            )
        return (
            f"sub-30 s SLO not met (conservative-upper p95 "
            f"{outcome['boottime_upper_p95_s']} s); latency work is tracked "
            "by the sibling boltz2-under-20 task; " + gaps
        )
    if status == "complete-n3":
        base = "fresh fail-closed n=20 rerun to the Boltz2/OpenFold2 evidence standard"
        if outcome and outcome["slo_pass"] is False:
            base += (
                f" (published T0-to-call-2 median {outcome['t0_to_call2_p50_s']} s "
                "already exceeds the 30 s SLO)"
            )
        return base
    if status == "complete-n3-unsealed":
        return (
            "commit a replayable per-run result artifact to reseal the "
            "existing cohort, or run a fresh sealed cohort; then a fresh "
            "fail-closed n=20 rerun to the Boltz2/OpenFold2 evidence "
            "standard"
        )
    if status == "complete-n3-conventional":
        return (
            "fresh fail-closed n=20 conventional rerun to the "
            "Boltz2/OpenFold2 evidence standard"
        )
    if status == "missing-production-shaped":
        return (
            "production-shaped capture and cohort on the pinned digest; "
            "deferred pending the explicit owner decision to release the "
            "only allowed H200"
        )
    raise SystemExit(f"no further-required rule for status {status}")


def build_bionemo_section(
    cohort_doc: dict, by_id: dict, cat_rows: dict
) -> tuple[list[dict], dict]:
    order = cohort_doc["evidence_order"]
    nims = cohort_doc["nims"]
    if set(order) != BIONEMO_NIMS or set(nims) != BIONEMO_NIMS:
        raise SystemExit("bionemo cohort table must cover exactly the ten NIMs")
    if order[:2] != ["boltz2", "openfold2"]:
        raise SystemExit("Boltz2/OpenFold2 evidence must rank first")
    min_samples = cohort_doc["new_preemptible_min_accepted_samples"]
    per_scenario = cohort_doc["new_preemptible_per_scenario"]
    default_required = cohort_doc["new_preemptible_required_default"]
    check_min_samples(min_samples, default_required, per_scenario)

    check_no_other_newnode_dirs(sorted(os.listdir(FASTSTART_ROOT)))
    audit_bytes = repo_read_bytes(NEWNODE_AUDIT_PATH)
    zero_proof = check_zero_newnode_samples(json.loads(audit_bytes))
    zero_proof = {
        "path": FS_PREFIX + NEWNODE_AUDIT_PATH,
        "sha256": sha256_hex(audit_bytes),
        **zero_proof,
    }

    entries = []
    for rank, nim in enumerate(order, start=1):
        spec = nims[nim]
        row = by_id.get(spec["row_id"])
        cat = cat_rows.get(spec["row_id"])
        if row is None or cat is None or row["source"] != "faststart-v2-lanes":
            raise SystemExit(f"bionemo NIM {nim} does not resolve to a faststart lane row")
        measured = cat["startup"].get("measured") or {}
        refs = evidence_refs(cat) + [
            FS_PREFIX + extra for extra in SUPPLEMENTARY_EVIDENCE.get(nim, [])
        ]
        verified = verify_lane_evidence(nim, cat, refs)
        status = derive_provisioned_status(
            measured.get("evidence_class"), verified["sealed"]
        )
        if (
            row["snapshot_class"] in ("direct-snapshot-safe",
                                      "snapshot-after-state-externalization")
            and verified["image_binding"] == "none"
        ):
            raise SystemExit(
                f"{nim}: snapshot-safe promotion without a verified exact "
                "image binding is forbidden"
            )
        outcome = provisioned_outcome(nim, status, measured, verified)

        gaps: list[str] = []
        if status == "complete-fresh-fail-closed-n20":
            gaps = [XID_GAP, RAWBODY_GAP]
        if not verified["sealed"]:
            gaps = gaps + [MOLMIM_SEAL_GAP]
        if nim in NO_CLEANUP_RECORD:
            gaps = gaps + [
                "the committed results file records no per-trial cleanup "
                "verification block, so cleanup cannot be bound from sealed "
                "bytes for this cohort; the missing record is disclosed, not "
                "assumed"
            ]

        newnode_status = derive_newnode_status(row["blockers"])
        historical_note = spec["newnode_historical_note"]
        if nim == "openfold2":
            for run_id in zero_proof["historical_run_ids"]:
                if run_id not in (historical_note or ""):
                    raise SystemExit(
                        "openfold2 historical note must name every "
                        f"non-poolable run; missing {run_id}"
                    )

        entries.append(
            {
                "nim": nim,
                "evidence_rank": rank,
                "row_id": spec["row_id"],
                "snapshot_class": row["snapshot_class"],
                "catalog_snapshot_eligibility": row["catalog"]["snapshot_eligibility"],
                "confidence": row["confidence"],
                "conventional_fallback": {
                    "path": row["fallback"]["path"],
                    "admission": row["fallback"]["admission"],
                    "measured": row["fallback"]["measured"],
                    "measurement_refs": row["fallback"]["measurement_refs"],
                },
                "storage_blockers": spec["storage_blockers"],
                "topology_blockers": spec["topology_blockers"],
                "cohorts": {
                    "provisioned_node": {
                        "status": status,
                        "evidence_class": measured.get("evidence_class"),
                        "evidence_refs": verified["refs"],
                        "sealed": verified["sealed"],
                        "image_binding": verified["image_binding"],
                        "outcome": outcome,
                        "outstanding_evidence_gaps": gaps,
                        "further_required": provisioned_further_required(
                            nim, status, outcome
                        ),
                    },
                    "new_preemptible_node": {
                        "status": newnode_status,
                        "min_accepted_samples": min_samples,
                        "per_scenario": per_scenario,
                        "required": default_required,
                        "requested_via": dict(REQUESTED_VIA),
                        "historical_note": historical_note,
                        "evidence_refs": (
                            [
                                {
                                    "path": zero_proof["path"],
                                    "sha256": zero_proof["sha256"],
                                }
                            ]
                            if nim == "openfold2"
                            else []
                        ),
                    },
                },
            }
        )
    return entries, zero_proof


def assert_modal_never_executes(doc: dict) -> None:
    """Modal is documentation-only: it must never appear in any execution-
    relevant field. The only permitted mentions are the scope notes."""
    pruned = json.loads(json.dumps(doc))
    pruned["meta"]["scope_notes"] = []
    if "modal" in json.dumps(pruned).lower():
        raise SystemExit("Modal appeared outside scope notes; it must not become an execution class")


def build():
    verify_pins()
    threat_ids = load_threat_model_ids()
    validate_gate_bindings(GATES, threat_ids)
    interfaces = verify_interfaces()
    catalog = read_json("inputs/catalog.json")
    lane_doc = read_json("inputs/lane_evidence.json")
    lanes = lane_doc["lanes"]
    if lane_doc["pinned_catalog_commit"] != PINS["catalog_commit"]:
        raise SystemExit("lane_evidence.json pinned to a different catalog commit")

    cat_rows = {r["id"]: r for r in catalog["rows"]}
    missing = sorted(set(lanes) - set(cat_rows))
    if missing:
        raise SystemExit(f"lane evidence names unknown rows: {missing}")

    out_rows = [classify_row(r, lanes) for r in catalog["rows"]]
    out_rows.sort(key=lambda x: x["id"])

    canary_plan = build_canary_plan(out_rows, lanes)
    by_id = {x["id"]: x for x in out_rows}
    for entry in canary_plan["entries"]:
        by_id[entry["row_id"]]["canary_ids"].append(entry["canary_id"])

    cohort_doc = read_json("inputs/bionemo_cohorts.json")
    if cohort_doc["pinned_catalog_commit"] != PINS["catalog_commit"]:
        raise SystemExit("bionemo_cohorts.json pinned to a different catalog commit")
    bionemo_nims, zero_proof = build_bionemo_section(cohort_doc, by_id, cat_rows)

    class_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    fleet_counts: dict[str, int] = {}
    for x in out_rows:
        class_counts[x["snapshot_class"]] = class_counts.get(x["snapshot_class"], 0) + 1
        rule_counts[x["decision_rule"]] = rule_counts.get(x["decision_rule"], 0) + 1
        fleet_counts[x["fleet_status"]] = fleet_counts.get(x["fleet_status"], 0) + 1

    doc = {
        "meta": {
            "artifact": "catalog-switch snapshot-eligibility classification",
            "task": "catalog-switch-snapshot-eligibility",
            "catalog_version": catalog["meta"]["catalog_version"],
            "pins": PINS,
            "interfaces": interfaces,
            "classes": CLASSES,
            "rules": RULES,
            "gates": GATES,
            "blockers": BLOCKERS,
            "class_counts": class_counts,
            "rule_counts": rule_counts,
            "fleet_counts": fleet_counts,
            "bionemo_nims": bionemo_nims,
            "newnode_zero_sample_proof": zero_proof,
            "fallback_policy": {
                "statement": (
                    "Every active row whose snapshot path is not direct-"
                    "snapshot-safe routes to an explicit conventional "
                    "fallback. A fallback is production-admissible for SLO "
                    "purposes only once measured through the shared "
                    "request-SLO harness; until then it is admissible for "
                    "functional serving and canary measurement only. Rows "
                    "without digest binding are blocked from switch-fleet "
                    "admission entirely, fail-closed."
                ),
                "admission_values": {
                    "measured": "a committed measurement exists (refs listed)",
                    "measurement-required": (
                        "functional conventional path; measurement owed to "
                        "the shared harness before SLO admission"
                    ),
                    "blocked-until-digest-bound": (
                        "no digest: both snapshot and conventional "
                        "switch-fleet admission are blocked"
                    ),
                    "excluded": "row is excluded from the switch fleet",
                },
            },
            "canary_plan": canary_plan,
            "scope_notes": [
                (
                    "Offline classification only: no network, credentials, "
                    "clusters, GPUs, or live resources were used; canaries "
                    "are requests, not runs."
                ),
                (
                    "Per the 2026-08-19 scope correction: Modal is reference "
                    "material only and receives no empirical or synthetic "
                    "ranking, live dependency, or test anywhere in this "
                    "lane. The sole external measured comparator is "
                    "Cerebrium; measured internal candidates are Kubernetes "
                    "and the direct/node-local VM runtime."
                ),
                (
                    "The Boltz external-/tmp worktree was read as evidence "
                    "only and never edited."
                ),
            ],
        },
        "rows": out_rows,
    }

    assert_modal_never_executes(doc)
    eligibility_json = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    tsv_cols = [
        "id",
        "name",
        "source",
        "fleet_status",
        "snapshot_class",
        "decision_rule",
        "confidence",
        "storage_bound",
        "blockers",
        "promotion_gates",
        "fallback_path",
        "fallback_admission",
        "canary_ids",
    ]
    lines = ["\t".join(tsv_cols)]
    for x in out_rows:
        lines.append(
            "\t".join(
                [
                    x["id"],
                    x["name"],
                    x["source"],
                    x["fleet_status"],
                    x["snapshot_class"],
                    x["decision_rule"],
                    x["confidence"],
                    str(x["storage_bound"]).lower(),
                    ";".join(x["blockers"]),
                    ";".join(x["promotion_gates"]),
                    x["fallback"]["path"],
                    x["fallback"]["admission"],
                    ";".join(x["canary_ids"]),
                ]
            )
        )
    eligibility_tsv = "\n".join(lines) + "\n"
    return doc, eligibility_json, eligibility_tsv


def main() -> None:
    _, eligibility_json, eligibility_tsv = build()
    with open(os.path.join(HERE, "eligibility.json"), "w", encoding="utf-8") as fh:
        fh.write(eligibility_json)
    with open(os.path.join(HERE, "eligibility.tsv"), "w", encoding="utf-8") as fh:
        fh.write(eligibility_tsv)
    print("wrote eligibility.json and eligibility.tsv")


if __name__ == "__main__":
    main()
