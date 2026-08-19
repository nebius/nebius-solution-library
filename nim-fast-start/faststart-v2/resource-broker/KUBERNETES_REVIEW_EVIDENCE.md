# Kubernetes v5 replacement review evidence

Recorded 2026-08-19 UTC from isolated branch
`agent/catalog-switch-resource-broker`. Rejected commit
`d40b6478275d5d5545786d5a3bf69ae46fe22c32` is preserved unchanged as the
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

- Lease/backend: `catalog-switch-kubernetes-resource-lease/v5` /
  `nebius-managed-kubernetes/v4`.
- Lease/state: `k8s-baseline-new-node-review3-candidate` / `PLANNED`.
- Project/region: `project-e00z6b02t8ddk96c49` / `eu-north1`.
- Prefix: `mlsp-csw-catalog-switch-k8s-ce39ad8b`.
- Canonical request SHA-256:
  `ce39ad8b333da2f2a8434299c15630a33a639a5ff6e01cad69e8372800a78c19`.
- Plan SHA-256:
  `8237e05be62691f72e8081774fd1b466b510ac702ebfb7ba3b92a1f60d87fe6e`.
- Lease file SHA-256:
  `6e2bd262ee42acfc5c5d11f5cae74e99c945462a4494be5f80f2072ac10dca20`.
- Expected duration/cost: four hours / `$8.940816`.
- TTL/deadline/ceiling: 24 hours / `2026-08-20T15:00:00Z` /
  `$53.644899`; hard cap `$60.000000`.
- Exact cleanup owner: `catalog-switch-resource-broker`.
- External accepted-event authority: `PENDING_CONSUMER_REVIEW`.
- Private runner reviewer authority: `PENDING_REVIEWER_REVIEW`.
- Private runner network evidence: `PENDING_CONSUMER_PROOF`.
- `live_creation_gates.admitted` is `false`; cloud IDs, resource rows, create
  operations, cluster/API server, GPU group IDs, and node IDs are all empty.

The 16 immutable graph vertices are exported as
`PLAN_ONLY_CREATE_NOT_ADMITTED`: null exact ID, no create intent, and no false
provider-absence claim. Offline planning created only an ignored task-local
mode-0600 signing key; it is not a cloud resource, is absent from supervisor
exports, and remains scheduled for exact unlink after a future reviewed
lifecycle.

## Rejection closure

### Separate trusted runner authority

`REVIEWED_ACTIVE` is no longer a self-asserted JSON state. A live plan requires
a separate pinned reviewer authority with an Ed25519 public key, reviewed
validator implementation hash, and reviewed source commit. The reviewer-signed
mode-0600 attestation binds the exact broker source commit and policy to the
lease/task/project/region, runner instance, current Linux boot ID, current
network-namespace inode, and named RFC1918 interface on the exact task-owned
network/subnet. The broker verifies regular-file ownership/mode, signature, and
the current host observation before every mutation. The executable adversary
rejects fabricated commits, signatures, modes, and boot identities before any
fake support create.

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
before optional NotFound handling. The VM regression presents
`Unauthenticated: sandbox profile not found` with `allow_not_found=true` and
requires the authentication stop rather than a false absence result; both VM
v1 and Kubernetes callers inherit the corrected boundary.

## Offline execution evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
  resource-broker/tests`: `52/52 PASS` — nine VM v1 regressions and 43
  Kubernetes/combined-supervisor tests.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v` from
  `faststart-v2`: `55/55 PASS` for the existing fast-start suites.
- Draft 2020-12 validation passed for the v4 request, v4 demand template, and
  v5 lease. Every resource-broker JSON document parsed; candidate
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
`catalog-switch-supervisor-resource-ledger/v2`, four leases, 41 rows, all
manager-required fields, 16 v5 plan-only rows, zero missing required fields,
and `contains_secrets=false`. Its sealed SHA-256 is
`86737e8be7829d9f54c5a7c72b11a6b4455b95c52307836b35fd94b46953375f`.

No network, subnet, security group, IAM object, registry, bucket, cluster,
control plane, node group, Compute node, GPU, kubeconfig, workload, or model was
created. Live work stays blocked until the baseline consumer supplies a
reviewed external validator and a separately signed current-runner attestation,
the private runner path is proven, the lease is replanned, and an independent
exact-commit review accepts that replacement.
