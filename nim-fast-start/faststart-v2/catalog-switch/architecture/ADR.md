# ADR: catalog-aware hybrid model switching

Status: **reopened for evidence-index update only; not final; no production backend promoted**

Decision date: 2026-08-19

Scope: internal Kubernetes and direct/node-local VM paths, compared empirically
only with Cerebrium. Modal appears only in `MODAL_REFERENCE.md`.

## Manager scope for the reopened revision

Commit `1db7703e` is preserved as the prior conditional baseline. This revision
adds only a versioned evidence index, an open decision matrix, exact provenance,
explicit unknowns, and null latency/cost budget placeholders. It neither
selects a backend nor upgrades the previous conditional sign-off.

The current decision matrix is open because matched Kubernetes/plain-VM/
Cerebrium cohorts, all-ten Arm A/Arm B evidence, and an accepted safe
drain/reclaim replacement are missing. Rejected commits `34d70fd0` and
`f5f2706a` and all rejected replacements are negative review evidence, not
production-design inputs. Cerebrium has zero measured cohorts. Modal remains
documentation-only and unscored.

## Context and evidence boundary

The product request names an arbitrary model from a heterogeneous catalog. The
system must account for catalog selection, queueing, an optional A-to-B drain,
GPU reclaim, placement, image/artifact/storage readiness, restore or
conventional load, service readiness, inference, semantic validation,
accounting, and cleanup. Prepared-Pod restore time is therefore useful internal
evidence but is not the product latency.

`R-METRIC` retains the reviewed v1 external-client contract for pre-resolved
benchmark cohorts: T0 is durable acceptance and success is the first complete
semantically valid response. Every attempt remains in the denominator. P50,
p95, and p99 require at least 2, 20, and 100 homogeneous raw attempts. Phase
percentiles are diagnostics and cannot be added into a product percentile.

The v1 contract also pins exact artifact identity, target-specific occupant,
queue/cache/capacity state, and exact resource ownership in the T0 event. That
is incompatible with the production API below, whose caller supplies
authenticated tenant, client idempotency key, `model_id`/optional version,
input, and deadline, while authoritative catalog, precondition, placement, and
demand-created resource facts occur after T0.
`BLK-ACCEPTANCE-CONTRACT` therefore blocks `G-CONTRACT`: a reviewed v2 ledger
must append those facts through `CatalogResolution`, placement,
`AttemptContext`, resource-inventory, and cleanup records, and retain the same
all-attempt and external-terminal invariants. No implementation may hide
catalog/cache/capacity lookup or resource creation before T0 to make the two
contracts appear compatible.

The evidence ledger is intentionally conservative:

- `E-OF2-PREPARED-001` proves an OpenFold2 internal-stage feasibility anchor
  (17.629887 seconds conservative-upper p95, n=20), not a product SLO.
- `E-BOLTZ-PREPARED-001` preserves Boltz2's internal-stage failure
  (30.310246 seconds conservative-upper p95, n=20) rather than hiding it.
- `E-NODE-CPU-001` selects the smallest evidenced isolation boundary, but its
  ~207 ms OCI overhead is a CPU fixture and predicts no GPU/model result.
- `E-SIM-001` supports structural hypotheses only. It cannot rank backends,
  eviction policies, prefetch, or production latency because most inputs are
  placeholders.
- `E-K8S-CONTRACT-001`, `E-NODE-SUPERVISOR-001`,
  `E-STORAGE-CONTRACT-001`, and `E-CEREBRIUM-001` are executable contracts or
  preflights with no product-boundary GPU cohort.
- `E-SECURITY-001` is normative only for the internal Kubernetes/node-VM
  architecture. Its source still contains legacy Modal rows and contains no
  Cerebrium mapping; `E-CEREBRIUM-SECURITY-PENDING-001` prevents that gap from
  being mistaken for provider coverage.

