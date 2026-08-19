"""Offline validation of the committed catalog artifacts.

Covers: schema validation, deterministic rebuild, id/link invariants,
availability classification rules, pilot selection, storage arithmetic,
provenance cross-checks against this repository, and sanitization of
every publishable artifact.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest

CATALOG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FASTSTART_ROOT = os.path.dirname(CATALOG_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(FASTSTART_ROOT))
sys.path.insert(0, CATALOG_DIR)

import build_catalog  # noqa: E402
from extract_forge_source import find_forbidden  # noqa: E402


def read(name: str) -> str:
    with open(os.path.join(CATALOG_DIR, name), encoding="utf-8") as fh:
        return fh.read()


class CatalogArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(read("catalog.json"))
        cls.rows = cls.doc["rows"]
        cls.by_id = {r["id"]: r for r in cls.rows}

    def test_rebuild_is_deterministic_and_matches_committed_outputs(self):
        doc, catalog_json, catalog_tsv, report = build_catalog.build()
        self.assertEqual(catalog_json, read("catalog.json"))
        self.assertEqual(catalog_tsv, read("catalog.tsv"))
        self.assertEqual(report, read("GAP_REPORT.md"))
        doc2, catalog_json2, _, _ = build_catalog.build()
        self.assertEqual(catalog_json, catalog_json2)

    def test_schema_validates(self):
        import jsonschema

        with open(os.path.join(CATALOG_DIR, "schema", "catalog.schema.json")) as fh:
            schema = json.load(fh)
        jsonschema.validate(self.doc, schema)

    def test_ids_unique_and_counts_match(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        counts = self.doc["meta"]["row_counts"]
        self.assertEqual(counts["total"], len(self.rows))
        self.assertEqual(
            counts["unique_canonical_models"],
            len({r["canonical_key"] for r in self.rows}),
        )
        self.assertEqual(
            sum(counts["by_availability"].values()), counts["total"]
        )
        self.assertEqual(sum(counts["by_source"].values()), counts["total"])

    def test_catalog_version_matches_rows(self):
        import hashlib

        serialized = json.dumps(self.rows, sort_keys=True, ensure_ascii=False)
        expected = "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()
        self.assertEqual(self.doc["meta"]["catalog_version"], expected)

    def test_related_ids_are_symmetric_and_resolve(self):
        for row in self.rows:
            for rid in row["related_ids"]:
                self.assertIn(rid, self.by_id)
                self.assertIn(row["id"], self.by_id[rid]["related_ids"])
                self.assertEqual(
                    row["canonical_key"], self.by_id[rid]["canonical_key"]
                )

    def test_availability_classification_rules(self):
        for row in self.rows:
            avail = row["availability"]
            if avail["evidence_tier"] == "referenced-only":
                self.assertEqual(avail["class"], "hypothetical")
            elif avail["gates"]:
                self.assertEqual(avail["class"], "gated")
            elif avail["evidence_tier"] in ("measured-local", "measured-source"):
                self.assertEqual(avail["class"], "verified")
            else:
                self.assertEqual(avail["class"], "discoverable")
        evo2 = self.by_id[
            "faststart:evo2-40b@sha256:561886bab1d2d0da836ebf5bec403f9de2baf6e92deb7eedf1b316aa994b5dd2"
        ]
        self.assertEqual(evo2["availability"]["class"], "gated")
        self.assertIn(
            "hardware-h200-release-required", evo2["availability"]["gates"]
        )

    def test_verified_rows_carry_evidence(self):
        for row in self.rows:
            if row["availability"]["class"] == "verified":
                self.assertTrue(row["availability"]["evidence"])
                self.assertIn(
                    row["availability"]["evidence_tier"],
                    ("measured-local", "measured-source"),
                )

    def test_snapshot_proven_only_with_measured_local_evidence(self):
        for row in self.rows:
            if row["snapshot"]["eligibility"] == "proven":
                self.assertEqual(row["source"], "faststart-v2-lanes")
                self.assertEqual(
                    row["availability"]["evidence_tier"], "measured-local"
                )
                self.assertIsNotNone(row["startup"]["measured"])

    def test_pilots_cover_mandated_classes_and_resolve(self):
        pilots = self.doc["meta"]["pilots"]
        self.assertEqual(
            {p["pilot_class"] for p in pilots},
            {"small-snapshot-friendly", "storage-heavy", "large-or-multi-gpu"},
        )
        for pilot in pilots:
            self.assertIn(pilot["selected_id"], self.by_id)
            if pilot["alternate_id"] is not None:
                self.assertIn(pilot["alternate_id"], self.by_id)
                self.assertNotEqual(
                    self.by_id[pilot["selected_id"]]["canonical_key"],
                    self.by_id[pilot["alternate_id"]]["canonical_key"],
                )
        small = self.by_id[
            next(p for p in pilots if p["pilot_class"] == "small-snapshot-friendly")[
                "selected_id"
            ]
        ]
        heavy = self.by_id[
            next(p for p in pilots if p["pilot_class"] == "storage-heavy")[
                "selected_id"
            ]
        ]
        pool = [
            r
            for r in self.rows
            if r["availability"]["class"] == "verified"
            and r["snapshot"]["eligibility"] == "proven"
            and r["storage"]["local_bytes_known"] > 0
        ]
        self.assertEqual(
            small["storage"]["local_bytes_known"],
            min(r["storage"]["local_bytes_known"] for r in pool),
        )
        self.assertEqual(
            heavy["storage"]["local_bytes_known"],
            max(r["storage"]["local_bytes_known"] for r in pool),
        )

    def test_storage_arithmetic(self):
        feas = self.doc["meta"]["storage_feasibility"]
        self.assertEqual(
            feas["known_local_bytes_total"],
            sum(r["storage"]["local_bytes_known"] for r in self.rows),
        )
        self.assertLessEqual(
            feas["estimated_total_bytes_low"], feas["estimated_total_bytes_high"]
        )
        self.assertEqual(
            feas["rows_fully_sized"]
            + feas["rows_partially_sized"]
            + feas["rows_unsized"],
            len(self.rows),
        )
        for row in self.rows:
            expected = sum(
                v
                for v in (
                    row["image"]["size_bytes"],
                    row["artifact"]["size_bytes"],
                    row["artifact"]["cache_bytes"],
                )
                if v
            )
            self.assertEqual(row["storage"]["local_bytes_known"], expected)

    def test_tsv_shape_matches_rows(self):
        lines = read("catalog.tsv").rstrip("\n").split("\n")
        self.assertEqual(len(lines), len(self.rows) + 1)
        header = lines[0].split("\t")
        self.assertEqual(header, build_catalog.TSV_COLUMNS)
        for line in lines[1:]:
            self.assertEqual(len(line.split("\t")), len(header))

    def test_taxonomy_sums_to_total(self):
        taxonomy = self.doc["meta"]["family_taxonomy"]
        self.assertEqual(
            sum(t["row_count"] for t in taxonomy), len(self.rows)
        )


class ProvenanceCrossChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(read("catalog.json"))
        cls.rows = cls.doc["rows"]

    def test_faststart_digests_and_validators_exist_in_repo(self):
        for row in self.rows:
            if row["source"] != "faststart-v2-lanes":
                continue
            validator = row["fixtures"]["validator_path"]
            self.assertTrue(
                os.path.exists(os.path.join(REPO_ROOT, validator)),
                validator,
            )
            digest = row["image"]["digest"]
            found = False
            for base, _dirs, files in os.walk(FASTSTART_ROOT):
                if os.path.commonpath([base, CATALOG_DIR]) == CATALOG_DIR:
                    continue
                for name in files:
                    if not name.endswith((".yaml", ".tmpl", ".json", ".py", ".sh", ".md")):
                        continue
                    path = os.path.join(base, name)
                    try:
                        with open(path, encoding="utf-8", errors="ignore") as fh:
                            if digest in fh.read():
                                found = True
                                break
                    except OSError:
                        continue
                if found:
                    break
            self.assertTrue(found, f"digest for {row['id']} not found in lanes")

    def test_nims_rows_match_terraform_catalog(self):
        catalog_tf = os.path.join(REPO_ROOT, "modules", "nims", "catalog.tf")
        with open(catalog_tf, encoding="utf-8") as fh:
            tf = fh.read()
        for row in self.rows:
            if row["source"] != "nims-terraform-catalog":
                continue
            self.assertIn(row["image"]["upstream_ref"], tf, row["id"])
            self.assertIn(f'"{row["version_id"]}"', tf, row["id"])

    def test_forge_source_meta_is_pinned(self):
        forge = json.loads(read(os.path.join("sources", "forge-models.json")))
        meta = forge["meta"]
        self.assertRegex(meta["provenance"]["commit"], r"^[0-9a-f]{40}$")
        self.assertFalse(meta["provenance"]["manifests_dirty"])
        self.assertEqual(meta["manifest_count"], len(forge["models"]))
        forge_rows = [r for r in self.rows if r["source"] == "forge-manifests"]
        self.assertEqual(len(forge_rows), len(forge["models"]))
        for row in forge_rows:
            self.assertEqual(
                row["provenance"][0]["ref"], meta["provenance"]["commit"]
            )

    def test_documented_candidate_paths_exist(self):
        for row in self.rows:
            if row["source"] != "documented-candidates":
                continue
            for prov in row["provenance"]:
                self.assertTrue(
                    os.path.exists(os.path.join(REPO_ROOT, prov["path"])),
                    prov["path"],
                )


class Sanitization(unittest.TestCase):
    ARTIFACTS = [
        "catalog.json",
        "catalog.tsv",
        "GAP_REPORT.md",
        "README.md",
        os.path.join("sources", "forge-models.json"),
        os.path.join("sources", "faststart-lanes.json"),
        os.path.join("sources", "nims-terraform.json"),
        os.path.join("sources", "documented-candidates.json"),
    ]

    def test_no_credentials_or_private_identifiers(self):
        for name in self.ARTIFACTS:
            text = read(name)
            leaks = find_forbidden(text)
            self.assertEqual(leaks, [], f"{name}: {sorted(set(leaks))[:10]}")
            self.assertNotIn("/home/", text, name)
            self.assertNotIn("nvapi-", text, name)

    def test_no_kubeconfig_or_cluster_identifiers(self):
        pattern = re.compile(
            r"mk8s[a-z]*-[a-z0-9]{6,}|BEGIN (RSA|OPENSSH|EC) PRIVATE"
        )
        for name in self.ARTIFACTS:
            self.assertIsNone(pattern.search(read(name)), name)


if __name__ == "__main__":
    unittest.main()
