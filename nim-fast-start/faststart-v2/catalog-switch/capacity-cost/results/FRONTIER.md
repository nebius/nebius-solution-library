# Capacity/cost frontier v7 (as of 2026-08-19)

Corrected candidate v7. Prepared versus request-triggered cost classes with explicit amortization; model-scoped inputs stay model-scoped (the OpenFold2 capture assumption is never applied to Boltz2); unmeasured relocation is separated from the measured cold-switch lower bound and emitted under both egress variants; complete totals and incomplete lower-bound subtotals are published in disjoint collections spanning the capture-reuse grid with nominal and pessimistic monthly values; the preemption sweep exposes its full grid with exact-Decimal strategy selection and explicit exact ties (p=0 ties preemptible-only with the fallback rather than crowning one winner); capacity curves price the L1 cache tier's storage from the captured node-disk quotes alongside GPU and egress; COMPLETE dedicated rows are additionally gated on captured quota-clipped availability (a plan needing more nodes than any single fabric offered at capture is demoted to a lower-bound subtotal) and every cost row pairs with the latency/p99/goodput/error evidence that sized it; rows missing a required component carry null complete totals and null decisions, publishing only explicitly-named lower-bound subtotals on which ranking and break-even decisions are forbidden; idle/reserved GPU capacity is explicitly allocated in the dedicated_prepared_node capacity model (whole-instance monthly quotes, node counts, utilization), while the marginal zero-idle bound is always an incomplete lower bound and the warm-vs-switch break-even is published only as a decision-forbidden upper bound; public prices are hash-bound to archived payloads whose exact fetch timestamps are the recorded retrieval times; all composite arithmetic is exact with one quantization at emission. Cerebrium is PENDING_MEASUREMENT (prices only, never measured) and Modal documentation-only. Cost is always paired with the latency and goodput of the same evidence.

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

Boltz2 cold switch is a measured LOWER BOUND: 422.854590 s preparation (local SFS cache read) + 30.310246 s p95 switch = 14.951x the prepared-switch cost at reuse=1; the amortization grid (reuse 1/2/5/10/50) is in frontier.json. Relocating the measured 27.550541 GiB from object storage is a SEPARATE UNMEASURED add-on: 0.413258 USD egress-billed / 0 USD egress-free per preparation, duration unmeasured.
OpenFold2 cold switch and all node-provision-miss rows are fail-closed PENDING_MEASUREMENT. Snapshot capture cost (272.426 s, snapshot_capture_seconds_of2) applies to OpenFold2 only; Boltz2 rows exclude it fail-closed.

## Per-success and monthly cost under explicit capacity models

Capacity model A, dedicated_prepared_node: idle and reserved GPU capacity fully allocated as whole dedicated H100 instance(s) (nodes = ceil(busy-seconds / node-month), whole monthly instance quotes charged, utilization shown). COMPLETE only where every component is available; Boltz2 capture is unavailable, so its dedicated rows are lower-bound subtotals (>=). Capacity model B, marginal_zero_idle_bound: only measured request/prep GPU seconds plus fixed overheads — ALWAYS an INCOMPLETE_LOWER_BOUND because idle/reserved capacity is unallocated by construction; ranking and break-even decisions are FORBIDDEN on every lower-bound row. Shared-pool allocation with contention is placeholder-derived and lives in the simulation frontier, where reserved GPU-hours are charged in full.

### A: dedicated prepared node(s) (sample: preemptible, OpenFold2 at R=100)

