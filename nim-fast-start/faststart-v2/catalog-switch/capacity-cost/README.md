# Capacity, availability, and cost model across backends (v2)

This subtree reconciles the program's **measured** switch latency with real,
dated resource prices and live capacity availability, producing a cost/
capacity frontier for the internal Kubernetes snapshot backend versus
Cerebrium (the sole external comparator). Modal appears only as a dated
documentation appendix and is excluded from every computation.

v2 is the corrected candidate after the independent review of `7f6e1080`
(preserved unchanged in history): prepared-versus-request-triggered cost
classes with amortization, strict measured/simulation provenance separation,
consumed preemption/regional-loss/fallback sweeps, complete per-success and
monthly totals, isolated top-K/cache curves, hash-bound archived public
inputs, and a parameterized capture script.

## Provenance chain, strictly separated

| Class | What | Where |
|---|---|---|
| Raw captures | Read-only `nebius billing v1alpha1 calculator estimate` quotes (exit code, exact command, UTC timestamp, full response) and the quota-clipped `nebius capacity resource-advice list` dump | `inputs/raw/*.json`, produced by `inputs/raw/capture_quotes.sh` on 2026-08-19 (profile/tenant/projects parameterized via env; committed evidence used the defaults: H100/H200/CPU/storage in eu-north1, B200 in us-central1) |
| Archived public payloads | Raw HTML of nebius.com/prices, cerebrium.ai/pricing, and modal.com/pricing with SHA-256 + retrieval time in `sources_manifest.json`; every transcribed price string is literally present in its payload, so the snapshot is offline-verifiable | `inputs/raw/sources/` |
| Price snapshot | Dated, sourced, versioned records: tenant calculator quotes (verbatim from raw), public list prices (URL + retrieval time + `archived_payload` hash binding), and explicit derivations | `inputs/price_snapshot.json`, built by `inputs/build_snapshots.py` (verifies hashes and price-string presence at build time) |
| Capacity snapshot | Per region/platform/preset/fabric availability levels and quota-clipped counts with effective timestamps | `inputs/capacity_snapshot.json` |
| Measured inputs | Checksum-pinned artifacts only: OpenFold2/Boltz2 fresh n=20 cohorts (switch and warm-hit metrics) and Boltz2's pre-T0 cache full read | `inputs/measured_inputs.json` `measured` section |
| Simulation inputs | Placeholder-derived, never measurement: the legacy catalog-sim matrix and the isolated K/cache sweeps, both checksum-pinned with explicit `input_provenance` | `inputs/measured_inputs.json` `simulation` section |
| Assumptions | Labeled grids and conventions (prep reuse, capture amortization, preemption loss, demand, egress attribution, ...) with basis and why-not-measured | `inputs/measured_inputs.json` `assumptions` section |
| Model | Decimal-exact cost math, percentiles, retry/preemption/fallback/break-even primitives, simulator repricing | `costmodel/lib.py` |
| Isolated sweeps | `costmodel/run_sweeps.py` runs the simulator varying exactly one axis (warm-K 1/2/4/8/16; L1 cache 150–1600 GiB, floor set by the largest 143.19 GiB catalog artifact) at base placeholders on the committed traces (checksums asserted) | `results/sweeps.json` |
| Results | Frontier, sweeps, and break-even curves | `results/frontier.json`, `results/FRONTIER.md`, `results/breakeven.tsv`, built by `costmodel/build_frontier.py` |

## Cost classes (prepared versus request-triggered)

Per model on the measured 1x H100:

- **warm_hit** — model already serving; measured second-call latency.
- **prepared_switch** — request-triggered switch on a prepared node
  (image resident, storage attached, pre-T0 preparation done); the n=20
  T0-to-second-response cohorts.
- **cold_switch** — request-triggered including pre-T0 preparation. Boltz2
  has a measured lower bound (422.854590 s cache full read → 14.951× the
  prepared-switch cost at reuse=1) amortized over the prep-reuse grid
  1/2/5/10/50; OpenFold2 is fail-closed PENDING_MEASUREMENT.
