import importlib.util
import json
import unittest
from pathlib import Path

CC = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "run_sweeps", CC / "costmodel" / "run_sweeps.py")
run_sweeps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_sweeps)


class SweepsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((CC / "results" / "sweeps.json").read_text())

    def test_axes_and_grids(self):
        self.assertEqual(self.doc["scenario"]["k_grid"], [1, 2, 4, 8, 16])
        self.assertEqual(self.doc["scenario"]["cache_gib_grid"],
                         [150, 200, 400, 800, 1600])
        self.assertEqual(len(self.doc["k_sweep"]), 25)
        self.assertEqual(len(self.doc["cache_sweep"]), 25)
        for rep in self.doc["k_sweep"]:
            self.assertEqual(rep["sweep_axis"], "warm_top_k")
            self.assertIn("placeholder", rep["input_provenance"])
        for rep in self.doc["cache_sweep"]:
            self.assertEqual(rep["sweep_axis"], "l1_capacity_gib")

    def test_isolation_k_sweep_shares_everything_but_k(self):
        """Every K point uses the same trace and the same policy family;
        only the warm-K suffix of the policy label differs."""
        by_family = {}
        for rep in self.doc["k_sweep"]:
            by_family.setdefault(rep["trace_family"], []).append(rep)
        for family, reps in by_family.items():
            checksums = {r["trace_checksum"] for r in reps}
            self.assertEqual(len(checksums), 1, family)
            bases = {r["policy"].rsplit("-k", 1)[0] for r in reps}
            self.assertEqual(
                bases,
                {"snapshot+shortest-switch-cost+lru+topk-adaptive"}, family)
            ks = sorted(int(r["policy"].rsplit("-k", 1)[1]) for r in reps)
            self.assertEqual(ks, [1, 2, 4, 8, 16], family)

    def test_isolation_cache_sweep_shares_everything_but_capacity(self):
        by_family = {}
        for rep in self.doc["cache_sweep"]:
            by_family.setdefault(rep["trace_family"], []).append(rep)
        for family, reps in by_family.items():
            self.assertEqual({r["trace_checksum"] for r in reps} and
                             len({r["trace_checksum"] for r in reps}), 1)
            self.assertEqual({r["policy"] for r in reps},
                             {"snapshot+shortest-switch-cost+lru"}, family)
            self.assertEqual(sorted(r["sweep_value"] for r in reps),
                             [150, 200, 400, 800, 1600], family)

    def test_trace_checksums_match_committed_simulator_traces(self):
        committed = json.loads(
            (CC.parent.parent / "catalog-sim/traces/CHECKSUMS.json")
            .read_text())["sha256"]
        self.assertEqual(self.doc["trace_checksums"], committed)

    def test_single_point_regenerates_identically(self):
        """Deterministic regeneration: recompute one sweep point live and
        compare to the committed report (full-run identity follows from the
        engine's determinism plus the shared scenario constants)."""
        catalog, traces = run_sweeps.build_scenario()
        base_fleet = run_sweeps.fleet_parameters("base")
        config = run_sweeps.PolicyConfig(
            strategy="snapshot", placement="shortest-switch-cost",
            eviction="lru", warm="topk-adaptive", warm_k=8)
        fresh = run_sweeps.run_point(
            catalog, traces["zipf"], config, dict(base_fleet),
            "warm_top_k", 8)
        committed = next(
            r for r in self.doc["k_sweep"]
            if r["trace_family"] == "zipf" and r["sweep_value"] == 8)
        self.assertEqual(json.dumps(fresh, sort_keys=True),
                         json.dumps(committed, sort_keys=True))

    def test_cache_floor_documented_reason(self):
        # The floor exists because the largest base-catalog artifact must fit.
        src = (CC / "costmodel" / "run_sweeps.py").read_text()
        self.assertIn("143.19", src)
        self.assertGreaterEqual(min(self.doc["scenario"]["cache_gib_grid"]),
                                144)


if __name__ == "__main__":
    unittest.main()