The resulting decision remains conditional under `R-PRODUCTION-PROMOTION`.

## Decision

Build one catalog-aware control plane and keep launch mechanisms as replaceable
strategies selected by measured scenario. Do not force one backend across the
catalog.

```text
external client
  -> edge recorder / idempotency journal (T0)
  -> catalog resolver + policy router
       -> Kubernetes baseline/fleet path
       -> signed node-local OCI command path
       -> disabled-by-default Cerebrium capacity path
  -> exact model endpoint -> semantic validator -> response commit
  -> causal event/accounting/cleanup ledger

catalog/control plane
  -> brokered capacity leases
  -> immutable L2 publication
  -> verified L1 cache population
  -> node lease + generation ownership
```

`R-CATALOG` compiles the versioned inventory plus runtime/security registries
into the closed `CatalogResolution` wire contract. `E-CATALOG-001` contains 220
source rows representing 171 canonical models, but its source-row schema does
not itself carry every driver/CUDA/topology, storage, fallback, or policy field
required by the production resolution. Missing compilation inputs fail
resolution; they are never defaulted or inferred.

`R-CONTROL-DATA-PLANE` keeps Kubernetes as fleet ownership and the empirical
baseline. A signed node-local OCI supervisor is the candidate data-plane hot
path for dedicated single-GPU nodes. It may remove API-server and
request-specific Kubernetes object creation from the critical path, but it may
not bypass catalog admission, node leases, generation fencing, isolation,
semantic validation, accounting, or cleanup. This choice is
`experiment-required`, not promoted.

`R-CEREBRIUM` reserves Cerebrium as the sole external comparator and a possible
deadline-aware capacity fallback. It starts with zero traffic. The claimed
Qwen3-8B headline was not reproducible from authoritative model/hardware/
boundary metadata; the program must measure a new, exact cohort. GLM-5.2 BF16
and GLM-5.2-FP8 remain distinct identities. Cerebrium cannot be enabled until
`G-LIVE-CEREBRIUM`, `G-CEREBRIUM-SECURITY`, `G-COST`, and `G-CHAOS` pass.
`BLK-CEREBRIUM-SECURITY` requires a provider-boundary threat/control map and
accepted-risk disposition for host/GPU residue that customers cannot verify.

`R-MODAL-REFERENCE` is documentation-only. Modal is absent from the empirical
backend list, benchmark matrix, routing weights, cost comparison, and rollout.

## Catalog and control-plane contract

One catalog version is an immutable digest over source rows and the registries
needed to compile them. `control-plane-api.schema.json#/$defs/CatalogResolution`
is the closed output contract. Every successful resolution must contain:

- canonical model and version;
- image digest, artifact digest/bytes, and immutable publication identity;
- workload/API type, semantic-validator digest, and exact input fixture class;
- GPU SKU/count/memory, runtime, driver/CUDA/topology constraints;
- L1/L2 storage compatibility and writable-state requirements;
- snapshot state (`eligible`, `ineligible`, or `unresolved`) with evidence;
- ordered launch ladder, always ending in conventional start or explicit
  failure; and
- license, tenant, secret, egress, and backend eligibility policy.

The external `AcceptRequest` accepts `model_id` plus inline input or an immutable
payload reference; the client does not assert internal artifact identity.
`ResolveCatalog` authoritatively returns the artifact and complete resolution.
`PlaceAttempt` consumes a point-in-time queue/cache/capacity snapshot and
returns backend, node lease, generation, estimated switch cost, and decision
evidence. A stale catalog or policy digest causes re-resolution; it is never
translated after the run into a more favorable identity.

The current ten compatibility operations have closed request, success, and
versioned failure fragments plus stated idempotency semantics in
`control-plane-api.schema.json`: acceptance, resolution, placement, context
commit, signed node commands, inference dispatch, semantic validation,
response commit/replay, resource lease, and terminal attempt commit. The signed-command envelope makes
signer, sequence, expiry, lease/boot/generation/model/input binding, transition,
and nonce visible rather than hiding them in an opaque payload. Eligible
snapshot rows may select snapshot then conventional, or conventional directly;
ineligible/unresolved rows can only select conventional then terminal failure.

