from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.adapters import (  # noqa: E402
    apply_fleet_overrides,
    apply_model_overrides,
)
from catalog_sim.catalog import build_catalog, fleet_parameters  # noqa: E402
from catalog_sim.engine import Simulator  # noqa: E402
from catalog_sim.policies import PolicyConfig  # noqa: E402
from catalog_sim.schema import SchemaError  # noqa: E402
from catalog_sim.traces import Trace  # noqa: E402


def override_doc(model_id: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "kind": "measured-overrides",
        "models": {
            model_id: {
                "source": "future harness cohort fixture",
                "evidence_class": "fresh fail-closed n=20",
                "strategy_default": "snapshot",
                "ready_seconds": [8.0, 8.5, 9.0],
                "call1_seconds": [1.0, 1.1, 1.2],
                "call2_seconds": [0.5, 0.5, 0.6],
                "artifact_bytes": 5_000_000_000,
                "artifact_digest": "sha256-measured-v2",
                "local_full_read_seconds": 4.0,
            }
        },
        "fleet": {
            "l2_fetch_bytes_per_s": {
                "value": 2_000_000_000,
                "source": "future storage-cache-matrix measurement",
            }
        },
    }


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.catalog, _ = build_catalog(20, "base")
        self.placeholder_id = sorted(
            m for m, c in self.catalog.items()
            if c.provenance == "placeholder-scaled"
        )[0]

    def test_override_promotes_placeholder_to_measured(self):
        doc = override_doc(self.placeholder_id)
        updated, replaced = apply_model_overrides(self.catalog, doc)
        self.assertEqual(replaced, [self.placeholder_id])
        model = updated[self.placeholder_id]
        self.assertEqual(model.provenance, "measured")
        self.assertEqual(model.ready_dist.provenance, "measured")
        self.assertEqual(model.artifact_digest, "sha256-measured-v2")
        self.assertEqual(model.ready_dist.median_micros(), 8_500_000)
        # Untouched models keep their original provenance.
        others = [m for m in updated if m != self.placeholder_id]
        self.assertEqual(
            {updated[m].provenance for m in others} - {"measured"},
            {"placeholder-scaled"},
        )
        # The original catalog is not mutated.
        self.assertEqual(
            self.catalog[self.placeholder_id].provenance, "placeholder-scaled"
        )

    def test_engine_semantics_unchanged_by_adapter(self):
        """An adapted catalog runs through the identical engine code path."""
        doc = override_doc(self.placeholder_id)
        updated, _ = apply_model_overrides(self.catalog, doc)
        fleet, replaced = apply_fleet_overrides(fleet_parameters("base"), doc)
        self.assertEqual(replaced, ["l2_fetch_bytes_per_s"])
        trace = Trace(
            name="adapter-toy",
            family="uniform",
            seed=0,
            horizon_micros=600_000_000,
            requests=((0, self.placeholder_id), (300_000_000, self.placeholder_id)),
        )
        sim = Simulator(
            catalog=updated,
            trace=trace,
            config=PolicyConfig(),
            fleet=fleet,
            n_nodes=1,
            seed=1,
            enable_failures=False,
        )
        report = sim.run()
        self.assertEqual(report["n_completed"], 2)
        # Second hit is warm L0; first is a cold L2 miss using measured dists:
        # fetch 5e9 B at 2e9 B/s = 2.5 s exactly.
        self.assertEqual(sim.completed[0].phases["fetch"], 2_500_000)

    def test_unknown_model_rejected(self):
        doc = override_doc("m999-ghost")
        with self.assertRaises(SchemaError):
            apply_model_overrides(self.catalog, doc)

    def test_missing_source_rejected(self):
        doc = override_doc(self.placeholder_id)
        doc["models"][self.placeholder_id]["source"] = " "
        with self.assertRaises(SchemaError):
            apply_model_overrides(self.catalog, doc)

    def test_bad_fleet_key_rejected(self):
        doc = override_doc(self.placeholder_id)
        doc["fleet"] = {"warp_speed": {"value": 1, "source": "x"}}
        with self.assertRaises(SchemaError):
            apply_fleet_overrides(fleet_parameters("base"), doc)


if __name__ == "__main__":
    unittest.main()
