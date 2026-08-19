#!/usr/bin/env python3
"""Fail-closed validator for the provenance-bound evidence-only ADR update."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ARCH_DIR = Path(__file__).resolve().parent
FASTSTART_ROOT = ARCH_DIR.parents[1]
REPO_ROOT = FASTSTART_ROOT.parents[1]
REPOSITORY = "https://github.com/nebius/nebius-solutions-library"
BASELINE_COMMIT = "1db7703e3078ce3236c4655816312416145eb709"
REJECTED_INDEX_COMMIT = "7dc39ea7903c8aa19fe8a8269ab435268a7ae4b7"
REVIEW_BUNDLE_COMMIT = "0c47062047d19b3271350e66cd86ee0de87a57e0"
REVIEW_BUNDLE_PATH = (
    "nim-fast-start/faststart-v2/catalog-switch/architecture/review-records.v1.json"
)
REVIEW_BUNDLE_SHA256 = "30ce34f768d382c2b74873d681475a9b813f68483ec2037e6b02f8dcfe2d71f7"
REVIEW_SCHEMA_PATH = (
    "nim-fast-start/faststart-v2/catalog-switch/architecture/review-records.v1.schema.json"
)
REVIEW_SCHEMA_SHA256 = "69e67c47b269b92aed21c264aa3382a9a23964ace9eb9f9cf4c745d533732ba8"

# No exact commit currently has a separately committed, independently authored
# acceptance record. Owner-controlled Task Deck claims cannot populate this set.
CONTENT_BOUND_ACCEPTED_EXACT_COMMITS: dict[str, str] = {}

ENTRY_RECORDS = {
    "EV3-METRIC-BA49": ("ba49c9e20f194e0f419d4209608904cc9335219d", "RR1-METRIC-BA49-PROVENANCE-UNVERIFIED"),
    "EV3-CATALOG-9ABD": ("9abd49204e7dbfb9be17ebf6c3f213227a88e5ca", "RR1-CATALOG-9ABD-PROVENANCE-UNVERIFIED"),
    "EV3-SECURITY-9CFB": ("9cfbc1b1311a1f784a407889b215aaec5200fe0e", "RR1-SECURITY-9CFB-PROVENANCE-UNVERIFIED"),
    "EV3-BROKER-CPU-2291": ("229101bb5430143e78c4bc796b30715a2a0a14df", "RR1-BROKER-2291-PROVENANCE-UNVERIFIED"),
    "EV3-OF2-PREPARED-0180": ("0180915001fff47fbed0f82292fe32edc40e40ea", "RR1-PREPARED-0180-PROVENANCE-UNVERIFIED"),
    "EV3-BOLTZ-PREPARED-0180": ("0180915001fff47fbed0f82292fe32edc40e40ea", "RR1-PREPARED-0180-PROVENANCE-UNVERIFIED"),
    "EV3-DRAIN-34D-REJECTED": ("34d70fd0b4c84ddd2375a9db1ec9d9961f4aa5be", "RR1-DRAIN-34D-REJECTED"),
    "EV3-SNAPSHOT-F5F-REJECTED": ("f5f2706a432bcc7795e51ab69fb64cd2e45ee2a2", "RR1-SNAPSHOT-F5F-REJECTED"),
    "EV3-BROKER-D40-REJECTED": ("d40b6478275d5d5545786d5a3bf69ae46fe22c32", "RR1-BROKER-D40-REJECTED"),
    "EV3-K8S-4E63-PENDING": ("4e63e8dde2c2df79ee2c1a11fb850de25b6993cb", "RR1-K8S-4E63-REJECTED"),
    "EV3-NODE-F4C9-DISCONNECTED": ("f4c9c1886ddd9c0bc04bd5804c348402ee429066", "RR1-NODE-F4C9-REJECTED"),
    "EV3-DRAIN-E2DA-REJECTED": ("e2dabf7a274f9db4287553154b625f838031a009", "RR1-DRAIN-E2DA-REJECTED"),
    "EV3-SNAPSHOT-71E1-REJECTED": ("71e15616a745a747368d3b58d572432b416124cc", "RR1-SNAPSHOT-71E1-REJECTED"),
    "EV3-COST-2BC0-REJECTED": ("2bc0f76044e9e2e960c2519cce260d36aa23331f", "RR1-COST-2BC0-REJECTED"),
    "EV3-QWEN-27C2-REJECTED": ("27c28e20e89193f3865b5aadf805d0e735f4e20e", "RR1-QWEN-27C2-REJECTED"),
    "EV3-BOLTZ-HIDDEN-SETUP-75E3": ("75e3b1faabc53a0c621d6efee84bd5b277bbc8bd", "RR1-STORAGE-75E3-REJECTED"),
    "EV3-STORAGE-75E3-REJECTED": ("75e3b1faabc53a0c621d6efee84bd5b277bbc8bd", "RR1-STORAGE-75E3-REJECTED"),
    "EV3-MODAL-530F-REFERENCE": ("530fa21207d6d716e441b2494c1389a7fa3dba3b", "RR1-MODAL-530F-REFERENCE"),
    "EV3-INDEX-7DC-REJECTED": (REJECTED_INDEX_COMMIT, "RR1-INDEX-7DC-REJECTED"),
    "EV3-BROKER-420D-REJECTED": ("420de38752da1708f52b7e7f68486cb9debf923d", "RR1-BROKER-420D-REJECTED"),
    "EV3-NODE-6246-REJECTED": ("6246c6ed2b6d13282d0c483aff258cb27786f305", "RR1-NODE-6246-REJECTED"),
    "EV3-NODE-4302-REJECTED": ("43026448ff4f9a3ac65c006d1ef7dd6c0f774fd8", "RR1-NODE-4302-REJECTED"),
    "EV3-DRAIN-3963-REJECTED": ("396351565f64b20e0d59e25cd34dc5c8af73a7aa", "RR1-DRAIN-3963-REJECTED"),
    "EV3-DRAIN-E365-PENDING": ("e365f4e7dadb97d976649eb254d9c1d2cde53427", "RR1-DRAIN-E365-PENDING"),
    "EV3-SNAPSHOT-3AF2-REJECTED": ("3af2e7a9a04e6740efd985870ed6ae1c37cb18a6", "RR1-SNAPSHOT-3AF2-REJECTED"),
    "EV3-SNAPSHOT-2A70-PENDING": ("2a70321e11e4f1b46dcfb17a873b69bf35408012", "RR1-SNAPSHOT-2A70-PENDING"),
    "EV3-COST-6310-REJECTED": ("6310caf6e1a41f4b178a60b569f316e3ed99bc7e", "RR1-COST-6310-REJECTED"),
    "EV3-COST-B52A-PENDING": ("b52ae52bcd5d39fd680173ee96bda973d3f50c7c", "RR1-COST-B52A-PENDING"),
    "EV3-QWEN-548A-REJECTED": ("548a7bf1ce5f6ed5caa0e17f04b4afa4585079f9", "RR1-QWEN-548A-REJECTED"),
    "EV3-STORAGE-999F-PENDING": ("999f1bf67082da618fdc949cde82384f9255af12", "RR1-STORAGE-999F-PENDING"),
}

REJECTED_IDS = {
    entry_id
    for entry_id in ENTRY_RECORDS
    if "REJECTED" in entry_id or entry_id in {"EV3-K8S-4E63-PENDING", "EV3-NODE-F4C9-DISCONNECTED"}
}
PENDING_IDS = {
    "EV3-DRAIN-E365-PENDING",
    "EV3-SNAPSHOT-2A70-PENDING",
    "EV3-COST-B52A-PENDING",
    "EV3-STORAGE-999F-PENDING",
}
PROVENANCE_UNVERIFIED_IDS = {
    "EV3-METRIC-BA49",
    "EV3-CATALOG-9ABD",
    "EV3-SECURITY-9CFB",
    "EV3-BROKER-CPU-2291",
    "EV3-OF2-PREPARED-0180",
    "EV3-BOLTZ-PREPARED-0180",
}
EXPECTED_BACKENDS = {"kubernetes", "node-vm", "cerebrium", "modal"}
EXPECTED_SCENARIOS = {
    "same_model_hot",
    "idle_local",
    "a_to_b_local",
    "a_to_b_remote",
    "checkpoint_fallback",
    "capacity_miss",
}
EXPECTED_REQUIREMENTS = {
    "matched-k8s-node-vm-cerebrium",
    "all-10-arm-a-arm-b",
    "safe-drain-reclaim-replacement",
}
FORBIDDEN_CLAIM_FRAGMENTS = (
    "production winner",
    "winning backend",
    "backend wins",
    "best backend",
    "final adr",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema(instance: dict[str, Any], schema_name: str) -> list[str]:
    try:
        schema = load_json(ARCH_DIR / schema_name)
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
        return [
            f"{schema_name}: {'/'.join(str(part) for part in error.path)}: {error.message}"
            for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
        ]
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        return [f"{schema_name}: unavailable or invalid: {exc}"]


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_blob(commit: Any, path: Any) -> tuple[bytes | None, str | None]:
    if not isinstance(commit, str) or _git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
        return None, "exact source commit does not exist"
    if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
        return None, "source path must be contained in the repository"
    blob = _git("show", f"{commit}:{path}")
    if blob.returncode:
        return None, "source commit/path blob is unavailable"
    return blob.stdout, None


def _validate_provenance(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entry_id = entry.get("id", "<unknown>")
    provenance = entry.get("provenance", {})
    commit = provenance.get("commit_sha")
    path = provenance.get("path")
    expected_url = f"{REPOSITORY}/commit/{commit}"
    if provenance.get("commit_url") != expected_url:
        errors.append(f"{entry_id}: commit_url is not the exact source commit link")
    blob, error = _git_blob(commit, path)
    if error:
        errors.append(f"{entry_id}: {error}")
    elif hashlib.sha256(blob or b"").hexdigest() != provenance.get("blob_sha256"):
        errors.append(f"{entry_id}: source commit/path blob sha256 mismatch")
    return errors


def _load_bound_review_bundle(index: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    binding = index.get("review_record_bundle", {})
    expected = {
        "repository": REPOSITORY,
        "commit_sha": REVIEW_BUNDLE_COMMIT,
        "commit_url": f"{REPOSITORY}/commit/{REVIEW_BUNDLE_COMMIT}",
        "path": REVIEW_BUNDLE_PATH,
        "blob_sha256": REVIEW_BUNDLE_SHA256,
        "schema_path": REVIEW_SCHEMA_PATH,
        "schema_blob_sha256": REVIEW_SCHEMA_SHA256,
    }
    if binding != expected:
        errors.append("review record bundle binding changed or is incomplete")
        return None, errors
    bundle_blob, bundle_error = _git_blob(REVIEW_BUNDLE_COMMIT, REVIEW_BUNDLE_PATH)
    schema_blob, schema_error = _git_blob(REVIEW_BUNDLE_COMMIT, REVIEW_SCHEMA_PATH)
    if bundle_error or schema_error:
        errors.append("bound review record bundle or schema is unavailable")
        return None, errors
    if hashlib.sha256(bundle_blob or b"").hexdigest() != REVIEW_BUNDLE_SHA256:
        errors.append("bound review record bundle blob sha256 mismatch")
    if hashlib.sha256(schema_blob or b"").hexdigest() != REVIEW_SCHEMA_SHA256:
        errors.append("bound review record schema blob sha256 mismatch")
    try:
        bundle = json.loads(bundle_blob or b"{}")
        schema = json.loads(schema_blob or b"{}")
        jsonschema.Draft202012Validator.check_schema(schema)
        schema_errors = list(
            jsonschema.Draft202012Validator(
                schema, format_checker=jsonschema.FormatChecker()
            ).iter_errors(bundle)
        )
        errors.extend(f"bound review bundle schema: {error.message}" for error in schema_errors)
    except (json.JSONDecodeError, jsonschema.SchemaError) as exc:
        errors.append(f"bound review record bundle is invalid: {exc}")
        return None, errors
    parent = _git("rev-parse", f"{REVIEW_BUNDLE_COMMIT}^")
    if parent.returncode or parent.stdout.decode().strip() != REJECTED_INDEX_COMMIT:
        errors.append("review record bundle is not the exact direct child of 7dc39ea7")
    return bundle, errors


def _validate_bundle_semantics(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = {item.get("id"): item for item in bundle.get("source_snapshots", [])}
    records = {item.get("id"): item for item in bundle.get("records", [])}
    if len(sources) != len(bundle.get("source_snapshots", [])):
        errors.append("review source snapshot IDs must be unique")
    if len(records) != len(bundle.get("records", [])):
        errors.append("review record IDs must be unique")
    for record_id, record in records.items():
        if record.get("source_snapshot_id") not in sources:
            errors.append(f"{record_id}: review source snapshot is unresolved")
        if record.get("positive_acceptance_eligible"):
            if not (
                record.get("authority_claim") == "independent-review"
                and record.get("authority_proven") is True
                and record.get("disposition") == "accepted"
            ):
                errors.append(f"{record_id}: positive acceptance is not independently proven")
    observations = {item.get("id"): item for item in bundle.get("raw_observations", [])}
    boltz = observations.get("OBS-BOLTZ-PRE-T0-COPY-HASH", {})
    if (
        boltz.get("source_join_status") != "missing-raw-receipt-source-join"
        or boltz.get("raw_receipt_paths") != []
        or boltz.get("raw_receipt_sha256") != []
        or boltz.get("numeric_claim_admissible") is not False
    ):
        errors.append("Boltz hidden-setup observation must remain non-admissible without raw receipt/source joins")
    return errors


def validate_index(index: dict[str, Any]) -> list[str]:
    errors = _validate_schema(index, "evidence-index.v3.schema.json")
    bundle, bundle_errors = _load_bound_review_bundle(index)
    errors.extend(bundle_errors)
    if bundle is None:
        return errors
    errors.extend(_validate_bundle_semantics(bundle))
    records = {item["id"]: item for item in bundle.get("records", [])}
    entries = index.get("entries", [])
    by_id = {item.get("id"): item for item in entries if isinstance(item, dict)}
    if len(by_id) != len(entries):
        errors.append("evidence entry IDs must be unique")
    if set(by_id) != set(ENTRY_RECORDS):
        errors.append("evidence snapshot entry set is incomplete or contains unreviewed additions")

    for entry_id, item in by_id.items():
        errors.extend(_validate_provenance(item))
        expected = ENTRY_RECORDS.get(str(entry_id))
        if expected is None:
            continue
        expected_commit, expected_record_id = expected
        if item.get("provenance", {}).get("commit_sha") != expected_commit:
            errors.append(f"{entry_id}: exact evidence commit changed")
        if item.get("review_record_id") != expected_record_id:
            errors.append(f"{entry_id}: review record binding changed")
        record = records.get(expected_record_id)
        if record is None:
            errors.append(f"{entry_id}: bound review record is unresolved")
            continue
        if record.get("subject_commit") != expected_commit:
            errors.append(f"{entry_id}: review record subject commit mismatch")
        if item.get("positive_evidence_eligible"):
            accepted = CONTENT_BOUND_ACCEPTED_EXACT_COMMITS.get(entry_id)
            if accepted != expected_commit:
                errors.append(f"{entry_id}: exact commit lacks a content-bound independent acceptance record")
            if not record.get("positive_acceptance_eligible"):
                errors.append(f"{entry_id}: bound review record forbids positive acceptance")
        if item.get("decision_score_eligible"):
            errors.append(f"{entry_id}: decision scoring is forbidden")
        if entry_id in REJECTED_IDS and (
            item.get("classification") != "rejected" or record.get("disposition") != "rejected"
        ):
            errors.append(f"{entry_id}: rejected disposition changed")
        if entry_id in PENDING_IDS and (
            item.get("classification") != "pending" or record.get("disposition") != "pending"
        ):
            errors.append(f"{entry_id}: pending replacement was promoted")
        if entry_id in PROVENANCE_UNVERIFIED_IDS and (
            item.get("classification") != "provenance-unverified"
            or record.get("disposition") != "provenance-unverified"
        ):
            errors.append(f"{entry_id}: unverified review provenance was promoted")
        claim_text = " ".join(
            [str(item.get("allowed_claim", "")), *map(str, item.get("excluded_claims", []))]
        ).lower()
        if any(fragment in claim_text for fragment in FORBIDDEN_CLAIM_FRAGMENTS):
            errors.append(f"{entry_id}: forbidden backend-winner/final-ADR claim")

    positive_ids = {item.get("id") for item in entries if item.get("positive_evidence_eligible")}
    if positive_ids != set(CONTENT_BOUND_ACCEPTED_EXACT_COMMITS):
        errors.append("positive evidence IDs must equal the content-bound independent-acceptance set")
    if "task-deck://" in json.dumps(index):
        errors.append("evidence index must not contain unresolved task-deck review references")

    boltz = by_id.get("EV3-BOLTZ-HIDDEN-SETUP-75E3", {})
    if boltz.get("classification") != "unverified-observation":
        errors.append("Boltz hidden setup must remain an unverified observation")
    allowed = str(boltz.get("allowed_claim", "")).lower()
    if any(value in allowed for value in ("1826220898", "1,826,220,898", "440", "442")):
        errors.append("Boltz numeric setup values are forbidden in allowed claims without raw receipts")

    modal = by_id.get("EV3-MODAL-530F-REFERENCE", {})
    if (
        modal.get("classification") != "reference-only"
        or modal.get("measurement_kind") != "documentation"
        or modal.get("backends") != ["modal"]
        or modal.get("positive_evidence_eligible")
        or modal.get("decision_score_eligible")
    ):
        errors.append("Modal must remain documentation-only, unmeasured, and unscored")

    k8s_findings = records.get("RR1-K8S-4E63-REJECTED", {}).get("findings", [])
    if len(k8s_findings) < 7:
        errors.append("complete K8s 4e63 adverse finding set is missing")
    storage_text = " ".join(records.get("RR1-STORAGE-75E3-REJECTED", {}).get("findings", [])).lower()
    for fragment in ("all-attempt", "one-clock", "physical-byte", "cleanup", "dirty-generation", "reviewed-commit", "canonical"):
        if fragment not in storage_text:
            errors.append(f"storage 75e3 adverse finding missing: {fragment}")
    return errors


def validate_matrix(matrix: dict[str, Any], index: dict[str, Any]) -> list[str]:
    errors = _validate_schema(matrix, "decision-matrix.v1.schema.json")
    evidence_by_id = {item["id"]: item for item in index.get("entries", [])}
    backends = {item.get("id"): item for item in matrix.get("backends", [])}
    if matrix.get("evidence_index") != "catalog-switch/architecture/evidence-index.v3.json":
        errors.append("decision matrix does not reference evidence index v3")
    if set(backends) != EXPECTED_BACKENDS:
        errors.append("decision matrix must contain exact Kubernetes/node-VM/Cerebrium/Modal rows")
    for backend_id, backend in backends.items():
        if backend.get("matched_measured_cohorts") != 0:
            errors.append(f"{backend_id}: measured cohort count must remain zero")
        if backend.get("score") is not None or backend.get("rank") is not None:
            errors.append(f"{backend_id}: score/rank is forbidden before matched cohorts")
        for evidence_id in backend.get("evidence_ids", []):
            if evidence_id not in evidence_by_id:
                errors.append(f"{backend_id}: unknown evidence reference {evidence_id}")
    if matrix.get("winner") is not None or matrix.get("final_adr") is not False:
        errors.append("decision matrix must remain open with no winner and no final ADR")
    if set(item.get("id") for item in matrix.get("scenarios", [])) != EXPECTED_SCENARIOS:
        errors.append("decision matrix scenario set changed")
    if any(item.get("winner") is not None for item in matrix.get("scenarios", [])):
        errors.append("scenario winner is forbidden before matched evidence")

    requirements = {item.get("id"): item for item in matrix.get("qualification_requirements", [])}
    if set(requirements) != EXPECTED_REQUIREMENTS:
        errors.append("qualification requirement set changed")
    for requirement_id, requirement in requirements.items():
        if requirement.get("status") != "missing" or requirement.get("accepted") != 0 or requirement.get("accepted_commit") is not None:
            errors.append(f"{requirement_id}: missing evidence was falsely accepted")
    if requirements.get("all-10-arm-a-arm-b", {}).get("required") != 20:
        errors.append("all-10 Arm A/Arm B requirement must remain 20 model-arm cells")
    if matrix.get("decision_inputs") != []:
        errors.append("decision inputs must remain empty until content-bound independent acceptance exists")
    if set(matrix.get("negative_review_evidence", [])) != REJECTED_IDS:
        errors.append("negative replacement review history is incomplete")
    if set(matrix.get("pending_review_evidence", [])) != PENDING_IDS:
        errors.append("pending replacement review history is incomplete")

    modal = backends.get("modal", {})
    if modal.get("role") != "documentation-reference-only" or modal.get("empirical_candidate"):
        errors.append("Modal must remain a non-empirical documentation reference")
    cerebrium = backends.get("cerebrium", {})
    if cerebrium.get("role") != "sole-intended-external-comparator":
        errors.append("Cerebrium must remain the sole intended external comparator")
    return errors


def validate_budgets(budgets: dict[str, Any]) -> list[str]:
    errors = _validate_schema(budgets, "budget-placeholders.v1.schema.json")
    if budgets.get("selection_permitted") is not False:
        errors.append("budget placeholders cannot select a backend")
    for item in budgets.get("latency", []):
        for field in ("p50_max", "p95_max", "p99_max"):
            if item.get(field) is not None:
                errors.append(f"{item.get('id')}: latency budget must remain null")
    for item in budgets.get("cost", []):
        for field in ("per_valid_response_max", "failed_attempt_max", "warm_idle_gpu_hour_max", "transfer_gib_max", "campaign_cap"):
            if item.get(field) is not None:
                errors.append(f"{item.get('id')}: cost budget must remain null")
    if {item.get("backend") for item in budgets.get("cost", [])} != {"kubernetes", "node-vm", "cerebrium"}:
        errors.append("cost placeholders must cover exact empirical backends and exclude Modal")
    return errors


def validate_architecture_link(architecture: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    update = architecture.get("evidence_index_update", {})
    expected = {
        "scope": "evidence-index-only",
        "baseline_commit": BASELINE_COMMIT,
        "rejected_predecessor_commit": REJECTED_INDEX_COMMIT,
        "review_record_bundle_commit": REVIEW_BUNDLE_COMMIT,
        "review_records": "catalog-switch/architecture/review-records.v1.json",
        "evidence_index": "catalog-switch/architecture/evidence-index.v3.json",
        "decision_matrix": "catalog-switch/architecture/decision-matrix.v1.json",
        "budget_placeholders": "catalog-switch/architecture/budget-placeholders.v1.json",
        "open_unknowns": "catalog-switch/architecture/OPEN_UNKNOWNS.md",
        "backend_selection_allowed": False,
        "final_adr_claim_allowed": False,
    }
    if update != expected:
        errors.append("architecture evidence_index_update link set changed or is incomplete")
    gates = {item.get("id"): item for item in architecture.get("rollout_gates", [])}
    if gates.get("G-INDEPENDENT-REVIEW", {}).get("status") != "pending":
        errors.append("the reopened evidence-index update must stop at pending independent review")
    if any(item.get("production_disposition") == "promoted" for item in architecture.get("backends", [])):
        errors.append("no backend may be promoted")
    return errors


def validate_all() -> list[str]:
    index = load_json(ARCH_DIR / "evidence-index.v3.json")
    matrix = load_json(ARCH_DIR / "decision-matrix.v1.json")
    budgets = load_json(ARCH_DIR / "budget-placeholders.v1.json")
    architecture = load_json(ARCH_DIR / "architecture.json")
    errors = validate_index(index)
    errors.extend(validate_matrix(matrix, index))
    errors.extend(validate_budgets(budgets))
    errors.extend(validate_architecture_link(architecture))
    for ancestor, label in ((BASELINE_COMMIT, "1db7703e"), (REJECTED_INDEX_COMMIT, "7dc39ea7"), (REVIEW_BUNDLE_COMMIT, "review bundle commit")):
        if _git("merge-base", "--is-ancestor", ancestor, "HEAD").returncode:
            errors.append(f"preserved {label} is not an ancestor of HEAD")
    return errors


def main() -> int:
    errors = validate_all()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    index = load_json(ARCH_DIR / "evidence-index.v3.json")
    print(
        "PASS: evidence-index/v3 "
        f"entries={len(index['entries'])} "
        "positive_exact=0 review_bundle=0c470620 winner=none cohorts=0 "
        "budgets=placeholders-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
