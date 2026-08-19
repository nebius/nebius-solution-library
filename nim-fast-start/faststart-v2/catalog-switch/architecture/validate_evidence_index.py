#!/usr/bin/env python3
"""Fail-closed validator for the evidence-only ADR update."""

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

INDEPENDENTLY_ACCEPTED_EXACT_COMMITS = {
    "EV2-METRIC-BA49": "ba49c9e20f194e0f419d4209608904cc9335219d",
    "EV2-CATALOG-9ABD": "9abd49204e7dbfb9be17ebf6c3f213227a88e5ca",
    "EV2-SECURITY-9CFB": "9cfbc1b1311a1f784a407889b215aaec5200fe0e",
    "EV2-BROKER-CPU-2291": "229101bb5430143e78c4bc796b30715a2a0a14df",
}

REQUIRED_REVIEWED_REPLACEMENTS = {
    "EV2-DRAIN-34D-REJECTED": (
        "34d70fd0b4c84ddd2375a9db1ec9d9961f4aa5be",
        "rejected",
        ("durability", "gpu scrub", "physical actions", "rollback"),
    ),
    "EV2-SNAPSHOT-F5F-REJECTED": (
        "f5f2706a432bcc7795e51ab69fb64cd2e45ee2a2",
        "rejected",
        ("new-node", "topology", "pins", "per-model"),
    ),
    "EV2-BROKER-D40-REJECTED": (
        "d40b6478275d5d5545786d5a3bf69ae46fe22c32",
        "rejected",
        ("self-asserted", "across leases", "still-live", "public-interface", "authentication failure"),
    ),
    "EV2-K8S-4E63-PENDING": (
        "4e63e8dde2c2df79ee2c1a11fb850de25b6993cb",
        "changes-requested",
        ("timing sensitivity", "pending", "unmeasured"),
    ),
    "EV2-NODE-F4C9-DISCONNECTED": (
        "f4c9c1886ddd9c0bc04bd5804c348402ee429066",
        "changes-requested",
        ("disconnected",),
    ),
    "EV2-DRAIN-E2DA-REJECTED": (
        "e2dabf7a274f9db4287553154b625f838031a009",
        "rejected",
        ("without an items list", "another trusted node key", "exact runtime authority"),
    ),
    "EV2-SNAPSHOT-71E1-REJECTED": (
        "71e15616a745a747368d3b58d572432b416124cc",
        "rejected",
        ("all-zero", "no image-digest column"),
    ),
    "EV2-COST-2BC0-REJECTED": (
        "2bc0f76044e9e2e960c2519cce260d36aa23331f",
        "rejected",
        ("rounding", "relocation"),
    ),
    "EV2-QWEN-27C2-REJECTED": (
        "27c28e20e89193f3865b5aadf805d0e735f4e20e",
        "rejected",
        ("forge", "subnet", "response-lost", "ordinal"),
    ),
}

