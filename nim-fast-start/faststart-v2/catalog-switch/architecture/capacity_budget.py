#!/usr/bin/env python3
"""Evaluate the provisional v1 warm-capacity formula."""

from __future__ import annotations

import argparse
import json
import math


FORMULA_VERSION = "catalog-switch-capacity-formula/v1"
UTILIZATION_TARGET = 0.70


def required_slots(
    arrival_rate_p95_per_second: float,
    occupancy_p95_seconds: float,
    preemptible_failover_slots: int,
) -> int:
    values = (arrival_rate_p95_per_second, occupancy_p95_seconds)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("arrival rate and occupancy must be finite and non-negative")
    if isinstance(preemptible_failover_slots, bool) or preemptible_failover_slots < 0:
        raise ValueError("preemptible failover slots must be a non-negative integer")
    if int(preemptible_failover_slots) != preemptible_failover_slots:
        raise ValueError("preemptible failover slots must be a non-negative integer")
    base_slots = max(
        1,
        math.ceil(
            arrival_rate_p95_per_second
            * occupancy_p95_seconds
            / UTILIZATION_TARGET
        ),
    )
    return base_slots + int(preemptible_failover_slots)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arrival-rate-p95", type=float, required=True)
    parser.add_argument("--occupancy-p95", type=float, required=True)
    parser.add_argument("--preemptible-failover-slots", type=int, default=0)
    args = parser.parse_args()
    slots = required_slots(
        args.arrival_rate_p95,
        args.occupancy_p95,
        args.preemptible_failover_slots,
    )
    print(
        json.dumps(
            {
                "formula_version": FORMULA_VERSION,
                "utilization_target": UTILIZATION_TARGET,
                "arrival_rate_p95_per_second": args.arrival_rate_p95,
                "occupancy_p95_seconds": args.occupancy_p95,
                "preemptible_failover_slots": args.preemptible_failover_slots,
                "required_slots": slots,
                "status": "provisional-until-cost-model",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