| Model | Completeness | D req/mo | Nodes | Feasibility (max avail) | Utilization | Per-success | Monthly nom/pess |
|---|---|---:|---:|---|---:|---:|---:|
| OpenFold2 | COMPLETE | 10000 | 1 | FEASIBLE (76) | 0.065839 | 0.198587 | 1985.87 / 1985.87 |
| OpenFold2 | COMPLETE | 100000 | 1 | FEASIBLE (76) | 0.658392 | 0.021323 | 2132.29 / 2132.29 |
| OpenFold2 | COMPLETE | 1000000 | 7 | FEASIBLE (76) | 0.940560 | 0.013014 | 13013.58 / 14583.08 |
| Boltz2 | INCOMPLETE_LOWER_BOUND | 10000 | 1 | FEASIBLE (76) | 0.109940 | >= 0.196960 | >= 1969.60 / >= 1969.60 |
| Boltz2 | INCOMPLETE_LOWER_BOUND | 100000 | 2 | FEASIBLE (76) | 0.549700 | >= 0.035391 | >= 3539.10 / >= 3539.10 |
| Boltz2 | INCOMPLETE_LOWER_BOUND | 1000000 | 11 | FEASIBLE (76) | 0.999455 | >= 0.017665 | >= 17664.60 / >= 20803.60 |

### B: marginal zero-idle sharing bound (sample: 100k req/mo, preemptible; every row is a lower-bound subtotal, no decisions)

| Model | Class | GPU p50 | Capture | Fixed share | Per-success | Monthly nom/pess | +Relocation (billed/free) |
|---|---|---:|---:|---:|---:|---:|---|
| OpenFold2 | prepared_switch | 0.010333 | 0.001627 | 0.004001 | >= 0.015961 | >= 1596.14 / >= 1778.50 | n/a |
| Boltz2 | prepared_switch | 0.017255 | unavailable | 0.004001 | >= 0.021256 | >= 2125.60 / >= 2430.11 | n/a |
| Boltz2 | cold_switch (reuse=1) | 0.269793 | unavailable | 0.004001 | >= 0.273794 | >= 27379.42 / >= 32140.48 | >= 0.687052 / >= 0.273794 |
| Boltz2 | cold_switch (reuse=10) | 0.042509 | unavailable | 0.004001 | >= 0.046510 | >= 4650.99 / >= 5401.14 | >= 0.087836 / >= 0.046510 |

Full grids (capture-reuse 1/10/100/1000, demand, reuse, both offers, pessimistic monthly, both egress variants for the relocation add-on) are in frontier.json and breakeven.tsv.

## Preemption / fallback sweep (prepared switch, per success, full grid)

one preemptible attempt, then one on-demand attempt (on_demand_loss_negligible assumption); expected extra latency = p * attempt p95. The fallback is cheaper than on-demand-only ONLY below the platform break-even p* = 1 - pre/od; above p* (e.g. p=0.60 on H100) on-demand-only is the cheapest strategy and the fallback's remaining value is bounding latency to one extra attempt.

Break-even loss probability: gpu-b200-sxm 0.44755245, gpu-h100-sxm 0.44155844, gpu-h200-sxm 0.45555556

| Model | p(loss) | Preemptible-only | Pre-then-OD fallback | On-demand | Cheapest |
|---|---:|---:|---:|---:|---|
| OpenFold2 | 0.00 | 0.010529 | 0.010529 | 0.018854 | exact tie: fallback_pre_then_od = preemptible_only |
| OpenFold2 | 0.05 | 0.011083 | 0.011472 | 0.018854 | preemptible_only |
| OpenFold2 | 0.10 | 0.011699 | 0.012414 | 0.018854 | preemptible_only |
| OpenFold2 | 0.20 | 0.013161 | 0.014300 | 0.018854 | preemptible_only |
| OpenFold2 | 0.30 | 0.015041 | 0.016185 | 0.018854 | preemptible_only |
| OpenFold2 | 0.44155844 | 0.018854 | 0.018854 | 0.018854 | preemptible_only |
| OpenFold2 | 0.60 | 0.026322 | 0.021841 | 0.018854 | on_demand_only |
| Boltz2 | 0.00 | 0.018102 | 0.018102 | 0.032415 | exact tie: fallback_pre_then_od = preemptible_only |
| Boltz2 | 0.05 | 0.019055 | 0.019723 | 0.032415 | preemptible_only |
| Boltz2 | 0.10 | 0.020113 | 0.021343 | 0.032415 | preemptible_only |
| Boltz2 | 0.20 | 0.022627 | 0.024585 | 0.032415 | preemptible_only |
| Boltz2 | 0.30 | 0.025860 | 0.027826 | 0.032415 | preemptible_only |
| Boltz2 | 0.44155844 | 0.032415 | 0.032415 | 0.032415 | preemptible_only |
| Boltz2 | 0.60 | 0.045255 | 0.037551 | 0.032415 | on_demand_only |

