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

Offline only: no network, credentials, clusters, or GPUs are touched.
"""

from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

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
        "Snapshot capture/restore is rejected for this row by evidence "
        "(e.g. topology-mismatched runtime) or by its nature (non-serving); "
        "the only permitted startup path is a conventional start."
    ),
    "unresolved": (
        "Insufficient evidence to admit any snapshot path; fail-closed to "
        "the conventional fallback until the named blockers are resolved "
        "through the shared canary process."
    ),
}

# Snapshot-path promotion gates. Bindings cite the reviewed threat model
# (invariants INV-*, controls CTL-*) at the pinned commit.
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
            "driver, kernel, or the runtime's process topology differs "
            "from capture. Runtimes evidenced to change process topology "
            "at load are conventional-only."
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


def read_json(name: str):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def read_bytes(name: str) -> bytes:
    with open(os.path.join(HERE, name), "rb") as fh:
        return fh.read()


def verify_pins() -> None:
    for fname, key in (
        ("inputs/catalog.json", "catalog_sha256"),
        ("inputs/catalog.schema.json", "catalog_schema_sha256"),
    ):
        digest = "sha256:" + hashlib.sha256(read_bytes(fname)).hexdigest()
        if digest != PINS[key]:
            raise SystemExit(f"pinned input mismatch: {fname} is {digest}")


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
        confidence = "high"
        detail = lane["basis"]
        if lane.get("caveats"):
            detail += " Caveats: " + " ".join(lane["caveats"])
        blockers.extend(lane.get("extra_blockers", []))
        if snapshot_class == "unresolved":
            blockers.append("state-audit-pending")
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
        entry["requested_via"] = {
            "resource_broker": (
                "nim-fast-start/faststart-v2/resource-broker (immutable "
                "lease plan, unique prefix, TTL, exact-ID cleanup)"
            ),
            "request_slo_harness": (
                "nim-fast-start/faststart-v2/performance/request_slo "
                "(external T0, semantic completion, full denominator)"
            ),
        }
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


def build():
    verify_pins()
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
            "classes": CLASSES,
            "rules": RULES,
            "gates": GATES,
            "blockers": BLOCKERS,
            "class_counts": class_counts,
            "rule_counts": rule_counts,
            "fleet_counts": fleet_counts,
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
