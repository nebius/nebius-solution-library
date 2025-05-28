#!/usr/bin/env python3
"""
create_slurm_topology.py – Convert Nebius GPU-cluster YAML topology to
SLURM *tree*-style topology.conf
https://slurm.schedmd.com/topology.conf.html#SECTION_topology/tree

Usage
-----
# Piping straight from the Nebius CLI
nebius compute gpu-cluster get --id <gpu-cluster-id> --format yaml \
    | python3 create_slurm_topology.py - > topology.conf
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import IO

import yaml  # pip install pyyaml


# --------------------------------------------------------------------------- helpers
def open_input(path: str) -> IO[str]:
    """Open *path* for reading, or return sys.stdin for '-' / empty."""
    if path in ("", "-"):
        return sys.stdin
    try:
        return Path(path).open("r", encoding="utf-8")
    except OSError as exc:
        sys.exit(f"Error opening input file '{path}': {exc}")


def find_ib_topology(doc: object) -> dict | None:
    """Depth-first search for the first 'infiniband_topology_path' mapping."""
    if isinstance(doc, dict):
        if "infiniband_topology_path" in doc:
            return doc["infiniband_topology_path"]
        # walk the values
        for val in doc.values():
            hit = find_ib_topology(val)
            if hit is not None:
                return hit
    elif isinstance(doc, (list, tuple)):
        for item in doc:
            hit = find_ib_topology(item)
            if hit is not None:
                return hit
    return None


# --------------------------------------------------------------------------- main
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="create_slurm_topology.py",
        description="Convert Nebius infiniband_topology_path → SLURM topology.conf",
    )
    p.add_argument(
        "yaml",
        nargs="?",
        default="-",
        help="Input YAML file (or '-' / nothing for stdin)",
    )
    return p.parse_args()


def main() -> None:
    ns = parse_args()

    with open_input(ns.yaml) as fh:
        try:
            doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            sys.exit(f"YAML parse error: {exc}")

    topo = find_ib_topology(doc)
    if topo is None:
        sys.exit("Error: no infiniband_topology_path section found.")

    instances = topo.get("instances") or []
    if not instances:
        sys.exit("Error: infiniband_topology_path.instances is missing or empty.")

    # Build topology relationships:
    lvl1_to_lvl2: dict[str, set[str]] = defaultdict(set)
    lvl2_to_lvl3: dict[str, set[str]] = defaultdict(set)
    lvl3_to_nodes: dict[str, set[str]] = defaultdict(set)

    for inst in instances:
        iid = inst.get("instance_id")
        path = inst.get("path") or []
        if iid is None or len(path) != 3:
            # malformed record – ignore but warn on stderr
            print(
                f"Warning: skipping bad instance record {inst!r}", file=sys.stderr
            )
            continue
        l1, l2, l3 = map(str, path)
        lvl1_to_lvl2[l1].add(l2)
        lvl2_to_lvl3[l2].add(l3)
        lvl3_to_nodes[l3].add(str(iid))

    # ------------------------------------------------------------------- emit
    print("# Switch configuration")

    def emit(parent_to_children: dict[str, set[str]], label: str) -> None:
        for parent in sorted(parent_to_children):
            children = ",".join(sorted(parent_to_children[parent]))
            if children:
                print(f"SwitchName={parent} {label}={children}")

    emit(lvl1_to_lvl2, "Switches")   # level-1 → level-2
    emit(lvl2_to_lvl3, "Switches")   # level-2 → level-3

    for leaf in sorted(lvl3_to_nodes):
        nodes = ",".join(sorted(lvl3_to_nodes[leaf]))
        if nodes:
            print(f"SwitchName={leaf} Nodes={nodes}")


if __name__ == "__main__":
    main()