REQUIRED_UNREVIEWED = {
    "EV2-BOLTZ-HIDDEN-SETUP-75E3": "75e3b1faabc53a0c621d6efee84bd5b277bbc8bd",
    "EV2-STORAGE-75E3-UNREVIEWED": "75e3b1faabc53a0c621d6efee84bd5b277bbc8bd",
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


def _validate_provenance(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entry_id = entry.get("id", "<unknown>")
    provenance = entry.get("provenance", {})
    commit = provenance.get("commit_sha")
    path = provenance.get("path")
    digest = provenance.get("blob_sha256")
    expected_url = f"{REPOSITORY}/commit/{commit}"
    if provenance.get("commit_url") != expected_url:
        errors.append(f"{entry_id}: commit_url is not the exact source commit link")
    if not isinstance(commit, str) or _git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
        errors.append(f"{entry_id}: exact source commit does not exist")
        return errors
    if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
        errors.append(f"{entry_id}: source path must be contained in the repository")
        return errors
    blob = _git("show", f"{commit}:{path}")
    if blob.returncode:
        errors.append(f"{entry_id}: source commit/path blob is unavailable")
        return errors
    actual = hashlib.sha256(blob.stdout).hexdigest()
    if actual != digest:
        errors.append(f"{entry_id}: source commit/path blob sha256 mismatch")
    return errors


def validate_index(index: dict[str, Any]) -> list[str]:
    errors = _validate_schema(index, "evidence-index.v2.schema.json")
    entries = index.get("entries", [])
    by_id = {item.get("id"): item for item in entries if isinstance(item, dict)}
    if len(by_id) != len(entries):
        errors.append("evidence entry IDs must be unique")

    for item in entries:
        if not isinstance(item, dict):
            continue
        errors.extend(_validate_provenance(item))
        entry_id = item.get("id")
        claim_text = " ".join(
            [str(item.get("allowed_claim", "")), *map(str, item.get("excluded_claims", []))]
        ).lower()
        if any(fragment in claim_text for fragment in FORBIDDEN_CLAIM_FRAGMENTS):
            errors.append(f"{entry_id}: forbidden backend-winner/final-ADR claim")

        positive = item.get("positive_evidence_eligible") is True
        review = item.get("review", {})
        source_commit = item.get("provenance", {}).get("commit_sha")
        if positive:
            accepted_commit = INDEPENDENTLY_ACCEPTED_EXACT_COMMITS.get(str(entry_id))
            if accepted_commit != source_commit:
                errors.append(f"{entry_id}: exact commit is not independently accepted positive evidence")
            if review.get("verdict") != "accepted" or review.get("authority") != "independent-review":
                errors.append(f"{entry_id}: positive evidence lacks independent acceptance")
            if review.get("reviewed_commit_sha") != source_commit:
                errors.append(f"{entry_id}: reviewed commit must equal the exact source commit")
        elif entry_id in INDEPENDENTLY_ACCEPTED_EXACT_COMMITS:
            errors.append(f"{entry_id}: accepted exact contract was unexpectedly demoted")

    positive_ids = {item.get("id") for item in entries if item.get("positive_evidence_eligible")}
    if positive_ids != set(INDEPENDENTLY_ACCEPTED_EXACT_COMMITS):
        errors.append("positive evidence IDs must equal the independently accepted exact-commit allowlist")

    for entry_id, (commit, verdict, required_fragments) in REQUIRED_REVIEWED_REPLACEMENTS.items():
        item = by_id.get(entry_id)
        if item is None:
            errors.append(f"{entry_id}: required replacement review evidence is missing")
            continue
        if item.get("provenance", {}).get("commit_sha") != commit:
            errors.append(f"{entry_id}: replacement commit changed")
        if item.get("review", {}).get("reviewed_commit_sha") != commit:
            errors.append(f"{entry_id}: review is not bound to the exact replacement commit")
        if item.get("review", {}).get("verdict") != verdict:
            errors.append(f"{entry_id}: review verdict changed")
        if item.get("positive_evidence_eligible") or item.get("decision_score_eligible"):
            errors.append(f"{entry_id}: rejected/pending replacement became positive or scored")
        review_text = " ".join(map(str, item.get("review", {}).get("reasons", []))).lower()
        for fragment in required_fragments:
            if fragment not in review_text:
                errors.append(f"{entry_id}: required review reason missing: {fragment}")

    for entry_id, commit in REQUIRED_UNREVIEWED.items():
        item = by_id.get(entry_id)
        if item is None:
            errors.append(f"{entry_id}: required unreviewed evidence entry is missing")
            continue
        if item.get("provenance", {}).get("commit_sha") != commit:
            errors.append(f"{entry_id}: unreviewed source commit changed")
        if item.get("review", {}).get("verdict") != "pending":
            errors.append(f"{entry_id}: unreviewed evidence cannot be promoted without a new review")
        if item.get("positive_evidence_eligible") or item.get("decision_score_eligible"):
            errors.append(f"{entry_id}: unreviewed evidence became positive or scored")

    modal = by_id.get("EV2-MODAL-530F-REFERENCE", {})
    if (
        modal.get("classification") != "reference-only"
        or modal.get("measurement_kind") != "documentation"
        or modal.get("backends") != ["modal"]
        or modal.get("positive_evidence_eligible")
        or modal.get("decision_score_eligible")
    ):
        errors.append("Modal must remain documentation-only, unmeasured, and unscored")
    return errors


def validate_matrix(matrix: dict[str, Any], index: dict[str, Any]) -> list[str]:
    errors = _validate_schema(matrix, "decision-matrix.v1.schema.json")
    evidence_by_id = {item["id"]: item for item in index.get("entries", [])}
    backends = {item.get("id"): item for item in matrix.get("backends", [])}
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
        if (
            requirement.get("status") != "missing"
            or requirement.get("accepted") != 0
            or requirement.get("accepted_commit") is not None
        ):
            errors.append(f"{requirement_id}: missing evidence was falsely accepted")
    if requirements.get("all-10-arm-a-arm-b", {}).get("required") != 20:
        errors.append("all-10 Arm A/Arm B requirement must remain 20 model-arm cells")

    decision_inputs = set(matrix.get("decision_inputs", []))
    if decision_inputs != set(INDEPENDENTLY_ACCEPTED_EXACT_COMMITS):
        errors.append("decision inputs must be only independently accepted exact contracts")
    for evidence_id in decision_inputs:
        if not evidence_by_id.get(evidence_id, {}).get("positive_evidence_eligible"):
            errors.append(f"decision input is not positive evidence: {evidence_id}")
    nonpositive_ids = set(REQUIRED_REVIEWED_REPLACEMENTS) | set(REQUIRED_UNREVIEWED)
    if decision_inputs & nonpositive_ids:
        errors.append("rejected, pending, or unreviewed evidence entered decision inputs")
    if not set(REQUIRED_REVIEWED_REPLACEMENTS).issubset(
        set(matrix.get("negative_review_evidence", []))
    ):
        errors.append("negative replacement review history is incomplete")

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
        for field in (
            "per_valid_response_max",
            "failed_attempt_max",
            "warm_idle_gpu_hour_max",
            "transfer_gib_max",
            "campaign_cap",
        ):
            if item.get(field) is not None:
                errors.append(f"{item.get('id')}: cost budget must remain null")
    if {item.get("backend") for item in budgets.get("cost", [])} != {
        "kubernetes",
        "node-vm",
        "cerebrium",
    }:
        errors.append("cost placeholders must cover exact empirical backends and exclude Modal")
    return errors


def validate_architecture_link(architecture: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    update = architecture.get("evidence_index_update", {})
    expected = {
        "scope": "evidence-index-only",
        "baseline_commit": BASELINE_COMMIT,
        "evidence_index": "catalog-switch/architecture/evidence-index.v2.json",
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
    index = load_json(ARCH_DIR / "evidence-index.v2.json")
    matrix = load_json(ARCH_DIR / "decision-matrix.v1.json")
    budgets = load_json(ARCH_DIR / "budget-placeholders.v1.json")
    architecture = load_json(ARCH_DIR / "architecture.json")
    errors = validate_index(index)
    errors.extend(validate_matrix(matrix, index))
    errors.extend(validate_budgets(budgets))
    errors.extend(validate_architecture_link(architecture))
    ancestry = _git("merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD")
    if ancestry.returncode:
        errors.append("preserved baseline commit 1db7703e is not an ancestor of HEAD")
    return errors


def main() -> int:
    errors = validate_all()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    index = load_json(ARCH_DIR / "evidence-index.v2.json")
    print(
        "PASS: evidence-index/v2 "
        f"entries={len(index['entries'])} "
        f"positive_exact={len(INDEPENDENTLY_ACCEPTED_EXACT_COMMITS)} "
        "winner=none cohorts=0 budgets=placeholders-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
