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
FASTSTART_ROOT = os.path.dirname(os.path.dirname(ELIG_DIR))
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
            (os.path.join("inputs", "threat_model.json"), "threat_model_sha256"),
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
        threat = json.loads(read(os.path.join("inputs", "threat_model.json")))
        self.assertEqual(threat["status"], "reviewed")
        threat_ids = {i["id"] for i in threat["invariants"]}
        threat_ids |= {c["id"] for c in threat["controls"]}
        for gate in self.meta["gates"]:
            for binding in gate["bindings"]:
                self.assertIn(binding, threat_ids, gate["id"])
            self.assertNotIn("CTL-17", gate["bindings"], "Modal control must not bind")

    def test_gate_binding_validator_rejects_unknown_and_modal_refs(self):
        ids = {"INV-01", "CTL-01", "CTL-17"}
        with self.assertRaises(SystemExit):
            build_eligibility.validate_gate_bindings(
                [{"id": "G-X", "bindings": ["INV-99"]}], ids
            )
        with self.assertRaises(SystemExit):
            build_eligibility.validate_gate_bindings(
                [{"id": "G-X", "bindings": ["CTL-17"]}], ids
            )

    def test_interfaces_are_in_tree_pinned_and_drift_checked(self):
        for iface in self.meta["interfaces"]:
            rel = iface["path"][len("nim-fast-start/faststart-v2/"):]
            path = os.path.join(FASTSTART_ROOT, rel)
            self.assertTrue(os.path.isfile(path), iface["path"])
            with open(path, "rb") as fh:
                data = fh.read()
            self.assertEqual(
                "sha256:" + hashlib.sha256(data).hexdigest(), iface["sha256"]
            )
            self.assertEqual(json.loads(data)["$id"], iface["schema_id"])
        schema_ids = {i["schema_id"] for i in self.meta["interfaces"]}
        self.assertEqual(len(schema_ids), 3)
        with self.assertRaises(SystemExit):
            build_eligibility.repo_read_bytes("does/not/exist.json")

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
            self.assertTrue(prov["further_required"], nim)
            self.assertIn("resource-broker", newnode["requested_via"]["resource_broker"], nim)
            self.assertIn("request_slo", newnode["requested_via"]["request_slo_harness"], nim)
            self.assertIn("preemptible", newnode["required"], nim)
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

    def test_provisioned_statuses_bound_to_catalog_evidence_class(self):
        cat_by_id = {r["id"]: r for r in self.catalog["rows"]}
        for e in self.meta["bionemo_nims"]:
            prov = e["cohorts"]["provisioned_node"]
            measured = cat_by_id[e["row_id"]]["startup"]["measured"]
            self.assertEqual(prov["evidence_class"], measured["evidence_class"], e["nim"])
            self.assertEqual(
                prov["status"],
                build_eligibility.derive_provisioned_status(
                    measured["evidence_class"], prov["sealed"]
                ),
                e["nim"],
            )

    def test_unsealed_evidence_never_supports_snapshot_safe_or_high(self):
        for e in self.meta["bionemo_nims"]:
            prov = e["cohorts"]["provisioned_node"]
            if prov["sealed"]:
                continue
            self.assertNotIn(
                e["snapshot_class"],
                ("direct-snapshot-safe", "snapshot-after-state-externalization"),
                e["nim"],
            )
            self.assertNotEqual(e["confidence"], "high", e["nim"])
            self.assertTrue(prov["status"].endswith("-unsealed"), e["nim"])
            self.assertIsNone(prov["outcome"]["slo_pass"], e["nim"])
            row = self.by_id[e["row_id"]]
            self.assertIn("unsealed-evidence-receipts", row["blockers"], e["nim"])

    def test_slo_outcomes_recomputed_not_trusted(self):
        cat_by_id = {r["id"]: r for r in self.catalog["rows"]}
        for e in self.meta["bionemo_nims"]:
            prov = e["cohorts"]["provisioned_node"]
            outcome = prov["outcome"]
            if outcome is None or outcome["slo_pass"] is None:
                continue
            measured = cat_by_id[e["row_id"]]["startup"]["measured"]
            # the builder recomputes; committed output must agree with both
            # the recomputation source and the cross-checked catalog flag
            self.assertEqual(outcome["slo_pass"], measured["slo_under_30s"], e["nim"])
            if prov["status"] == "complete-fresh-fail-closed-n20":
                self.assertEqual(
                    outcome["slo_pass"],
                    outcome["boottime_upper_p95_s"] < 30.0,
                    e["nim"],
                )
            else:
                self.assertEqual(
                    outcome["slo_pass"],
                    outcome["t0_to_call2_p50_s"] < 30.0,
                    e["nim"],
                )
        with self.assertRaises(SystemExit):
            build_eligibility.assert_slo_consistent(True, False, "adversary")
        with self.assertRaises(SystemExit):
            build_eligibility.assert_slo_consistent(False, None, "adversary")

    def test_bionemo_evidence_refs_resolve_to_committed_bytes(self):
        for e in self.meta["bionemo_nims"]:
            for section in ("provisioned_node", "new_preemptible_node"):
                for ref in e["cohorts"][section]["evidence_refs"]:
                    rel = ref["path"][len("nim-fast-start/faststart-v2/"):]
                    full = os.path.join(FASTSTART_ROOT, rel)
                    if ref["sha256"] is None:
                        self.assertTrue(os.path.isdir(full), ref["path"])
                        self.assertFalse(
                            e["cohorts"][section].get("sealed", True), e["nim"]
                        )
                        continue
                    self.assertTrue(os.path.isfile(full), ref["path"])
                    with open(full, "rb") as fh:
                        digest = "sha256:" + hashlib.sha256(fh.read()).hexdigest()
                    self.assertEqual(digest, ref["sha256"], ref["path"])

    def test_n20_outcomes_recomputed_and_slo_honest(self):
        by_nim = {e["nim"]: e for e in self.meta["bionemo_nims"]}
        boltz = by_nim["boltz2"]["cohorts"]["provisioned_node"]
        of2 = by_nim["openfold2"]["cohorts"]["provisioned_node"]
        self.assertFalse(boltz["outcome"]["slo_pass"])
        self.assertEqual(boltz["outcome"]["boottime_upper_p95_s"], 30.310246)
        self.assertIn("latency result", boltz["outcome"]["note"])
        self.assertIn("boltz2-under-20", boltz["further_required"])
        self.assertTrue(of2["outcome"]["slo_pass"])
        self.assertEqual(of2["outcome"]["boottime_upper_p95_s"], 17.629887)
        self.assertIn("not closed by the SLO pass", of2["further_required"])
        for prov in (boltz, of2):
            self.assertEqual(len(prov["outstanding_evidence_gaps"]), 3)
            gaps = " ".join(prov["outstanding_evidence_gaps"])
            self.assertIn("Xid", gaps)
            self.assertIn("80 raw response bodies", gaps)
        for nim in ("openfold3", "rfdiffusion"):
            prov = by_nim[nim]["cohorts"]["provisioned_node"]
            self.assertFalse(prov["outcome"]["slo_pass"], nim)
            self.assertIn("exceeds the 30 s SLO", prov["further_required"], nim)

    def test_molmim_evidence_disclosed_as_not_sealed(self):
        molmim = next(e for e in self.meta["bionemo_nims"] if e["nim"] == "molmim")
        prov = molmim["cohorts"]["provisioned_node"]
        self.assertFalse(prov["sealed"])
        gaps = " ".join(prov["outstanding_evidence_gaps"])
        self.assertIn("not sealed", gaps)
        self.assertIn("harness tree", gaps)
        for e in self.meta["bionemo_nims"]:
            if e["nim"] != "molmim":
                self.assertTrue(e["cohorts"]["provisioned_node"]["sealed"], e["nim"])

    def test_newnode_cohorts_require_at_least_20_accepted_samples(self):
        proof = self.meta["newnode_zero_sample_proof"]
        self.assertEqual(proof["sample_count"], 0)
        self.assertEqual(proof["poolable_run_ids"], [])
        for e in self.meta["bionemo_nims"]:
            newnode = e["cohorts"]["new_preemptible_node"]
            self.assertGreaterEqual(newnode["min_accepted_samples"], 20, e["nim"])
            self.assertIn("at least 20 accepted samples", newnode["required"], e["nim"])
            for match in re.finditer(r"n\s*>=\s*(\d+)", newnode["required"]):
                self.assertGreaterEqual(int(match.group(1)), 20, e["nim"])
            self.assertNotIn("n>=3", newnode["required"], e["nim"])

    def test_newnode_requirement_reconciles_with_authoritative_audit(self):
        with open(
            os.path.join(FASTSTART_ROOT, "openfold2-newnode", "CURRENT_STATUS.json"),
            encoding="utf-8",
        ) as fh:
            audit = json.load(fh)
        self.assertEqual(audit["current_contract"]["sample_count"], 0)
        self.assertIn(
            "n>=20 cohort aggregator",
            audit["v1_blockers"]["missing_current_contract_evidence"],
        )
        self.assertTrue(
            any(
                "at least 20 accepted samples" in step
                for step in audit["newnode_v2_plan"]
            )
        )
        of2 = next(e for e in self.meta["bionemo_nims"] if e["nim"] == "openfold2")
        note = of2["cohorts"]["new_preemptible_node"]["historical_note"]
        for run in audit["historical_runs"]:
            self.assertIn(run["run_id"], note)

    def test_msa_exclusion_is_correctable_not_permanent(self):
        with open(
            os.path.join(FASTSTART_ROOT, "msa-search-native", "results.json"),
            encoding="utf-8",
        ) as fh:
            results = json.load(fh)
        native = results["native_checkpoint"]
        self.assertIn("emptyDir", native["reason"])
        self.assertIn("cache PVC", native["reason"])
        self.assertIn("fresh checkpoint", native["required_fix"])
        self.assertIn("/opt/nim/.cache", native["required_fix"])
        msa = next(e for e in self.meta["bionemo_nims"] if e["nim"] == "msa-search")
        row = self.by_id[msa["row_id"]]
        blob = json.dumps(msa) + row["evidence"]["detail"]
        self.assertIn("correctable", blob)
        self.assertIn("fresh checkpoint", blob)
        self.assertNotIn("permanent", blob.lower())
        # "inherent" may appear only inside the explicit negation.
        lowered = blob.lower()
        self.assertEqual(
            lowered.count("inherent"), lowered.count("not an inherent")
        )
        self.assertIn(
            "new exact capture", self.meta["classes"]["conventional-only"]
        )

    def test_negative_mutations_per_status_class(self):
        b = build_eligibility
        # unknown evidence class can never silently become a status
        with self.assertRaises(SystemExit):
            b.derive_provisioned_status("some new cohort kind")
        with self.assertRaises(SystemExit):
            b.derive_provisioned_status(None)
        # complete-fresh-fail-closed-n20 adversaries: sample count,
        # denominator, percentiles, qualification, cleanup, run/cohort
        # binding, semantic exercise, outcome column, summaries
        tsv_path = os.path.join(
            FASTSTART_ROOT, "boltz2-native", "fresh-cohort-n20-results.tsv"
        )
        with open(tsv_path, encoding="utf-8") as fh:
            good = fh.read()
        args = (28.794544, 30.208757, "b2-n20-")
        b.check_n20_tsv(good, *args)
        lines = good.splitlines()
        sample_idx = next(i for i, l in enumerate(lines) if l.startswith("sample"))
        missing_row = "\n".join(lines[:sample_idx] + lines[sample_idx + 1:]) + "\n"
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(missing_row, *args)
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(good, 28.794544, 29.0, "b2-n20-")
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(good.replace("0/20", "1/20"), *args)
        # qualification / cleanup flipped to FAIL must be rejected
        first_sample = lines[sample_idx]
        qual_fail = first_sample.replace("\tPASS\tPASS\t", "\tFAIL\tPASS\t", 1)
        cleanup_fail = first_sample.replace("\tPASS\tPASS\t", "\tPASS\tFAIL\t", 1)
        for mutated_line in (qual_fail, cleanup_fail):
            self.assertNotEqual(mutated_line, first_sample)
            mutated = "\n".join(
                lines[:sample_idx] + [mutated_line] + lines[sample_idx + 1:]
            ) + "\n"
            with self.assertRaises(SystemExit):
                b.check_n20_tsv(mutated, *args)
        # duplicated run id
        second_sample = lines[sample_idx + 1].split("\t")
        first_fields = first_sample.split("\t")
        second_sample[3] = first_fields[3]
        dup = "\n".join(
            lines[:sample_idx + 1]
            + ["\t".join(second_sample)]
            + lines[sample_idx + 2:]
        ) + "\n"
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(dup, *args)
        # cohort not bound to this NIM
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(good, 28.794544, 30.208757, "of2-n20-")
        # cohort_outcome contradicting the recomputed SLO
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(good.replace("SLO_FAIL", "PASS"), *args)
        # semantic exercise zeroed out
        sem_zero = first_fields[:]
        sem_zero[10] = "0.0"
        mutated = "\n".join(
            lines[:sample_idx] + ["\t".join(sem_zero)] + lines[sample_idx + 1:]
        ) + "\n"
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(mutated, *args)
        # summary rows removed
        no_summary = "\n".join(
            l for l in lines if not l.startswith("summary")
        ) + "\n"
        with self.assertRaises(SystemExit):
            b.check_n20_tsv(no_summary, *args)
        # complete-n3 adversaries: structural extraction, never token presence
        spec = b.N3_SPECS["genmol"]
        with open(
            os.path.join(FASTSTART_ROOT, "genmol-native", "results.json"),
            encoding="utf-8",
        ) as fh:
            genmol = json.load(fh)
        p50 = 12.177434
        image = "nvcr.io/nim/nvidia/genmol@sha256:139b909a450fe1fb81198214784a15f67e172e766a93a1569827ba5aa05b4541"
        b.check_n3_results(genmol, spec, p50, image)
        # unrelated JSON that merely contains the p50 token must be rejected
        with self.assertRaises(SystemExit):
            b.check_n3_results(
                {"unrelated": [p50], "note": b.RESPONSE_CONTRACT, "img": image},
                spec,
                p50,
                image,
            )
        mutated = json.loads(json.dumps(genmol))
        mutated["status"] = "FAIL"
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, spec, p50, image)
        mutated = json.loads(json.dumps(genmol))
        mutated["buffered"]["demand_to_two_semantic_seconds"][0] = 99.9
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, spec, p50, image)
        mutated = json.loads(json.dumps(genmol))
        mutated["image"] = "nvcr.io/nim/nvidia/genmol@sha256:" + "0" * 64
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, spec, p50, image)
        mutated = json.loads(json.dumps(genmol))
        mutated["timing_measurement"]["response_timing_contract"] = "other/v2"
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, spec, p50, image)
        # interface pin adversaries: drifted bytes and drifted $id
        contract = dict(b.INTERFACE_CONTRACTS[0])
        data = b.repo_read_bytes(contract["path"])
        b.check_interface_bytes(data, contract)
        with self.assertRaises(SystemExit):
            b.check_interface_bytes(data + b" ", contract)
        wrong_id = dict(contract, schema_id="https://nebius.example/other-v1.json")
        with self.assertRaises(SystemExit):
            b.check_interface_bytes(data, wrong_id)
        # unsealed evidence derivation
        self.assertEqual(
            b.derive_provisioned_status("exact response-boundary n=3", sealed=False),
            "complete-n3-unsealed",
        )
        with self.assertRaises(SystemExit):
            b.derive_provisioned_status("fresh fail-closed n=20", sealed=False)
        # complete-n3 (proteinmpnn TSV shape)
        head = "run_id\tstatus\tdemand_to_two_semantic_responses_seconds"
        good_pmpnn = f"{head}\nr1\tPASS\t1.0\nr2\tPASS\t2.0\nr3\tPASS\t3.0\n"
        b.check_pmpnn_tsv(good_pmpnn, 2.0)
        with self.assertRaises(SystemExit):
            b.check_pmpnn_tsv(good_pmpnn.replace("r3\tPASS\t3.0\n", ""), 2.0)
        with self.assertRaises(SystemExit):
            b.check_pmpnn_tsv(good_pmpnn.replace("r2\tPASS", "r2\tFAIL"), 2.0)
        # complete-n3-conventional (msa) and its exclusion record
        with open(
            os.path.join(FASTSTART_ROOT, "msa-search-native", "results.json"),
            encoding="utf-8",
        ) as fh:
            msa = json.load(fh)
        p50 = msa["conventional_cached_n3"]["demand_to_call2_response_seconds"]["median"]
        b.check_msa_results(msa, p50)
        mutated = json.loads(json.dumps(msa))
        mutated["conventional_cached_n3"]["trial_count"] = 2
        with self.assertRaises(SystemExit):
            b.check_msa_results(mutated, p50)
        mutated = json.loads(json.dumps(msa))
        mutated["native_checkpoint"]["counted_trials"] = 1
        with self.assertRaises(SystemExit):
            b.check_msa_results(mutated, p50)
        mutated = json.loads(json.dumps(msa))
        mutated["native_checkpoint"]["required_fix"] = "n/a"
        with self.assertRaises(SystemExit):
            b.check_msa_results(mutated, p50)
        # missing-production-shaped (evo2): digest identity
        with self.assertRaises(SystemExit):
            b.check_evo2_profile({"model": {"image": "img@sha256:other"}}, "sha256:x")
        # zero-sample proof mutations (required-not-run must stay proven)
        with open(
            os.path.join(FASTSTART_ROOT, "openfold2-newnode", "CURRENT_STATUS.json"),
            encoding="utf-8",
        ) as fh:
            audit = json.load(fh)
        for mutate in (
            lambda d: d["current_contract"].__setitem__("sample_count", 1),
            lambda d: d["current_contract"].__setitem__("poolable_run_ids", ["x"]),
            lambda d: d["current_contract"].__setitem__("classification", "OTHER"),
            lambda d: d["v1_blockers"].__setitem__(
                "missing_current_contract_evidence", []
            ),
            lambda d: d.__setitem__("newnode_v2_plan", ["run some samples"]),
        ):
            copy = json.loads(json.dumps(audit))
            mutate(copy)
            with self.assertRaises(SystemExit):
                b.check_zero_newnode_samples(copy)
        # blocked-hardware-gate-h200 vs required-not-run derivation
        self.assertEqual(
            b.derive_newnode_status(["hardware-gate-h200"]),
            "blocked-hardware-gate-h200",
        )
        self.assertEqual(b.derive_newnode_status([]), "required-not-run")
        # n>=20 floor, per-scenario strictness
        good_text = "at least 20 accepted samples per scenario (n>=20)"
        b.check_min_samples(20, good_text)
        with self.assertRaises(SystemExit):
            b.check_min_samples(19, good_text)
        with self.assertRaises(SystemExit):
            b.check_min_samples(20, "fail-closed n>=3 lifecycle")
        with self.assertRaises(SystemExit):
            b.check_min_samples(20, "at least 20 accepted samples")
        with self.assertRaises(SystemExit):
            b.check_min_samples(
                20, "at least 20 accepted samples per scenario, in total"
            )
        with self.assertRaises(SystemExit):
            b.check_min_samples(
                20,
                "at least 20 accepted samples per scenario total across scenarios",
            )
        with self.assertRaises(SystemExit):
            b.check_min_samples(20, good_text, per_scenario=False)
        # foreign new-node evidence directories must fail closed
        with self.assertRaises(SystemExit):
            b.check_no_other_newnode_dirs(["openfold2-newnode", "boltz2-newnode"])
        with self.assertRaises(SystemExit):
            b.check_no_other_newnode_dirs([])
        # metrics-doc drift
        with self.assertRaises(SystemExit):
            b.check_metrics_doc("nothing relevant here")

    def test_snapshot_safe_requires_verified_image_binding(self):
        for e in self.meta["bionemo_nims"]:
            binding = e["cohorts"]["provisioned_node"]["image_binding"]
            self.assertIn(
                binding,
                ("in-file", "checkpoint-join", "cohort-receipt-doc", "none"),
                e["nim"],
            )
            if e["snapshot_class"] in SNAPSHOT_SAFE:
                self.assertNotEqual(binding, "none", e["nim"])
        by_nim = {e["nim"]: e["cohorts"]["provisioned_node"] for e in self.meta["bionemo_nims"]}
        self.assertEqual(by_nim["openfold3"]["image_binding"], "checkpoint-join")
        self.assertEqual(by_nim["proteinmpnn"]["image_binding"], "in-file")
        self.assertEqual(by_nim["molmim"]["image_binding"], "none")
        for nim in ("boltz2", "openfold2"):
            self.assertEqual(by_nim[nim]["image_binding"], "cohort-receipt-doc", nim)
            gaps = " ".join(by_nim[nim]["outstanding_evidence_gaps"])
            self.assertIn("qualification document", gaps, nim)
        b2_paths = {r["path"] for r in by_nim["boltz2"]["evidence_refs"]}
        self.assertIn("nim-fast-start/faststart-v2/boltz2-native/README.md", b2_paths)
        of2_paths = {r["path"] for r in by_nim["openfold2"]["evidence_refs"]}
        self.assertIn(
            "nim-fast-start/faststart-v2/performance/openfold2/README.md", of2_paths
        )

    def test_n20_wrong_digest_adversaries(self):
        """The reviewer's executable proof: zeroing either n20 row's catalog
        digest while leaving every cited evidence byte untouched must now
        refuse the build for BOTH lanes."""
        b = build_eligibility
        cat_by_id = {r["id"]: r for r in self.catalog["rows"]}
        for nim, prefix in (("boltz2", "faststart:boltz2@"), ("openfold2", "faststart:openfold2@")):
            row = next(v for k, v in cat_by_id.items() if k.startswith(prefix))
            refs = sorted({p["path"] for p in row["provenance"]}) + [
                "nim-fast-start/faststart-v2/" + extra
                for extra in b.SUPPLEMENTARY_EVIDENCE[nim]
            ]
            # untampered row verifies and yields the receipt-doc binding
            verified = b.verify_lane_evidence(nim, row, refs)
            self.assertEqual(verified["image_binding"], "cohort-receipt-doc", nim)
            # all-zero digest with untouched evidence must be refused
            mutated = json.loads(json.dumps(row))
            mutated["image"]["digest"] = "sha256:" + "0" * 64
            with self.assertRaises(SystemExit):
                b.verify_lane_evidence(nim, mutated, refs)
        # unit-level receipt-doc adversaries
        with open(
            os.path.join(FASTSTART_ROOT, "boltz2-native", "README.md"),
            encoding="utf-8",
        ) as fh:
            readme = fh.read()
        good_digest = (
            "sha256:0788c95c8b5b6c1a73a62c656b298ecc353a8187dc22b794f496ae40672c4c98"
        )
        b.check_n20_receipt_doc(readme, "b2-n20-v3-20260818t1532z", good_digest, "boltz2")
        with self.assertRaises(SystemExit):
            b.check_n20_receipt_doc(
                readme, "b2-n20-v3-20260818t1532z", "sha256:" + "0" * 64, "boltz2"
            )
        with self.assertRaises(SystemExit):
            b.check_n20_receipt_doc(readme, "b2-n20-other-cohort", good_digest, "boltz2")
        with self.assertRaises(SystemExit):
            b.check_n20_receipt_doc(readme, "b2-n20-v3-20260818t1532z", good_digest, "openfold2")
        with self.assertRaises(SystemExit):
            b.check_n20_receipt_doc(readme, "b2-n20-v3-20260818t1532z", "not-a-digest", "boltz2")
        # ProteinMPNN's digest-bearing results file and OpenFold3's
        # digest-join prior evidence must be cited and hash-bound.
        by_nim = {
            e["nim"]: e["cohorts"]["provisioned_node"]
            for e in self.meta["bionemo_nims"]
        }
        pm_paths = {r["path"] for r in by_nim["proteinmpnn"]["evidence_refs"]}
        self.assertIn(
            "nim-fast-start/faststart-v2/proteinmpnn-native/results.json", pm_paths
        )
        of3_paths = {r["path"] for r in by_nim["openfold3"]["evidence_refs"]}
        self.assertIn(
            "nim-fast-start/faststart-v2/openfold3-native/prior-evidence.json",
            of3_paths,
        )
        for nim in ("openfold3", "rfdiffusion"):
            gaps = " ".join(by_nim[nim]["outstanding_evidence_gaps"])
            self.assertIn("no per-trial cleanup", gaps, nim)

    def test_selected_cohort_binding_adversaries(self):
        b = build_eligibility

        def load(rel):
            with open(os.path.join(FASTSTART_ROOT, rel), encoding="utf-8") as fh:
                return json.load(fh)

        # DiffDock: selected status FAIL / semantic passes 0 must be rejected
        dd = load("diffdock-native/results.json")
        b.assert_lane_bindings("diffdock", dd)
        for mutate in (
            lambda d: d["selected_response_boundary_n3"].__setitem__("status", "FAIL"),
            lambda d: d["selected_response_boundary_n3"].__setitem__("semantic_passes", 0),
            lambda d: d["cleanup"].__setitem__("uid_preconditions_enforced", False),
            lambda d: d["cleanup"].__setitem__("active_gpu_requests_final", 1),
            lambda d: d["selected_response_boundary_n3"].__setitem__(
                "runs", ["r1", "r1", "r2"]
            ),
            # string "PASS"-shaped truthy values of the wrong type also fail
            lambda d: d["selected_response_boundary_n3"].__setitem__(
                "semantic_passes", "6"
            ),
        ):
            mutated = json.loads(json.dumps(dd))
            mutate(mutated)
            with self.assertRaises(SystemExit):
                b.assert_lane_bindings("diffdock", mutated)
        # GenMol: qualification FAIL / semantic passes 0 / cleanup false
        gm = load("genmol-native/results.json")
        b.assert_lane_bindings("genmol", gm)
        for mutate in (
            lambda d: d["response_boundary_requalification"].__setitem__("status", "FAIL"),
            lambda d: d["response_boundary_requalification"].__setitem__(
                "semantic_pass_count", 0
            ),
            lambda d: d["response_boundary_requalification"].__setitem__(
                "cleanup_commands_succeeded_after_each_trial", False
            ),
            lambda d: d["response_boundary_requalification"].__setitem__(
                "target_image_and_worker_image_resident_before_t0", False
            ),
        ):
            mutated = json.loads(json.dumps(gm))
            mutate(mutated)
            with self.assertRaises(SystemExit):
                b.assert_lane_bindings("genmol", mutated)
        # MSA: wrong digest, wrong timing contract, qualification FAIL
        msa = load("msa-search-native/results.json")
        b.assert_lane_bindings("msa-search", msa)
        image_ref = msa["nim_image"]
        self.assertTrue(image_ref.endswith(
            "sha256:944f3cf845761be8e42b33147ae08b68c61eca7cad67bf5251e1708d03c0165c"
        ))
        for mutate in (
            lambda d: d["response_boundary_requalification"].__setitem__(
                "response_timing_contract", "other/v2"
            ),
            lambda d: d["response_boundary_requalification"].__setitem__("status", "FAIL"),
            lambda d: d["conventional_cached_n3"]["target_image_residency"].__setitem__(
                "preloaded_outside_t0", False
            ),
            lambda d: d["cleanup"].__setitem__("counted_run_pods_remaining", 2),
        ):
            mutated = json.loads(json.dumps(msa))
            mutate(mutated)
            with self.assertRaises(SystemExit):
                b.assert_lane_bindings("msa-search", mutated)
        # ProteinMPNN results.json bindings and structural spec
        pm = load("proteinmpnn-native/results.json")
        b.assert_lane_bindings("proteinmpnn", pm)
        pm_spec = b.N3_SPECS["proteinmpnn"]
        pm_image = pm["image"]
        b.check_n3_results(pm, pm_spec, 10.249097, pm_image)
        mutated = json.loads(json.dumps(pm))
        mutated["metric_contract"]["response_timing_contract"] = "other/v2"
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, pm_spec, 10.249097, pm_image)
        mutated = json.loads(json.dumps(pm))
        mutated["image"] = pm_image.split("@")[0] + "@sha256:" + "0" * 64
        with self.assertRaises(SystemExit):
            b.check_n3_results(mutated, pm_spec, 10.249097, pm_image)
        mutated = json.loads(json.dumps(pm))
        mutated["selected_n3"]["semantic_pass_count"] = 0
        with self.assertRaises(SystemExit):
            b.assert_lane_bindings("proteinmpnn", mutated)
        # OpenFold3 digest join breaks
        of3 = load("openfold3-native/results.json")
        prior = load("openfold3-native/prior-evidence.json")
        of3_image = prior["execution_identity"]["image"]
        b.check_of3_digest_join(of3, prior, of3_image)
        for mutate_pair in (
            lambda r, p: r["selected"].__setitem__("checkpoint_id", "other-ckpt"),
            lambda r, p: r["selected"].__setitem__("manifest_sha256", "0" * 64),
            lambda r, p: p["checkpoint"].__setitem__("artifact_version", "2"),
            lambda r, p: p["execution_identity"].__setitem__(
                "image", of3_image.split("@")[0] + "@sha256:" + "0" * 64
            ),
            lambda r, p: p.__setitem__("status", "FAIL"),
        ):
            r2 = json.loads(json.dumps(of3))
            p2 = json.loads(json.dumps(prior))
            mutate_pair(r2, p2)
            with self.assertRaises(SystemExit):
                b.check_of3_digest_join(r2, p2, of3_image)
        with self.assertRaises(SystemExit):
            b.check_of3_digest_join(of3, prior, "wrong@sha256:" + "0" * 64)

    def test_clean_tree_offline_reconstruction(self):
        import shutil
        import subprocess
        import tempfile

        needed = [
            "performance/COLD_START_METRICS.md",
            "performance/openfold2/fresh-cohort-n20-results.tsv",
            "boltz2-native/fresh-cohort-n20-results.tsv",
            "diffdock-native/results.json",
            "genmol-native/results.json",
            "openfold3-native/results.json",
            "rfdiffusion-native/results.json",
            "msa-search-native/results.json",
            "boltz2-native/README.md",
            "performance/openfold2/README.md",
            "proteinmpnn-native/response-boundary-results.tsv",
            "proteinmpnn-native/results.json",
            "openfold3-native/prior-evidence.json",
            "evo2-native/profile.json",
            "openfold2-newnode/CURRENT_STATUS.json",
            "resource-broker/lease.schema.json",
            "performance/request_slo/event.schema.json",
            "performance/request_slo/trace.schema.json",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "nim-fast-start", "faststart-v2")
            dst = os.path.join(root, "catalog-switch", "snapshot-eligibility")
            shutil.copytree(
                ELIG_DIR, dst, ignore=shutil.ignore_patterns("__pycache__")
            )
            for rel in needed:
                src = os.path.join(FASTSTART_ROOT, rel)
                target = os.path.join(root, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy(src, target)
            os.makedirs(os.path.join(root, "molmim-native", "conventional"))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            subprocess.run(
                [sys.executable, "build_eligibility.py"],
                cwd=dst,
                check=True,
                env=env,
                capture_output=True,
            )
            for out in ("eligibility.json", "eligibility.tsv"):
                with open(os.path.join(dst, out), encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), read(out), out)

    def test_modal_is_never_an_execution_class(self):
        pruned = json.loads(read("eligibility.json"))
        pruned["meta"]["scope_notes"] = []
        self.assertNotIn("modal", json.dumps(pruned).lower())

    # -- scope and sanitization ------------------------------------------

    def test_no_modal_dependency_anywhere(self):
        # The vendored threat model is immutable reviewed bytes (SHA-pinned)
        # that survey Modal as one program backend; it is reference material,
        # not a dependency, and its Modal control (CTL-17) is separately
        # forbidden from gate bindings.
        scanned = [a for a in ARTIFACTS if not a.endswith("threat_model.json")]
        for name in scanned:
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
            leaks = [
                leak
                for leak in find_forbidden(text)
                if leak not in SANITIZER_FALSE_POSITIVES
            ]
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
    os.path.join("inputs", "threat_model.json"),
    os.path.join("schema", "eligibility.schema.json"),
]

# The vendored reviewed threat model labels an asset class
# "tenant-confidential"; that phrase pattern-matches the tenant-resource-id
# regex but is a classification label, not an identifier.
SANITIZER_FALSE_POSITIVES = frozenset(["tenant-confidential"])


if __name__ == "__main__":
    unittest.main()