The control plane owns catalog publication, capacity intent, routing policy,
provider adapters, price snapshots, rollout weights, and reconciliation. The
node agent owns only its signed lease/generation, verified cache, runtime,
GPU, and exact cleanup. The edge recorder and evidence ledger are independent
of both so neither backend can move T0 or suppress failures.

`BLK-CONTROL-CHAIN` remains open because the current wire package does not yet
establish a generic backend-specific runtime prepare/readiness receipt before
`DispatchInference`, bind boot attestation to the exact leased instance, carry
authenticated tenant/client-idempotency/deadline identity through every hop,
or retain the typed request and canonical receipt for the operation that
failed. Therefore these ten fragments are not called a production-complete API.
The checked context/receipt fixtures are compatibility proofs, not a claim that
those missing production links exist.

## Request hot path and state machine

The normative hot path is:

1. `AcceptRequest` authenticates, deduplicates, durably binds model and input,
   fsyncs `request.accepted`, and returns request/attempt/input identity.
2. `ResolveCatalog` binds the complete immutable workload identity.
3. `PlaceAttempt` selects a backend and node generation using only causal
   state. A capacity miss is an explicit terminal or a bounded queue decision.
4. If A is present, stop A admission and drain until the recorded deadline.
5. Terminate A, revoke its credentials, remove its exact runtime/UID/cgroup/
   namespaces/mounts/logs, actively scrub VRAM, and verify the GPU baseline.
6. Verify/localize B image, artifact, storage, and checkpoint branches. Bytes
   requested after T0 are charged to this attempt.
7. Launch B conventionally or through a verified signed snapshot binding.
8. `DispatchInference` hands the accepted immutable input to the exact leased
   runtime once and records the raw-output receipt.
9. Readiness is diagnostic. `ValidateResponse` must accept the complete output
   with the pinned validator before success.
10. `CommitResponse` atomically commits/replays one byte-identical client
    response. Only after the external recorder receives the complete response
    may it emit `response.validated`; the terminal cannot be an input to the
    response commit.
11. `CommitAttempt` binds acceptance, the latest append-only context, response
    commit, later external terminal, accounting, and cleanup. Failure branches
    commit the typed `attempt.failed` event without inventing missing placement,
    dispatch, validation, or client-success receipts. Finalize exact cleanup or
    quarantine.

The design supports all scenarios, but its A-to-B implementation is blocked by
`BLK-DRAIN`: the reviewed `E-DRAIN-REJECTED-001` revision did not sufficiently
bind physical backend actions, durable identity/fencing, GPU scrub, partial
launch recovery, or restart behavior. It is not integrated here.

Late A responses carry the wrong generation and cannot commit. A failed B
launch is itself a launched attempt and must pass credential revocation,
runtime cleanup, active scrub, and receipt durability before another ladder
rung. An unverifiable cleanup quarantines/recycles the node; it never returns
to the eligible pool. These properties are gates inherited from
`E-SECURITY-001`, not latency optimizations that may be skipped.

## Scenario routing and backend fallback

| Scenario | Primary decision | Required fallback |
| --- | --- | --- |
| `same_model_hot` | Retain exact healthy generation at L0. | Re-resolve as `idle_local` on stale generation/health. |
| `idle_local` | Verify L1, acquire lease, snapshot-or-conventional launch. | Treat unverifiable/missing bytes as remote miss. |
| `a_to_b_local` | Fenced drain, exact teardown, scrub, then local B launch. | Quarantine and re-place; never co-reside. |
| `a_to_b_remote` | Reclaim, fetch immutable L2 bytes after T0, atomically publish L1, launch. | Alternate capacity within deadline or explicit failure. |
| `checkpoint_fallback` | Verify full binding; try restore once. | Scrub and descend exactly once to conventional start. |
| `capacity_miss` | Fresh internal capacity, eligible Cerebrium, bounded queue, or failure. | Preserve exact identity/deadline and expose the miss. |

