from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.schema import (  # noqa: E402
    EmpiricalDist,
    MeasuredQuantity,
    PlaceholderQuantity,
    SchemaError,
    require_schema_version,
)
from catalog_sim.units import (  # noqa: E402
    UnitError,
    gib_to_bytes,
    micros_to_seconds,
    seconds_to_micros,
    transfer_micros,
)


class UnitsTest(unittest.TestCase):
    def test_round_trip_exact(self):
        self.assertEqual(seconds_to_micros(17.629887), 17_629_887)
        self.assertEqual(micros_to_seconds(17_629_887), 17.629887)

    def test_negative_and_nonfinite_rejected(self):
        for bad in (-1.0, float("nan"), float("inf")):
            with self.assertRaises(UnitError):
                seconds_to_micros(bad)
        with self.assertRaises(UnitError):
            micros_to_seconds(-1)
        with self.assertRaises(UnitError):
            micros_to_seconds(1.5)  # type: ignore[arg-type]

    def test_gib(self):
        self.assertEqual(gib_to_bytes(1), 1024**3)

    def test_transfer_ceiling(self):
        # 10 bytes at 3 B/s -> ceil(10/3 s) in micros = 3333334
        self.assertEqual(transfer_micros(10, 3), 3_333_334)
        self.assertEqual(transfer_micros(0, 100), 0)
        with self.assertRaises(UnitError):
            transfer_micros(10, 0)


class SchemaTest(unittest.TestCase):
    def test_measured_requires_source(self):
        with self.assertRaises(SchemaError):
            MeasuredQuantity("x", 1.0, "seconds", "  ")

    def test_placeholder_requires_bounded_range(self):
        with self.assertRaises(SchemaError):
            PlaceholderQuantity("x", 2.0, 1.0, 3.0, "s", "why")
        with self.assertRaises(SchemaError):
            PlaceholderQuantity("x", 1.0, 1.0, 1.0, "s", "why")
        with self.assertRaises(SchemaError):
            PlaceholderQuantity("x", 1.0, 2.0, 3.0, "s", " ")
        q = PlaceholderQuantity("x", 1.0, 2.0, 3.0, "s", "why")
        self.assertEqual(q.at("low"), 1.0)
        self.assertEqual(q.at("high"), 3.0)
        with self.assertRaises(SchemaError):
            q.at("medium")

    def test_empirical_nearest_rank(self):
        d = EmpiricalDist.from_seconds("d", [1.0, 2.0, 3.0, 4.0], "src")
        # nearest-rank: p50 of 4 -> rank 2; p95 -> rank 4
        self.assertEqual(d.percentile(50), 2_000_000)
        self.assertEqual(d.percentile(95), 4_000_000)
        self.assertEqual(d.percentile(100), 4_000_000)

    def test_scaled_is_placeholder(self):
        base = EmpiricalDist.from_seconds("d", [1.0, 2.0], "src")
        self.assertEqual(base.provenance, "measured")
        scaled = EmpiricalDist.scaled(base, 1.5, "d2")
        self.assertEqual(scaled.provenance, "placeholder")
        self.assertEqual(scaled.samples_micros, (1_500_000, 3_000_000))
        self.assertIn("placeholder factor", scaled.source)

    def test_empirical_rejects_bad_samples(self):
        with self.assertRaises(SchemaError):
            EmpiricalDist.from_seconds("d", [], "src")
        with self.assertRaises(SchemaError):
            EmpiricalDist.from_seconds("d", [-1.0], "src")

    def test_schema_version_gate(self):
        require_schema_version({"schema_version": "1.0.0"}, "ok")
        with self.assertRaises(SchemaError):
            require_schema_version({"schema_version": "0.9.0"}, "bad")


if __name__ == "__main__":
    unittest.main()
