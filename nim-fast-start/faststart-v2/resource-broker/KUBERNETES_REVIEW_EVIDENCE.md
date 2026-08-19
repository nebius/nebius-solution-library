# Kubernetes v6 replacement review evidence

Recorded 2026-08-19 UTC from isolated branch
`agent/catalog-switch-resource-broker`. Rejected commit
`420de38752da1708f52b7e7f68486cb9debf923d` is preserved unchanged as the
direct parent of this replacement. No Nebius, kubectl, Capacity Advisor, or
provider operation was invoked while preparing or testing this candidate.

## Prior read-only evidence

No new cloud inventory call was made because the manager required a sealed,
zero-resource candidate. The previously recorded read-only evidence remains:

- Nebius CLI `/usr/local/bin/nebius` version `0.12.206`; frozen profile
  `sandbox`.
- Frozen caller `service_account_profile` identity
  `serviceaccount-i00pafr0ydvbaxj952`, parent
  `project-i00xz31gpr00xp9jhp982v`.
- All three authorized projects were `ACTIVE` in their expected regions;
  Kubernetes 1.34, Ubuntu 24.04, the CPU/H100 presets, and `cuda13.0` were
  advertised.
- The installed create API supplies no provider correlation token or audit
  receipt that can distinguish an interrupted broker create from another actor
  copying the exact name, labels, and spec. Such an object remains foreign and
  ambiguous; it is never adopted or deleted.

Canonical prior artifacts:

- `evidence/kubernetes-authorized-inventory-20260819.json`, SHA-256
  `05c0f3b761baf2d9515fc65ab9b90a3be190c3c9e4840861e44624caf8e7243c`.
- `evidence/kubernetes-orphan-scan-review-candidate.json`, SHA-256
  `a16f2bbcb71163d5b9ec5d19da9277efbb906b97622e4036004cc3ba3417accd`.

## Immutable non-admitted candidate

- Lease/backend: `catalog-switch-kubernetes-resource-lease/v6` /
  `nebius-managed-kubernetes/v5`.
- Shared provider-error classifier: `catalog-switch-nebius-error-classifier/v2`;
  new VM plans are `catalog-switch-resource-lease/v2` and cleanup safely reads
  historical VM v1 leases.
- Lease/state: `k8s-baseline-new-node-review4-candidate` / `PLANNED`.
- Project/region: `project-e00z6b02t8ddk96c49` / `eu-north1`.
- Prefix: `mlsp-csw-catalog-switch-k8s-f47bdbe3`.
- Canonical request SHA-256:
  `f47bdbe3dd446b7f346cd5bacf698c82a85d98abfa0df2c6b48567383230ced4`.
- Plan SHA-256:
  `0ff427e6bdbce6d1d3acb7fba226fb463b82636836402b10098966545cc1a6bb`.
- Lease file SHA-256:
  `b63d3e3246dcb8728ec592184f208dd2b0e3a3459e44ccb975281184c5da97e1`.
- Expected duration/cost: four hours / `$8.940816`.
- TTL/deadline/ceiling: 24 hours / `2026-08-20T15:00:00Z` /
  `$53.644899`; hard cap `$60.000000`.
- Exact cleanup owner: `catalog-switch-resource-broker`.
- External accepted-event authority: `PENDING_CONSUMER_REVIEW`.
- Private runner reviewer authority: `PENDING_REVIEWER_REVIEW`.
- Private runner network evidence: `PENDING_CONSUMER_PROOF`.
- `live_creation_gates.admitted` is `false`; cloud IDs, resource rows, create
  operations, cluster/API server, GPU group IDs, and node IDs are all empty.

The 18 immutable graph vertices are exported as
`PLAN_ONLY_CREATE_NOT_ADMITTED`: null exact ID, no create intent, and no false
provider-absence claim. Offline planning created only an ignored task-local
mode-0600 signing key; it is not a cloud resource, is absent from supervisor
exports, and remains scheduled for exact unlink after a future reviewed
lifecycle. Its signed collection begins with one zero-operation/zero-resource
genesis entry and root; neither is provider evidence or live admission.

## Rejection closure

### Executing sealed-source runner authority

`REVIEWED_ACTIVE` is no longer a self-asserted JSON state. A live plan requires
a separate pinned reviewer authority with an Ed25519 public key, reviewed
validator implementation hash, and reviewed source commit. The reviewer-signed
mode-0600 attestation binds the reviewer implementation and the actual executing
broker commit, Git tree, source manifest, entrypoint bytes, and shared CLI bytes
to the lease/task/project/region, runner instance, current Linux boot ID,
current network-namespace inode, and named RFC1918 interface on the exact
task-owned network/subnet. The broker requires the executing files to be clean,
tracked, and byte-identical to that commit before every mutation. The exact
adversary signs `dddd...` as source commit while the observed sealed commit is
`aaaa...`; all fake provider create counts remain zero.

### Authenticated complete resource collection

