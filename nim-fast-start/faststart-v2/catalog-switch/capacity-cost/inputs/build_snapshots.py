#!/usr/bin/env python3
"""Build the dated price and capacity snapshots from raw captured evidence.

Reads ``inputs/raw/*.json`` (read-only Nebius billing-calculator quotes and
capacity resource-advice captured on 2026-08-19) plus hardcoded, dated public
list prices, and emits:

- ``inputs/price_snapshot.json``    (schema capacity-cost-price-snapshot/v1)
- ``inputs/capacity_snapshot.json`` (schema capacity-cost-capacity-snapshot/v1)

Every price record separates its source class:

- ``tenant_calculator_quote``: value copied verbatim from a captured
  ``billing v1alpha1 calculator estimate`` response in ``raw/``;
- ``public_list_price``: value transcribed from a public pricing page with
  the retrieval date and URL recorded;
- ``derived``: arithmetic on the above, with the derivation recorded.

Modal prices are deliberately absent: Modal is documentation-only for this
program and its terms live in ``../MODAL_APPENDIX.md``, excluded from every
empirical computation. No network access is used here; regeneration is
deterministic from the committed raw files.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
SOURCES = RAW / "sources"

_MANIFEST = json.loads((SOURCES / "sources_manifest.json").read_text())
_ARCHIVES_BY_URL = {a["url"]: a for a in _MANIFEST["archives"]}


def _archive_binding(url: str, unit_price: str) -> dict:
    """Return the archived-payload binding for a public price record.

    Fails closed if the archive is missing, its hash drifted, or the quoted
    price string is not literally present in the payload (offline check).
    """
    arch = _ARCHIVES_BY_URL.get(url)
    if arch is None:
        raise SystemExit(f"no archived payload for {url}")
    payload = (SOURCES / arch["file"]).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != arch["sha256"]:
        raise SystemExit(f"payload hash drift for {arch['file']}: {actual}")
    if unit_price.encode() not in payload:
        raise SystemExit(
            f"price {unit_price} not found in archived {arch['file']}")
    return {
        "file": f"inputs/raw/sources/{arch['file']}",
        "sha256": arch["sha256"],
        "retrieved_at_utc": arch["retrieved_at_utc"],
    }

NEBIUS_PRICES_URL = "https://nebius.com/prices"
CEREBRIUM_PRICES_URL = "https://www.cerebrium.ai/pricing"

# Regions are bound to projects here, in exactly one place. A tenant quote's
# region is derived from the project recorded in its raw command, never
# hardcoded per record, so a re-capture with overridden PROJECT_* variables
# cannot silently keep a stale region label.
PROJECT_REGION = {
    "project-e00z6b02t8ddk96c49": "eu-north1",
    "project-u00tds8vpr00jaxa76s22d": "us-central1",
    # project-i00xz31gpr00xp9jhp982v is allowlisted for the epic but its
    # region is unattested here; a quote captured in it fails closed until
    # this map is extended with verified evidence.
}

HOURS_PER_MONTH = Decimal("730")


def _quote(name: str) -> dict:
    doc = json.loads((RAW / f"{name}.json").read_text())
    if doc["exit_code"] != 0 or doc["response"] is None:
        raise SystemExit(f"raw quote {name} is not a successful capture")
    resp = doc["response"]
    # Bind project/region from the evidence itself: prefer the explicit
    # parameters block emitted by current capture_quotes.sh; fall back to
    # parsing the recorded command for captures that predate the block.
    params = doc.get("parameters")
    if params:
        project = params["project"]
        if params["region"] != PROJECT_REGION.get(project):
            raise SystemExit(
                f"{name}: emitted region {params['region']} contradicts the "
                f"attested region map for {project}")
    else:
        m = re.search(r"parent-id (\S+)", doc["command"])
        if not m:
            raise SystemExit(f"{name}: no parent-id in recorded command")
        project = m.group(1)
    region = PROJECT_REGION.get(project)
    if region is None:
        raise SystemExit(
            f"{name}: project {project} has no attested region; extend "
            f"PROJECT_REGION with verified evidence before pricing it")
    return {
        "hourly": resp["hourly_cost"]["general"]["total"]["cost"],
        "monthly": resp["monthly_cost"]["general"]["total"]["cost"],
        "captured_at_utc": doc["captured_at_utc"],
        "command": doc["command"],
        "project": project,
        "region": region,
        "evidence_file": f"inputs/raw/{name}.json",
    }


def tenant_record(record_id: str, name: str, sku: str, unit: str,
                  offer_class: str, notes: str = "") -> dict:
    q = _quote(name)
    return {
        "record_id": record_id,
        "sku": sku,
        "unit": unit,
        "currency": "USD",
        "unit_price": q["hourly"],
        "monthly_price": q["monthly"],
        "offer_class": offer_class,
        "region_scope": q["region"],
        "source": {
            "kind": "tenant_calculator_quote",
            "command": q["command"],
            "project": q["project"],
            "region": q["region"],
            "retrieved_at_utc": q["captured_at_utc"],
            "evidence_file": q["evidence_file"],
        },
        "notes": notes,
    }


def public_record(record_id: str, sku: str, unit: str, unit_price: str,
                  offer_class: str, url: str,
                  notes: str = "") -> dict:
    binding = _archive_binding(url, unit_price)
    return {
        "record_id": record_id,
        "sku": sku,
        "unit": unit,
        "currency": "USD",
        "unit_price": unit_price,
        "monthly_price": None,
        "offer_class": offer_class,
        "region_scope": "published-list",
        "source": {
            "kind": "public_list_price",
            "url": url,
            "retrieved_at_utc": binding["retrieved_at_utc"],
            "archived_payload": binding,
        },
        "notes": notes,
    }


def derived_record(record_id: str, sku: str, unit: str, unit_price: str,
                   offer_class: str, derived_from: list[str],
                   derivation: str) -> dict:
    return {
        "record_id": record_id,
        "sku": sku,
        "unit": unit,
        "currency": "USD",
        "unit_price": unit_price,
        "monthly_price": None,
        "offer_class": offer_class,
        "region_scope": "derived",
        "source": {
            "kind": "derived",
            "derived_from": derived_from,
            "derivation": derivation,
        },
        "notes": "",
    }


def build_price_snapshot() -> dict:
    records: list[dict] = []

    # --- Nebius tenant-effective calculator quotes (authoritative here) ---
    gpu_quotes = [
        ("nebius-h100-1g-od", "quote-gpu-h100-sxm-1gpu-16vcpu-200gb-ondemand",
         "gpu-h100-sxm/1gpu-16vcpu-200gb", "on_demand"),
        ("nebius-h100-1g-pre", "quote-gpu-h100-sxm-1gpu-16vcpu-200gb-preemptible",
         "gpu-h100-sxm/1gpu-16vcpu-200gb", "preemptible"),
        ("nebius-h200-1g-od", "quote-gpu-h200-sxm-1gpu-16vcpu-200gb-ondemand",
         "gpu-h200-sxm/1gpu-16vcpu-200gb", "on_demand"),
        ("nebius-h200-1g-pre", "quote-gpu-h200-sxm-1gpu-16vcpu-200gb-preemptible",
         "gpu-h200-sxm/1gpu-16vcpu-200gb", "preemptible"),
        ("nebius-b200-1g-od", "quote-gpu-b200-sxm-1gpu-20vcpu-224gb-ondemand",
         "gpu-b200-sxm/1gpu-20vcpu-224gb", "on_demand"),
        ("nebius-b200-1g-pre", "quote-gpu-b200-sxm-1gpu-20vcpu-224gb-preemptible",
         "gpu-b200-sxm/1gpu-20vcpu-224gb", "preemptible"),
        ("nebius-cpu-d3-4v16g-od", "quote-cpu-d3-4vcpu-16gb-ondemand",
         "cpu-d3/4vcpu-16gb", "on_demand"),
    ]
    for rid, raw_name, sku, offer in gpu_quotes:
        records.append(tenant_record(
            rid, raw_name, sku, "USD/instance-hour", offer,
            notes="Whole-instance quote; the GPU platform bundles vCPU/RAM."))

    records.append(tenant_record(
        "nebius-sfs-1024gib", "quote-filesystem-network-ssd-1024gib",
        "filesystem/network_ssd/1024GiB", "USD/filesystem-hour", "committed"))
    records.append(tenant_record(
        "nebius-sfs-4096gib", "quote-filesystem-network-ssd-4096gib",
        "filesystem/network_ssd/4096GiB", "USD/filesystem-hour", "committed",
        notes="4 TiB matches the SFS size used by the measured artifact tier."))
    records.append(tenant_record(
        "nebius-disk-nssd-200gib", "quote-disk-network-ssd-200gib",
        "disk/network_ssd/200GiB", "USD/disk-hour", "committed"))
    records.append(tenant_record(
        "nebius-disk-nrd-930gib", "quote-disk-network-ssd-nonreplicated-930gib",
        "disk/network_ssd_non_replicated/930GiB", "USD/disk-hour", "committed"))

    # Derived per-GiB-month storage rates from tenant quotes.
    sfs = _quote("quote-filesystem-network-ssd-4096gib")
    sfs_gib_month = (Decimal(sfs["monthly"]) / Decimal(4096)).quantize(
        Decimal("0.000000001"))
    records.append(derived_record(
        "nebius-sfs-gib-month", "filesystem/network_ssd", "USD/GiB-month",
        str(sfs_gib_month), "committed", ["nebius-sfs-4096gib"],
        "monthly_price / 4096 GiB, quantized to 1e-9"))

    # --- Nebius public list prices (cross-check + items not quotable) ---
    records += [
        public_record("nebius-list-h100-od", "gpu-h100-sxm", "USD/GPU-hour",
                      "3.85", "on_demand", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-h100-1g-od."),
        public_record("nebius-list-h100-pre", "gpu-h100-sxm", "USD/GPU-hour",
                      "2.15", "preemptible", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-h100-1g-pre."),
        public_record("nebius-list-h200-od", "gpu-h200-sxm", "USD/GPU-hour",
                      "4.50", "on_demand", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-h200-1g-od."),
        public_record("nebius-list-h200-pre", "gpu-h200-sxm", "USD/GPU-hour",
                      "2.45", "preemptible", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-h200-1g-pre."),
        public_record("nebius-list-b200-od", "gpu-b200-sxm", "USD/GPU-hour",
                      "7.15", "on_demand", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-b200-1g-od."),
        public_record("nebius-list-b200-pre", "gpu-b200-sxm", "USD/GPU-hour",
                      "3.95", "preemptible", NEBIUS_PRICES_URL,
                      "Matches tenant quote nebius-b200-1g-pre."),
        public_record("nebius-list-b300-od", "gpu-b300-sxm", "USD/GPU-hour",
                      "7.85", "on_demand", NEBIUS_PRICES_URL, "No tenant quote captured."),
        public_record("nebius-list-b300-pre", "gpu-b300-sxm", "USD/GPU-hour",
                      "4.30", "preemptible", NEBIUS_PRICES_URL, "No tenant quote captured."),
        public_record("nebius-list-sfs", "filesystem/network_ssd",
                      "USD/GiB-month", "0.08", "committed",
                      NEBIUS_PRICES_URL,
                      "Matches derived nebius-sfs-gib-month within rounding."),
        public_record("nebius-list-object-volume", "object-storage/standard",
                      "USD/GiB-month", "0.0147", "committed",
                      NEBIUS_PRICES_URL, ""),
        public_record("nebius-list-object-egress", "object-storage/egress",
                      "USD/GiB", "0.0150", "usage",
                      NEBIUS_PRICES_URL,
                      "Object Storage egress. VPC networking egress/ingress "
                      "and public IPs are listed as free on the same page."),
    ]

    # --- Cerebrium public prices (sole external measured comparator) ---
    per_second = [
        ("cerebrium-h100-s", "H100", "0.000944"),
        ("cerebrium-h200-s", "H200", "0.001166"),
        ("cerebrium-b200-s", "B200", "0.00167"),
        ("cerebrium-a100-80-s", "A100-80GB", "0.000583"),
        ("cerebrium-l40s-s", "L40S", "0.000542"),
        ("cerebrium-a10-s", "A10", "0.000306"),
    ]
    for rid, sku, price in per_second:
        records.append(public_record(
            rid, f"cerebrium/{sku}", "USD/GPU-second", price, "on_demand",
            CEREBRIUM_PRICES_URL,
            "Per-second metered; GPU price excludes CPU/memory add-ons."))
        hourly = (Decimal(price) * Decimal(3600)).normalize()
        records.append(derived_record(
            rid.replace("-s", "-h"), f"cerebrium/{sku}", "USD/GPU-hour",
            format(hourly, "f"), "on_demand", [rid], "per-second price * 3600"))
    records += [
        public_record("cerebrium-cpu-s", "cerebrium/vCPU", "USD/vCPU-second",
                      "0.00000655", "on_demand", CEREBRIUM_PRICES_URL, ""),
        public_record("cerebrium-mem-s", "cerebrium/memory", "USD/GB-second",
                      "0.00000222", "on_demand", CEREBRIUM_PRICES_URL, ""),
        public_record("cerebrium-storage", "cerebrium/storage",
                      "USD/GB-month", "0.05", "committed",
                      CEREBRIUM_PRICES_URL,
                      "First 100 GB free."),
        public_record("cerebrium-plan-standard", "cerebrium/plan-standard",
                      "USD/month", "100", "committed",
                      CEREBRIUM_PRICES_URL,
                      "Standard plan platform fee, plus metered compute."),
    ]

    records.sort(key=lambda r: r["record_id"])
    return {
        "schema_version": "capacity-cost-price-snapshot/v1",
        "generated_by": "catalog-switch/capacity-cost/inputs/build_snapshots.py",
        "as_of_date": "2026-08-19",
        "statement": (
            "Prices are point-in-time quotes/list prices retrieved on the "
            "dated timestamps, not invoices. Billing increments, minimums, "
            "discounts, and taxes are out of scope, consistent with "
            "performance/cost-ledger semantics. Modal terms are excluded by "
            "design; see MODAL_APPENDIX.md."),
        "records": records,
    }


def build_capacity_snapshot() -> dict:
    doc = json.loads((RAW / "capacity-resource-advice.json").read_text())
    if doc["exit_code"] != 0 or doc["response"] is None:
        raise SystemExit("capacity capture is not a successful response")
    rows = []
    for item in doc["response"]["items"]:
        spec = item["spec"]
        ci = spec.get("compute_instance")
        if not ci:
            continue
        offers = {}
        for offer in ("on_demand", "preemptible", "reserved"):
            st = item["status"].get(offer)
            if st is None:
                continue
            offers[offer] = {
                "availability_level": st.get("availability_level"),
                "available": st.get("available"),
                "limit": st.get("limit"),
                "data_state": st.get("data_state"),
                "effective_at": st.get("effective_at"),
            }
        rows.append({
            "region": spec["region"],
            "fabric": spec.get("fabric"),
            "platform": ci["platform"],
            "preset": ci["preset"]["name"],
            "gpu_count": ci["preset"]["resources"].get("gpu_count", 0),
            "offers": offers,
        })
    rows.sort(key=lambda r: (r["region"], r["platform"], r["preset"]))
    return {
        "schema_version": "capacity-cost-capacity-snapshot/v1",
        "generated_by": "catalog-switch/capacity-cost/inputs/build_snapshots.py",
        "as_of_utc": doc["captured_at_utc"],
        "tenant": "tenant-e00f3wdfzwfjgbcyfv",
        "statement": (
            "Quota-clipped availability from the read-only capacity "
            "resource-advice service at capture time. Availability levels "
            "are point-in-time observations, not commitments."),
        "source_evidence_file": "inputs/raw/capacity-resource-advice.json",
        "rows": rows,
    }


def main() -> int:
    price = build_price_snapshot()
    capacity = build_capacity_snapshot()
    (HERE / "price_snapshot.json").write_text(
        json.dumps(price, indent=2, sort_keys=True) + "\n")
    (HERE / "capacity_snapshot.json").write_text(
        json.dumps(capacity, indent=2, sort_keys=True) + "\n")
    print(f"price records: {len(price['records'])}")
    print(f"capacity rows: {len(capacity['rows'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
