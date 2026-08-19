# Capacity/cost frontier v2 (as of 2026-08-19)

Corrected candidate. Prepared versus request-triggered cost classes with explicit amortization; measured and placeholder-derived provenance separated end to end; preemption/regional-loss/fallback sweeps consume their assumption grids; per-success and monthly totals include GPU, capture amortization, traffic, fixed SFS/controller, and retry sensitivity. Cerebrium stays PENDING_MEASUREMENT and Modal documentation-only. Every USD value traces to a dated record in inputs/price_snapshot.json (public records hash-bound to archived payloads) and every latency to a checksum-pinned measured artifact; cost is always paired with the latency and goodput of the same evidence.

## Measured cost classes (1x H100, eu-north1)

| Model | Class | Status | p50 s | p95 s | ≤30s | cost p95 pre / od (USD) |
|---|---|---|---:|---:|---:|---|
| OpenFold2 | warm_hit | MEASURED | 1.015083 | 1.032614 | 1.0000 | 0.000606 / 0.001086 |
| OpenFold2 | prepared_switch | MEASURED | 17.302540 | 17.629887 | 1.0000 | 0.010529 / 0.018854 |
| OpenFold2 | cold_switch | PENDING_MEASUREMENT | — | — | — | — |
| OpenFold2 | node_provision_miss | PENDING_MEASUREMENT | — | — | — | — |
| Boltz2 | warm_hit | MEASURED | 0.282071 | 0.300494 | 1.0000 | 0.000168 / 0.000302 |
| Boltz2 | prepared_switch | MEASURED | 28.892235 | 30.310246 | 0.9000 | 0.018102 / 0.032415 |
| Boltz2 | cold_switch (reuse=1) | MEASURED_LOWER_BOUND | — | 453.16483 | — | 0.270640 / 0.484635 |
| Boltz2 | node_provision_miss | PENDING_MEASUREMENT | — | — | — | — |

Boltz2 cold switch is a measured LOWER BOUND: 422.854590 s preparation + 30.310246 s p95 switch = 14.951x the prepared-switch cost at reuse=1; the amortization grid (reuse 1/2/5/10/50) is in frontier.json.
OpenFold2 cold switch and all node-provision-miss rows are fail-closed PENDING_MEASUREMENT.

## Fully-loaded per-success cost (sample: 100k req/month, preemptible, nominal)

| Model | Class | GPU p50 | Capture(R=100) | Traffic | Fixed share | Total | Monthly |
|---|---|---:|---:|---:|---:|---:|---:|
| OpenFold2 | prepared_switch | 0.010333 | 0.001627 | 0.000000 | 0.004001 | 0.015961 | 1596.10 |
| Boltz2 | prepared_switch | 0.017255 | 0.001627 | 0.000000 | 0.004001 | 0.022883 | 2288.30 |
| Boltz2 | cold_switch (reuse=1) | 0.269793 | 0.001627 | 0.413258 | 0.004001 | 0.688679 | 68867.90 |
| Boltz2 | cold_switch (reuse=10) | 0.042509 | 0.001627 | 0.041326 | 0.004001 | 0.089463 | 8946.30 |

Retry sensitivity: pessimistic totals apply the rule-of-three x1.176 bound to the GPU components (full grid in frontier.json).

## Preemption / fallback sweep (prepared switch, per success)

Break-even loss probability: gpu-b200-sxm 0.44755245, gpu-h100-sxm 0.44155844, gpu-h200-sxm 0.45555556

| Model | p(loss) | Preemptible-only | Pre-then-OD fallback | On-demand |
|---|---:|---:|---:|---:|
| OpenFold2 | 0.00 | 0.010529 | 0.010529 | 0.018854 |
| OpenFold2 | 0.10 | 0.011699 | 0.012414 | 0.018854 |
| OpenFold2 | 0.30 | 0.015041 | 0.016185 | 0.018854 |
| OpenFold2 | 0.44155844 | 0.018854 | 0.018854 | 0.018854 |
| Boltz2 | 0.00 | 0.018102 | 0.018102 | 0.032415 |
| Boltz2 | 0.10 | 0.020113 | 0.021344 | 0.032415 |
| Boltz2 | 0.30 | 0.025860 | 0.027826 | 0.032415 |
| Boltz2 | 0.44155844 | 0.032415 | 0.032415 | 0.032415 |

## Regional capacity loss fallbacks (eu-north1 preemptible H100 pool unavailable (regional capacity loss); options priced from the snapshot, availability from the capacity capture)

| Option | USD/h | Availability at capture | Relocalization |
|---|---:|---|---|
| same-region on-demand H100 | 3.85 | AVAILABILITY_LEVEL_HIGH,AVAILABILITY_LEVEL_LOW | none (same nodes/storage) |
| same-region H200 preemptible | 2.45 | AVAILABILITY_LEVEL_HIGH | same region; storage reattach, no cross-region artifact transfer |
| cross-region B200 preemptible (us-central1) | 3.95 | AVAILABILITY_LEVEL_HIGH | measured Boltz2 artifact+cache 27.550541 GiB; egress-billed 0.413258 USD, egress-free 0 USD, per node |

UNMEASURED for cross-region and cross-platform fallbacks (cross_region_relocalization assumption); these rows carry cost and capacity only.

## Isolated top-K and cache curves (placeholder-derived simulation)

Each sweep varies exactly one axis at base placeholders on the committed traces (checksums asserted). Zipf family shown; all five families are in frontier.json.

| Axis | Value | p95 s | ≤60s goodput | USD/1k (pre, egress-billed) |
|---|---:|---:|---:|---:|
| warm_top_k | 1 | 101.3 | 0.909 | 99.07307 |
| warm_top_k | 2 | 119.0 | 0.907 | 100.1422 |
| warm_top_k | 4 | 109.1 | 0.906 | 98.57184 |
| warm_top_k | 8 | 107.8 | 0.914 | 99.16424 |
| warm_top_k | 16 | 102.6 | 0.910 | 102.9310 |
| l1_capacity_gib | 150 | 148.2 | 0.882 | 126.3548 |
| l1_capacity_gib | 200 | 144.1 | 0.891 | 117.1079 |
| l1_capacity_gib | 400 | 150.0 | 0.887 | 106.5039 |
| l1_capacity_gib | 800 | 103.3 | 0.912 | 99.10383 |
| l1_capacity_gib | 1600 | 103.3 | 0.912 | 99.05171 |

Knees (smallest value within 2% of best p95 per family): adversarial: K=4; bursty: K=4; correlated: K=1; uniform: K=1; zipf: K=1 | cache: adversarial: 400 GiB; bursty: 800 GiB; correlated: 800 GiB; uniform: 400 GiB; zipf: 800 GiB

## Unmeasured backends (fail-closed)

| Backend | Status |
|---|---|
| Cerebrium | PENDING_MEASUREMENT |
| Node-local VM | PENDING_MEASUREMENT |
| Modal | EXCLUDED_DOCUMENTATION_ONLY |

Storage: SFS 0.079999970 vs object 0.0147 USD/GiB-month; egress-billed break-even 4.3533 refetches/GiB-month.

Full detail: `frontier.json`; grid tables: `breakeven.tsv`; isolated sweep raw points: `sweeps.json`.