`R-SNAPSHOT-FALLBACK` makes snapshot a launch strategy, not a backend. The
classification at `E-SNAPSHOT-REJECTED-001` is rejected; `BLK-SNAPSHOT` must
close before row-level snapshot promotion. Incompatible artifacts, unpinned
images, topology changes, unsigned/untrusted captures, multi-GPU uncertainty,
or semantic mismatch all choose conventional start or explicit failure.

## Cache and placement policy

`R-CACHE-PLACEMENT` defines three immutable-identity tiers:

- L0 is the exact GPU-resident model generation.
- L1 is verified local content, written only by the cache ingester, published
  atomically under a digest, enforced read-only/fs-verity at use, and isolated
  from model UIDs.
- L2 is immutable remote publication with task/tenant access policy and exact
  request-causal byte and cost receipts.

The initial experiment compares shortest verified switch cost against
least-loaded placement and adds a queue-depth cap as a separate variable.
Simulation suggests these effects are structural, while eviction ranking is
placeholder-sensitive. GDSF is only the candidate; LRU is the control.
Prefetch defaults off and requires real per-model demand/transition telemetry,
product-p95 improvement, and an approved byte/cost budget.

`BLK-STORAGE` remains open: the live local-NVMe cohort lacks allowed-project
entitlement proof. Attached-block and remote-only evidence cannot be relabeled
as local NVMe.

## Backend disposition by workload tier

| Tier | Kubernetes | Node-local VM | Cerebrium |
| --- | --- | --- | --- |
| Fast-switch, dedicated single GPU | Control/fleet default and baseline; candidate node-local subpath. | Candidate if all live isolation and A-to-B gates pass. | Disabled comparator/capacity candidate only. |
| Standard on-demand | Baseline, including conventional fallback. | Candidate when dedicated-node economics win. | Disabled until matched cohort and spend cap. |
| Large/multi-GPU | Only internal candidate currently shaped for orchestration; no latency budget yet. | Not in v1 scope. | Exact-provider placement candidate only; GLM gates are unresolved. |

No cell is promoted. `G-LIVE-K8S`, `G-LIVE-NODE`, and
`G-LIVE-CEREBRIUM` are blocked by `BLK-LIVE-BACKENDS` and other named gates.

## SLO, capacity, and cost budgets

All latency and cost ceilings are **null, unratified placeholders** in this
revision. The earlier 30-second internal program objective is evidence context,
not a current budget or product SLO. `BLK-PRODUCT-BUDGETS` requires product
owners to define p50/p95/p99 semantics after matched evidence exists. Promotion
also requires
at least 100 attempts, >=99% valid-response success, zero semantic
false successes, zero duplicates, zero unaccounted attempts, and 100% cleanup,
GPU-scrub, and cost receipts. These gates are executable in
`architecture.json`; they are not claims that a backend currently passes.

The fast-switch p50/p95/p99 decision and absolute standard-on-demand and
large/multi-GPU latency budgets are blocked by `BLK-PRODUCT-BUDGETS` and
`BLK-COST`. They must not be invented from prepared-stage data. Until ratified,
standard routes must at least match their exact frozen production baseline and
large routes remain explicitly queued/asynchronous or unavailable.

The provisional warm-capacity formula is:

```text
max(1, ceil(arrival_rate_p95 * occupancy_p95 / 0.70))
  + preemptible_failover_slots
```

It is a testable starting point, not a capacity conclusion. Every route must
publish p50/p95 cost per valid response, failed-attempt cost, warm-idle cost,
pre-T0 cache investment, post-response cleanup tail, and price provenance.
Historical child campaign ceilings remain source provenance, not current
budgets. Every current campaign cost placeholder is null.
`G-COST` cannot pass until `E-COST-PENDING-001` is replaced.

