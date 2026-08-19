# Catalog switch policy simulator

A deterministic, trace-driven discrete-event simulator for a ~200-model
inference catalog served by a preemptible GPU fleet. It compares routing/
placement, L1 cache eviction, warm-capacity, admission, and prefetch policies
under uniform, skewed (Zipf-like), bursty, correlated (pipeline), and
adversarial demand, and reports tail latency, SLO goodput, hit rates, cache
churn, bytes moved, reserved GPU-hours, failures, and cost.

This is task `catalog-switch-policy-simulator` under the
`catalog-fast-switch-architecture-program` epic. It is an **offline modeling
deliverable**: no cloud resources, GPUs, clusters, or live endpoints are used
or touched. All results here are **provisional planning evidence, not product
SLO claims** — see the scope limits below and `HANDOFF.md`.

## Provenance discipline: measured vs placeholder

Every input is one of:

- **Measured** — backed by retained faststart-v2 evidence, with a mandatory
  source reference:
  - OpenFold2 and Boltz2 fresh fail-closed n=20 cohorts, loaded directly from
    `performance/openfold2/fresh-cohort-n20-results.tsv` and
    `boltz2-native/fresh-cohort-n20-results.tsv` (conservative CLOCK_BOOTTIME
    upper readiness clock, exact response-boundary call timers);
  - the nine production-shaped n=3 lanes from
    `performance/COLD_START_METRICS.md`, whose published
    `median [minimum-maximum]` triples with n=3 *are* the complete sample
    sets, embedded exactly in `catalog_sim/measured.py`;
  - measured artifact byte counts and pre-T0 full-read (prewarm) times from
    the same document's storage audit;
  - Evo2-40B, carried only with its `manual/provisional` evidence class.
- **Placeholder** — everything else, declared through
  `schema.PlaceholderQuantity` with a **mandatory bounded sensitivity range**
  (`low < high`) and a rationale. This includes the 190 synthetic catalog
  rows (bounded scale factors applied to anchor shapes; their distributions
  carry `provenance="placeholder"`), L2 fetch bandwidth, L1 capacity, GPU
  release/drain time, conventional-load init and ingest bandwidth (only MSA
  Search's conventional cached start is measured), preemption MTBF,
  reprovision time, and prices.

Scaled distributions are demoted to placeholder provenance by construction
(`EmpiricalDist.scaled`), so an inferred distribution can never masquerade as
a measurement. `results/reports.json` embeds the full placeholder table with
the selected sensitivity level per run.

### Replacing placeholders with measurements later

`catalog_sim/adapters.py` accepts a versioned `measured-overrides` JSON
document (per-model phase sample arrays, artifact bytes/digest, full-read
time, plus optional measured fleet scalars). Applying it swaps measured
distributions in for placeholder rows **without changing engine semantics** —
the engine only ever reads `CatalogModel` fields and the resolved fleet dict.
This is the integration point for the catalog-inventory and
request-SLO-harness tasks; simulation reruns then requalify the comparison on
measured inputs.

## Model

- Time is integer microseconds end to end (`catalog_sim/units.py`); event
  arithmetic is exact and replayable, and all randomness flows from explicit
  seeds. No wall clock is read anywhere.
- Per request, causally ordered: external arrival (T0) -> placement -> queue
  wait -> drain/GPU release -> L2 artifact fetch (if L1 miss) -> local
  prewarm full-read (first touch per node, if the lane requires prewarm) ->
  snapshot restore (empirical readiness sample) or conventional load ->
  first-request inference (call 1) or warm inference (call 2). Completion is
  the response boundary, mirroring the shared metric contract's
  T0-to-complete-response clock shape.
- Cache tiers: **L0** = model resident on the node GPU (hot hit, call-2
  path); **L1-warm** = artifact node-local and page-warm; **L1-cold** =
  node-local but never prewarmed on this node; **L2** = remote, must fetch.
- Preemptible failures (Poisson, placeholder MTBF) wipe a node's L0/L1 state,
  cancel in-flight work, and force retries (max 3, then the request is a
  visible failure); reprovision takes placeholder time.
- Warm capacity: `topk-adaptive` pins the K hottest models of a trailing
  window to distinct nodes and proactively restores them when idle; the GPU
  time spent is accounted as reserved-but-not-serving warm-setup hours.
- Failed/rejected requests are sorted **after** successes in the percentile
  denominator (nearest-rank, matching `aggregate_fresh_cohort.py`), so a
  policy cannot improve its tail by dropping requests: a p95 that lands on a
  dropped request reports `unbounded`.

Known simplifications (all conservative-or-labeled): homogeneous H100-class
nodes (the Evo2 anchor's H200 requirement is flattened — placeholder);
prefetch bandwidth does not contend with the foreground fetch; one GPU and
one resident model per node; artifact versions are fixed per run (staleness
is enforced as an invariant, exercised in tests, not injected by traces).

## Invariants (enforced at runtime, not just in tests)

`InvariantViolation` aborts a run on: time moving backwards or negative
phases/waits, non-causal per-request timestamps, L1 over capacity or
accounting drift, busy time exceeding online time (no free capacity), serving
from an artifact whose digest differs from the catalog identity (no stale
artifacts), and request-conservation failures (every arrival must end
completed, rejected, or failed — no omitted requests).

## Traces

Five families (`catalog_sim/traces.py`), all deterministic with SHA-256
checksums pinned in `traces/CHECKSUMS.json` and verified by the test suite:
`uniform`, `zipf` (skewed, exponent 1.1 over a shuffled ranking), `bursty`
(alternating quiet/burst intervals at 0.5x/4x the mean rate), `correlated`
(four-stage pipeline sessions, e.g. MSA -> fold -> design shapes), and
`adversarial` (two disjoint working sets alternating every 240 s to maximize
switch thrash).

## Running

```bash
cd nim-fast-start/faststart-v2/catalog-sim
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v tests   # 60 tests
python3 run_simulation.py            # full matrix -> results/, traces/
python3 run_simulation.py --quick    # 30-minute-horizon smoke matrix
```

The generated artifacts (`results/reports.json`, `results/summary.tsv`,
`traces/CHECKSUMS.json`) are byte-for-byte reproducible by re-running
`run_simulation.py` (no timestamps or machine state in outputs);
`results/RESULTS.md` is the hand-written analysis of that run.

## Validation

- Closed-form D/D/1 and switch-sequence tests assert **exact** equality of
  waits, phase durations, and end-to-end latencies (integer-microsecond
  arithmetic makes this possible).
- Calibration tests reproduce the published cohort aggregates from the loaded
  inputs: OpenFold2 n=20 readiness BOOTTIME-upper p50/p95/max
  14.342258/14.671991/15.099141 s, Boltz2 27.070530/28.429408/29.095697 s,
  and all seven embedded n=3 lane medians.
- Property tests cover every eviction policy, pinning, admission bounds,
  failure/retry conservation, stale-artifact refusal, and adapter behavior.

## Scope limits

Per manager guidance (2026-08-19): the 190 synthetic catalog rows and every
inferred distribution stay placeholder-only, and **no production policy
ranking is claimed** until the catalog inventory
(`catalog-switch-model-inventory`) and the shared request-SLO harness
schema (`catalog-switch-request-slo-harness`) land. `results/RESULTS.md`
reports provisional policy *sensitivities* and hands candidate policies plus
the online telemetry needed to validate them to the router/runtime tasks
(`HANDOFF.md`).
