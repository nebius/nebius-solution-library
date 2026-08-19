"""Placement, eviction, warm-capacity, admission, and prefetch policies.

Policies are deterministic given the engine state passed to them; ties break
on stable keys (node id, model id) so runs replay exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .schema import SchemaError

EVICTION_POLICIES = ("lru", "lfu", "size", "gdsf")
PLACEMENT_POLICIES = ("least-loaded", "shortest-switch-cost")
WARM_POLICIES = ("none", "topk-adaptive")
ADMISSION_POLICIES = ("unbounded", "bounded-queue")
PREFETCH_POLICIES = ("none", "pipeline-next")


@dataclass(frozen=True)
class PolicyConfig:
    placement: str = "shortest-switch-cost"
    eviction: str = "lru"
    warm: str = "none"
    admission: str = "unbounded"
    prefetch: str = "none"
    strategy: str = "snapshot"  # "snapshot" or "conventional" setup path
    warm_k: int = 6
    warm_window_micros: int = 600 * 1_000_000
    max_queue_per_node: int = 12

    def __post_init__(self) -> None:
        checks = (
            (self.placement, PLACEMENT_POLICIES, "placement"),
            (self.eviction, EVICTION_POLICIES, "eviction"),
            (self.warm, WARM_POLICIES, "warm"),
            (self.admission, ADMISSION_POLICIES, "admission"),
            (self.prefetch, PREFETCH_POLICIES, "prefetch"),
            (self.strategy, ("snapshot", "conventional"), "strategy"),
        )
        for value, allowed, label in checks:
            if value not in allowed:
                raise SchemaError(f"unknown {label} policy {value!r}")
        if self.warm_k < 1 or self.max_queue_per_node < 1:
            raise SchemaError("warm_k and max_queue_per_node must be >= 1")

    def label(self) -> str:
        parts = [self.strategy, self.placement, self.eviction]
        if self.warm != "none":
            parts.append(f"{self.warm}-k{self.warm_k}")
        if self.admission != "unbounded":
            parts.append(self.admission)
        if self.prefetch != "none":
            parts.append(self.prefetch)
        return "+".join(parts)


@dataclass
class CacheEntry:
    model_id: str
    num_bytes: int
    digest: str
    prewarmed: bool
    inserted_at: int
    last_used_at: int
    use_count: int = 1
    gdsf_priority: float = 0.0


class L1Cache:
    """Node-local NVMe artifact cache with pluggable eviction."""

    def __init__(self, capacity_bytes: int, policy: str) -> None:
        if policy not in EVICTION_POLICIES:
            raise SchemaError(f"unknown eviction policy {policy!r}")
        self.capacity_bytes = capacity_bytes
        self.policy = policy
        self.entries: Dict[str, CacheEntry] = {}
        self.used_bytes = 0
        self._gdsf_clock = 0.0
        self.eviction_count = 0
        self.evicted_bytes = 0

    def contains(self, model_id: str) -> bool:
        return model_id in self.entries

    def touch(self, model_id: str, now: int, setup_cost_micros: int) -> None:
        entry = self.entries[model_id]
        entry.last_used_at = now
        entry.use_count += 1
        if self.policy == "gdsf":
            entry.gdsf_priority = self._gdsf_clock + (
                entry.use_count * setup_cost_micros / max(1, entry.num_bytes)
            )

    def insert(
        self,
        model_id: str,
        num_bytes: int,
        digest: str,
        now: int,
        setup_cost_micros: int,
        prewarmed: bool,
        pinned: Optional[set] = None,
    ) -> List[CacheEntry]:
        """Insert an artifact, evicting victims as needed. Returns victims."""
        if num_bytes > self.capacity_bytes:
            raise SchemaError(
                f"artifact {model_id} ({num_bytes} B) exceeds L1 capacity "
                f"({self.capacity_bytes} B); catalog and capacity inputs are "
                f"inconsistent"
            )
        if model_id in self.entries:
            self.touch(model_id, now, setup_cost_micros)
            self.entries[model_id].prewarmed = self.entries[model_id].prewarmed or prewarmed
            return []
        victims: List[CacheEntry] = []
        pinned = pinned or set()
        while self.used_bytes + num_bytes > self.capacity_bytes:
            victim_id = self._select_victim(exclude=pinned | {model_id})
            if victim_id is None:
                raise SchemaError(
                    f"L1 cache cannot fit {model_id}: all residents pinned"
                )
            victim = self.entries.pop(victim_id)
            self.used_bytes -= victim.num_bytes
            self.eviction_count += 1
            self.evicted_bytes += victim.num_bytes
            victims.append(victim)
        entry = CacheEntry(
            model_id=model_id,
            num_bytes=num_bytes,
            digest=digest,
            prewarmed=prewarmed,
            inserted_at=now,
            last_used_at=now,
        )
        if self.policy == "gdsf":
            entry.gdsf_priority = self._gdsf_clock + (
                setup_cost_micros / max(1, num_bytes)
            )
        self.entries[model_id] = entry
        self.used_bytes += num_bytes
        return victims

    def _select_victim(self, exclude: set) -> Optional[str]:
        candidates = [
            (mid, e) for mid, e in self.entries.items() if mid not in exclude
        ]
        if not candidates:
            return None
        if self.policy == "lru":
            key = lambda item: (item[1].last_used_at, item[0])
        elif self.policy == "lfu":
            key = lambda item: (item[1].use_count, item[1].last_used_at, item[0])
        elif self.policy == "size":
            key = lambda item: (-item[1].num_bytes, item[1].last_used_at, item[0])
        else:  # gdsf
            key = lambda item: (item[1].gdsf_priority, item[0])
        victim_id, victim = min(candidates, key=key)
        if self.policy == "gdsf":
            self._gdsf_clock = max(self._gdsf_clock, victim.gdsf_priority)
        return victim_id

    def drop_all(self) -> None:
        self.entries.clear()
        self.used_bytes = 0


def choose_node(config: PolicyConfig, nodes, model, now: int, est_setup) -> Optional[int]:
    """Pick a node id for a request, or None when admission rejects it.

    ``nodes`` is the engine's node list; ``est_setup(node, model)`` returns
    the estimated switch/setup micros for placing ``model`` on ``node``.
    """
    online = [n for n in nodes if n.online]
    if not online:
        return None
    if config.admission == "bounded-queue":
        online = [n for n in online if len(n.queue) < config.max_queue_per_node]
        if not online:
            return None

    if config.placement == "least-loaded":
        return min(
            online, key=lambda n: (len(n.queue) + (1 if n.busy else 0), n.node_id)
        ).node_id

    # shortest-switch-cost: expected wait until free plus estimated setup.
    def score(n):
        backlog = max(0, n.expected_free_at - now)
        return (backlog + est_setup(n, model), n.node_id)

    return min(online, key=score).node_id


def warm_pin_assignments(
    config: PolicyConfig, window_counts: Dict[str, int], nodes
) -> Dict[int, str]:
    """Top-K adaptive warm policy: pin the K hottest models to distinct nodes.

    Returns {node_id: model_id}. Deterministic: counts break ties on model id,
    nodes are assigned in node-id order, and nodes already holding a pinned
    model keep it to avoid churn.
    """
    if config.warm != "topk-adaptive":
        return {}
    ranked = sorted(window_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [model_id for model_id, count in ranked[: config.warm_k] if count > 0]
    online = sorted((n for n in nodes if n.online), key=lambda n: n.node_id)
    if not top or not online:
        return {}
    assignments: Dict[int, str] = {}
    remaining = list(top)
    # Keep existing residents pinned where they already match.
    for n in online:
        if n.l0_model in remaining:
            assignments[n.node_id] = n.l0_model
            remaining.remove(n.l0_model)
    for n in online:
        if not remaining:
            break
        if n.node_id in assignments:
            continue
        assignments[n.node_id] = remaining.pop(0)
    return assignments