The provisional calculation is executable and rejects negative, non-finite,
or fractional failover inputs:

```bash
python3 catalog-switch/architecture/capacity_budget.py \
  --arrival-rate-p95 0.5 --occupancy-p95 20 \
  --preemptible-failover-slots 2
```

## Telemetry and observability

The canonical v1 event envelope requires request/attempt identity, sequence,
recorder identity, clocks, and event-specific data. It does not carry the
post-T0 placement identity. The companion closed `AttemptContext` is committed
after placement and binds catalog, policy, backend, exact broker/provider
resource receipt, node lease, boot, generation, model, image/artifact/
checkpoint, input, and validator identities. Every downstream receipt carries
its context-commit digest. Snapshot failure creates one append-only v2 context
that binds the prior commit, failure receipt, scrub receipt, and conventional
rung; terminal commit must use the latest context. Required causal phases are
catalog, queue, drain, GPU release, placement, image/artifact/storage/cache
readiness, runtime launch, service readiness, inference, response validation,
accounting, and cleanup.

Operational views must derive from raw ledgers and expose:

- offered/observed/success/failure counts and failure class;
- request p50/p95/p99 only at allowed sample counts;
- queue/drain/reclaim/localize/launch/readiness/inference diagnostics;
- cache hit/miss, generation, age, insert/evict, digest, and bytes;
- GPU active/idle/billed time, utilization, and preemption;
- cost per valid response and failed attempt; and
- cleanup, quarantine, orphan scan, and rollback completeness.

Alerts gate rollout on semantic-invalid HTTP 200, duplicate response,
unaccounted attempt, audit-chain gap, stale generation, unexpected resident
GPU process, missing scrub/cleanup/cost receipt, budget exhaustion, or foreign
resource identity.

## Security, failure handling, and cleanup

`E-SECURITY-001` is normative for internal Kubernetes and node-VM paths. The
source contains 21 controls and 17 test families total; 20 controls and 16 test
families apply to the internal paths. CTL-17 and TST-14 are legacy Modal-only,
non-operative in this program, and the artifact supplies no Cerebrium coverage.
Model code on internal paths runs non-root with a
read-only root and artifact view, per-attempt scratch/namespaces, no metadata
or control socket, default-deny egress, and one exclusive GPU occupant. Only
the small root-owned agent surface may access runtime, cgroup, checkpoint, and
GPU controls.

Cerebrium requires a separately reviewed provider-boundary model covering
authenticated tenant/model isolation, provider/image/artifact identity,
credential scope and egress, audit/idempotency, provider outages, cost caps,
cleanup and rollback. Host/GPU residue and physical scrub may be unverifiable;
those gaps need explicit accepted-risk or provider-attestation treatment, not
silent reuse of internal receipts. `G-CEREBRIUM-SECURITY` stays blocked until
that work and its mapped adversarial evidence are independently reviewed.

Images/artifacts are digest pinned; checkpoint capture is golden-state only,
encrypted, signed, and fully bound to model/image/artifact/driver/CUDA/runtime/
GPU/topology/mount/security state. The full content is verified at ingest and
use. Commands are authenticated, monotonic, nonce protected, lease/generation
bound, and hash chained off-node.

Provider/API loss after T0 cannot change identity or erase an attempt. The node
may continue only within a valid signed lease and local policy. Otherwise it
fails closed and reconciliation uses exact IDs. Cleanup never deletes by name:
it revokes credentials, terminates exact UIDs/runtime identities, clears
mounts/scratch/logs, scrubs GPU memory, deletes exact task-owned resources in
reverse dependency order, verifies absence, and scans for orphan prefixes.

