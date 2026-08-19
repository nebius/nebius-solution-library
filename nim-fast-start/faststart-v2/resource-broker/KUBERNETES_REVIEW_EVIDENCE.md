# Kubernetes v2 review evidence

Recorded 2026-08-19 UTC from isolated branch
`agent/catalog-switch-resource-broker`. This is a sealed offline/read-only
candidate. The extension created no VPC, IAM, Registry, Object Storage,
Managed Kubernetes, Compute, GPU, kubeconfig, workload, or model resource.

## Read-only provider evidence

- Nebius CLI: `/usr/local/bin/nebius` 0.12.206, profile `sandbox`.
- Caller: service account `serviceaccount-i00pafr0ydvbaxj952`, rooted in the
  allowed `project-i00xz31gpr00xp9jhp982v` project. No credential content was
  printed or persisted.
- All three allowed projects were `ACTIVE` in their exact expected regions.
- Managed Kubernetes 1.34, Ubuntu 24.04, `cpu-e2/2vcpu-8gb`, and
  `gpu-h100-sxm/1gpu-16vcpu-200gb` with `cuda13.0` were advertised by the live
  version/platform/compatibility APIs.
- At inventory time `2026-08-19T15:06:55.583194Z`, exact one-H100
  preemptible advice was fresh: fabric-2 76/high, fabric-3 76/high, fabric-4
  67/medium, and fabric-6 46/medium. This is planning evidence only; Arm B
  repeats Capacity Advisor after each durable T0.
- The read-only orphan scan at `2026-08-19T15:11:04.269168Z` completed across
  the allowlist with no errors, no broker-prefixed cloud resources, and no
  unregistered resources.

Canonical files:

- `evidence/kubernetes-authorized-inventory-20260819.json`, SHA-256
  `05c0f3b761baf2d9515fc65ab9b90a3be190c3c9e4840861e44624caf8e7243c`.
- `evidence/kubernetes-orphan-scan-review-candidate.json`, SHA-256
  `a16f2bbcb71163d5b9ec5d19da9277efbb906b97622e4036004cc3ba3417accd`.

## Immutable candidate

- Lease: `k8s-baseline-new-node-candidate`.
- Schema/backend:
  `catalog-switch-kubernetes-resource-lease/v2` /
  `nebius-managed-kubernetes/v1`.
- State: `PLANNED`; cloud resource IDs and GPU node/group IDs are empty.
- Project/region: `project-e00z6b02t8ddk96c49`, `eu-north1`.
- Prefix: `mlsp-csw-catalog-switch-k8s-df4e41bc`.
- Request SHA-256:
  `df4e41bc8d3e913e9778fef1f8e34c0cc4a3b5df9585164fa623b44a5e714982`.
- Immutable plan SHA-256:
  `4d8614b557c22ad054feaa2857285b6255dbdfa7e6879d50ff83b88ae64c9e1b`.
- Lease file SHA-256:
  `32a23113b368e08e350e2c0c4efce1586886b0578ecbd2f2dbc9056a69dc12fd`.
- Expected duration/cost: four hours / `$8.940816`.
- TTL/deadline/ceiling: 24 hours / `2026-08-20T15:00:00Z` /
  `$53.644899`.
- Hard cap/cleanup owner: `$60.000000` /
  `catalog-switch-resource-broker`.

The plan has 16 explicit graph vertices before provider children are known:
network, subnet, deny-all security group, service account, custom IAM group,
membership, registry, registry permit, artifact bucket, artifact permit,
cluster, system node group/node, kubeconfig authority, and demand-gated GPU
node group/node. Every planned supervisor row has a null ID, `NOT_CREATED`,
desired final state `ABSENT`, and explicit no-create evidence.

## Offline execution evidence

- 25 installed CLI create/delete/version/compatibility/get-credentials command
  paths returned help successfully; no create/delete command was executed.
- Draft 2020-12 validation passed for the frozen request and generated v2
  lease.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
  resource-broker/tests`: 24/24 passed. This includes all eight unchanged VM v1
  tests and 16 Kubernetes/combined-ledger tests.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v` from
  `faststart-v2`: 55/55 existing tests passed.
- `python3 -m py_compile` passed for the backend, union supervisor, and tests;
  every new JSON document parsed; `git diff --check` passed.
- The atomic Task Deck supervisor export has schema
  `catalog-switch-supervisor-resource-ledger/v2`, four total leases, 41 rows,
  zero missing manager-required fields, explicit cleanup/absence evidence on
  every row, and `contains_secrets=false`.

Mock adversaries proved: immutable-plan tamper rejection; foreign exact-name
preservation; duplicate plan/demand idempotency; Arm B GPU-create rejection
before durable T0; future-clock rejection; capacity failure retention without
a create; interruption after both cluster and GPU group creates; adoption only
from a persisted exact intent; no duplicate create on resume; interrupted GPU
group/node reconciliation before cleanup; Arm A prepared-node behavior; reverse
exact-ID cleanup; provider-child NotFound receipts; and kubeconfig-tamper
preservation.

## Review stop

Per manager direction, no live support or GPU resource will be created from
this candidate until independent review accepts the schema, cost/TTL plan,
security-group limitation, IAM graph, causal demand interface, and cleanup
proof design.
