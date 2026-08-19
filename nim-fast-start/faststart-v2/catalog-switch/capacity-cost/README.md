# Capacity, availability, and cost model across backends

This subtree reconciles the program's **measured** switch latency with real,
dated resource prices and live capacity availability, producing a cost/
capacity frontier for the internal Kubernetes snapshot backend versus
Cerebrium (the sole external comparator). Modal appears only as a dated
documentation appendix and is excluded from every computation.

## Provenance chain, strictly separated

| Class | What | Where |
|---|---|---|
| Raw captures | Read-only `nebius billing v1alpha1 calculator estimate` quotes (exit code, exact command, UTC timestamp, full response) and the quota-clipped `nebius capacity resource-advice list` dump | `inputs/raw/*.json`, produced by `inputs/raw/capture_quotes.sh` on 2026-08-19 |
| Price snapshot | Dated, sourced, versioned records: tenant calculator quotes (verbatim from raw), public list prices (URL + retrieval time), and explicit derivations | `inputs/price_snapshot.json`, built by `inputs/build_snapshots.py` |
| Capacity snapshot | Per region/platform/preset/fabric availability levels and quota-clipped counts with effective timestamps | `inputs/capacity_snapshot.json` |
| Measured inputs | Checksum-pinned pointers to the OpenFold2/Boltz2 fresh n=20 cohorts, the policy-simulator outputs, and COLD_START_METRICS; plus an explicitly labeled `assumptions` list and `unmeasured_backends` declarations | `inputs/measured_inputs.json` |
| Model | Decimal-exact cost math, percentiles, retry/preemption/break-even primitives, simulator repricing | `costmodel/lib.py` |
| Results | The frontier and break-even curves | `results/frontier.json`, `results/FRONTIER.md`, `results/breakeven.tsv`, built by `costmodel/build_frontier.py` |

## Fail-closed rules

- A measured file whose SHA-256 drifts aborts the build.
- Backends without program-measured latency (Cerebrium pending its blocked
  sibling benchmark, node-local VM pending its prototype's live cohort) get
  **no** latency, per-request cost, or rank — only their dated unit prices
  and a status. Modal gets not even prices, only the appendix pointer.
- The policy simulator's own `cost_usd` uses declared placeholder prices and
  is discarded; only its capacity outputs (reserved GPU-hours, GiB fetched,
  latency/goodput/hit-rate distributions) are consumed and re-priced with the
  sourced quotes.
- Every cost figure is emitted beside the p50/p95 and SLO goodput of the same
  evidence; no cost is published alone.
- No theoretical FLOPS, no unverified price equivalences: USD values are
  quoted strings from the calculator or a dated public page, multiplied with
  `decimal.Decimal`. Quotes are point-in-time prices, not invoices — billing
  increments, minimums, discounts, and taxes are out of scope, matching
  `performance/cost-ledger` semantics.

## Regeneration and tests

```bash
# from nim-fast-start/faststart-v2
python3 catalog-switch/capacity-cost/inputs/build_snapshots.py   # from raw/
python3 catalog-switch/capacity-cost/costmodel/build_frontier.py # offline
cd catalog-switch/capacity-cost && python3 -m unittest discover tests
```

Both builders are deterministic (no runtime clocks or randomness); the test
suite asserts the committed results regenerate byte-identically, that tenant
quote records match their raw evidence, that public list prices cross-check
the tenant quotes, that unmeasured backends stay fail-closed, and that Modal
never receives a priced or ranked row.

## Headline results (see results/FRONTIER.md for the full tables)

- Measured switch cost on the quoted 1x H100 (eu-north1): OpenFold2 p95
  17.63 s -> $0.0105 preemptible / $0.0189 on-demand per switch; Boltz2 p95
  30.31 s -> $0.0181 / $0.0324. Boltz2's 20 s goodput is honestly 0.0000.
- Preemptible stops paying above a per-attempt loss probability of ~0.44
  (H100/B200) to ~0.46 (H200) — far above anything observed (0/40 failed
  attempts across both cohorts).
- One dedicated warm H100 ($2,810.50/month quoted) beats pay-per-switch only
  above ~267k requests/month for OpenFold2 (preemptible switching) down to
  ~87k for Boltz2 (on-demand switching) — upper bounds that assume every
  request pays a full switch.
- Storage: SFS at the quoted ~$0.08/GiB-month beats object storage
  ($0.0147/GiB-month) once a GiB is re-fetched more than ~4.35 times/month
  under egress-billed accounting; if intra-cloud object reads are unbilled,
  object storage always wins on cost and the decision is latency-only.
- Repriced simulator frontier (adversarial trace, base sensitivity): the
  best snapshot policies cost ~$107–120 per 1,000 completed requests on
  preemptible quotes with p95 ≈ 121–128 s, versus ~$219 and p95 ≈ 3,149 s for
  the conventional baseline — snapshot switching dominates on both axes.
