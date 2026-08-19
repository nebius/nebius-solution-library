from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog_sim.policies import L1Cache, PolicyConfig  # noqa: E402
from catalog_sim.schema import SchemaError  # noqa: E402


def fill(cache: L1Cache, model_id: str, num_bytes: int, now: int, cost: int = 100):
    return cache.insert(model_id, num_bytes, f"sha-{model_id}", now, cost, True)


class PolicyConfigTest(unittest.TestCase):
    def test_rejects_unknown_policies(self):
        for kwargs in (
            {"placement": "random"},
            {"eviction": "fifo"},
            {"warm": "always"},
            {"admission": "drop-all"},
            {"prefetch": "aggressive"},
            {"strategy": "magic"},
        ):
            with self.assertRaises(SchemaError):
                PolicyConfig(**kwargs)

    def test_label_stable(self):
        config = PolicyConfig(
            strategy="snapshot", placement="shortest-switch-cost", eviction="gdsf",
            warm="topk-adaptive", warm_k=8,
        )
        self.assertEqual(
            config.label(), "snapshot+shortest-switch-cost+gdsf+topk-adaptive-k8"
        )


class EvictionTest(unittest.TestCase):
    def test_lru_evicts_least_recent(self):
        cache = L1Cache(100, "lru")
        fill(cache, "a", 40, now=1)
        fill(cache, "b", 40, now=2)
        cache.touch("a", now=3, setup_cost_micros=100)
        victims = fill(cache, "c", 40, now=4)
        self.assertEqual([v.model_id for v in victims], ["b"])
        self.assertEqual(sorted(cache.entries), ["a", "c"])

    def test_lfu_evicts_least_frequent(self):
        cache = L1Cache(100, "lfu")
        fill(cache, "a", 40, now=1)
        fill(cache, "b", 40, now=2)
        cache.touch("a", 3, 100)
        cache.touch("a", 4, 100)
        victims = fill(cache, "c", 40, now=5)
        self.assertEqual([v.model_id for v in victims], ["b"])

    def test_size_evicts_largest_first(self):
        cache = L1Cache(100, "size")
        fill(cache, "small", 10, now=1)
        fill(cache, "big", 80, now=2)
        victims = fill(cache, "c", 40, now=3)
        self.assertEqual([v.model_id for v in victims], ["big"])
        self.assertEqual(sorted(cache.entries), ["c", "small"])

    def test_gdsf_prefers_cheap_large_victims(self):
        cache = L1Cache(100, "gdsf")
        # big artifact with tiny setup cost -> low priority -> first victim
        cache.insert("cheap-big", 60, "sha-1", 1, setup_cost_micros=10, prewarmed=True)
        cache.insert("dear-small", 30, "sha-2", 2, setup_cost_micros=10_000_000, prewarmed=True)
        victims = cache.insert("new", 40, "sha-3", 3, 100, True)
        self.assertEqual([v.model_id for v in victims], ["cheap-big"])

    def test_pinned_entries_survive(self):
        cache = L1Cache(100, "lru")
        fill(cache, "a", 40, now=1)
        fill(cache, "b", 40, now=2)
        victims = cache.insert(
            "c", 40, "sha-c", 3, 100, True, pinned={"a"}
        )
        self.assertEqual([v.model_id for v in victims], ["b"])
        self.assertIn("a", cache.entries)

    def test_oversized_artifact_rejected(self):
        cache = L1Cache(100, "lru")
        with self.assertRaises(SchemaError):
            fill(cache, "huge", 101, now=1)

    def test_capacity_never_exceeded_and_accounting_exact(self):
        cache = L1Cache(100, "lru")
        for i in range(20):
            fill(cache, f"m{i}", 30, now=i)
            self.assertLessEqual(cache.used_bytes, 100)
            self.assertEqual(
                cache.used_bytes, sum(e.num_bytes for e in cache.entries.values())
            )
        self.assertEqual(cache.eviction_count, 17)


if __name__ == "__main__":
    unittest.main()
