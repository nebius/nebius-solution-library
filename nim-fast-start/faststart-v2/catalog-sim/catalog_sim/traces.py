"""Deterministic trace families with fixed content checksums.

Each trace is a sequence of ``(arrival_micros, model_id)`` requests plus
metadata. Serialization is canonical (one tab-separated line per request in
arrival order) so the SHA-256 checksum of a regenerated trace must match the
checksums pinned in ``traces/CHECKSUMS.json`` exactly.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .schema import SchemaError
from .units import seconds_to_micros

TRACE_SEED = 4207
TRACE_FAMILIES = ("uniform", "zipf", "bursty", "correlated", "adversarial")


@dataclass(frozen=True)
class Trace:
    name: str
    family: str
    seed: int
    horizon_micros: int
    requests: Tuple[Tuple[int, str], ...]  # (arrival_micros, model_id), sorted

    def canonical_bytes(self) -> bytes:
        lines = [f"{self.name}\t{self.family}\t{self.seed}\t{self.horizon_micros}"]
        for seq, (t, model_id) in enumerate(self.requests):
            lines.append(f"{seq}\t{t}\t{model_id}")
        return ("\n".join(lines) + "\n").encode("utf-8")

    def checksum(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _finalize(name, family, seed, horizon_micros, requests) -> Trace:
    requests = tuple(sorted(requests))
    for t, model_id in requests:
        if t < 0 or t > horizon_micros:
            raise SchemaError(f"trace {name}: arrival {t} outside horizon")
        if not model_id:
            raise SchemaError(f"trace {name}: empty model id")
    return Trace(name, family, seed, horizon_micros, requests)


def _poisson_arrivals(rng, rate_per_s: float, horizon_micros: int) -> List[int]:
    arrivals = []
    t = 0.0
    horizon_s = horizon_micros / 1_000_000
    while True:
        t += rng.expovariate(rate_per_s)
        if t >= horizon_s:
            break
        arrivals.append(seconds_to_micros(t))
    return arrivals


def _zipf_weights(n: int, exponent: float) -> List[float]:
    weights = [1.0 / (rank**exponent) for rank in range(1, n + 1)]
    total = sum(weights)
    return [w / total for w in weights]


def generate_trace(
    family: str,
    model_ids: Sequence[str],
    horizon_seconds: float = 7200.0,
    mean_rate_per_s: float = 0.5,
    seed: int = TRACE_SEED,
) -> Trace:
    """Generate one deterministic trace of the requested family."""
    if family not in TRACE_FAMILIES:
        raise SchemaError(f"unknown trace family {family!r}")
    model_ids = sorted(model_ids)
    horizon_micros = seconds_to_micros(horizon_seconds)
    rng = random.Random((family, seed, len(model_ids)).__repr__())
    name = f"{family}-n{len(model_ids)}-h{int(horizon_seconds)}-s{seed}"
    requests: List[Tuple[int, str]] = []

    if family == "uniform":
        for t in _poisson_arrivals(rng, mean_rate_per_s, horizon_micros):
            requests.append((t, rng.choice(model_ids)))

    elif family == "zipf":
        # Popularity ranks are a deterministic shuffle of the catalog so rank
        # order is not correlated with anchor family order.
        ranked = list(model_ids)
        rng.shuffle(ranked)
        weights = _zipf_weights(len(ranked), exponent=1.1)
        for t in _poisson_arrivals(rng, mean_rate_per_s, horizon_micros):
            requests.append((t, rng.choices(ranked, weights=weights, k=1)[0]))

    elif family == "bursty":
        # Alternate quiet and burst intervals (rate x8) over a zipf popularity.
        ranked = list(model_ids)
        rng.shuffle(ranked)
        weights = _zipf_weights(len(ranked), exponent=1.1)
        quiet_rate = mean_rate_per_s / 2
        burst_rate = mean_rate_per_s * 4
        period_s = 300.0
        t = 0.0
        horizon_s = horizon_seconds
        while t < horizon_s:
            phase_burst = int(t // period_s) % 2 == 1
            rate = burst_rate if phase_burst else quiet_rate
            t += rng.expovariate(rate)
            if t >= horizon_s:
                break
            requests.append(
                (seconds_to_micros(t), rng.choices(ranked, weights=weights, k=1)[0])
            )

    elif family == "correlated":
        # Session pipelines: a session starts on a group's first stage and
        # walks the four-stage pipeline with short think times, modeling
        # MSA -> fold -> design style chained demand.
        groups: Dict[int, List[str]] = {}
        for m in model_ids:
            groups.setdefault(_group_of(m, model_ids), []).append(m)
        group_keys = sorted(groups)
        session_rate = mean_rate_per_s / 3.2  # ~3.2 requests per session
        t = 0.0
        while True:
            t += rng.expovariate(session_rate)
            if t >= horizon_seconds:
                break
            chain = groups[rng.choice(group_keys)]
            step_t = t
            for stage, model_id in enumerate(sorted(chain)):
                if stage > 0:
                    step_t += rng.uniform(5.0, 30.0)
                if step_t >= horizon_seconds:
                    break
                requests.append((seconds_to_micros(step_t), model_id))
                if rng.random() < 0.2:  # session abandons pipeline
                    break

    elif family == "adversarial":
        # Two disjoint working sets, each larger than any plausible warm L0
        # capacity, alternating every 240 s to force maximal switch thrash.
        half = len(model_ids) // 2
        set_a, set_b = model_ids[:half], model_ids[half:]
        period_s = 240.0
        for t in _poisson_arrivals(rng, mean_rate_per_s, horizon_micros):
            phase = int((t / 1_000_000) // period_s) % 2
            pool = set_a if phase == 0 else set_b
            requests.append((t, rng.choice(pool)))

    return _finalize(name, family, seed, horizon_micros, requests)


def _group_of(model_id: str, ordered_ids: Sequence[str]) -> int:
    return ordered_ids.index(model_id) // 4


def generate_all(model_ids: Sequence[str], **kwargs) -> Dict[str, Trace]:
    return {family: generate_trace(family, model_ids, **kwargs) for family in TRACE_FAMILIES}