- **node_provision_miss** — declared, fail-closed PENDING_MEASUREMENT (the
  legacy new-node lane is fail-closed on this branch).

Fully-loaded per-success and monthly totals combine switch GPU, capture
amortization (grid 1/10/100/1000; headline R=100), preparation traffic under
both egress variants, the fixed SFS+controller share at each demand-grid
point, and nominal/pessimistic (rule-of-three) retry sensitivity.

## Fail-closed rules

- A pinned file (measured or simulation) whose SHA-256 drifts aborts the
  build; a public price whose string is absent from its archived payload
  aborts snapshot generation.
- Backends without program-measured latency (Cerebrium pending its blocked
  sibling benchmark, node-local VM pending its prototype's live cohort) get
  **no** latency, per-request cost, or rank — only dated unit prices and a
  status. Modal gets not even prices, only the appendix pointer. Unmeasured
  cost classes are declared the same way.
- Simulation is never labeled measured: the simulator's `cost_usd` uses
  declared placeholder prices and is discarded; only capacity outputs
  (reserved GPU-hours, GiB fetched, latency/goodput/hit-rate distributions)
  are consumed, re-priced with sourced quotes, and tagged with
  `input_provenance`.
- Every cost figure is emitted beside the latency/goodput of the same
  evidence; no cost is published alone. Quotes are point-in-time prices, not
  invoices — billing increments, minimums, discounts, and taxes are out of
  scope, matching `performance/cost-ledger` semantics.

## Regeneration and tests

```bash
# from nim-fast-start/faststart-v2
python3 catalog-switch/capacity-cost/inputs/build_snapshots.py   # from raw/
python3 catalog-switch/capacity-cost/costmodel/run_sweeps.py     # ~5 s
python3 catalog-switch/capacity-cost/costmodel/build_frontier.py # offline
cd catalog-switch/capacity-cost && python3 -m unittest discover tests
```

All builders are deterministic (no run-time clocks or randomness). The test
suite asserts byte-identical regeneration of the committed results, raw-quote
and archived-payload cross-validation, capture-script/evidence project
consistency, sweep isolation and single-point live regeneration, fail-closed
checksum drift, consumed assumption grids, and Modal/Cerebrium exclusion
rules.

## Headline results (results/FRONTIER.md has the full tables)

- Prepared switch on the quoted 1x H100 (eu-north1): OpenFold2 p95 17.63 s →
  $0.0105 preemptible / $0.0189 on-demand; Boltz2 p95 30.31 s → $0.0181 /
  $0.0324. Boltz2's 20 s goodput is honestly 0.0000.
- Boltz2 request-triggered **cold** switch (measured lower bound): 453.16 s
  and $0.27 preemptible at reuse=1, falling to ~$0.043 GPU at reuse=10.
- Preemptible stops paying above ~0.44 per-attempt loss (H100/B200) to ~0.46
  (H200); the pre-then-on-demand fallback stays at or below on-demand cost
  across the entire loss grid while bounding latency to one extra attempt.
- Fully loaded at 100k requests/month (preemptible, nominal): OpenFold2
  prepared $0.0160, Boltz2 prepared $0.0229, Boltz2 cold at reuse=1 $0.689
  per success — versus $3,210.60/month for one dedicated warm on-demand H100
  plus the same fixed SFS/controller overhead.
- Isolated sweeps (placeholder-derived simulation): warm-K knees at K=1–4
  depending on trace family; cache knees at 400–800 GiB, with cost per 1k
  requests falling from ~$126 (150 GiB) to ~$99 (800 GiB) on the Zipf trace.
- Storage: SFS ~$0.08/GiB-month beats object+egress above ~4.35
  refetches/GiB-month (egress-billed variant); if intra-cloud reads are
  unbilled, object always wins on cost and the decision is latency-only.
