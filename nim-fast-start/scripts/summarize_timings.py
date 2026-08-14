#!/usr/bin/env python3

import csv
import math
import statistics
import sys


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} CSV FIELD [FIELD ...]", file=sys.stderr)
        return 2

    with open(sys.argv[1], newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))

    print("metric,count,p50,p95,min,max")
    for field in sys.argv[2:]:
        values = [float(row[field]) for row in rows if row.get(field)]
        if not values:
            print(f"{field},0,,,,")
            continue
        print(
            f"{field},{len(values)},{statistics.median(values):.3f},"
            f"{percentile(values, 0.95):.3f},{min(values):.3f},{max(values):.3f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
