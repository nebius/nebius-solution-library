# Catalog-boundary storage and cache analysis

This offline package replaces the prepared-node interpretation with a strict
external-request boundary. It creates no resources and publishes no latency or
throughput measurement. Live execution remains disabled until cleanly committed
task-specific broker and bootstrap capability contracts are independently
approved together with the experiment plan.

## Mutually exclusive request states

| State | State at external T0 | Work charged inside request T0 | Classification |
|---|---|---|---|
| A | Exact model/artifact generation is already materialized on the selected node | No localization; inference still follows the shared ledger | Cache hit. Prehydration bytes/cost and residency bytes/seconds/cost are reported separately. |
| B | Immutable node-local seed exists, but no request-owned materialization exists | Clone/materialization, full-byte validation, first read, load/restore, and response | Unknown-model cold start only when every request-specific operation starts at or after T0. |
| C | Neither materialization nor node seed exists; immutable remote publication exists | Remote fetch, write, full-byte validation, first read, load/restore, and response | Remote artifact miss. |
| D | A different active model owns the selected GPU/node and the target is not materialized | Drain, GPU release, eviction/reclaim, B- or C-style target localization, load/restore, and response | Active A-to-B switch. |

The attempt validator rejects overlapping starting-state claims, any B-D
request operation before external T0, physical-byte total mismatches, mutable
namespace reuse, and dirty generation reuse. In particular, a prepared clone
cannot be labeled `unknown_model_cold_start`.

The bound request-SLO trace and ledger remain authoritative for T0, model/input
identity, terminal semantic response, GPU/cost accounting, failures, and
cleanup. This receipt only adds causal storage operations and read/write/network
/deleted byte counters. Phase-percentile summation remains forbidden.

## Source-pinned conclusions

The source manifest pins the reviewed request-SLO files, catalog commit, and
Boltz external-`/tmp` lifecycle commit. The available Boltz status observation
says each attempt copied/hashed 1,826,220,898 bytes for roughly 440--442 seconds
*before* admission/T0. That is prepared-clone evidence, not a request-bound
cold-start result. The package deliberately exposes no Boltz latency
distribution because the raw per-attempt external-T0 receipts are not present.

Local NVMe remains `unavailable-entitlement-not-proven`; Network SSD or Object
Storage must never be relabeled as local NVMe.

## Capacity and reuse projections

`analysis_config.json` analyzes a 200-model planning catalog with cache budgets,
top-K policies, and uniform/Zipf-like reuse exponents. Its two homogeneous size
profiles come from the pinned 145 known-positive canonical model footprints;
55 models are explicitly imputed. It also retains the catalog's known-byte
lower bound and a separately labeled row-level high planning ceiling. These are
capacity projections, not benchmark results.

`results/capacity-summary.json` is the checked-in compact result: the homogeneous
median profile needs 1.577 TiB for 200 models and the p90 profile needs 2.449
TiB. A 1 TiB cache fits 126 or 81 models respectively. The complete 48-point
top-K/reuse curve and 162-point A-D state-mix grid are emitted by the analyzer;
the summary retains representative points and is regression-checked against
the generated result. The pinned 2026-08-19 broker profile prices Network SSD
residency at $0.071/GiB-month and Object Storage publication at
$0.0147/GiB-month: the two full-catalog profiles project $114.65/$23.74 and
$178.05/$36.86 per month respectively. Request-triggered prehydration
transfer/compute remains a separate receipt field and is not invented offline.

Run from `nim-fast-start/faststart-v2`:

```bash
python3 -m performance.storage_cache_matrix.catalog_boundary_analysis.cli \
  verify-sources --repo-root ../..
python3 -m performance.storage_cache_matrix.catalog_boundary_analysis.cli \
  analyze --output performance/storage_cache_matrix/catalog_boundary_analysis/results/capacity-sensitivity.json
python3 -m unittest discover -v \
  performance/storage_cache_matrix/catalog_boundary_analysis/tests
```

Add `--task-deck-root /home/tux/dashboard/data` to `verify-sources` to verify the
pinned manager observation is still present. `validate-attempts` is the future
live-receipt gate; it validates canonical JSON Lines against the source manifest
and exact request-SLO evidence root.
