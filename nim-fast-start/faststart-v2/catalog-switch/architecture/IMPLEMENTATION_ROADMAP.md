# Implementation, migration, and rollback roadmap

This roadmap begins from the conditional decision in `ADR.md`. It separates
contract implementation from evidence-based promotion. Calendar estimates are
planning ranges, not delivery promises; cloud amounts are hard safety ceilings
already recorded by child plans, not a final cost model.

## Ownership model

| Area | Accountable owner | Responsibilities |
| --- | --- | --- |
| Product/SLO | Product owner + serving SRE | Ratify or replace the provisional fast-switch p95 objective, define p99, and ratify standard/large tier semantics, deadlines, and error/cost budgets. |
| Catalog/API | Catalog platform team | Immutable schema, validator registry, digest publication, N/N-1 compatibility. |
| Router/control plane | Serving platform team | Admission, placement policy, backend weights, idempotency, reconciliation. |
| Kubernetes backend | Kubernetes serving team | Baseline adapter, fresh campaign, target-neutral Service, exact cleanup. |
| Node runtime | Runtime/security team | Signed agent, OCI isolation, cache, physical drain/scrub/launch actions. |
| Provider comparator | Benchmark team | Matched Cerebrium cohorts and provider-specific receipts. |
| Broker/cost | Infrastructure efficiency team | Fresh leases, prices, capacity, TTL, exact-ID cleanup, unit economics. |
| Evidence/observability | Performance + SRE | External recorder, ledger validation, dashboards, alert and canary gates. |
| Independent review | Security/reliability reviewer | Review raw evidence, threat controls, rollback, and promotion claims. |

No phase may use an existing resource in the three internal projects. Every
live phase begins with a reviewed immutable broker plan, unique `mlsp-csw-`
prefix, project/region, duration, budget, TTL, cleanup owner, and exact desired
final state. Authentication or permission failure stops the phase.

## Phase 0 — contract integration

Status: decision and wire contracts are reviewable in this branch, but the
production acceptance ledger is blocked. Estimate: 1 engineer-week (realized
for this package) plus the v2 acceptance work below.

- Retain the reviewed v1 external evidence schema for pre-resolved cohorts.
- Close `BLK-ACCEPTANCE-CONTRACT`: version acceptance so a model-id-plus-input
  request binds only authenticated tenant/idempotency/model/input/deadline at
  T0, then append authoritative post-T0 catalog/preconditions, placement,
  resource inventory/cleanup, context, and the later external terminal.
- Close `BLK-CONTROL-CHAIN`: add runtime prepare/readiness and boot attestation,
  carry tenant/idempotency/deadline end to end, and bind every failed
  operation's typed request and canonical receipt.
- Freeze the inventory input and closed compiled `CatalogResolution`/API wire
  contracts (`R-CATALOG`); missing source-row enrichment remains fail-closed.
- Integrate the broker, backend contracts, simulator, storage contract,
  Cerebrium preflight, and Modal reference without promoting them.
- Add machine-readable evidence, budgets, scenarios, ten API request/success/
  failure contracts, ownership/idempotency, hashes, validation, and mutation
  tests.

Exit: reviewed v2 ledger and backend adapters close
`BLK-ACCEPTANCE-CONTRACT` and `BLK-CONTROL-CHAIN`, then `G-CONTRACT` may pass; every recommendation
traces to evidence and every missing child result appears as a blocker.

Rollback: revert only this offline decision package. No live system changes.

## Phase 1 — close safety and planning blockers

Status: blocked. Estimate: 2 runtime engineers + 1 security reviewer for
2–3 weeks; no GPU creation until code review passes.

1. Replace the rejected drain revision (`BLK-DRAIN`, `G-DRAIN`). Bind every
   state transition and receipt to exact node/boot/generation/runtime/model/
   request identity; implement physical K8s and node-VM actions; prove restart
   durability, partial-B cleanup, active scrub, and rollback.
2. Replace the rejected snapshot classification (`BLK-SNAPSHOT`,
   `G-SNAPSHOT`). Restore n>=20 new-node gates, correct topology claims,
   self-verify all source pins, and publish explicit conventional outcomes for
   every covered model.
3. Seal Kubernetes cluster/node-group lease v2 (`BLK-K8S-BROKER`), including
   versioned demand-after-T0, provider children, rollback, and exact absence.