Failure semantics are closed by stage. `authentication_denied` is pre-T0 and
creates no request/attempt. Eight post-T0 product failures—resolution,
capacity, deadline, command, runtime, semantic, cancellation, and integrity—
produce a typed `attempt.failed` terminal and remain aggregate eligible.
Pre-context failures carry no invented lease/placement receipt; later failures
bind the latest context. `cleanup_incomplete` is different: it is a
`CommitAttempt` operational error after the product terminal, forces retained
or quarantined final state, and cannot be embedded as the attempt's product
failure or erase an already delivered valid response.

`G-CHAOS` and `BLK-CHAOS` require real preemption, API partition, stale/corrupt
content, invalid semantic HTTP 200, cancellation, stuck A, partial launch,
cleanup failure, accounting loss, foreign replacement, and rollback drills.
`E-CHAOS-PENDING-001` confirms this evidence does not exist yet.

## Rollout and rollback

The schema/catalog/event APIs must remain N/N-1 wire compatible. Each service
or agent release carries current and `previous_good_digest`. Shadow evaluation
precedes a 0% dry canary, then 1%, 5%, 25%, and 50% workload-tier canaries;
100% requires every universal budget and independent review.

Rollback triggers on any semantic false success, duplicate, audit gap,
unaccounted attempt, cleanup/scrub failure, backend identity drift, SLO/cost
regression, or sibling-feature loss. Rollback sets new route weight to zero,
fences the generation, drains accepted attempts within their deadline,
quarantines incomplete nodes, restores previous-good catalog/policy/agent
digests, validates serving and receipt health, and preserves both pre- and
post-rollback evidence. Shared-service deployment additionally requires the
task branch to contain the currently deployed work and records the previous
image digest before rollout.

Detailed phases and ownership are in `IMPLEMENTATION_ROADMAP.md`.

## Rejected alternatives and open unknowns

- Direct uncontained process serving is rejected: lower overhead does not
  satisfy the isolation contract.
- Firecracker is rejected for this program revision: no evidenced H100 device
  path or compatible snapshot lineage was demonstrated.
- A Kubernetes-only request path and a node-agent-only control plane are both
  rejected as absolutes; the former has unmeasured hot-path overhead and the
  latter loses authoritative fleet ownership/reconciliation.
- Snapshot-everything is rejected; conventional fallback is mandatory.
- `E-DRAIN-REJECTED-001` and `E-SNAPSHOT-REJECTED-001` are explicitly excluded
  from implementation despite green offline tests.
- Cerebrium headline claims cannot substitute for a matched raw cohort.
- Modal execution/ranking is outside scope.

Open blockers are `BLK-ACCEPTANCE-CONTRACT`, `BLK-CONTROL-CHAIN`, `BLK-DRAIN`, `BLK-SNAPSHOT`, `BLK-COST`,
`BLK-K8S-BROKER`, `BLK-LIVE-BACKENDS`, `BLK-CEREBRIUM-SECURITY`,
`BLK-STORAGE`, `BLK-CHAOS`, and `BLK-PRODUCT-BUDGETS`. No gate passes;
`G-CONTRACT` is explicitly blocked by the v1/v2 acceptance incompatibility.
The remaining promotion gates are `G-LIVE-K8S`, `G-LIVE-NODE`,
`G-LIVE-CEREBRIUM`, `G-CEREBRIUM-SECURITY`, `G-DRAIN`, `G-SNAPSHOT`,
`G-COST`, `G-CHAOS`, and `G-INDEPENDENT-REVIEW`.

## Consequences

After the v2 acceptance blocker closes, the system can add backends and launch
strategies without redefining the product metric, and failures remain
comparable. This costs an authoritative
catalog, immutable content, signed commands, active GPU scrub, durable audit/
idempotency dependencies, exclusive occupancy, and more conservative rollout.
Those are deliberate production costs. The package enables implementation now
while preventing the current incomplete evidence from becoming a winner by
accident.
