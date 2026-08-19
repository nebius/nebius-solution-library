#!/usr/bin/env python3
"""Atomically export the union of VM v1 and Kubernetes v2 resource ledgers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import broker as vm  # noqa: E402
import kubernetes_broker as k8s  # noqa: E402


def cleanup_evidence(row: dict[str, Any]) -> str:
    existing = row.get("cleanup_evidence")
    if existing:
        return str(existing)
    if row.get("cleanup_state") == "NOT_CREATED" or not row.get("resource_id"):
        return "No resource ID was created or recorded; desired final state already holds."
    if row.get("absence_verified_at"):
        return (
            f"Exact resource ID {row['resource_id']} returned NotFound/absence at "
            f"{row['absence_verified_at']}."
        )
    return "No cleanup or absence proof yet; exact-ID cleanup remains pending."


def build(vm_registry: Path, k8s_registry: Path) -> dict[str, Any]:
    sources = []
    if vm_registry.exists():
        sources.append(vm.supervisor_ledger(vm_registry))
    if k8s_registry.exists():
        sources.append(k8s.supervisor_ledger(k8s_registry))
    leases: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    registries: list[str] = []
    for source in sources:
        canonical = source.get("canonical_registries") or [source.get("canonical_registry")]
        registries.extend(str(item) for item in canonical if item)
        leases.extend(source.get("leases", []))
        for original in source.get("resources", []):
            row = dict(original)
            row["cleanup_evidence"] = cleanup_evidence(row)
            resources.append(row)
    leases.sort(key=lambda item: (item.get("lease_id", ""), item.get("schema_version", "")))
    resources.sort(
        key=lambda item: (
            item.get("lease_id", ""),
            item.get("resource_type", ""),
            item.get("resource_name", ""),
            item.get("resource_id") or "",
        )
    )
    return {
        "schema_version": "catalog-switch-supervisor-resource-ledger/v2",
        "updated_at": vm.iso(k8s.precise_utc_now()),
        "canonical_registries": sorted(set(registries)),
        "contains_secrets": False,
        "leases": leases,
        "resources": resources,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vm-registry", type=Path, default=ROOT / "leases" / "registry.json")
    parser.add_argument(
        "--kubernetes-registry",
        type=Path,
        default=ROOT / "kubernetes-leases" / "registry.json",
    )
    parser.add_argument("--output", type=Path, default=vm.DEFAULT_SUPERVISOR_LEDGER)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    value = build(args.vm_registry, args.kubernetes_registry)
    vm.atomic_json(args.output, value)
    json.dump(value, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