4. Finish capacity/cost inputs (`BLK-COST`): price snapshots, capacity classes,
   warm idle, preemptible interruption, storage/egress, failed-attempt cost,
   and exclusive-occupancy cost.
5. Resolve or explicitly descope local NVMe (`BLK-STORAGE`). No attached block
   observation may satisfy it implicitly.
6. Close `BLK-CEREBRIUM-SECURITY` and `G-CEREBRIUM-SECURITY` with a fresh
   provider-boundary threat/control model. It must cover authenticated tenant
   and model isolation, identity, credentials/egress, audit/idempotency,
   cleanup/rollback and provider outages, and explicitly accept or attest host/
   GPU residue controls that are not customer-verifiable. The legacy threat
   model's Modal rows cannot satisfy this work.
7. Product owners close `BLK-PRODUCT-BUDGETS` by ratifying or replacing the
   provisional fast-switch p95 objective, defining its p99 semantics, approving
   standard and large-tier latency semantics, and setting a Cerebrium spend
   ceiling.
8. Do not start product-boundary live cohorts until
   `BLK-ACCEPTANCE-CONTRACT` and `BLK-CONTROL-CHAIN` close; otherwise adapters would either hide
   artifact resolution before T0 or emit a ledger incompatible with the
   external API.

Exit: replacements receive fresh independent review; all offline suites pass;
broker dry-run proves no foreign references; live plans name exact fixtures,
digests, hardware, regions, budgets, and cleanup.

Rollback: discard rejected candidate commits; keep `architecture.json`
blockers open and production routing unchanged.

## Phase 2 — task-owned live GPU evidence

Status: blocked by Phase 1 and `BLK-LIVE-BACKENDS`. Estimate: 3 engineers +
1 reviewer for 4–6 weeks, with serialized cohorts to preserve homogeneous
conditions.

### Internal representative lanes

- `B-INTERNAL-SMALL`: ProteinMPNN on Kubernetes and node-VM, all six scenarios,
  n=30 per homogeneous cell, preemptible H100 first.
- `B-INTERNAL-STORAGE`: Boltz2 on both internal paths, all six scenarios, n=30,
  attached/remote tiers and local NVMe only if entitlement is proven.
- `B-INTERNAL-LARGE`: Evo2-40B or catalog-selected non-gated alternate on its
  exact compatible hardware; never relabel another GPU shape.

### External matched lane

- `B-EXTERNAL-MATCHED-QWEN`: exact Qwen3-8B revision/input/runtime across
  Kubernetes, node-VM, and Cerebrium where the contract permits. Checkpointing
  remains off unless separately evidenced. Each provider cohort is homogeneous
  and never pooled with a claim-native or different-model result.

### Resource and spend envelopes

| Campaign | Fresh resources | Current hard ceiling |
| --- | --- | ---: |
| Kubernetes first H100 | Private cluster/control plane, preemptible H100 node group, task registry/storage/credentials, exact provider children | USD 27 |
| Node-VM H100 control | Private network, preemptible H100 VM, encrypted boot/attached storage, task publication/credentials | USD 13.082801 TTL ceiling (USD 8.721867 expected) |
| Internal Qwen H100 TTL | Broker-created private stack | USD 8.721867 |
| Internal GLM H200 TTL | Exact 8xH200 TP8 normal stack if capacity/approval passes | USD 289.409894 |
| Cerebrium | New task app at min replicas zero, authenticated endpoint, task artifacts | Blocked until spend cap approval |

The table is a set of stop limits, not estimated production economics. Every
cohort records actual resource IDs, tenant/project/region, GPU, preemptible
choice, image/artifact/input hashes, calls, samples, bytes, billed/idle/active
time, price source, failures, cleanup commands, NotFound receipts, and final
GPU state. Temporary resources are removed after evidence capture.

Exit: the representative live cohort requirements for `G-LIVE-K8S`,
`G-LIVE-NODE`, and `G-LIVE-CEREBRIUM` are accepted only for their exact
qualified workload classes. Results must meet the universal receipt/error
gates and ratified latency/cost budgets. The three `G-LIVE-*` gates remain
blocked until `B-TRACE-REPLAY` completes in Phase 3. A cohort can fail without
blocking evidence publication; failures remain in the ledger.

Rollback: stop the campaign, reject new attempts, preserve ledgers, scrub and
clean exact resources, verify absence, and leave production untouched.