## Regional capacity loss fallbacks (eu-north1 preemptible H100 pool unavailable (regional capacity loss); options priced from the snapshot, availability from the capacity capture)

| Option | USD/h | Availability at capture | Relocation |
|---|---:|---|---|
| same-region on-demand H100 | 3.85 | AVAILABILITY_LEVEL_HIGH,AVAILABILITY_LEVEL_LOW | none (same nodes/storage) |
| same-region H200 preemptible | 2.45 | AVAILABILITY_LEVEL_HIGH | same region; storage reattach, no cross-region artifact transfer |
| cross-region B200 preemptible (us-central1) | 3.95 | AVAILABILITY_LEVEL_HIGH | measured Boltz2 artifact+cache 27.550541 GiB; egress-billed 0.413258 USD, egress-free 0 USD, per node (unmeasured duration) |

UNMEASURED for cross-region and cross-platform fallbacks (cross_region_relocalization assumption); these rows carry cost and capacity only.

## Isolated top-K and cache curves (placeholder-derived simulation)

Each sweep varies exactly one axis at base placeholders on the committed traces (checksums asserted). The +L1 storage columns price the node-local cache capacity itself from the captured disk quotes (non-replicated and network SSD per-GiB-hour). Zipf family shown; all five families are in frontier.json.

| Axis | Value | p95 s | ≤60s goodput | USD/1k (pre, billed) | USD/1k +L1 storage (NRD / NSSD) |
|---|---:|---:|---:|---:|---|
| warm_top_k | 1 | 101.3 | 0.909 | 99.07307 | 99.82384 / 100.0837 |
| warm_top_k | 2 | 119.0 | 0.907 | 100.1422 | 100.8929 / 101.1528 |
| warm_top_k | 4 | 109.1 | 0.906 | 98.57184 | 99.32260 / 99.58248 |
| warm_top_k | 8 | 107.8 | 0.914 | 99.16424 | 99.91500 / 100.1748 |
| warm_top_k | 16 | 102.6 | 0.910 | 102.9310 | 103.6818 / 103.9417 |
| l1_capacity_gib | 150 | 148.2 | 0.882 | 126.3548 | 126.6364 / 126.7338 |
| l1_capacity_gib | 200 | 144.1 | 0.891 | 117.1079 | 117.4833 / 117.6132 |
| l1_capacity_gib | 400 | 150.0 | 0.887 | 106.5039 | 107.2547 / 107.5146 |
| l1_capacity_gib | 800 | 103.3 | 0.912 | 99.10383 | 100.6053 / 101.1251 |
| l1_capacity_gib | 1600 | 103.3 | 0.912 | 99.05171 | 102.0547 / 103.0942 |

Knees (smallest value within 2% of best p95 per family): adversarial: K=4; bursty: K=4; correlated: K=1; uniform: K=1; zipf: K=1 | cache: adversarial: 400 GiB; bursty: 800 GiB; correlated: 800 GiB; uniform: 400 GiB; zipf: 800 GiB

## Unmeasured backends (fail-closed)

| Backend | Status |
|---|---|
| Cerebrium | PENDING_MEASUREMENT (prices only, never measured) |
| Node-local VM | PENDING_MEASUREMENT |
| Modal | EXCLUDED_DOCUMENTATION_ONLY |

Storage: SFS 0.079999970 vs object 0.0147 USD/GiB-month; egress-billed break-even 4.3533 refetches/GiB-month.

Full detail: `frontier.json`; grid tables: `breakeven.tsv`; isolated sweep raw points: `sweeps.json`.
