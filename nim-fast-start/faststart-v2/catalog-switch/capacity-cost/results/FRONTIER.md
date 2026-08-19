# Capacity/cost frontier (as of 2026-08-19)

Measured internal Kubernetes snapshot backend versus Cerebrium (sole external comparator, latency pending) with Modal excluded as documentation-only. Every USD value traces to a dated record in inputs/price_snapshot.json and every latency to a checksum-pinned measured artifact. Cost values are always paired with the p50/p95 and SLO goodput of the same evidence.

## Measured internal Kubernetes snapshot backend (1x H100, eu-north1)

| Model | n | p50 s | p95 s | ≤20s | ≤30s | ≤60s | switch cost p95 pre / od (USD) |
|---|---:|---:|---:|---:|---:|---:|---|
| OpenFold2 | 20 | 17.3025 | 17.6298 | 1.0000 | 1.0000 | 1.0000 | 0.010529 / 0.018854 |
| Boltz2 | 20 | 28.8922 | 30.3102 | 0.0000 | 0.9000 | 1.0000 | 0.018102 / 0.032415 |

Failed-attempt denominators are the measured 0/20; the pessimistic column in frontier.json applies the rule-of-three ×1.176 bound.

H100 availability at capture (quota-clipped, per fabric): fabric-2 od=HIGH pre=HIGH (76/128); fabric-3 od=HIGH pre=HIGH (76/128); fabric-4 od=HIGH pre=MEDIUM (67/128); fabric-6 od=LOW pre=MEDIUM (46/128).

Snapshot capture (assumption-flagged, per capture): 272.426 s -> 0.162699 USD preemptible / 0.291344 USD on-demand.

## Unmeasured backends (fail-closed)

| Backend | Status | Dated price basis |
|---|---|---|
| Cerebrium | PENDING_MEASUREMENT | H100 3.3984, H200 4.1976, B200 6.012 USD/GPU-h equivalent + 100 USD/mo plan |
| Node-local VM | PENDING_MEASUREMENT | same Nebius instance quotes as internal |
| Modal | EXCLUDED_DOCUMENTATION_ONLY | MODAL_APPENDIX.md only |

## Break-even summary

Preemption loss probability where preemptible stops paying: gpu-b200-sxm 0.44755245, gpu-h100-sxm 0.44155844, gpu-h200-sxm 0.45555556

| Model | Switch offer | Per-switch p95 USD | Warm break-even req/mo |
|---|---|---:|---:|
| OpenFold2 | preemptible | 0.010529 | 266929.43 |
| OpenFold2 | on_demand | 0.018854 | 149066.51 |
| Boltz2 | preemptible | 0.018102 | 155259.09 |
| Boltz2 | on_demand | 0.032415 | 86703.69 |

Storage: SFS 0.079999970 vs object 0.0147 USD/GiB-month; egress-billed break-even 4.3533 refetches/GiB-month; egress-free variant favors object storage on cost at any rate.

## Repriced simulator frontier (base sensitivity, adversarial trace)

| Policy | p95 s | ≤60s goodput | USD/1k req (pre, egress-billed) | USD/1k req (od, egress-billed) |
|---|---:|---:|---:|---:|
| conventional+shortest-switch-cost+lru | 3148.7 | 0.031 | 218.9020 | 291.8698 |
| snapshot+least-loaded+lru | 951.5 | 0.216 | 337.4256 | 391.3292 |
| snapshot+shortest-switch-cost+gdsf | 122.0 | 0.877 | 107.8294 | 153.2056 |
| snapshot+shortest-switch-cost+lfu | 128.6 | 0.852 | 119.4163 | 164.3137 |
| snapshot+shortest-switch-cost+lru | 127.7 | 0.864 | 116.9398 | 161.8435 |
| snapshot+shortest-switch-cost+lru+bounded-queue | 121.0 | 0.867 | 106.9864 | 152.5983 |
| snapshot+shortest-switch-cost+lru+pipeline-next | 121.7 | 0.869 | 163.8817 | 208.9532 |
| snapshot+shortest-switch-cost+lru+topk-adaptive-k8 | 126.1 | 0.857 | 114.6747 | 159.9858 |
| snapshot+shortest-switch-cost+size | 121.7 | 0.894 | 115.1898 | 160.9629 |

Full detail, every sensitivity/trace/policy and both egress variants: `frontier.json`. Demand-grid and warm-pool tables: `breakeven.tsv`.
