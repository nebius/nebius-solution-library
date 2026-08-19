# Storage and cache tier matrix

This package is the evidence contract for task
`catalog-switch-storage-cache-matrix`. It measures artifact localization under
the program's already-reviewed product boundary. It does **not** introduce a
second latency definition:

- T0 is the external recorder accepting a request containing the exact model,
  artifact, and input identity.
- success is the first complete response body accepted by the pinned semantic
  validator for that model version;
- every failed attempt remains in the denominator and failure inventory; and
- end-to-end percentiles are calculated from raw per-attempt totals. Phase
  percentiles are diagnostic and are never added together.

Every detailed receipt is cryptographically and identity-bound to a canonical
`performance/request_slo/` trace and ledger. The matrix adds the resolution the
shared ledger deliberately does not carry: image pull/unpack, artifact fetch,
volume attach/mount, clone, copy, hash, first read/COW, restore, conventional
load, runtime launch, readiness, inference, semantic validation, bytes, cache
generation, cache age/version, cost, and cleanup.

## Evidence layout

One immutable evidence directory contains:

- canonical `plan.json`, pinned to the request-SLO implementation and, when
  enabled, the Boltz external-`/tmp` contract;
- canonical `attempts.jsonl`, one detailed receipt per request attempt;
- the bound canonical request-SLO trace and ledger;
- digest-pinned backend receipts referenced by each attempt; and
- generated aggregate, simulator override, and router-locality documents.

The plan freezes the artifact digest/version/size/payload, matrix cells,
minimum samples, project allowlist, resource prefix, expected duration/budget,
TTL owner, exact-ID cleanup, and the local-NVMe entitlement gate before live
creation. A plan distinguishes one-time catalog publication cost from ongoing
node-cache investment and from request-triggered cost.

Receipts accept exactly three scheduler-facing tiers:

| Tier | Required live meaning |
| --- | --- |
| `local_nvme` | task-owned host-local NVMe, with explicit entitlement and device inventory |
| `attached_block_pvc` | task-owned attached block storage or a task-owned PVC backed by it |
| `remote_artifact` | immutable task-owned remote publication fetched after T0 on a miss |

The required cohorts are hot, warm, cold, eviction/repopulation, concurrent
fetch, corruption, Boltz external-`/tmp` hit, and Boltz external-`/tmp`
clone/miss. Concurrent attempts must use distinct mutable namespaces and an
immutable read-only publication source; their fetch intervals must actually
overlap. Dirty or corrupt generations must end `ABSENT`, carry an absence
receipt, and can never appear in a later attempt.

## Commands

From `nim-fast-start/faststart-v2`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  performance/storage_cache_matrix/tests

smoke_dir="$(mktemp -d)"
python3 -m performance.storage_cache_matrix.cli smoke \
  --output-dir "$smoke_dir"
python3 -m performance.storage_cache_matrix.cli validate \
  --plan "$smoke_dir/plan.json" \
  --attempts "$smoke_dir/attempts.jsonl"
python3 -m performance.storage_cache_matrix.cli aggregate \
  --plan "$smoke_dir/plan.json" \
  --attempts "$smoke_dir/attempts.jsonl" \
  --evidence-source "synthetic contract smoke; not performance evidence" \
  --output "$smoke_dir/rebuilt-aggregate.json" \
  --simulator-output "$smoke_dir/rebuilt-simulator-overrides.json" \
  --router-output "$smoke_dir/rebuilt-router-locality-costs.json"
```

The smoke is deterministic contract coverage only. Its files and timings are
explicitly labeled `synthetic-smoke-not-performance-evidence`; they cannot be
promoted into a measured Boltz conclusion or simulator evidence.

Measured-live evidence uses the existing `measured-overrides` v1 adapter shape.
Synthetic output instead uses
`synthetic-contract-overrides-not-admissible`, which that adapter rejects.
The router export preserves raw request-causal localization and product-latency
samples plus failures, bytes, and cost per cell. Neither export invents p95 or
p99 when the shared minimum sample counts (20 and 100) are unavailable.

## Current live gates

No live result is committed by this change. Read-only capability checks and the
full-matrix local-NVMe blocker are recorded in `LIVE_EXECUTION_PLAN.md`. The
resource broker correctly refuses local NVMe for all three epic projects
because no allowed project/platform entitlement has been verified. The known
supported B300 path is in `uk-south1`, outside the epic's immutable
project/region allowlist, so it must not be used as a workaround.

That unavailable tier does not block a separately labeled partial baseline.
`network_baseline_handoff/` now defines a Network SSD/PVC and Object Storage
remote-fetch handoff that uses the same external-T0 contract. It contains no
results and cannot claim the local-NVMe tier, a complete matrix, or a Boltz
external-`/tmp` conclusion. Its read-only preflight forbids resource creation
until the exact broker and bootstrap candidates are clean, pushed, and covered
by an independent approval receipt.

No service, endpoint, image, manifest, or shared deployment is created by this
package. Any later execution uses fresh broker-leased resources and must not
attach to any existing VM, cluster, disk, bucket, registry, service account,
endpoint, or model artifact.
