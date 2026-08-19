from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from performance.storage_cache_matrix.network_baseline_handoff.preflight import (
    APPROVAL_SCHEMA,
    HANDOFF_BRANCH,
    HandoffError,
    _document_sha256,
    evaluate_preflight,
    load_handoff,
    validate_handoff,
)


PACKAGE = Path(__file__).resolve().parents[1]
FASTSTART_ROOT = PACKAGE.parents[2]
REPOSITORY_ROOT = FASTSTART_ROOT.parents[1]


def run(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        list(args),
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HandoffContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.handoff = load_handoff(PACKAGE / "handoff.json")

    def test_checked_in_handoff_is_planning_only_and_locally_unavailable(self) -> None:
        self.assertEqual(
            self.handoff["evidence_classification"],
            "execution-plan-only-no-performance-evidence",
        )
        self.assertEqual(
            {tier["tier_id"] for tier in self.handoff["scope"]["included_tiers"]},
            {"network_ssd_pvc", "object_store_remote_fetch"},
        )
        self.assertEqual(
            self.handoff["scope"]["local_nvme"]["status"],
            "unavailable-unverified-entitlement",
        )
        self.assertIsNone(self.handoff["scope"]["local_nvme"]["substituted_by"])
        self.assertFalse(self.handoff["scope"]["full_matrix_completion_claim"])
        self.assertFalse(self.handoff["scope"]["boltz_external_tmp_conclusion_claim"])

    def test_local_nvme_cannot_be_substituted_or_renamed(self) -> None:
        changed = copy.deepcopy(self.handoff)
        changed["scope"]["local_nvme"]["substituted_by"] = "network_ssd_pvc"
        with self.assertRaisesRegex(HandoffError, "unsubstituted"):
            validate_handoff(changed)
        changed = copy.deepcopy(self.handoff)
        changed["scope"]["included_tiers"][0]["matrix_tier"] = "local_nvme"
        with self.assertRaisesRegex(HandoffError, "attached_block_pvc"):
            validate_handoff(changed)

    def test_result_and_readiness_claims_fail_closed(self) -> None:
        changed = copy.deepcopy(self.handoff)
        changed["status"] = "measured"
        with self.assertRaisesRegex(HandoffError, "non-executed"):
            validate_handoff(changed)
        changed = copy.deepcopy(self.handoff)
        changed["approval_gate"]["resource_creation_permitted"] = True
        with self.assertRaisesRegex(HandoffError, "approval gate"):
            validate_handoff(changed)
        changed = copy.deepcopy(self.handoff)
        changed["scope"]["full_matrix_completion_claim"] = True
        with self.assertRaisesRegex(HandoffError, "full-matrix"):
            validate_handoff(changed)

    def test_external_t0_and_request_work_boundaries_are_frozen(self) -> None:
        changed = copy.deepcopy(self.handoff)
        changed["external_t0_contract"]["t0_boundary"] = "pod-ready"
        with self.assertRaisesRegex(HandoffError, "T0 boundary"):
            validate_handoff(changed)
        changed = copy.deepcopy(self.handoff)
        changed["measurement_plan"]["request_boundary"] = "prefetch before T0"
        with self.assertRaisesRegex(HandoffError, "request-work boundary"):
            validate_handoff(changed)
        changed = copy.deepcopy(self.handoff)
        changed["measurement_plan"]["phase_percentile_summation"] = "allowed"
        with self.assertRaisesRegex(HandoffError, "phase percentiles"):
            validate_handoff(changed)

    def test_json_schemas_are_closed_and_parseable(self) -> None:
        for name in ("handoff.schema.json", "approval-receipt.schema.json"):
            schema = json.loads((PACKAGE / name).read_text())
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_checked_in_preflight_is_blocked_without_mutation(self) -> None:
        result = evaluate_preflight(
            self.handoff,
            handoff_path=PACKAGE / "handoff.json",
            handoff_worktree=REPOSITORY_ROOT,
        )
        self.assertEqual(result["admission"], "BLOCKED")
        self.assertFalse(result["resource_creation_permitted"])
        self.assertEqual(result["created_resource_ids"], [])
        self.assertIn("independent_approval", result["blockers"])
        self.assertIn("broker.storage_baseline_capability_pinned", result["blockers"])
        self.assertIn("bootstrap.storage_baseline_capability_pinned", result["blockers"])


class AdmissionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.handoff = load_handoff(PACKAGE / "handoff.json")
        self.handoff_repo, self.handoff_commit = self.make_repo(
            "handoff",
            HANDOFF_BRANCH,
            external_t0_files=True,
        )
        self.broker_repo, self.broker_commit = self.make_repo(
            "broker", "agent/catalog-switch-resource-broker"
        )
        self.bootstrap_repo, self.bootstrap_commit = self.make_repo(
            "bootstrap", "agent/catalog-switch-k8s-baseline"
        )
        self.handoff["broker_candidate"].update(
            {
                "worktree": str(self.broker_repo),
                "frozen_commit": self.broker_commit,
                "required_files": [
                    {"path": "contract.txt", "sha256": sha256(self.broker_repo / "contract.txt")}
                ],
            }
        )
        self.handoff["broker_candidate"]["capability_contract"].update(
            {
                "status": "pinned-in-frozen-commit",
                "path": "capability.txt",
                "sha256": sha256(self.broker_repo / "capability.txt"),
            }
        )
        self.handoff["bootstrap_candidate"].update(
            {
                "worktree": str(self.bootstrap_repo),
                "frozen_commit": self.bootstrap_commit,
                "required_files": [
                    {
                        "path": "contract.txt",
                        "sha256": sha256(self.bootstrap_repo / "contract.txt"),
                    }
                ],
            }
        )
        self.handoff["bootstrap_candidate"]["capability_contract"].update(
            {
                "status": "pinned-in-frozen-commit",
                "path": "capability.txt",
                "sha256": sha256(self.bootstrap_repo / "capability.txt"),
            }
        )
        validate_handoff(self.handoff)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_repo(
        self, name: str, branch: str, *, external_t0_files: bool = False
    ) -> tuple[Path, str]:
        worktree = self.root / name
        remote = self.root / f"{name}.git"
        worktree.mkdir()
        run("git", "init", "--initial-branch", branch, cwd=worktree)
        run("git", "config", "user.name", "Handoff Test", cwd=worktree)
        run("git", "config", "user.email", "handoff-test@example.invalid", cwd=worktree)
        if external_t0_files:
            for item in self.handoff["external_t0_contract"]["files"]:
                source = REPOSITORY_ROOT / item["path"]
                target = worktree / item["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        else:
            (worktree / "contract.txt").write_text(f"{name} contract\n")
            (worktree / "capability.txt").write_text(f"{name} storage capability\n")
        run("git", "add", ".", cwd=worktree)
        run("git", "commit", "-m", f"freeze {name}", cwd=worktree)
        run("git", "init", "--bare", str(remote), cwd=self.root)
        run("git", "remote", "add", "origin", str(remote), cwd=worktree)
        run("git", "push", "--set-upstream", "origin", branch, cwd=worktree)
        return worktree, run("git", "rev-parse", "HEAD", cwd=worktree)

    def write_approval(self, **changes: object) -> Path:
        value = {
            "schema": APPROVAL_SCHEMA,
            "decision": "approved",
            "review_id": "independent-review-test",
            "reviewer_id": "security-reliability-reviewer",
            "reviewer_role": "independent-reviewer",
            "reviewed_at_utc": "2026-08-19T16:00:00.000000Z",
            "handoff_commit": self.handoff_commit,
            "handoff_sha256": _document_sha256(self.handoff),
            "broker_commit": self.broker_commit,
            "bootstrap_commit": self.bootstrap_commit,
            "review_scope": {
                item: True for item in self.handoff["approval_gate"]["required_review_scope"]
            },
            "notes": "test-only approval fixture",
        }
        value.update(changes)
        path = self.root / "approval.json"
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        return path

    def evaluate(self, approval: Path | None) -> dict[str, object]:
        return evaluate_preflight(
            self.handoff,
            handoff_path=PACKAGE / "handoff.json",
            handoff_worktree=self.handoff_repo,
            broker_worktree=self.broker_repo,
            bootstrap_worktree=self.bootstrap_repo,
            approval_receipt=approval,
        )

    def test_clean_pushed_exact_candidates_and_independent_approval_admit(self) -> None:
        result = self.evaluate(self.write_approval())
        self.assertEqual(result["admission"], "ADMITTED")
        self.assertTrue(result["resource_creation_permitted"])
        self.assertEqual(result["blockers"], [])
        self.assertTrue(all(gate["passed"] for gate in result["gates"]))

    def test_missing_approval_blocks_even_when_candidates_are_clean(self) -> None:
        result = self.evaluate(None)
        self.assertFalse(result["resource_creation_permitted"])
        self.assertEqual(result["blockers"], ["independent_approval"])

    def test_missing_storage_capability_blocks_even_with_approval(self) -> None:
        self.handoff["broker_candidate"]["capability_contract"].update(
            {"status": "missing-awaiting-clean-commit", "sha256": None}
        )
        result = self.evaluate(self.write_approval())
        self.assertIn("broker.storage_baseline_capability_pinned", result["blockers"])
        self.assertFalse(result["resource_creation_permitted"])

    def test_dirty_broker_and_bootstrap_each_block(self) -> None:
        (self.broker_repo / "uncommitted.txt").write_text("dirty\n")
        (self.bootstrap_repo / "uncommitted.txt").write_text("dirty\n")
        result = self.evaluate(self.write_approval())
        self.assertIn("broker.worktree_clean", result["blockers"])
        self.assertIn("bootstrap.worktree_clean", result["blockers"])
        self.assertFalse(result["resource_creation_permitted"])

    def test_unpushed_candidate_commit_blocks(self) -> None:
        (self.bootstrap_repo / "contract.txt").write_text("new bootstrap contract\n")
        run("git", "add", "contract.txt", cwd=self.bootstrap_repo)
        run("git", "commit", "-m", "unpublished bootstrap", cwd=self.bootstrap_repo)
        result = self.evaluate(self.write_approval())
        self.assertIn("bootstrap.head_is_frozen_commit", result["blockers"])
        self.assertIn("bootstrap.remote_divergence_zero", result["blockers"])

    def test_stale_or_non_independent_approval_blocks(self) -> None:
        result = self.evaluate(self.write_approval(handoff_commit="0" * 40))
        self.assertIn("independent_approval", result["blockers"])
        result = self.evaluate(
            self.write_approval(reviewer_id="codex", reviewer_role="implementer")
        )
        self.assertIn("independent_approval", result["blockers"])

    def test_noncanonical_approval_blocks(self) -> None:
        canonical = json.loads(self.write_approval().read_text())
        path = self.root / "pretty-approval.json"
        path.write_text(json.dumps(canonical, indent=2) + "\n")
        result = self.evaluate(path)
        self.assertIn("independent_approval", result["blockers"])

    def test_contract_content_drift_blocks_even_at_expected_branch(self) -> None:
        changed = copy.deepcopy(self.handoff)
        changed["broker_candidate"]["required_files"][0]["sha256"] = "f" * 64
        result = evaluate_preflight(
            changed,
            handoff_path=PACKAGE / "handoff.json",
            handoff_worktree=self.handoff_repo,
            broker_worktree=self.broker_repo,
            bootstrap_worktree=self.bootstrap_repo,
            approval_receipt=self.write_approval(handoff_sha256=_document_sha256(changed)),
        )
        self.assertTrue(
            any(
                blocker.startswith("broker.file.contract.txt")
                for blocker in result["blockers"]
            )
        )


if __name__ == "__main__":
    unittest.main()
