"""Capacity/cost model core for the catalog fast-switch program.

Fail-closed rules:

- every measured file named in ``inputs/measured_inputs.json`` must match its
  pinned SHA-256 or loading aborts;
- a backend listed in ``unmeasured_backends`` never receives a latency value,
  a per-request cost, or an empirical rank — its frontier row carries only its
  dated unit prices and a status;
- all money math is ``decimal.Decimal`` on the exact quoted strings; binary
  floats never enter a USD value (measured seconds stay as Decimal built from
  the TSV strings);
- cost is always emitted next to the latency/goodput of the same evidence,
  never alone.
"""
from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

CENT6 = Decimal("0.000001")
SECONDS_PER_HOUR = Decimal("3600")


class InputError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Inputs:
    """Validated bundle of price, capacity, and measured inputs."""

    def __init__(self, root: Path):
        # root is the faststart-v2 directory.
        self.root = Path(root)
        base = self.root / "catalog-switch" / "capacity-cost" / "inputs"
        self.price = json.loads((base / "price_snapshot.json").read_text())
        self.capacity = json.loads(
            (base / "capacity_snapshot.json").read_text())
        self.measured = json.loads(
            (base / "measured_inputs.json").read_text())
        for doc, expect in (
            (self.price, "capacity-cost-price-snapshot/v1"),
            (self.capacity, "capacity-cost-capacity-snapshot/v1"),
            (self.measured, "capacity-cost-measured-inputs/v2"),
        ):
            if doc.get("schema_version") != expect:
                raise InputError(f"schema mismatch: want {expect}")
        self._price_by_id = {}
        for rec in self.price["records"]:
            rid = rec["record_id"]
            if rid in self._price_by_id:
                raise InputError(f"duplicate price record {rid}")
            self._price_by_id[rid] = rec
        self._verify_measured_files()

    def _verify_measured_files(self) -> None:
        entries = (list(self.measured["measured"])
                   + list(self.measured.get("simulation", [])))
        for entry in entries:
            path = self.root / entry["file"]
            if not path.is_file():
                raise InputError(f"pinned file missing: {entry['file']}")
            actual = sha256_file(path)
            if actual != entry["sha256"]:
                raise InputError(
                    f"checksum drift for {entry['file']}: {actual}")

    # ---- price access -------------------------------------------------
    def price_record(self, record_id: str) -> dict:
        try:
            return self._price_by_id[record_id]
        except KeyError:
            raise InputError(f"no price record {record_id}") from None

    def unit_price(self, record_id: str) -> Decimal:
        return Decimal(self.price_record(record_id)["unit_price"])

    def monthly_price(self, record_id: str) -> Decimal:
        rec = self.price_record(record_id)
        if rec["monthly_price"] is None:
            raise InputError(f"{record_id} has no monthly price")
        return Decimal(rec["monthly_price"])

    def assumption(self, name: str):
        for a in self.measured["assumptions"]:
            if a["name"] == name:
                return a["value"]
        raise InputError(f"no assumption {name}")

    def measured_entry(self, entry_id: str) -> dict:
        for entry in self.measured["measured"]:
            if entry["id"] == entry_id:
                return entry
        raise InputError(f"no measured entry {entry_id}")

    def simulation_entry(self, entry_id: str) -> dict:
        for entry in self.measured.get("simulation", []):
            if entry["id"] == entry_id:
                return entry
        raise InputError(f"no simulation entry {entry_id}")

    def unmeasured_cost_class(self, cost_class: str, model: str) -> dict:
        for entry in self.measured.get("unmeasured_cost_classes", []):
            if entry["cost_class"] == cost_class and entry["model"] in (
                    model, "all"):
                return entry
        raise InputError(
            f"cost class {cost_class}/{model} is not declared unmeasured")

    def unmeasured(self, backend: str) -> dict:
        for entry in self.measured["unmeasured_backends"]:
            if entry["backend"] == backend:
                return entry
        raise InputError(f"backend {backend} is not declared unmeasured")

    # ---- capacity access ----------------------------------------------
    def availability_rows(self, region: str, platform: str,
                          gpu_count: int) -> list[dict]:
        """All per-fabric capacity rows for one region/platform/GPU count."""
        rows = [row for row in self.capacity["rows"]
                if (row["region"] == region and row["platform"] == platform
                    and row["gpu_count"] == gpu_count)]
        if not rows:
            raise InputError(
                f"no capacity row for {region}/{platform}/{gpu_count}gpu")
        return sorted(rows, key=lambda r: r["fabric"])


