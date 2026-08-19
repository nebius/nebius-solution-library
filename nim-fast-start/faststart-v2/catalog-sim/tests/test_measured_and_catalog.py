from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.catalog import PLACEHOLDERS, build_catalog  # noqa: E402
from catalog_sim.measured import load_anchors, load_n20_dists  # noqa: E402
from catalog_sim.units import micros_to_seconds  # noqa: E402


class MeasuredCalibrationTest(unittest.TestCase):
    """The loaded measured inputs must reproduce the published aggregates."""

    def test_openfold2_n20_matches_published_percentiles(self):
        dists = load_n20_dists("openfold2")
        self.assertEqual(len(dists["ready"].samples_micros), 20)
        # Published: BOOTTIME upper T0->HTTP ready p50/p95/max
        self.assertEqual(micros_to_seconds(dists["ready"].percentile(50)), 14.342258)
        self.assertEqual(micros_to_seconds(dists["ready"].percentile(95)), 14.671991)
        self.assertEqual(
            micros_to_seconds(max(dists["ready"].samples_micros)), 15.099141
        )
        # Published call 1 / call 2 p50
        self.assertEqual(micros_to_seconds(dists["call1"].percentile(50)), 1.938516)
        self.assertEqual(micros_to_seconds(dists["call2"].percentile(50)), 1.015083)

    def test_boltz2_n20_matches_published_percentiles(self):
        dists = load_n20_dists("boltz2")
        self.assertEqual(micros_to_seconds(dists["ready"].percentile(50)), 27.070530)
        self.assertEqual(micros_to_seconds(dists["ready"].percentile(95)), 28.429408)
        self.assertEqual(
            micros_to_seconds(max(dists["ready"].samples_micros)), 29.095697
        )

    def test_n3_lanes_match_published_medians(self):
        anchors = load_anchors()
        published_ready_medians = {
            "proteinmpnn": 9.460347,
            "diffdock": 12.127239,
            "openfold3": 12.271182,
            "msa-search": 4.872400,
            "genmol": 10.400351,
            "rfdiffusion": 17.662044,
            "molmim": 10.520799,
        }
        for name, median in published_ready_medians.items():
            self.assertEqual(
                micros_to_seconds(anchors[name].ready_dist.median_micros()),
                median,
                name,
            )
            self.assertEqual(len(anchors[name].ready_dist.samples_micros), 3, name)

    def test_every_anchor_has_provenance_and_source(self):
        anchors = load_anchors()
        self.assertEqual(len(anchors), 10)
        for name, anchor in anchors.items():
            for dist in (anchor.ready_dist, anchor.call1_dist, anchor.call2_dist):
                self.assertEqual(dist.provenance, "measured", name)
                self.assertTrue(dist.source.strip(), name)
            self.assertGreater(anchor.artifact_bytes.value, 0, name)
        self.assertIn("manual/provisional", anchors["evo2-40b"].evidence_class)
        self.assertEqual(anchors["msa-search"].strategy, "conventional")


class CatalogTest(unittest.TestCase):
    def test_catalog_size_and_provenance_split(self):
        catalog, _ = build_catalog(200, "base")
        self.assertEqual(len(catalog), 200)
        measured = [m for m in catalog.values() if m.provenance == "measured"]
        placeholder = [
            m for m in catalog.values() if m.provenance == "placeholder-scaled"
        ]
        self.assertEqual(len(measured), 10)
        self.assertEqual(len(placeholder), 190)
        for model in placeholder:
            self.assertEqual(model.ready_dist.provenance, "placeholder", model.model_id)
            self.assertIn("placeholder", model.evidence_class)
        for model in measured:
            self.assertEqual(model.ready_dist.provenance, "measured", model.model_id)
            self.assertEqual(model.scale, 1.0)

    def test_catalog_deterministic(self):
        c1, _ = build_catalog(200, "base")
        c2, _ = build_catalog(200, "base")
        self.assertEqual(sorted(c1), sorted(c2))
        for mid in c1:
            self.assertEqual(c1[mid].scale, c2[mid].scale, mid)
            self.assertEqual(
                c1[mid].ready_dist.samples_micros, c2[mid].ready_dist.samples_micros
            )

    def test_scales_within_declared_bounds(self):
        for level in ("low", "base", "high"):
            catalog, _ = build_catalog(200, level)
            lo = PLACEHOLDERS["synthetic_scale_min"].at(level)
            hi = PLACEHOLDERS["synthetic_scale_max"].at(level)
            for model in catalog.values():
                if model.provenance == "placeholder-scaled":
                    self.assertGreaterEqual(model.scale, lo, model.model_id)
                    self.assertLessEqual(model.scale, hi, model.model_id)

    def test_all_placeholders_declare_sensitivity(self):
        for name, q in PLACEHOLDERS.items():
            self.assertLess(q.at("low"), q.at("high"), name)
            self.assertTrue(q.rationale.strip(), name)

    def test_groups_are_pipelines_of_four(self):
        catalog, _ = build_catalog(200, "base")
        groups = {}
        for model in catalog.values():
            groups.setdefault(model.group, []).append(model.model_id)
        for group, members in groups.items():
            self.assertEqual(len(members), 4, group)


if __name__ == "__main__":
    unittest.main()
