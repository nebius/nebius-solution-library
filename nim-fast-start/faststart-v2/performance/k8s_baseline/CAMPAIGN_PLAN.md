# Kubernetes campaign and evidence plan

Status: **offline contracts implemented; first live campaign PLANNED; no cloud
or Kubernetes mutation admitted**.

## Immutable boundaries and denominators

For every attempt, T0 is the external controller's durable acceptance of the
exact trace request containing `model_id`, model version, artifact identity,
input identity, payload digest, scenario, and starting-state declaration. The
product terminal is call 1's complete response after the pinned model-specific
semantic validator passes. ARCHVTEAMS-2407 qualification additionally requires
call 2 to pass, and records raw T0-to-call-2 time. A call-2 failure does not
rewrite a valid call-1 product result; it remains a failed two-call
qualification in a separate denominator.

All offered attempts remain in the ledger. Aggregates report attempts offered,
observed, successful, failed, failure classes, raw attempt rows, and p50/p95/p99
only where the shared sample-size contract supports them. No phase percentile
is summed into a product percentile. Bytes moved, GPU active/idle/billed time,
cost, cache state, exact environment, cleanup receipt, and final GPU state are
joined by attempt ID. Provisioned-node billing is continuous from the first T0:
idle gaps are allocated to the next attempt, call 2 remains GPU-active time,
pre-T0 setup and byte-transfer costs are explicit, and the cleanup tail is
recorded before final reconciliation to the broker's actual-cost receipt.

## Arm A — provisioned node

Boundary: demand T0 to first and second semantic responses on an already
provisioned, fresh task-owned node. Before T0, the v2 broker may create the
fresh cluster and preemptible GPU node group, install target-neutral support,
and establish the explicitly declared occupant/cache precondition. After T0,
the canonical path records catalog selection, queue, drain, GPU-free proof,
placement/support-object creation, exact image/artifact/storage/cache
readiness, restore or conventional load, readiness, call 1, and call 2.

Each promoted scenario gets a separate homogeneous trace and aggregate:

1. same-model hot;
2. idle node with local image/artifact/checkpoint;
3. active A to B with local image/artifact/checkpoint;
4. active A to B with remote image/artifact localization;
5. checkpoint miss or stale-version conventional fallback; and
6. capacity miss with no runtime launch.

Same-model-hot uses one per-NIM trace and strategy `none`: the measured request
does not restore or conventionally launch a runtime. Switch/fallback traces use
two targets whose completed target is the next declared occupant; idle and
capacity-miss traces re-arm to no occupant. This transition rule is tested for
all six scenarios.

The current path creates a request-specific Service after T0. The only promoted
hot-path change precreates one model-neutral Service. Pod/runtime manifests,
storage, cache state, node, request, validator, model pair, and offered schedule
must remain identical. Workload cleanup deletes the active target and scrubs
the GPU, so the candidate cannot reuse the baseline's old initial-state
receipt. The broker must first return the versioned pair-handoff/rearm receipt
in `campaign/broker-cluster-interface-required.json`: the same lease/resource
graph, source-bound baseline cleanup and GPU-zero, equivalent re-established
occupant and cache targets, rearm cost/bytes/GPU evidence, and an audit
extension, all completed before candidate T0. Until that backend exists,
`finalize-live --promote` seals `promotion_allowed=false` and exits fail-closed.

After that dependency is implemented, promotion requires at least 30 offered attempts and 30
two-call-qualified attempts per exact NIM, arm,
scenario, strategy, support variant, cache state, and GPU-profile stratum, with
every failure retained. Failed/unreceipted attempt cleanup, an accounting
sentinel, failed final cleanup, or an unverified joint seal blocks promotion.

The first frozen campaign is local A-to-B switching between Boltz2 and
OpenFold2. The initial occupant is OpenFold2; targets alternate naturally, so
each completed attempt establishes the next attempt's occupant. Both artifacts,
images, and compatible checkpoints must have broker-owned, hash-checked local
receipts before the first T0. The 900-second offered interval protects
independence; an overrun is retained as queue/precondition failure rather than
moving T0.