## Phase 3 — policy replay and chaos qualification

Status: blocked. Estimate: 2 performance engineers + 1 SRE/security reviewer
for 2–4 weeks; GPU hours and spend derive from the completed capacity model.

- Replace simulator placeholders with accepted per-model raw distributions.
- Run `B-TRACE-REPLAY` for uniform, Zipf-like, correlated, bursty, and
  adversarial traces at n>=100 per promoted cell.
- Compare shortest verified switch cost against least loaded, then queue cap;
  compare GDSF against LRU separately. Keep prefetch off unless a dedicated
  transition experiment proves p95/cost benefit.
- Run `B-CHAOS` and close `BLK-CHAOS`: preemption, control-plane blackhole,
  corrupt/stale content, capacity loss, partial launch, cancellation, stuck A,
  invalid semantic HTTP 200, accounting loss, cleanup failure, foreign
  replacement, replay, and rollback.

Exit: `G-CHAOS` passes, all requests are conserved, zero semantic false
success/duplicate/unaccounted attempt occurs, and cleanup/scrub/cost receipt
rates remain 100%. After `B-TRACE-REPLAY` and the corresponding Phase-2 cohort
requirements are accepted, each exact-workload `G-LIVE-*` gate may also pass;
no result is generalized to an untested catalog class.

Rollback: reset policy to least-loaded/no-prefetch, set experimental backend
weights to zero, recycle quarantined nodes, and retain the failed trace.

## Phase 4 — shadow and canary migration

Status: future. Estimate: 2 platform engineers + 1 SRE for 3–4 weeks.

Precondition: all relevant live, cost, chaos, and independent-review gates pass.
Before a shared-service deployment, inspect the live image tag/digest, rollout
history, running endpoints/resources, and user-visible sibling features. The
deployment branch must contain the currently deployed commit or use an
isolated preview/integration path. Record `previous_good_digest`.

Canary sequence per workload tier:

1. Shadow catalog/policy decisions only; zero model traffic.
2. 0% dry canary: signed node commands execute only against synthetic fixture
   leases and must clean completely.
3. 1% request traffic for >=100 attempts and one full failure/cleanup window.
4. 5%, 25%, and 50%, each with >=100 attempts and one preemption/rollback
   drill; do not pool tiers or cache states.
5. 100% only after `G-INDEPENDENT-REVIEW` and every universal gate passes.

Automatic rollback triggers:

- any semantic-invalid success, duplicate response, or unaccounted attempt;
- any missing audit, accounting, scrub, cleanup, or exact-identity receipt;
- p95/p99, success, unit-cost, warm-idle, queue, or capacity regression beyond
  the ratified gate;
- stale generation, foreign process/resource, unexpected egress, or catalog/
  policy digest drift; or
- loss of a pre-existing endpoint, agent, or sibling user-visible feature.

Rollback procedure:

1. Atomically set the new backend/policy weight to zero.
2. Fence its generation and stop new admissions.
3. Finish or cancel accepted attempts by their recorded deadlines.
4. Quarantine nodes whose exact cleanup cannot be proven.
5. Restore previous-good router/catalog/policy/agent/image digests.
6. Verify old and sibling features, response semantics, ledgers, and running
   resources; preserve both sides of the rollback evidence.

## Phase 5 — production operations

Status: future. Estimate: one owning platform team plus SRE on-call; quarterly
catalog/security review and per-release canary.

- Continuously validate catalog/artifact/validator digests and provider
  entitlement/capacity.
- Recompute warm slots with measured occupancy and failure rate; enforce spend
  and TTL ceilings.
- Requalify on model, image, artifact, driver, CUDA, runtime, GPU/topology,
  security policy, cache filesystem, provider, or price change.
- Run scheduled orphan scans and periodic rollback/preemption drills.
- Keep conventional fallback available for every snapshot-enabled row.

Production is not reached by this task. The roadmap is implementable now, but
all material unknowns remain explicit in `BLK-ACCEPTANCE-CONTRACT`,
`BLK-CONTROL-CHAIN`,
`BLK-DRAIN`, `BLK-SNAPSHOT`, `BLK-COST`, `BLK-K8S-BROKER`,
`BLK-LIVE-BACKENDS`, `BLK-STORAGE`,
`BLK-CEREBRIUM-SECURITY`, `BLK-CHAOS`, and `BLK-PRODUCT-BUDGETS`.