# ---- cohort parsing -----------------------------------------------------

def load_cohort_seconds(inputs: Inputs, entry_id: str,
                        metric: str | None = None) -> list[Decimal]:
    """Return the per-run metric values of an n=20 cohort as Decimals."""
    entry = inputs.measured_entry(entry_id)
    if metric is None:
        metric = entry["metric"]
    elif metric not in (entry["metric"], entry.get("warm_hit_metric")):
        raise InputError(f"{entry_id}: metric {metric} is not declared")
    values: list[Decimal] = []
    with open(inputs.root / entry["file"], newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["record_type"] != "sample":
                continue
            if row["failed_attempt_denominator"] != entry[
                    "failed_attempt_denominator"]:
                raise InputError(
                    f"{entry_id}: denominator drift in row {row['record']}")
            values.append(Decimal(row[metric]))
    if len(values) != entry["n"]:
        raise InputError(
            f"{entry_id}: expected n={entry['n']}, found {len(values)}")
    return values


def nearest_rank(sorted_values: list[Decimal], pct: int) -> Decimal:
    if not sorted_values:
        raise InputError("empty sample")
    n = len(sorted_values)
    rank = -(-pct * n // 100)  # ceil(pct*n/100)
    return sorted_values[rank - 1]


def goodput_within(values: list[Decimal], threshold_s: Decimal) -> Decimal:
    ok = sum(1 for v in values if v <= threshold_s)
    return (Decimal(ok) / Decimal(len(values))).quantize(Decimal("0.0001"))


# ---- cost primitives ----------------------------------------------------

def gpu_seconds_cost_exact(seconds: Decimal, hourly_usd: Decimal) -> Decimal:
    """Unrounded (28-significant-digit context) GPU-seconds cost.

    Use this inside composite computations (sums, amortizations, monthly
    scaling) and quantize exactly once at emission, so intermediate rounding
    never drifts into totals."""
    return seconds * hourly_usd / SECONDS_PER_HOUR


def gpu_seconds_cost(seconds: Decimal, hourly_usd: Decimal) -> Decimal:
    return gpu_seconds_cost_exact(seconds, hourly_usd).quantize(CENT6)


def retry_multiplier(failure_probability: Decimal) -> Decimal:
    if not Decimal(0) <= failure_probability < Decimal(1):
        raise InputError("failure probability must be in [0, 1)")
    return Decimal(1) / (Decimal(1) - failure_probability)


def preemption_breakeven(pre_hourly: Decimal, od_hourly: Decimal) -> Decimal:
    """Per-attempt loss probability where preemptible expected cost per
    success equals on-demand (identical attempt duration both sides)."""
    return (Decimal(1) - pre_hourly / od_hourly).quantize(Decimal("0.00000001"))


def expected_cost_per_success(attempt_cost: Decimal,
                              loss_probability: Decimal) -> Decimal:
    return (attempt_cost * retry_multiplier(loss_probability)).quantize(CENT6)


def preemptible_expected_cost_exact(attempt_seconds: Decimal,
                                    pre_hourly: Decimal,
                                    loss_probability: Decimal) -> Decimal:
    """Unrounded preemptible-only expected cost per success (attempt cost x
    geometric retry multiplier). Strategy comparisons MUST use this exact
    value: near the break-even probability the three strategies differ only
    below the display precision, so selecting after quantization picks the
    wrong strategy."""
    return (gpu_seconds_cost_exact(attempt_seconds, pre_hourly)
            * retry_multiplier(loss_probability))


def preemptible_expected_cost(attempt_seconds: Decimal, pre_hourly: Decimal,
                              loss_probability: Decimal) -> Decimal:
    return preemptible_expected_cost_exact(
        attempt_seconds, pre_hourly, loss_probability).quantize(CENT6)


def fallback_blend_cost(attempt_seconds: Decimal, pre_hourly: Decimal,
                        od_hourly: Decimal, loss_probability: Decimal) -> Decimal:
    """Expected cost per success for 'one preemptible attempt, then on-demand'.

    The first attempt always pays the preemptible rate; with probability p it
    is lost and one on-demand attempt (assumed loss-free per the
    on_demand_loss_negligible assumption) completes the request. This blend
    is cheaper than on-demand only below the platform break-even loss
    probability p* = 1 - pre/od; above p* on-demand-only wins on cost, and
    the blend's value is bounding latency to at most one extra attempt.
    Exact arithmetic inside, one final quantization.
    """
    return fallback_blend_cost_exact(
        attempt_seconds, pre_hourly, od_hourly, loss_probability
    ).quantize(CENT6)


def fallback_blend_cost_exact(attempt_seconds: Decimal, pre_hourly: Decimal,
                              od_hourly: Decimal,
                              loss_probability: Decimal) -> Decimal:
    """Unrounded pre-then-on-demand blend; see fallback_blend_cost."""
    pre_cost = gpu_seconds_cost_exact(attempt_seconds, pre_hourly)
    od_cost = gpu_seconds_cost_exact(attempt_seconds, od_hourly)
    return pre_cost + loss_probability * od_cost


def bytes_to_gib_exact(byte_count) -> Decimal:
    """Unrounded GiB for a byte count. Traffic arithmetic (reuse division,
    egress multiplication, monthly scaling) must consume this exact value;
    a display-quantized GiB propagates its rounding into every product."""
    return Decimal(byte_count) / (Decimal(2) ** 30)


def warm_breakeven_requests_per_month(warm_gpu_month_usd: Decimal,
                                      per_switch_usd_exact: Decimal) -> Decimal:
    """Monthly demand above which one dedicated warm GPU is cheaper than
    paying a full switch on every request (worst-case switch bound).

    ``per_switch_usd_exact`` must be the UNROUNDED per-switch cost
    (gpu_seconds_cost_exact); only this final quotient is quantized. A
    display-rounded intermediate shifts the published break-even by up to
    ~1.5 requests/month at these magnitudes."""
    if per_switch_usd_exact <= 0:
        raise InputError("per-switch cost must be positive")
    return (warm_gpu_month_usd / per_switch_usd_exact).quantize(
        Decimal("0.01"))


def storage_breakeven_refetches_per_gib_month(
        sfs_gib_month: Decimal, object_gib_month: Decimal,
        egress_per_gib: Decimal) -> Decimal:
    """Object-store refetches per GiB per month above which keeping the GiB
    on SFS is cheaper than object storage plus billed egress refetches."""
    if egress_per_gib <= 0:
        raise InputError("egress price must be positive")
    return ((sfs_gib_month - object_gib_month) / egress_per_gib).quantize(
        Decimal("0.0001"))


# ---- simulator repricing -------------------------------------------------

def reprice_simulator_report(report: dict, gpu_hourly: dict,
                             egress_per_gib: Decimal) -> dict:
    """Re-price one catalog-sim report with sourced prices.

    ``gpu_hourly`` maps offer class ('on_demand'/'preemptible') to Decimal
    hourly USD. The simulator's placeholder cost_usd is ignored entirely.
    """
    reserved_h = Decimal(str(report["gpu"]["reserved_gpu_hours"]))
    fetched_gib = Decimal(str(report["bytes"]["fetched_gib"]))
    n_completed = report["n_completed"]
    if n_completed <= 0:
        raise InputError("report has no completed requests")
    out = {
        "trace_family": report["trace_family"],
        "policy": report["policy"],
        "sensitivity": report["sensitivity"],
        "n_requests": report["n_requests"],
        "n_completed": n_completed,
        "n_failed": report["n_failed"],
        "latency_seconds": report["latency_seconds"],
        "slo_goodput": report["slo_goodput"],
        "hot_hit_rate": report["cache"]["hot_hit_rate"],
        "utilization": report["gpu"]["utilization"],
        "reserved_gpu_hours": str(reserved_h),
        "fetched_gib": str(fetched_gib),
        "cost_usd": {},
    }
    # All components stay exact; each emitted field is quantized exactly
    # once from the exact chain. Never sum rounded components or divide a
    # rounded total: at 1e-6 that drifts published fields.
    egress_billed_exact = fetched_gib * egress_per_gib
    for offer, hourly in sorted(gpu_hourly.items()):
        gpu_exact = reserved_h * hourly
        for variant, egress_exact in (("egress_billed", egress_billed_exact),
                                      ("egress_free", Decimal(0))):
            total_exact = gpu_exact + egress_exact
            per_1k_exact = total_exact / Decimal(n_completed) * Decimal(1000)
            out["cost_usd"][f"{offer}/{variant}"] = {
                "gpu": str(gpu_exact.quantize(CENT6)),
                "egress": str(egress_exact.quantize(CENT6)),
                "total": str(total_exact.quantize(CENT6)),
                "per_1000_completed": str(per_1k_exact.quantize(CENT6)),
            }
    return out
