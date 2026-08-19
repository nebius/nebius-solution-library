# Request-to-valid-response catalog switch contract

This package is the backend-neutral measurement contract for catalog selection
and model switching. It does not change the published OpenFold2 or Boltz2
cohorts and does not launch infrastructure.

## Frozen product boundary

- **T0:** the external client has accepted a request containing the exact
  `model_id`, model/artifact versions, and input identity. The first ledger
  event for every attempt must be `request.accepted` with boundary
  `external-client-request-accepted/v1`.
- **Terminal success:** the same external recorder has received the first
  complete response body and a pinned semantic validator has accepted it for
  the requested model version. The event is `response.validated` with boundary
  `first-complete-semantically-valid-response/v1`.
- **Terminal failure:** `attempt.failed`. Every offered trace attempt must be in
  the ledger, including capacity misses, validation failures, timeouts,
  preemptions, and exhausted retries.
- Request-specific selection, queueing, draining, release, placement,
  localization, launch, and inference cannot precede T0. Backend clocks may be
  retained in supporting evidence, but cannot replace the single external
  recorder's UTC and monotonic timestamps.

The product latency for one successful attempt is calculated from its raw
monotonic timestamps before any percentile is computed. Diagnostic phase
percentiles are never added together to manufacture an end-to-end percentile.

## Contract files

- `event.schema.json` is the versioned JSON Schema for one JSONL event.
- `trace.schema.json` is the versioned JSON Schema for a generated trace.
- `harness.py` is the normative semantic validator and aggregator. It adds
  exact-key, causal, identity, canonicalization, checksum, clock, and
  cross-record checks that JSON Schema alone cannot express.
- `cli.py` provides trace generation, external recording, validation,
  aggregation, legacy import, and an offline synthetic smoke test.

Canonical traces are one compact, sorted JSON object plus one newline.
Canonical ledgers are compact, sorted JSON objects, one per line, with no blank
lines. Duplicate keys, alternate formatting, mixed ledger/trace identities,
non-contiguous sequence numbers, symlinks, and missing terminal newlines fail
closed.

## Required causal record

Every attempt records all phases, including explicit `skipped` outcomes:

```text
external request acceptance (T0)
  -> catalog selection -> queue -> drain -> GPU release -> placement
  -> image/artifact/storage/cache readiness -> runtime launch
  -> service readiness -> inference -> valid response or exposed failure
  -> accounting -> cleanup receipt/final state
```

The four readiness branches may overlap after placement. Runtime launch cannot
start until each has a terminal state. A completed or failed phase has a
`phase.started` and `phase.finished` pair. A skipped phase has only a
`phase.finished` event. Inference retry occurrence numbers are contiguous;
each retry follows an exposed failed occurrence. All other phases have
occurrence `0` exactly once.

The request-acceptance event pins:

- target model, artifact identity, exact versions, artifact digest, workload,
  input digest, and input size;
- scenario, current node occupant, queue depth, capacity state, and every cache
  tier;
- backend/provider/version, project, region, node, GPU, image, code commit,
  config digest, and experiment identity; and
- task owner, unique resource prefix, dedicated resource inventory, and cleanup
  requirement.

Accounting is mandatory after either terminal and records USD cost, billed
time, GPU active/idle time, and total bytes. The validator reconciles total
bytes with per-phase records. Cleanup is the last event and records deleted or
retained resource identities plus a receipt digest when available.

## Exact scenarios and state labels

The trace and ledger accept exactly these scenarios:

| Scenario | Required initial fact |
| --- | --- |
| `same_model_hot` | node occupant exactly matches target model and version |
| `idle_local` | node has no occupant and artifacts are local |
| `a_to_b_local` | distinct occupant A; B artifact is a declared local hit |
| `a_to_b_remote` | distinct occupant A; B artifact is `remote_miss` |
| `checkpoint_fallback` | checkpoint is missing, stale, or restore-failed |
| `capacity_miss` | capacity is unavailable and placement fails explicitly |

Cache labels are closed enums:

| Tier | Labels |
| --- | --- |
| image | `local_verified`, `remote_required`, `unavailable`, `not_applicable` |
| artifact | `memory_hit`, `node_local_hit`, `attached_storage_hit`, `remote_miss`, `unavailable`, `not_applicable` |
| checkpoint | `compatible_hit`, `stale_version`, `missing`, `restore_failed`, `not_applicable` |
| storage | `ready`, `localization_required`, `unavailable`, `not_applicable` |
| capacity | `allocated`, `queued`, `unavailable` |

