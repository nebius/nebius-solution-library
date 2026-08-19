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

The v2 attempt validator is a full-ledger gate, not a sample-row checker. It
requires exactly one storage receipt for every request-SLO attempt, including
failures, and one shared external recorder clock identity. The selected node,
owner, broker lease, PVC, PV, provider volume, node seed, Object Storage object,
artifact version/digest/size, and cleanup IDs are joined to the authoritative
request-SLO ledger and typed ownership receipt. A receipt is rejected when it
invents an independent monotonic clock, omits a failure, inverts an operation,
or places B-D work outside T0.

Every executed operation and cleanup action has its own canonical typed JSON
receipt and content digest. Operation receipts carry exact resource UIDs and
physical read/write/network/deleted counters; `slo_bytes_moved` is assigned only
to the source localization operation and must exactly reconcile with both the
artifact size and request-SLO ledger. Dirty generations are tracked by physical
generation and writable-resource UIDs, so renaming a PVC, PV, volume, or clone
cannot make it reusable. Concurrent cohorts require a real localization
interval overlap on the shared recorder clock and distinct mutable namespaces.
In particular, a prepared clone cannot be labeled
`unknown_model_cold_start`.

The bound request-SLO trace and ledger remain authoritative for T0, model/input
identity, terminal semantic response, GPU/cost accounting, failures, and
cleanup. This receipt only adds causal storage operations and read/write/network
/deleted byte counters. Phase-percentile summation remains forbidden.

The source classification is exact rather than a broad per-state allowlist:
`same_model_hot/memory_hit` is A/materialized;
`idle_local/node_local_hit` is B/node seed;
`capacity_miss/unavailable` is C/remote source;
`a_to_b_remote/remote_miss` is D/remote source; and
`a_to_b_local` or `checkpoint_fallback` with `attached_storage_hit` is D/node
seed. A remote-miss D receipt cannot replace fetch evidence with internally
consistent clone evidence.

Cleanup state is also derived, not asserted. A failed SLO terminal must delete
every owned PVC/PV/provider-volume ID. Any full writable deletion requires the
storage receipt to be dirty, non-reusable, verified absent, and `ABSENT`; a
successful receipt with no writable deletion must be reusable and
`SEALED_RETAINED`. Partial writable deletion is invalid. Runtime validation
executes the checked-in Draft 2020-12 attempt, ownership, and typed-evidence
schemas. Every cleanup proof, including a clean A hit, must name the exact
nonempty set of owned generation, PVC, PV, and provider-volume UIDs.

## Source-pinned conclusions

The source manifest resolves both the reviewed and integrated request-SLO Git
commits, verifies all five files at both commits, and requires their complete
request-SLO subtree object IDs to be identical. It also pins the catalog commit
and Boltz external-`/tmp` lifecycle commit. The available Boltz status observation
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
55 of the 200 planning slots are explicitly imputed. The pinned inventory has
171 canonical models represented by 220 rows. Its 220-row duplicate-inclusive
high ceiling is retained only as an excluded source fact: it is never scaled by
`200/220`, never labeled as canonical-model capacity, and never used by the
projection. These are capacity projections, not benchmark results.

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
python3 -m pip install -r \
  performance/storage_cache_matrix/catalog_boundary_analysis/requirements.txt
python3 -m performance.storage_cache_matrix.catalog_boundary_analysis.cli \
  verify-sources --repo-root ../.. \
  --task-deck-root /home/tux/dashboard/data
python3 -m performance.storage_cache_matrix.catalog_boundary_analysis.cli \
  analyze --output performance/storage_cache_matrix/catalog_boundary_analysis/results/capacity-sensitivity.json
python3 -m unittest discover -v \
  performance/storage_cache_matrix/catalog_boundary_analysis/tests
```

The 10-attempt adversarial test fixture covers A-D, two retained capacity
failures, and a true two-model overlap. It is explicitly
`synthetic-contract-smoke-not-performance-evidence`; it publishes no latency or
throughput result. `validate-attempts` is the future live-receipt gate, but it
remains closed while the manifest's broker/bootstrap approval prerequisites are
unmet. The schema surface consists of `attempt.schema.json`,
`ownership-receipt.schema.json`, and `operation-evidence.schema.json`.
