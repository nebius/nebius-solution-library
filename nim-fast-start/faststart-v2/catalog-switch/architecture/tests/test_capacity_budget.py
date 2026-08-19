from __future__ import annotations

import importlib.util
import math
import unittest
from pathlib import Path


ARCH_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capacity_budget", ARCH_DIR / "capacity_budget.py")
assert SPEC and SPEC.loader
CAPACITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPACITY)


class CapacityBudgetTests(unittest.TestCase):
    def test_zero_demand_retains_one_base_slot(self) -> None:
        self.assertEqual(1, CAPACITY.required_slots(0.0, 0.0, 0))

    def test_closed_form_with_failover(self) -> None:
        self.assertEqual(17, CAPACITY.required_slots(0.5, 20.0, 2))

    def test_rounds_up(self) -> None:
        self.assertEqual(2, CAPACITY.required_slots(0.071, 10.0, 0))

    def test_invalid_values_fail_closed(self) -> None:
        for arrival, occupancy, failover in (
            (-1.0, 1.0, 0),
            (1.0, -1.0, 0),
            (math.inf, 1.0, 0),
            (1.0, math.nan, 0),
            (1.0, 1.0, -1),
            (1.0, 1.0, 1.5),
        ):
            with self.subTest(arrival=arrival, occupancy=occupancy, failover=failover):
                with self.assertRaises(ValueError):
                    CAPACITY.required_slots(arrival, occupancy, failover)


if __name__ == "__main__":
    unittest.main()
