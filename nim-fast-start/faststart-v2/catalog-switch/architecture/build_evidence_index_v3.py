#!/usr/bin/env python3
"""Build the provenance-bound evidence index from sealed Git objects."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ARCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = ARCH_DIR.parents[3]
REPOSITORY = "https://github.com/nebius/nebius-solutions-library"
BASELINE_COMMIT = "1db7703e3078ce3236c4655816312416145eb709"
REJECTED_INDEX_COMMIT = "7dc39ea7903c8aa19fe8a8269ab435268a7ae4b7"
REVIEW_BUNDLE_COMMIT = "0c47062047d19b3271350e66cd86ee0de87a57e0"
REVIEW_BUNDLE_PATH = (
    "nim-fast-start/faststart-v2/catalog-switch/architecture/review-records.v1.json"
)
REVIEW_BUNDLE_SCHEMA_PATH = (
    "nim-fast-start/faststart-v2/catalog-switch/architecture/review-records.v1.schema.json"
)


BASE_RECORDS = {
    "EV2-METRIC-BA49": "RR1-METRIC-BA49-PROVENANCE-UNVERIFIED",
    "EV2-CATALOG-9ABD": "RR1-CATALOG-9ABD-PROVENANCE-UNVERIFIED",
    "EV2-SECURITY-9CFB": "RR1-SECURITY-9CFB-PROVENANCE-UNVERIFIED",
    "EV2-BROKER-CPU-2291": "RR1-BROKER-2291-PROVENANCE-UNVERIFIED",
    "EV2-OF2-PREPARED-0180": "RR1-PREPARED-0180-PROVENANCE-UNVERIFIED",
    "EV2-BOLTZ-PREPARED-0180": "RR1-PREPARED-0180-PROVENANCE-UNVERIFIED",
    "EV2-DRAIN-34D-REJECTED": "RR1-DRAIN-34D-REJECTED",
    "EV2-SNAPSHOT-F5F-REJECTED": "RR1-SNAPSHOT-F5F-REJECTED",
    "EV2-BROKER-D40-REJECTED": "RR1-BROKER-D40-REJECTED",
    "EV2-K8S-4E63-PENDING": "RR1-K8S-4E63-REJECTED",
    "EV2-NODE-F4C9-DISCONNECTED": "RR1-NODE-F4C9-REJECTED",
    "EV2-DRAIN-E2DA-REJECTED": "RR1-DRAIN-E2DA-REJECTED",
    "EV2-SNAPSHOT-71E1-REJECTED": "RR1-SNAPSHOT-71E1-REJECTED",
    "EV2-COST-2BC0-REJECTED": "RR1-COST-2BC0-REJECTED",
    "EV2-QWEN-27C2-REJECTED": "RR1-QWEN-27C2-REJECTED",
    "EV2-BOLTZ-HIDDEN-SETUP-75E3": "RR1-STORAGE-75E3-REJECTED",
    "EV2-STORAGE-75E3-UNREVIEWED": "RR1-STORAGE-75E3-REJECTED",
    "EV2-MODAL-530F-REFERENCE": "RR1-MODAL-530F-REFERENCE",
}


NEW_ENTRIES = [
    {
        "id": "EV3-INDEX-7DC-REJECTED",
        "lane": "architecture-evidence",
        "subject": "evidence-index v2 review provenance",
        "backends": ["backend-neutral"],
        "classification": "rejected",
        "measurement_kind": "review-artifact",
        "allowed_claim": "Exact 7dc39ea7 is rejected evidence-index history and cannot authorize a backend decision.",
        "excluded_claims": ["review provenance is independently bound", "evidence snapshot is complete"],
        "commit": REJECTED_INDEX_COMMIT,
        "path": "nim-fast-start/faststart-v2/catalog-switch/architecture/evidence-index.v2.json",
        "record": "RR1-INDEX-7DC-REJECTED",
    },
    {
        "id": "EV3-BROKER-420D-REJECTED",
        "lane": "resource-broker",
        "subject": "Kubernetes lease v5 private-runner authority",
        "backends": ["kubernetes"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 420de387 is negative review evidence for an unbound executing-source attestation.",
        "excluded_claims": ["live creation admission", "reviewed broker replacement"],
        "commit": "420de38752da1708f52b7e7f68486cb9debf923d",
        "path": "nim-fast-start/faststart-v2/resource-broker/KUBERNETES_REVIEW_EVIDENCE.md",
        "record": "RR1-BROKER-420D-REJECTED",
    },
    {
        "id": "EV3-NODE-6246-REJECTED",
        "lane": "node-local-runtime",
        "subject": "disconnected node-runtime CLI",
        "backends": ["node-vm"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 6246c6ed is negative evidence for fabricated receipts and a missing OCI/containerd execution path.",
        "excluded_claims": ["production node runtime", "live OCI evidence"],
        "commit": "6246c6ed2b6d13282d0c483aff258cb27786f305",
        "path": "nim-fast-start/faststart-v2/node-local-runtime/node_runtime/cli.py",
        "record": "RR1-NODE-6246-REJECTED",
    },
    {
        "id": "EV3-NODE-4302-REJECTED",
        "lane": "node-local-runtime",
        "subject": "supervisor-bypassing node-runtime CLI",
        "backends": ["node-vm"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 43026448 is negative evidence for bypassed Supervisor.run, fake adapters, missing durable cleanup, and a red canonical suite.",
        "excluded_claims": ["connected production runtime", "passing release gate"],
        "commit": "43026448ff4f9a3ac65c006d1ef7dd6c0f774fd8",
        "path": "nim-fast-start/faststart-v2/node-local-runtime/node_runtime/cli.py",
        "record": "RR1-NODE-4302-REJECTED",
    },
    {
        "id": "EV3-DRAIN-3963-REJECTED",
        "lane": "drain-reclaim",
        "subject": "drain/reclaim v4 receiver occupancy",
        "backends": ["kubernetes", "node-vm"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 39635156 is negative evidence for unjoined receiver occupancy and mutable authority state.",
        "excluded_claims": ["safe A-to-B replacement", "live H100 proof"],
        "commit": "396351565f64b20e0d59e25cd34dc5c8af73a7aa",
        "path": "nim-fast-start/faststart-v2/catalog-switch/drain-reclaim/contract.json",
        "record": "RR1-DRAIN-3963-REJECTED",
    },
    {
        "id": "EV3-DRAIN-E365-PENDING",
        "lane": "drain-reclaim",
        "subject": "drain/reclaim v5 replacement",
        "backends": ["kubernetes", "node-vm"],
        "classification": "pending",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact e365f4e7 is an offline candidate awaiting fresh exact review.",
        "excluded_claims": ["accepted drain/reclaim replacement", "live switch evidence"],
        "commit": "e365f4e7dadb97d976649eb254d9c1d2cde53427",
        "path": "nim-fast-start/faststart-v2/catalog-switch/drain-reclaim/contract.json",
        "record": "RR1-DRAIN-E365-PENDING",
    },
    {
        "id": "EV3-SNAPSHOT-3AF2-REJECTED",
        "lane": "snapshot-eligibility",
        "subject": "cross-section n20 image receipt join",
        "backends": ["kubernetes", "node-vm"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 3af2e7a9 is negative evidence for a prose-token image/cohort join.",
        "excluded_claims": ["exact snapshot image binding", "production eligibility classification"],
        "commit": "3af2e7a9a04e6740efd985870ed6ae1c37cb18a6",
        "path": "nim-fast-start/faststart-v2/catalog-switch/snapshot-eligibility/eligibility.json",
        "record": "RR1-SNAPSHOT-3AF2-REJECTED",
    },
    {
        "id": "EV3-SNAPSHOT-2A70-PENDING",
        "lane": "snapshot-eligibility",
        "subject": "structured n20 snapshot evidence join",
        "backends": ["kubernetes", "node-vm"],
        "classification": "pending",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 2a70321e is an offline structured-join candidate awaiting fresh exact review.",
        "excluded_claims": ["accepted snapshot eligibility", "per-run machine image proof"],
        "commit": "2a70321e11e4f1b46dcfb17a873b69bf35408012",
        "path": "nim-fast-start/faststart-v2/catalog-switch/snapshot-eligibility/eligibility.json",
        "record": "RR1-SNAPSHOT-2A70-PENDING",
    },
    {
        "id": "EV3-COST-6310-REJECTED",
        "lane": "capacity-cost",
        "subject": "cost completeness labeling",
        "backends": ["kubernetes", "node-vm", "cerebrium"],
        "classification": "rejected",
        "measurement_kind": "offline-projection",
        "allowed_claim": "Exact 6310caf6 is negative evidence for labeling incomplete Boltz subtotals as fully loaded.",
        "excluded_claims": ["accepted cost model", "backend cost ranking"],
        "commit": "6310caf6e1a41f4b178a60b569f316e3ed99bc7e",
        "path": "nim-fast-start/faststart-v2/catalog-switch/capacity-cost/results/frontier.json",
        "record": "RR1-COST-6310-REJECTED",
    },
    {
        "id": "EV3-COST-B52A-PENDING",
        "lane": "capacity-cost",
        "subject": "cost completeness v6 replacement",
        "backends": ["kubernetes", "node-vm", "cerebrium"],
        "classification": "pending",
        "measurement_kind": "offline-projection",
        "allowed_claim": "Exact b52ae52b is an offline cost candidate awaiting fresh exact review.",
        "excluded_claims": ["accepted cost values", "backend cost ranking"],
        "commit": "b52ae52bcd5d39fd680173ee96bda973d3f50c7c",
        "path": "nim-fast-start/faststart-v2/catalog-switch/capacity-cost/results/frontier.json",
        "record": "RR1-COST-B52A-PENDING",
    },
    {
        "id": "EV3-QWEN-548A-REJECTED",
        "lane": "cerebrium-comparator",
        "subject": "Qwen v5 bootstrap listener and egress ordering",
        "backends": ["node-vm", "cerebrium"],
        "classification": "rejected",
        "measurement_kind": "offline-test",
        "allowed_claim": "Exact 548a7bf1 is negative evidence for accepting application traffic before bootstrap egress narrows.",
        "excluded_claims": ["authorized live Qwen cohort", "measured Cerebrium cohort"],
        "commit": "548a7bf1ce5f6ed5caa0e17f04b4afa4585079f9",
        "path": "nim-fast-start/faststart-v2/catalog-switch/cerebrium-comparator/PRE_CREATION_REVIEW_V5.md",
        "record": "RR1-QWEN-548A-REJECTED",
    },
    {
        "id": "EV3-STORAGE-999F-PENDING",
        "lane": "storage-cache",
        "subject": "storage catalog-boundary v2 offline replacement",
        "backends": ["kubernetes", "node-vm"],
        "classification": "pending",
        "measurement_kind": "offline-projection",
        "allowed_claim": "Exact 999f1bf6 is an offline candidate awaiting fresh exact review and has no live storage cohort.",
        "excluded_claims": ["measured A-D package", "backend storage score"],
        "commit": "999f1bf67082da618fdc949cde82384f9255af12",
        "path": "nim-fast-start/faststart-v2/performance/storage_cache_matrix/catalog_boundary_analysis/source_manifest.json",
        "record": "RR1-STORAGE-999F-PENDING",
    },
]


def git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise SystemExit(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


def provenance(commit: str, path: str) -> dict[str, str]:
    return {
        "repository": REPOSITORY,
        "commit_sha": commit,
        "commit_url": f"{REPOSITORY}/commit/{commit}",
        "path": path,
        "blob_sha256": hashlib.sha256(git_blob(commit, path)).hexdigest(),
    }


def convert_base(entry: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in entry.items() if key != "review"}
    old_id = result["id"]
    result["id"] = old_id.replace("EV2-", "EV3-", 1)
    result["review_record_id"] = BASE_RECORDS[old_id]
    result["positive_evidence_eligible"] = False
    result["decision_score_eligible"] = False
    if old_id in {
        "EV2-METRIC-BA49",
        "EV2-CATALOG-9ABD",
        "EV2-SECURITY-9CFB",
        "EV2-BROKER-CPU-2291",
    }:
        result["classification"] = "provenance-unverified"
        result["allowed_claim"] = (
            "The exact source blob exists, but positive use is blocked until an "
            "independently authored committed acceptance record is bound."
        )
        result["excluded_claims"] = [
            "independently accepted positive evidence",
            "backend decision input",
        ]
    elif old_id in {"EV2-OF2-PREPARED-0180", "EV2-BOLTZ-PREPARED-0180"}:
        result["classification"] = "provenance-unverified"
        result["allowed_claim"] = "The exact prepared-stage source file exists; its review disposition is not independently commit-bound."
        result["excluded_claims"] = [
            "unknown-model product-boundary latency",
            "independently accepted measurement",
        ]
    elif old_id == "EV2-K8S-4E63-PENDING":
        result["classification"] = "rejected"
        result["allowed_claim"] = "Exact 4e63e8dd is complete negative evidence for seven deterministic or release-gate blocker families."
        result["excluded_claims"] = ["approved Kubernetes baseline", "measured Cerebrium cohort"]
    elif old_id == "EV2-NODE-F4C9-DISCONNECTED":
        result["classification"] = "rejected"
    elif old_id == "EV2-BOLTZ-HIDDEN-SETUP-75E3":
        result["classification"] = "unverified-observation"
        result["measurement_kind"] = "unverified-observation"
        result["allowed_claim"] = "A sealed task-status snapshot reports hidden preparation, but no numeric byte or duration claim is admissible without raw receipts and a source join."
        result["excluded_claims"] = [
            "measured preparation bytes",
            "measured preparation duration",
            "product-boundary Boltz latency",
        ]
    elif old_id == "EV2-STORAGE-75E3-UNREVIEWED":
        result["id"] = "EV3-STORAGE-75E3-REJECTED"
        result["classification"] = "rejected"
        result["allowed_claim"] = "Exact 75e3b1fa is negative review evidence for missing causal, denominator, physical-identity, byte, cleanup, and provenance joins."
        result["excluded_claims"] = ["measured A-D storage package", "canonical 200-model projection"]
    return result


def build() -> dict[str, Any]:
    base = json.loads((ARCH_DIR / "evidence-index.v2.json").read_text(encoding="utf-8"))
    entries = [convert_base(item) for item in base["entries"]]
    for item in NEW_ENTRIES:
        item = dict(item)
        commit = item.pop("commit")
        path = item.pop("path")
        record = item.pop("record")
        item["positive_evidence_eligible"] = False
        item["decision_score_eligible"] = False
        item["provenance"] = provenance(commit, path)
        item["review_record_id"] = record
        entries.append(item)

    bundle_blob = git_blob(REVIEW_BUNDLE_COMMIT, REVIEW_BUNDLE_PATH)
    bundle_schema = git_blob(REVIEW_BUNDLE_COMMIT, REVIEW_BUNDLE_SCHEMA_PATH)
    return {
        "$schema": "./evidence-index.v3.schema.json",
        "schema_version": "catalog-switch-evidence-index/v3",
        "index_version": 3,
        "as_of": "2026-08-19T17:35:00Z",
        "baseline_architecture_commit": BASELINE_COMMIT,
        "rejected_predecessor_commit": REJECTED_INDEX_COMMIT,
        "scope": base["scope"],
        "positive_evidence_policy": {
            "exact_commit_required": True,
            "independent_acceptance_required": True,
            "source_blob_hash_required": True,
            "review_record_commit_required": True,
            "review_record_blob_hash_required": True,
            "reviewed_commit_must_equal_source_commit": True,
            "embedded_review_metadata_trusted": False,
            "label_change_can_promote": False,
        },
        "review_record_bundle": {
            "repository": REPOSITORY,
            "commit_sha": REVIEW_BUNDLE_COMMIT,
            "commit_url": f"{REPOSITORY}/commit/{REVIEW_BUNDLE_COMMIT}",
            "path": REVIEW_BUNDLE_PATH,
            "blob_sha256": hashlib.sha256(bundle_blob).hexdigest(),
            "schema_path": REVIEW_BUNDLE_SCHEMA_PATH,
            "schema_blob_sha256": hashlib.sha256(bundle_schema).hexdigest(),
        },
        "entries": entries,
    }


def main() -> int:
    output = json.dumps(build(), indent=2, sort_keys=False) + "\n"
    target = ARCH_DIR / "evidence-index.v3.json"
    if "--check" in sys.argv[1:]:
        if not target.exists() or target.read_text(encoding="utf-8") != output:
            print("evidence-index.v3.json is not the deterministic generated output", file=sys.stderr)
            return 1
        print(f"PASS deterministic evidence-index.v3.json sha256={hashlib.sha256(output.encode()).hexdigest()}")
        return 0
    target.write_text(output, encoding="utf-8")
    print(f"wrote evidence-index.v3.json sha256={hashlib.sha256(output.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
