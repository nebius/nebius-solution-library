#!/usr/bin/env python3
"""Read-only admission preflight for the storage baseline handoff.

This module deliberately has no resource-creation operation.  It proves that
the shared metric, broker candidate, bootstrap candidate, task branch, and an
independent approval receipt all refer to the same immutable inputs.  A caller
may use an ``ADMITTED`` receipt as one input to a separate reviewed execution
owner; a ``BLOCKED`` receipt is planning evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


HANDOFF_SCHEMA = "archvteams.nebius.ai/network-storage-baseline-handoff/v1"
APPROVAL_SCHEMA = "archvteams.nebius.ai/network-storage-baseline-approval/v1"
PREFLIGHT_SCHEMA = "archvteams.nebius.ai/network-storage-baseline-preflight/v1"
T0_BOUNDARY = "external-client-request-accepted/v1"
TERMINAL_BOUNDARY = "first-complete-semantically-valid-response/v1"
HANDOFF_BRANCH = "agent/catalog-switch-storage-cache-network-baseline-handoff"
TASK_ID = "catalog-switch-storage-cache-matrix"
EVIDENCE_CLASSIFICATION = "execution-plan-only-no-performance-evidence"

SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)

HANDOFF_KEYS = {
    "schema",
    "handoff_id",
    "task_id",
    "status",
    "evidence_classification",
    "created_at_utc",
    "scope",
    "external_t0_contract",
    "broker_candidate",
    "bootstrap_candidate",
    "approval_gate",
    "resource_plan",
    "measurement_plan",
    "required_outputs",
}
SCOPE_KEYS = {
    "included_tiers",
    "local_nvme",
    "full_matrix_completion_claim",
    "boltz_external_tmp_conclusion_claim",
}
TIER_KEYS = {
    "tier_id",
    "matrix_tier",
    "status",
    "label",
    "measured_operations",
    "claims_forbidden",
}
LOCAL_NVME_KEYS = {
    "matrix_tier",
    "status",
    "reason",
    "included_in_baseline",
    "substituted_by",
    "result_claim_permitted",
}
EXTERNAL_T0_KEYS = {
    "reviewed_commit",
    "integrated_commit",
    "t0_boundary",
    "terminal_boundary",
    "request_specific_work_before_t0",
    "files",
}
PINNED_FILE_KEYS = {"path", "sha256"}
CANDIDATE_KEYS = {
    "kind",
    "worktree",
    "branch",
    "remote_branch",
    "frozen_commit",
    "required_files",
    "capability_contract",
}
CAPABILITY_KEYS = {"status", "path", "sha256", "requirements"}
APPROVAL_GATE_KEYS = {
    "status",
    "receipt_path",
    "independent_reviewer_required",
    "required_review_scope",
    "resource_creation_permitted",
}
RESOURCE_PLAN_KEYS = {
    "allowed_projects",
    "selected_project_id",
    "selected_region",
    "resource_prefix",
    "fresh_resources_only",
    "reuse_forbidden",
    "expected_duration_hours",
    "ttl_hours",
    "hard_cost_cap_usd",
    "cleanup_owner",
    "planned_resources",
    "created_resource_ids",
}
MEASUREMENT_PLAN_KEYS = {
    "artifact_and_payload_identity",
    "publication_boundary",
    "request_boundary",
    "minimum_attempts_per_cell",
    "cells",
    "failures_retained",
    "phase_percentile_summation",
}
CELL_KEYS = {"cell_id", "tier_id", "cohort", "starting_state", "required_phases"}

APPROVAL_KEYS = {
    "schema",
    "decision",
    "review_id",
    "reviewer_id",
    "reviewer_role",
    "reviewed_at_utc",
    "handoff_commit",
    "handoff_sha256",
    "broker_commit",
    "bootstrap_commit",
    "review_scope",
    "notes",
}


class HandoffError(ValueError):
    """The handoff or approval document violates the frozen contract."""


def _expect_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise HandoffError(
            f"{label} keys differ; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HandoffError(f"{label} is not a lowercase SHA-256")
    return value


def _commit(value: Any, label: str) -> str:
    if not isinstance(value, str) or COMMIT_RE.fullmatch(value) is None:
        raise HandoffError(f"{label} is not a full lowercase Git commit")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{label} must be a non-empty string")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _document_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise HandoffError(f"{label} must be a regular non-symlink file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"{label} must contain one JSON object")
    return value


def _validate_pinned_files(files: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(files, list) or not files:
        raise HandoffError(f"{label} must be a non-empty list")
    shaped: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(files):
        item = _expect_keys(raw, PINNED_FILE_KEYS, f"{label}[{index}]")
        path = _nonempty(item["path"], f"{label}[{index}].path")
        if path.startswith("/") or ".." in Path(path).parts:
            raise HandoffError(f"{label}[{index}].path is not safe and relative")
        if path in seen:
            raise HandoffError(f"{label} repeats {path}")
        seen.add(path)
        shaped.append({"path": path, "sha256": _sha256(item["sha256"], f"{path} hash")})
    return shaped


def _validate_candidate(value: Any, label: str) -> dict[str, Any]:
    item = _expect_keys(value, CANDIDATE_KEYS, label)
    _nonempty(item["kind"], f"{label}.kind")
    worktree = Path(_nonempty(item["worktree"], f"{label}.worktree"))
    if not worktree.is_absolute():
        raise HandoffError(f"{label}.worktree must be absolute")
    branch = _nonempty(item["branch"], f"{label}.branch")
    remote_branch = _nonempty(item["remote_branch"], f"{label}.remote_branch")
    if remote_branch != f"origin/{branch}":
        raise HandoffError(f"{label}.remote_branch must be origin/<branch>")
    _commit(item["frozen_commit"], f"{label}.frozen_commit")
    _validate_pinned_files(item["required_files"], f"{label}.required_files")
    capability = _expect_keys(
        item["capability_contract"], CAPABILITY_KEYS, f"{label}.capability_contract"
    )
    capability_path = _nonempty(
        capability["path"], f"{label}.capability_contract.path"
    )
    if capability_path.startswith("/") or ".." in Path(capability_path).parts:
        raise HandoffError(f"{label}.capability_contract.path is not safe and relative")
    if capability["status"] == "missing-awaiting-clean-commit":
        if capability["sha256"] is not None:
            raise HandoffError(f"{label} missing capability cannot have a hash")
    elif capability["status"] == "pinned-in-frozen-commit":
        _sha256(capability["sha256"], f"{label}.capability_contract.sha256")
    else:
        raise HandoffError(f"{label} capability status is invalid")
    requirements = capability["requirements"]
    if (
        not isinstance(requirements, list)
        or len(requirements) < 3
        or any(not isinstance(requirement, str) or not requirement for requirement in requirements)
        or len(set(requirements)) != len(requirements)
    ):
        raise HandoffError(f"{label} capability requirements are incomplete")
    return item


def validate_handoff(value: Any) -> dict[str, Any]:
    handoff = _expect_keys(value, HANDOFF_KEYS, "handoff")
    if handoff["schema"] != HANDOFF_SCHEMA:
        raise HandoffError("handoff schema differs")
    if handoff["task_id"] != TASK_ID:
        raise HandoffError("handoff task_id differs")
    _nonempty(handoff["handoff_id"], "handoff.handoff_id")
    if handoff["status"] != "candidate-not-executed-awaiting-independent-approval":
        raise HandoffError("handoff status must remain non-executed and approval-pending")
    if handoff["evidence_classification"] != EVIDENCE_CLASSIFICATION:
        raise HandoffError("handoff evidence classification is not planning-only")
    if not isinstance(handoff["created_at_utc"], str) or UTC_RE.fullmatch(
        handoff["created_at_utc"]
    ) is None:
        raise HandoffError("handoff.created_at_utc is not canonical UTC")

    scope = _expect_keys(handoff["scope"], SCOPE_KEYS, "handoff.scope")
    tiers = scope["included_tiers"]
    if not isinstance(tiers, list) or len(tiers) != 2:
        raise HandoffError("handoff must contain exactly two included baseline tiers")
    tier_ids: list[str] = []
    for index, raw in enumerate(tiers):
        tier = _expect_keys(raw, TIER_KEYS, f"handoff.scope.included_tiers[{index}]")
        tier_id = _nonempty(tier["tier_id"], f"included tier {index} id")
        tier_ids.append(tier_id)
        if tier["status"] != "planned-unmeasured-requires-approved-bootstrap":
            raise HandoffError(f"{tier_id} is not labeled planned and unmeasured")
        if not isinstance(tier["measured_operations"], list) or not tier[
            "measured_operations"
        ]:
            raise HandoffError(f"{tier_id} has no measured-operation plan")
        if not isinstance(tier["claims_forbidden"], list) or not tier["claims_forbidden"]:
            raise HandoffError(f"{tier_id} has no forbidden-claim boundary")
    if set(tier_ids) != {"network_ssd_pvc", "object_store_remote_fetch"}:
        raise HandoffError("included tiers must be Network SSD/PVC and Object Storage")
    tier_by_id = {tier["tier_id"]: tier for tier in tiers}
    if tier_by_id["network_ssd_pvc"]["matrix_tier"] != "attached_block_pvc":
        raise HandoffError("Network SSD/PVC may map only to attached_block_pvc")
    if tier_by_id["object_store_remote_fetch"]["matrix_tier"] != "remote_artifact":
        raise HandoffError("Object Storage fetch may map only to remote_artifact")

    local_nvme = _expect_keys(scope["local_nvme"], LOCAL_NVME_KEYS, "scope.local_nvme")
    if local_nvme != {
        "matrix_tier": "local_nvme",
        "status": "unavailable-unverified-entitlement",
        "reason": (
            "No host-local NVMe entitlement and device layout is verified in any "
            "authorized project/platform pair."
        ),
        "included_in_baseline": False,
        "substituted_by": None,
        "result_claim_permitted": False,
    }:
        raise HandoffError("local NVMe must be explicit, unavailable, and unsubstituted")
    if scope["full_matrix_completion_claim"] is not False:
        raise HandoffError("the baseline cannot claim full-matrix completion")
    if scope["boltz_external_tmp_conclusion_claim"] is not False:
        raise HandoffError("the baseline cannot claim a Boltz external-/tmp conclusion")

    metric = _expect_keys(
        handoff["external_t0_contract"], EXTERNAL_T0_KEYS, "external_t0_contract"
    )
    _commit(metric["reviewed_commit"], "external_t0_contract.reviewed_commit")
    _commit(metric["integrated_commit"], "external_t0_contract.integrated_commit")
    if metric["t0_boundary"] != T0_BOUNDARY:
        raise HandoffError("external T0 boundary drifted")
    if metric["terminal_boundary"] != TERMINAL_BOUNDARY:
        raise HandoffError("product terminal boundary drifted")
    if metric["request_specific_work_before_t0"] != "forbidden":
        raise HandoffError("request-specific pre-T0 work must be forbidden")
    _validate_pinned_files(metric["files"], "external_t0_contract.files")

    _validate_candidate(handoff["broker_candidate"], "broker_candidate")
    _validate_candidate(handoff["bootstrap_candidate"], "bootstrap_candidate")

    approval = _expect_keys(handoff["approval_gate"], APPROVAL_GATE_KEYS, "approval_gate")
    if approval != {
        "status": "pending",
        "receipt_path": None,
        "independent_reviewer_required": True,
        "required_review_scope": [
            "artifact_identity_and_external_t0",
            "cost_ttl_and_exact_id_cleanup",
            "dirty_generation_and_failure_retention",
            "fresh_resource_isolation",
            "network_ssd_and_object_store_labels",
        ],
        "resource_creation_permitted": False,
    }:
        raise HandoffError("approval gate must remain pending and fail closed in source")

    resources = _expect_keys(handoff["resource_plan"], RESOURCE_PLAN_KEYS, "resource_plan")
    allowed = resources["allowed_projects"]
    expected_allowed = {
        "project-e00z6b02t8ddk96c49": "eu-north1",
        "project-i00xz31gpr00xp9jhp982v": "me-west1",
        "project-u00tds8vpr00jaxa76s22d": "us-central1",
    }
    if allowed != expected_allowed:
        raise HandoffError("resource plan project/region allowlist differs")
    selected = resources["selected_project_id"]
    if selected not in allowed or resources["selected_region"] != allowed[selected]:
        raise HandoffError("selected project/region is outside the exact allowlist")
    for field in ("fresh_resources_only", "reuse_forbidden"):
        if resources[field] is not True:
            raise HandoffError(f"resource_plan.{field} must be true")
    if resources["created_resource_ids"] != []:
        raise HandoffError("a handoff candidate cannot contain created resource IDs")
    if not isinstance(resources["planned_resources"], list) or not resources[
        "planned_resources"
    ]:
        raise HandoffError("resource plan must enumerate the fresh intended footprint")
    for field in ("expected_duration_hours", "ttl_hours", "hard_cost_cap_usd"):
        if not isinstance(resources[field], (int, float)) or isinstance(resources[field], bool):
            raise HandoffError(f"resource_plan.{field} must be numeric")
        if resources[field] <= 0:
            raise HandoffError(f"resource_plan.{field} must be positive")
    if resources["ttl_hours"] < resources["expected_duration_hours"]:
        raise HandoffError("resource TTL is shorter than expected duration")

    measurement = _expect_keys(
        handoff["measurement_plan"], MEASUREMENT_PLAN_KEYS, "measurement_plan"
    )
    if measurement["artifact_and_payload_identity"] != "exactly-matched-and-digest-pinned":
        raise HandoffError("artifact/payload identity is not frozen as a matching requirement")
    if measurement["publication_boundary"] != (
        "one-time immutable catalog publication may precede T0 and is costed separately"
    ):
        raise HandoffError("catalog publication boundary drifted")
    if measurement["request_boundary"] != (
        "all request-triggered create/attach/mount/fetch/copy/hash/first-read/load "
        "work starts at or after T0"
    ):
        raise HandoffError("request-work boundary drifted")
    if measurement["minimum_attempts_per_cell"] != 20:
        raise HandoffError("the p95-capable cell minimum must remain 20")
    if measurement["failures_retained"] is not True:
        raise HandoffError("all offered failures must remain in the denominator")
    if measurement["phase_percentile_summation"] != "forbidden":
        raise HandoffError("independently aggregated phase percentiles are forbidden")
    cells = measurement["cells"]
    if not isinstance(cells, list) or len(cells) < 4:
        raise HandoffError("measurement plan has insufficient baseline cells")
    seen_cells: set[str] = set()
    for index, raw in enumerate(cells):
        cell = _expect_keys(raw, CELL_KEYS, f"measurement_plan.cells[{index}]")
        cell_id = _nonempty(cell["cell_id"], f"measurement cell {index} id")
        if cell_id in seen_cells:
            raise HandoffError(f"duplicate measurement cell {cell_id}")
        seen_cells.add(cell_id)
        if cell["tier_id"] not in set(tier_ids):
            raise HandoffError(f"measurement cell {cell_id} names an excluded tier")
        if not isinstance(cell["required_phases"], list) or not cell["required_phases"]:
            raise HandoffError(f"measurement cell {cell_id} has no causal phases")

    outputs = handoff["required_outputs"]
    if not isinstance(outputs, list) or len(outputs) < 5 or len(set(outputs)) != len(outputs):
        raise HandoffError("required outputs must be a unique, complete list")
    return handoff


def load_handoff(path: Path) -> dict[str, Any]:
    return validate_handoff(_read_json(path, "handoff"))


def _git(worktree: Path, *args: str) -> tuple[bool, str]:
    try:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        completed = subprocess.run(
            ["git", "-C", str(worktree), *args],
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = completed.stdout.strip()
    detail = output if output else completed.stderr.strip()
    return completed.returncode == 0, detail


def _git_file_sha256(worktree: Path, commit: str, path: str) -> tuple[bool, str]:
    try:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        completed = subprocess.run(
            ["git", "-C", str(worktree), "show", f"{commit}:{path}"],
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if completed.returncode != 0:
        return False, completed.stderr.decode(errors="replace").strip()
    return True, hashlib.sha256(completed.stdout).hexdigest()


def _gate(gates: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    gates.append({"name": name, "passed": bool(passed), "detail": detail})


def _candidate_gates(
    gates: list[dict[str, Any]], label: str, candidate: dict[str, Any], worktree: Path
) -> None:
    exists = worktree.is_dir()
    _gate(gates, f"{label}.worktree_exists", exists, str(worktree))
    if not exists:
        return
    ok, head = _git(worktree, "rev-parse", "HEAD^{commit}")
    frozen = candidate["frozen_commit"]
    _gate(gates, f"{label}.head_is_frozen_commit", ok and head == frozen, head or "unreadable")
    ok, branch = _git(worktree, "branch", "--show-current")
    _gate(
        gates,
        f"{label}.branch_is_expected",
        ok and branch == candidate["branch"],
        branch or "unreadable",
    )
    ok, remote_tracking = _git(
        worktree, "rev-parse", f"{candidate['remote_branch']}^{{commit}}"
    )
    _gate(
        gates,
        f"{label}.local_remote_tracking_is_frozen_commit",
        ok and remote_tracking == frozen,
        remote_tracking or "unreadable",
    )
    ok, remote_line = _git(
        worktree,
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{candidate['branch']}",
    )
    remote_commit = remote_line.split()[0] if ok and remote_line.split() else ""
    _gate(
        gates,
        f"{label}.remote_branch_is_frozen_commit",
        ok and remote_commit == frozen,
        remote_commit or remote_line or "remote branch unreadable",
    )
    ok, dirty = _git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    _gate(
        gates,
        f"{label}.worktree_clean",
        ok and not dirty,
        "clean" if ok and not dirty else (dirty or "status failed"),
    )
    ok, divergence = _git(worktree, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    _gate(
        gates,
        f"{label}.remote_divergence_zero",
        ok and divergence.split() == ["0", "0"],
        divergence or "no upstream",
    )
    for item in candidate["required_files"]:
        ok, digest = _git_file_sha256(worktree, frozen, item["path"])
        _gate(
            gates,
            f"{label}.file.{item['path']}",
            ok and digest == item["sha256"],
            digest or "unreadable",
        )
    capability = candidate["capability_contract"]
    if capability["status"] != "pinned-in-frozen-commit":
        _gate(
            gates,
            f"{label}.storage_baseline_capability_pinned",
            False,
            f"awaiting clean committed {capability['path']}",
        )
    else:
        ok, digest = _git_file_sha256(worktree, frozen, capability["path"])
        _gate(
            gates,
            f"{label}.storage_baseline_capability_pinned",
            ok and digest == capability["sha256"],
            digest or "unreadable",
        )


def _validate_approval(
    value: dict[str, Any],
    handoff: dict[str, Any],
    handoff_sha256: str,
    handoff_head: str,
) -> None:
    approval = _expect_keys(value, APPROVAL_KEYS, "approval receipt")
    if approval["schema"] != APPROVAL_SCHEMA:
        raise HandoffError("approval receipt schema differs")
    if approval["decision"] != "approved":
        raise HandoffError("approval receipt decision is not approved")
    _nonempty(approval["review_id"], "approval receipt review_id")
    reviewer_id = _nonempty(approval["reviewer_id"], "approval receipt reviewer_id")
    reviewer_role = _nonempty(approval["reviewer_role"], "approval receipt reviewer_role")
    if reviewer_id in {TASK_ID, "codex"} or reviewer_role in {"task-owner", "implementer"}:
        raise HandoffError("approval reviewer is not independent from the implementing task")
    if not isinstance(approval["reviewed_at_utc"], str) or UTC_RE.fullmatch(
        approval["reviewed_at_utc"]
    ) is None:
        raise HandoffError("approval receipt reviewed_at_utc is not canonical UTC")
    if _commit(approval["handoff_commit"], "approval handoff commit") != handoff_head:
        raise HandoffError("approval receipt does not match the handoff HEAD")
    if _sha256(approval["handoff_sha256"], "approval handoff hash") != handoff_sha256:
        raise HandoffError("approval receipt does not match the handoff document")
    if _commit(approval["broker_commit"], "approval broker commit") != handoff[
        "broker_candidate"
    ]["frozen_commit"]:
        raise HandoffError("approval receipt does not match the broker commit")
    if _commit(approval["bootstrap_commit"], "approval bootstrap commit") != handoff[
        "bootstrap_candidate"
    ]["frozen_commit"]:
        raise HandoffError("approval receipt does not match the bootstrap commit")
    scope = approval["review_scope"]
    expected = {item: True for item in handoff["approval_gate"]["required_review_scope"]}
    if scope != expected:
        raise HandoffError("approval receipt does not cover every required review scope")
    if not isinstance(approval["notes"], str):
        raise HandoffError("approval receipt notes must be a string")


def evaluate_preflight(
    handoff: dict[str, Any],
    *,
    handoff_path: Path,
    handoff_worktree: Path,
    broker_worktree: Path | None = None,
    bootstrap_worktree: Path | None = None,
    approval_receipt: Path | None = None,
) -> dict[str, Any]:
    """Return a complete non-mutating admission receipt."""

    handoff = validate_handoff(handoff)
    gates: list[dict[str, Any]] = []

    handoff_sha = _document_sha256(handoff)
    for item in handoff["external_t0_contract"]["files"]:
        target = handoff_worktree / item["path"]
        passed = target.is_file() and not target.is_symlink() and _file_sha256(target) == item[
            "sha256"
        ]
        _gate(
            gates,
            f"external_t0.file.{item['path']}",
            passed,
            _file_sha256(target) if target.is_file() and not target.is_symlink() else "missing",
        )

    ok, handoff_head = _git(handoff_worktree, "rev-parse", "HEAD^{commit}")
    _gate(
        gates,
        "handoff.head_readable",
        ok and COMMIT_RE.fullmatch(handoff_head) is not None,
        handoff_head,
    )
    ok_branch, branch = _git(handoff_worktree, "branch", "--show-current")
    _gate(gates, "handoff.branch_is_dedicated", ok_branch and branch == HANDOFF_BRANCH, branch)
    ok_status, dirty = _git(
        handoff_worktree, "status", "--porcelain=v1", "--untracked-files=all"
    )
    _gate(
        gates,
        "handoff.worktree_clean",
        ok_status and not dirty,
        "clean" if ok_status and not dirty else (dirty or "status failed"),
    )
    ok_tracking, remote_tracking = _git(
        handoff_worktree, "rev-parse", f"origin/{HANDOFF_BRANCH}^{{commit}}"
    )
    _gate(
        gates,
        "handoff.local_remote_tracking_is_head",
        ok and ok_tracking and remote_tracking == handoff_head,
        remote_tracking or "remote-tracking branch not present",
    )
    ok_remote, remote_line = _git(
        handoff_worktree,
        "ls-remote",
        "--exit-code",
        "origin",
        f"refs/heads/{HANDOFF_BRANCH}",
    )
    remote_commit = remote_line.split()[0] if ok_remote and remote_line.split() else ""
    _gate(
        gates,
        "handoff.remote_branch_is_head",
        ok and ok_remote and remote_commit == handoff_head,
        remote_commit or remote_line or "remote branch not present",
    )

    broker = handoff["broker_candidate"]
    bootstrap = handoff["bootstrap_candidate"]
    _candidate_gates(
        gates,
        "broker",
        broker,
        broker_worktree if broker_worktree is not None else Path(broker["worktree"]),
    )
    _candidate_gates(
        gates,
        "bootstrap",
        bootstrap,
        bootstrap_worktree
        if bootstrap_worktree is not None
        else Path(bootstrap["worktree"]),
    )

    if approval_receipt is None:
        _gate(
            gates,
            "independent_approval",
            False,
            "no independent approval receipt supplied",
        )
    else:
        try:
            approval = _read_json(approval_receipt, "approval receipt")
            raw = approval_receipt.read_bytes()
            if raw != _canonical_bytes(approval) + b"\n":
                raise HandoffError("approval receipt must be canonical sorted compact JSON")
            _validate_approval(approval, handoff, handoff_sha, handoff_head)
        except (HandoffError, OSError) as exc:
            _gate(gates, "independent_approval", False, str(exc))
        else:
            _gate(
                gates,
                "independent_approval",
                True,
                f"approved by {approval['reviewer_id']} as {approval['review_id']}",
            )

    admitted = all(gate["passed"] for gate in gates)
    blockers = [gate["name"] for gate in gates if not gate["passed"]]
    return {
        "schema": PREFLIGHT_SCHEMA,
        "handoff_id": handoff["handoff_id"],
        "evidence_classification": "read-only-admission-preflight-not-performance-evidence",
        "admission": "ADMITTED" if admitted else "BLOCKED",
        "resource_creation_permitted": admitted,
        "handoff_source": str(handoff_path.resolve()),
        "handoff_sha256": handoff_sha,
        "gates": gates,
        "blockers": blockers,
        "created_resource_ids": [],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only admission preflight; this command cannot create resources."
    )
    package = Path(__file__).resolve().parent
    parser.add_argument("--handoff", type=Path, default=package / "handoff.json")
    parser.add_argument("--handoff-worktree", type=Path)
    parser.add_argument("--broker-worktree", type=Path)
    parser.add_argument("--bootstrap-worktree", type=Path)
    parser.add_argument("--approval-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        handoff = load_handoff(args.handoff)
        if args.handoff_worktree is None:
            ok, root = _git(args.handoff.parent, "rev-parse", "--show-toplevel")
            if not ok:
                raise HandoffError(f"cannot locate handoff Git worktree: {root}")
            handoff_worktree = Path(root)
        else:
            handoff_worktree = args.handoff_worktree
        result = evaluate_preflight(
            handoff,
            handoff_path=args.handoff,
            handoff_worktree=handoff_worktree,
            broker_worktree=args.broker_worktree,
            bootstrap_worktree=args.bootstrap_worktree,
            approval_receipt=args.approval_receipt,
        )
    except HandoffError as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if result["resource_creation_permitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