Every persisted operation and resource row is a member of a signed append-only
collection snapshot containing the immutable graph digest and ordered full-row
hashes. The chain, current signed root, task-local signed anti-rollback anchor,
and graph-to-operation-to-row joins are verified before cleanup. The exact
adversary removes both a live bucket row and its valid signed create operation;
integrity fails, zero bucket deletes occur, and the provider bucket remains
live. A second adversary replays the earlier valid planned collection
root/journal after support creation and is rejected by the latest durable
anchor.

### Complete ACTIVE-entry reconciliation

Control-plane re-entry and GPU re-entry now use one complete-graph routine.
Each reconciles and re-signs current/replacement system provider and Kubernetes
nodes, rebuilds support isolation, then reconciles the GPU group/node and
recomputes exact live product, allocatable count, node identity, and network
proof. Failure is durably `ACTIVE_RECONCILIATION_FAILED`, and only a subsequent
successful full pass restores active state. Exact adversaries prove that
control-plane re-entry rejects a replacement advertising `FOREIGN-GPU`/zero
allocatable GPU, while GPU re-entry rejects a replacement system node carrying
public IP `203.0.113.55`.

### Exact source-bound Arm B identity

Demand v4, the canonical `request.accepted` event, external signed receipt, and
immutable lease must agree on lease ID, request SHA-256, plan SHA-256,
metric-contract SHA-256, trace/trace-request hash, scenario, target/artifact,
input, attempt, request, event, and ledger identities. Clocks still come only
from the signed durable event. Tests reject an actual event with an all-zero
metric hash under an all-one frozen/receipt hash, and reject replay of lease A's
signed event/receipt into lease B even when trace and input match.

### Authenticated cleanup lifecycle

Every resource row now has independent signed ownership and lifecycle
commitments. Lifecycle material covers delete operation, `deleted_at`,
`absence_verified_at`, cleanup evidence, and the exact structured signed
absence receipt. Cleanup verifies both signatures before deciding whether a row
is live or absent. The exact adversary changes a live bucket to forged
deleted/absent evidence; integrity fails, cleanup never reports release, and the
fake provider still contains the bucket. Existing crash-idempotent delete,
dependency barrier, and canonical retry receipt tests remain green.

### Observed worker-network isolation

Every initial and replacement system/GPU Compute node must expose exactly one
RFC1918 address on the lease's exact task-owned network/subnet and no public
interface. Its Kubernetes Node must expose the same `InternalIP` and no
`ExternalIP`. Provider and Kubernetes observations are retained as signed
per-generation evidence, and `public_worker_ips` is derived from observations.
Executable adversaries reject a system node with `203.0.113.10` before support
activation and a public-IP GPU replacement during active reconciliation.

All earlier defenses remain: frozen profile/authority, strict installed
provider schemas, private control plane/internal kubeconfig, signed spec-hashed
intents, ambiguous copied-object preservation, exclusive mutation locking,
provider-child/replacement reconciliation, live GPU product/allocatable
attestation, exact pre-delete ownership checks, capacity-miss no-create proof,
fsynced atomic state, dependency barriers, canonical retry receipts, and
truthful supervisor ambiguity.

The shared CLI wrapper now classifies authentication/authorization failure
before optional absence handling and accepts absence only from a structured
provider `NotFound` code. The VM and Kubernetes adversaries iterate every
cleanup `get`, present
`Unauthenticated: sandbox profile not found` with `allow_not_found=true` and
require the authentication stop rather than a false absence result. A plain
descriptive `profile was not found` error is also rejected. VM lease v2 records
the classifier version; historical v1 cleanup inherits the safe runtime.

## Offline execution evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
  resource-broker/tests`: `57/57 PASS` — ten VM regressions and 47
  Kubernetes/combined-supervisor tests.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v` from
  `faststart-v2`: `55/55 PASS` for the existing fast-start suites.
- Draft 2020-12 validation passed for the v5 request, v4 demand template, VM v2
  lease, and Kubernetes v6 lease. Every resource-broker JSON document parsed;
  candidate
  `assert_integrity`, exact pending gates, and zero-mutation assertions passed.
- Python compilation, secret scan, and `git diff --check` passed.
- Strict provider serialization tests retain `boot_disk.size_bytes`, omit
  disabled Karpenter and public control-plane endpoints, and reject unknown
  provider fields.
- All previous profile/identity, kubeconfig crash window, copied-label/spec,
  provider-child, capacity miss, GPU attestation, concurrent create,
  delete-before-save, parent-skip, retry receipt, and supervisor ambiguity
  adversaries remain green.

## Supervisor ledger and stop condition

The atomic Task Deck ledger at `docs/supervision/resources.json` has schema
`catalog-switch-supervisor-resource-ledger/v2`, four leases, 43 rows, all
manager-required fields, 18 v6 plan-only rows, zero missing required fields,
and `contains_secrets=false`. Its sealed SHA-256 is
`70677c98a0f2dfa1c875c81a5ec275450e479d9ebbc8dd2a5277db443737058b`.

No network, subnet, security group, IAM object, registry, bucket, cluster,
control plane, node group, Compute node, GPU, kubeconfig, workload, or model was
created. Live work stays blocked until the baseline consumer supplies a
reviewed external validator and a separately signed current-runner attestation,
the private runner path is proven, the lease is replanned, and an independent
exact-commit review accepts that replacement.