No backend may translate private cache labels into a more favorable canonical
state after a run.

## Deterministic traces

The generator consumes a pinned catalog, uses Python's isolated seeded random
generator, and emits a canonical SHA-256 over the complete trace payload.
`uniform` selects catalog entries uniformly, `skewed` uses a fixed
rank^-1.2 distribution, and `adversarial` alternates catalog extremes while
cycling hot, remote, capacity, fallback, local-switch, and idle cases. Every
mode cycles all six scenario contracts when at least six requests are emitted.
External acceptance deltas must follow the trace's offered offsets within the
v1 100 ms scheduler-error ceiling; a backend cannot silently replay an easier,
more slowly paced arrival pattern. Signed per-attempt error and its distribution
are retained in the aggregate.

From `nim-fast-start/faststart-v2`:

```bash
python3 -m performance.request_slo.cli generate-trace \
  --catalog performance/request_slo/examples/catalog.json \
  --distribution adversarial \
  --seed 2407 \
  --requests 120 \
  --trace-id catalog-switch-adversarial-001 \
  --output /tmp/catalog-switch-trace.json
```

The reference `record` command appends under an exclusive lock, derives both
sequence fields, samples external UTC and monotonic clocks together, rejects a
mixed recorder clock, and fsyncs the canonical event. `--data` and `--recorder`
accept inline JSON or `@path`. The event-specific exact keys are enforced when
the complete ledger is validated.

```bash
python3 -m performance.request_slo.cli record \
  --ledger /tmp/catalog-switch-ledger.jsonl \
  --ledger-id catalog-switch-run-001 \
  --trace-id catalog-switch-adversarial-001 \
  --request-id catalog-switch-adversarial-001-request-000001 \
  --attempt-id catalog-switch-adversarial-001-attempt-000001 \
  --event-type request.accepted \
  --data @/tmp/request-accepted-data.json
```

Validate before aggregating:

```bash
python3 -m performance.request_slo.cli validate \
  --trace /tmp/catalog-switch-trace.json \
  --ledger /tmp/catalog-switch-ledger.jsonl \
  --output /tmp/catalog-switch-validation.json
python3 -m performance.request_slo.cli aggregate \
  --trace /tmp/catalog-switch-trace.json \
  --ledger /tmp/catalog-switch-ledger.jsonl \
  --output /tmp/catalog-switch-aggregate.json
```

Aggregates include every offered/observed attempt, per-attempt results, failure
classes, scenario totals, exact cache-state counts and hit rates, phase
operation distributions, bytes, GPU active/idle time, cost, and cleanup states.
Nearest-rank `p50`, `p95`, and `p99` require at least 2, 20, and 100 raw samples
respectively; unsupported percentiles are `null`.

## Existing Kubernetes evidence

The legacy adapter reads a source TSV without modifying it, captures its
SHA-256, excludes already-aggregated summary rows, and emits
`prepared-node-internal-stage-only` with `eligible_for_product_slo: false`.
It never creates canonical product ledger events because the historical source
does not contain external-client T0 or the full causal record.

```bash
python3 -m performance.request_slo.cli import-legacy \
  --model openfold2 \
  --input performance/openfold2/fresh-cohort-n20-results.tsv \
  --output /tmp/openfold2-prepared-node-import.json
python3 -m performance.request_slo.cli import-legacy \
  --model boltz2 \
  --input boltz2-native/fresh-cohort-n20-results.tsv \
  --output /tmp/boltz2-prepared-node-import.json
```

## Offline smoke and tests

The smoke data are deliberately labeled synthetic and are never performance
evidence:

```bash
slo_smoke_dir="$(mktemp -d)"
python3 -m performance.request_slo.cli smoke --output-dir "$slo_smoke_dir"
python3 -m performance.request_slo.cli validate \
  --trace "$slo_smoke_dir/trace.json" \
  --ledger "$slo_smoke_dir/ledger.jsonl"
python3 -m performance.request_slo.cli aggregate \
  --trace "$slo_smoke_dir/trace.json" \
  --ledger "$slo_smoke_dir/ledger.jsonl"
```

Run focused tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  performance/request_slo/tests
```

This package is offline tooling, not a service or model wrapper. It creates no
cloud resources, does not use an existing deployment, and requires no GPU or
shared-service rollout. Live backends must first adopt this reviewed contract
and use fresh, task-owned resources under the program's resource-broker rules.
