"""Offline validation of the committed snapshot-eligibility artifacts.

Covers: pinned-input integrity, schema validation of both the vendored
catalog and the eligibility output, deterministic rebuild, one-to-one
row coverage, fail-closed classification invariants (multi-GPU,
closed-image, storage-bound, topology, semantic gates), fallback
honesty, canary-plan discipline, and sanitization of every publishable
artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unittest

ELIG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ELIG_DIR)

import build_eligibility  # noqa: E402

SNAPSHOT_SAFE = {"direct-snapshot-safe", "snapshot-after-state-externalization"}

# Mirrors the inventory extractor's publishable-artifact scan
# (catalog/extract_forge_source.py at the pinned commit).
FORBIDDEN_PATTERNS = [
    re.compile(r"cr\.[a-z0-9-]+\.nebius\.cloud"),
    re.compile(
        r"\b(?:tenant|project|registry|computeinstance|mk8scluster|"
        r"mk8snodegroup|vpcsubnet|vpcnetwork)-[a-z0-9]{8,}\b"
    ),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?<!@sha256)"),
]
ORG_ID_CANDIDATE_RE = re.compile(r"\b[eiu]\d{2}[a-z0-9]{12,}\b")
NON_HEX_RE = re.compile(r"[g-z]")


def read(name: str) -> str:
    with open(os.path.join(ELIG_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def find_forbidden(text: str) -> list[str]:
    hits = [m.group(0) for pat in FORBIDDEN_PATTERNS for m in pat.finditer(text)]
    for m in ORG_ID_CANDIDATE_RE.finditer(text):
        if NON_HEX_RE.search(m.group(0)):
            hits.append(m.group(0))
    return hits


class EligibilityArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(read("eligibility.json"))
        cls.meta = cls.doc["meta"]
        cls.rows = cls.doc["rows"]
        cls.by_id = {r["id"]: r for r in cls.rows}
        cls.catalog = json.loads(read(os.path.join("inputs", "catalog.json")))
        cls.gate_ids = {g["id"] for g in cls.meta["gates"]}
        cls.blocker_ids = {b["id"] for b in cls.meta["blockers"]}
        cls.rule_ids = {r["id"] for r in cls.meta["rules"]}

    # -- pinned inputs -------------------------------------------------

    def test_pinned_inputs_match_recorded_hashes(self):
        for fname, key in (
            (os.path.join("inputs", "catalog.json"), "catalog_sha256"),
            (os.path.join("inputs", "catalog.schema.json"), "catalog_schema_sha256"),
        ):
            with open(os.path.join(ELIG_DIR, fname), "rb") as fh:
                digest = "sha256:" + hashlib.sha256(fh.read()).hexdigest()
            self.assertEqual(digest, build_eligibility.PINS[key], fname)
            self.assertEqual(digest, self.meta["pins"][key], fname)

    def test_catalog_version_pinned(self):
        self.assertEqual(
            self.meta["catalog_version"], self.catalog["meta"]["catalog_version"]
        )

    # -- schemas -------------------------------------------------------

    def test_vendored_catalog_validates_against_catalog_schema(self):
        import jsonschema

        schema = json.loads(read(os.path.join("inputs", "catalog.schema.json")))
        jsonschema.validate(self.catalog, schema)

    def test_eligibility_validates_against_eligibility_schema(self):
        import jsonschema

        schema = json.loads(read(os.path.join("schema", "eligibility.schema.json")))
        jsonschema.validate(self.doc, schema)

    # -- determinism and coverage --------------------------------------

    def test_rebuild_is_deterministic_and_matches_committed_outputs(self):
        _, elig_json, elig_tsv = build_eligibility.build()
        self.assertEqual(elig_json, read("eligibility.json"))
        self.assertEqual(elig_tsv, read("eligibility.tsv"))
        _, elig_json2, _ = build_eligibility.build()
        self.assertEqual(elig_json, elig_json2)

    def test_one_to_one_row_coverage(self):
        catalog_ids = sorted(r["id"] for r in self.catalog["rows"])
        out_ids = [r["id"] for r in self.rows]
        self.assertEqual(out_ids, sorted(out_ids))
        self.assertEqual(len(out_ids), len(set(out_ids)))
        self.assertEqual(sorted(out_ids), catalog_ids)

    def test_counts_match_rows(self):
        for field, counts in (
            ("snapshot_class", self.meta["class_counts"]),
            ("decision_rule", self.meta["rule_counts"]),
            ("fleet_status", self.meta["fleet_counts"]),
        ):
            observed: dict[str, int] = {}
            for r in self.rows:
                observed[r[field]] = observed.get(r[field], 0) + 1
            self.assertEqual(counts, observed, field)
        self.assertEqual(sum(self.meta["class_counts"].values()), len(self.rows))

    def test_tsv_matches_rows(self):
        lines = read("eligibility.tsv").splitlines()
        self.assertEqual(len(lines), len(self.rows) + 1)
        ids = [line.split("\t", 1)[0] for line in lines[1:]]
        self.assertEqual(ids, [r["id"] for r in self.rows])

    # -- fail-closed classification invariants -------------------------

    def test_every_row_has_class_rule_evidence_confidence(self):
        for r in self.rows:
            self.assertIn(r["snapshot_class"], self.meta["classes"], r["id"])
            self.assertIn(r["decision_rule"], self.rule_ids, r["id"])
            self.assertTrue(r["evidence"]["refs"], r["id"])
            self.assertTrue(r["evidence"]["detail"], r["id"])
            self.assertIn(r["confidence"], ("high", "medium", "low"), r["id"])

    def test_multi_gpu_never_snapshot_safe(self):
        seen = 0
        for r in self.rows:
            if r["catalog"]["multi_gpu_required"]:
                seen += 1
                self.assertEqual(r["snapshot_class"], "unresolved", r["id"])
                self.assertIn("multi-gpu-restore-unqualified", r["blockers"], r["id"])
        self.assertGreater(seen, 0)

    def test_snapshot_safe_requires_measured_local_lane_evidence(self):
        for r in self.rows:
            if r["snapshot_class"] in SNAPSHOT_SAFE:
                self.assertEqual(r["decision_rule"], "R01-lane-evidence", r["id"])
                self.assertEqual(r["evidence"]["tier"], "measured-local", r["id"])
                self.assertEqual(r["confidence"], "high", r["id"])
                self.assertIsNotNone(r["catalog"]["image_digest"], r["id"])
                self.assertIsNotNone(r["catalog"]["validator"], r["id"])
                self.assertFalse(r["catalog"]["multi_gpu_required"], r["id"])
                self.assertEqual(r["blockers"], [], r["id"])

    def test_closed_image_rows_fail_closed(self):
        seen = 0
        for r in self.rows:
            digestless = r["catalog"]["image_digest"] is None
            unknown_reg = r["catalog"]["registry_visibility"] == "unknown"
            if (digestless or unknown_reg) and r["fleet_status"] == "active":
                seen += 1
                self.assertNotIn(r["snapshot_class"], SNAPSHOT_SAFE, r["id"])
                if r["decision_rule"] == "R05-closed-image":
                    self.assertIn("no-digest-binding", r["blockers"], r["id"])
                    self.assertEqual(
                        r["fallback"]["admission"], "blocked-until-digest-bound", r["id"]
                    )
        self.assertGreater(seen, 0)

    def test_storage_bound_rows_require_storage_gate(self):
        seen = 0
        for r in self.rows:
            if r["snapshot_class"] == "conventional-only":
                self.assertNotIn("G-STORAGE", r["promotion_gates"], r["id"])
                continue
            if r["storage_bound"]:
                seen += 1
                self.assertIn("G-STORAGE", r["promotion_gates"], r["id"])
            else:
                self.assertNotIn("G-STORAGE", r["promotion_gates"], r["id"])
        self.assertGreater(seen, 0)

    def test_semantic_and_core_gates_on_every_active_row(self):
        for r in self.rows:
            if r["fleet_status"] != "active":
                continue
            for gate in ("G-DIGEST", "G-SEMEQ", "G-ROLLBACK"):
                self.assertIn(gate, r["promotion_gates"], r["id"])
            if r["snapshot_class"] != "conventional-only":
                self.assertIn("G-TOPOLOGY", r["promotion_gates"], r["id"])
                self.assertIn("G-CORRUPT", r["promotion_gates"], r["id"])

    def test_gate_and_blocker_references_resolve(self):
        for r in self.rows:
            for gate in r["promotion_gates"]:
                self.assertIn(gate, self.gate_ids, r["id"])
            for blocker in r["blockers"]:
                base = "access-gate" if blocker.startswith("access-gate:") else blocker
                self.assertIn(base, self.blocker_ids, r["id"])
        for gate in self.meta["gates"]:
            for binding in gate["bindings"]:
                self.assertRegex(binding, r"^(INV|CTL)-\d{2}$")
            self.assertNotIn("CTL-17", gate["bindings"], "Modal control must not bind")

    def test_unresolved_rows_name_blockers(self):
        for r in self.rows:
            if r["snapshot_class"] == "unresolved":
                self.assertTrue(r["blockers"], r["id"])

    def test_family_proven_rows_carry_rebind_blocker(self):
        seen = 0
        for r in self.rows:
            if r["catalog"]["snapshot_eligibility"] == "candidate-family-proven":
                seen += 1
                self.assertIn("digest-rebind-required", r["blockers"], r["id"])
        self.assertGreater(seen, 0)

    def test_conventional_only_rows_carry_rejection_evidence(self):
        seen = 0
        for r in self.rows:
            if r["snapshot_class"] == "conventional-only" and r["fleet_status"] == "active":
                seen += 1
                self.assertEqual(r["evidence"]["tier"], "measured-local", r["id"])
                self.assertIn("topology", r["evidence"]["detail"], r["id"])
        self.assertGreater(seen, 0)

    def test_availability_gates_become_access_blockers(self):
        for r in self.rows:
            for gate in r["catalog"]["availability_gates"]:
                self.assertIn(f"access-gate:{gate}", r["blockers"], r["id"])

    # -- fallback honesty ----------------------------------------------

    def test_every_active_row_has_explicit_fallback(self):
        for r in self.rows:
            fb = r["fallback"]
            if r["fleet_status"] != "active":
                self.assertEqual(fb["admission"], "excluded", r["id"])
                continue
            self.assertIn(
                fb["path"],
                ("conventional-cached-start", "conventional-pull-and-load"),
                r["id"],
            )
            self.assertNotEqual(fb["admission"], "excluded", r["id"])
            if fb["measured"]:
                self.assertEqual(fb["admission"], "measured", r["id"])
                self.assertTrue(fb["measurement_refs"], r["id"])
            else:
                self.assertEqual(fb["measurement_refs"], [], r["id"])
                self.assertIn(
                    fb["admission"],
                    ("measurement-required", "blocked-until-digest-bound"),
                    r["id"],
                )
            self.assertTrue(fb["measurement_owner"], r["id"])

    def test_measured_fallback_exists_for_msa_search(self):
        measured = [
            r
            for r in self.rows
            if r["fallback"]["measured"] and r["fleet_status"] == "active"
        ]
        self.assertEqual(len(measured), 1)
        self.assertTrue(measured[0]["id"].startswith("faststart:msa-search@"))

    # -- canary discipline ----------------------------------------------

    def test_canaries_resolve_and_are_requested_not_run(self):
        plan = self.meta["canary_plan"]
        canary_ids = [e["canary_id"] for e in plan["entries"]]
        self.assertEqual(len(canary_ids), len(set(canary_ids)))
        for e in plan["entries"]:
            row = self.by_id[e["row_id"]]
            self.assertEqual(e["status"], "requested-not-run", e["canary_id"])
            self.assertEqual(row["fleet_status"], "active", e["canary_id"])
            self.assertEqual(row["catalog"]["availability_gates"], [], e["canary_id"])
            self.assertIsNotNone(row["catalog"]["image_digest"], e["canary_id"])
            self.assertIn("resource-broker", e["requested_via"]["resource_broker"])
            self.assertIn("request_slo", e["requested_via"]["request_slo_harness"])
            self.assertIn(e["canary_id"], row["canary_ids"])
            if row["catalog"]["multi_gpu_required"]:
                self.assertFalse(e["snapshot_attempt_allowed"], e["canary_id"])
            if not e["snapshot_attempt_allowed"]:
                self.assertNotIn(row["snapshot_class"], SNAPSHOT_SAFE, e["canary_id"])
        for d in plan["deferred"]:
            self.assertEqual(d["status"], "deferred-not-requested")
            self.assertIn(d["row_id"], self.by_id)

    def test_row_canary_ids_backlink(self):
        plan_ids = {
            (e["row_id"], e["canary_id"]) for e in self.meta["canary_plan"]["entries"]
        }
        row_ids = {
            (r["id"], cid) for r in self.rows for cid in r["canary_ids"]
        }
        self.assertEqual(plan_ids, row_ids)

    # -- BioNeMo NIM coverage (ARCHVTEAMS-2407) ---------------------------

    def test_bionemo_covers_all_ten_nims_evidence_first(self):
        entries = self.meta["bionemo_nims"]
        names = [e["nim"] for e in entries]
        self.assertEqual(
            sorted(names),
            sorted(
                [
                    "boltz2", "openfold2", "diffdock", "evo2-40b", "genmol",
                    "molmim", "msa-search", "openfold3", "proteinmpnn",
                    "rfdiffusion",
                ]
            ),
        )
        self.assertEqual(names[:2], ["boltz2", "openfold2"])
        self.assertEqual(names[2:], sorted(names[2:]))
        self.assertEqual(
            [e["evidence_rank"] for e in entries], list(range(1, 11))
        )
        for e in entries[:2]:
            self.assertEqual(
                e["cohorts"]["provisioned_node"]["status"],
                "complete-fresh-fail-closed-n20",
                e["nim"],
            )

    def test_bionemo_entries_consistent_with_rows(self):
        for e in self.meta["bionemo_nims"]:
            row = self.by_id[e["row_id"]]
            self.assertEqual(row["source"], "faststart-v2-lanes", e["nim"])
            self.assertEqual(e["snapshot_class"], row["snapshot_class"], e["nim"])
            self.assertEqual(
                e["catalog_snapshot_eligibility"],
                row["catalog"]["snapshot_eligibility"],
                e["nim"],
            )
            self.assertEqual(e["confidence"], row["confidence"], e["nim"])
            fb = e["conventional_fallback"]
            self.assertEqual(fb["path"], row["fallback"]["path"], e["nim"])
            self.assertEqual(fb["admission"], row["fallback"]["admission"], e["nim"])
            self.assertEqual(fb["measured"], row["fallback"]["measured"], e["nim"])

    def test_bionemo_blockers_and_cohorts_fail_closed(self):
        by_nim = {e["nim"]: e for e in self.meta["bionemo_nims"]}
        for nim, e in by_nim.items():
            self.assertTrue(e["storage_blockers"], nim)
            prov = e["cohorts"]["provisioned_node"]
            newnode = e["cohorts"]["new_preemptible_node"]
            self.assertTrue(prov["evidence_refs"], nim)
            self.assertIn("resource-broker", newnode["requested_via"]["resource_broker"], nim)
            self.assertIn("request_slo", newnode["requested_via"]["request_slo_harness"], nim)
            self.assertIn("preemptible", newnode["required"], nim)
            if prov["status"] != "complete-fresh-fail-closed-n20":
                self.assertTrue(prov["further_required"], nim)
        self.assertTrue(by_nim["msa-search"]["topology_blockers"])
        self.assertTrue(by_nim["evo2-40b"]["topology_blockers"])
        self.assertEqual(
            by_nim["evo2-40b"]["cohorts"]["new_preemptible_node"]["status"],
            "blocked-hardware-gate-h200",
        )
        self.assertEqual(
            by_nim["evo2-40b"]["cohorts"]["provisioned_node"]["status"],
            "missing-production-shaped",
        )
        self.assertEqual(by_nim["msa-search"]["snapshot_class"], "conventional-only")
        self.assertTrue(by_nim["openfold2"]["cohorts"]["new_preemptible_node"]["historical_note"])

    def test_modal_is_never_an_execution_class(self):
        pruned = json.loads(read("eligibility.json"))
        pruned["meta"]["scope_notes"] = []
        self.assertNotIn("modal", json.dumps(pruned).lower())

    # -- scope and sanitization ------------------------------------------

    def test_no_modal_dependency_anywhere(self):
        for name in ARTIFACTS:
            text = read(name).lower()
            for token in ("modal.com", "import modal", "modal app", "modal deploy"):
                self.assertNotIn(token, text, name)
        # The only permitted mentions are the scope note stating Modal is
        # reference-only and excluded.
        for note_hit in re.finditer(r"[Mm]odal", read("eligibility.json")):
            context = read("eligibility.json")[
                max(0, note_hit.start() - 400) : note_hit.end() + 400
            ]
            self.assertIn("reference", context.lower())

    def test_no_credentials_or_private_identifiers(self):
        for name in ARTIFACTS:
            text = read(name)
            leaks = find_forbidden(text)
            self.assertEqual(leaks, [], f"{name}: {sorted(set(leaks))[:10]}")
            self.assertNotIn("/home/", text, name)
            self.assertNotIn("nvapi-", text, name)


ARTIFACTS = [
    "eligibility.json",
    "eligibility.tsv",
    "README.md",
    "ELIGIBILITY_POLICY.md",
    os.path.join("inputs", "catalog.json"),
    os.path.join("inputs", "catalog.schema.json"),
    os.path.join("inputs", "lane_evidence.json"),
    os.path.join("inputs", "bionemo_cohorts.json"),
    os.path.join("schema", "eligibility.schema.json"),
]


if __name__ == "__main__":
    unittest.main()
