# Simulation results (provisional — placeholder-sensitive)

Generated from `run_simulation.py` (75 runs: 9 policy configs x 5 traces at
base sensitivity, plus 3 headline configs x 5 traces at low/high). Raw rows
are in `summary.tsv`; full per-run reports, the complete placeholder table
with selected values, and trace checksums are in `reports.json`. All latency
figures are seconds, nearest-rank percentiles, with rejected/failed requests
sorted after successes (a tail rank landing on one reports `unbounded`).

**These numbers rank nothing for production.** 190 of 200 catalog rows and
several fleet parameters are bounded placeholders; per manager guidance the
comparison is requalified once the catalog inventory and shared harness
schemas land (via `catalog_sim/adapters.py`). What is reported below is which
effects are structural (stable across the whole declared sensitivity range)
and which are inside placeholder noise.

## Scenario

200 models (10 measured anchors + 190 placeholder-scaled), 24 single-GPU
nodes, 2-hour trace horizon, mean 0.25 req/s (bursty phases reach 1.0 req/s),
preemptible failures enabled at every sensitivity level. Request counts per
trace: uniform 1796, zipf 1847, bursty 3964, correlated 1689, adversarial
1789. All 75 runs conserved every request; the only non-completed outcomes
were 8 failed requests (retry exhaustion after preemptions) in two
low-sensitivity conventional-strategy runs, which correctly surfaced as
`unbounded` tail candidates.

## Effects stable across the full sensitivity range (structural)

1. **Switch-cost-aware placement dominates everything else.** Replacing
   `shortest-switch-cost` with `least-loaded` placement multiplied base p50
   by 8-50x (e.g. uniform 23.5 s -> 481.5 s; adversarial 22.7 s -> 192.4 s)
   and collapsed 120 s goodput from ~0.93 to 0.04-0.36, at 2-3x the cost.
   The effect holds at every sensitivity level and in every trace family.
2. **Conventional loading cannot hold this offered load; snapshot can.**
   With placeholder conventional-load times (only MSA's conventional route is
   measured), the conventional strategy saturates every non-zipf trace (base
   uniform p50 896 s, p95 5099 s vs snapshot 23.5/147.8 s). Under zipf skew
   its hot hits keep it merely worse (p95 215.9 vs 150.0 s), not collapsed.
   The gap widens monotonically from low to high sensitivity.
3. **Queue-depth-bounded placement is the best burst defense observed.**
   Under the bursty trace, capping per-node queue depth cut base p95 from
   3748 s to 210 s and raised 120 s goodput from 0.72 to 0.84 — with zero
   rejections at base (the cap acts as forced load spreading before it ever
   rejects). This is the only policy that materially tamed burst tails.
4. **Artifact localization, not restore, sets the cold tail.** A first
   node-touch of a Boltz2-class model costs ~423 s of measured prewarm
   against ~27 s of measured restore, and Evo2-class fetches move ~100 GB;
   the worst per-request latencies in every run are localization-bound L2
   misses, not restores. Tail policy is cache policy.

## Effects inside placeholder noise (no claim made)

- **Eviction policy ranking.** LRU/LFU/size-aware/GDSF stay within ~±20% p95
  of each other at base and swap order across traces and sensitivity levels
  (e.g. zipf base p95: size 103.1, lfu 103.2, gdsf 147.9, lru 150.0; low
  sensitivity flips lru ahead of gdsf). GDSF remains the structurally
  motivated candidate given the 0.1-100 GB / 5-450 s asymmetry, but the data
  does not rank it.
- **Top-K warm and pipeline prefetch.** Both help in their target regimes
  (warm after preemption wipes; prefetch on correlated sessions) but their
  net effect at base is within noise, and prefetch pays 40-50% more bytes
  moved. Both need measured demand/transition inputs to be judged.

## Reproduction

```bash
cd nim-fast-start/faststart-v2/catalog-sim
python3 run_simulation.py   # rewrites reports.json, summary.tsv, CHECKSUMS.json
```

Outputs are deterministic; `reports.json` and `summary.tsv` regenerate
byte-for-byte. This analysis file is hand-written and pinned to the run whose
trace checksums are in `../traces/CHECKSUMS.json`.