## Arm B — newly created preemptible node

Boundary: external request T0 to first and second semantic responses, including
GPU node-group demand and creation. Arm B uses a different v2 lease and may
have only a fresh target-neutral cluster/control plane before T0. Immediately
after the durable `request.accepted` event, the controller passes the lease ID,
attempt ID, accepted-event hash, UTC T0, and monotonic T0 to the broker demand
operation. That operation creates one unique preemptible single-H100 node group
for that attempt.

Node-group demand/create, node readiness, image pulls, artifact localization,
checkpoint selection/restore, model-specific Jobs/Pods, readiness, and both
semantic calls must all have timestamps at or after T0. There is no prestaged
model DaemonSet, image pre-pull, artifact copy, checkpoint selection, or
request-derived support object. Each attempt deletes its exact node-group and
provider-created child IDs and verifies absence before the next independent
attempt. Partial creates and cleanup failures remain in the denominator.

Arm B runs conventional and eligible snapshot paths separately for each model;
snapshot-ineligible models retain a conventional result and an explicit
snapshot-not-applicable record. It is never aggregated with Arm A.

The reviewed request-SLO v1 vocabulary cannot encode a successful Arm B run:
`a_to_b_remote` requires a distinct pre-T0 node occupant, while Arm B forbids
any GPU node or model state before T0. This lane therefore admits only the Arm
B capacity-miss negative control until a reviewed versioned `new_node_remote`
scenario is integrated. The broker support-only graph and post-durable-T0
demand interface remain frozen and executable-tested; no run may invent a
donor/occupant to clear this gate.

## Ordered campaign waves

- Wave 1: Boltz2 and OpenFold2, both arms. Arm A runs all six starting states
  and both support variants. Arm B runs conventional and snapshot/new-node
  paths with 30 attempts each after smoke qualification.
- Wave 2: ProteinMPNN, DiffDock, OpenFold3, MSA Search, GenMol, RFdiffusion, and
  MolMIM, using the same arm separation and two-call semantic gates.
- Wave 3: Evo2-40B on its catalog-compatible large-GPU profile. It must not be
  mislabeled as a one-H100 result or mixed into H100 denominators.

The detailed ten-model mapping is in `NIM_COVERAGE_MATRIX.md`.

## Live admission gates

No mutation occurs until all gates pass:

- the resource broker publishes and reviews
  `catalog-switch-kubernetes-resource-lease/v2` with the exact interface frozen
  in `campaign/broker-cluster-interface-required.json`;
- the broker implements that interface's paired-variant handoff/rearm receipt
  before any precreated-Service result can be promoted;
- the shared request-SLO contract publishes a versioned successful new-node
  scenario with no pre-T0 occupant or local cache state;
- the first campaign is materialized as an immutable v2 request and remains
  `PLANNED` until its cost, TTL, prefix, cleanup owner, trace, metric hashes,
  and exact resource graph are reviewed;
- NGC/NIM registry credentials are supplied through the task-owned deployment
  path (credentials are never committed or printed);
- the task-owned image/artifact byte totals, OpenFold2 artifact digest/size,
  templates, semantic validators, cache-control receipts, and GPU sentinel
  image are digest-pinned in one broker-bound reviewed runtime-source manifest;
  support-image build and receipt commits must be reproducible ancestor Git
  blobs;
- capacity advice and project/region/auth checks pass without switching
  profiles, credentials, projects, or regions; and
- server/context, namespace ownership, Ready H100 identity, preemptible flag,
  isolation proof, and rollback/cleanup commands validate before Arm A T0.

After the final cohort, exact-ID broker cleanup must reach `RELEASED`; all task
Pods/services/namespaces/node groups/clusters and provider children must be
NotFound, the task credential and external token must be revoked, and the final
H100 process count and memory baseline must be zero. Provider evidence files
and a five-event audit extension from the admitted lease head are required
before the final seal.
