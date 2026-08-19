# Kubernetes v3 replacement review evidence

Recorded 2026-08-19 UTC from isolated branch
`agent/catalog-switch-resource-broker`. Commit `662666c7` remains in history
unchanged. This replacement is sealed for a new exact-commit review and created
no Nebius resource.

## Read-only provider evidence

- Nebius CLI `/usr/local/bin/nebius` is version `0.12.206`; frozen profile is
  `sandbox`.
- Frozen caller is `service_account_profile` identity
  `serviceaccount-i00pafr0ydvbaxj952`, parent
  `project-i00xz31gpr00xp9jhp982v`.
- The prior zero-mutation inventory remains canonical: all three allowed
  projects were `ACTIVE` in their expected regions; Kubernetes 1.34, Ubuntu
  24.04, the CPU/H100 presets, and `cuda13.0` were advertised.
- Planning Capacity Advisor evidence for exact preemptible one-H100 capacity was
  fresh on four `eu-north1` fabrics. It is not execution authority; Arm B must
  query again after a source-bound T0.
- Installed create help/schema was reread without cloud mutation. It confirms
  `boot_disk.size_bytes`, object-valued enabled Karpenter/public endpoint fields,
  and omission for disabled/private configuration.
- The prior complete orphan scan found zero broker-prefixed resources. No scan
  or create was needed for this code-only replacement because manager direction
  forbids a cluster before review.

Canonical read-only artifacts:

- `evidence/kubernetes-authorized-inventory-20260819.json`, SHA-256
  `05c0f3b761baf2d9515fc65ab9b90a3be190c3c9e4840861e44624caf8e7243c`.
- `evidence/kubernetes-orphan-scan-review-candidate.json`, SHA-256
  `a16f2bbcb71163d5b9ec5d19da9277efbb906b97622e4036004cc3ba3417accd`.

## Immutable candidate

- Lease/backend: `catalog-switch-kubernetes-resource-lease/v3` /
  `nebius-managed-kubernetes/v2`.
- Lease/state: `k8s-baseline-new-node-candidate` / `PLANNED`.
- Project/region: `project-e00z6b02t8ddk96c49` / `eu-north1`.
- Prefix: `mlsp-csw-catalog-switch-k8s-4ea2e0e1`.
- Request SHA-256:
  `4ea2e0e15a57bff09d35a637b867d154e867af4c4e4cdf76f4a942e358052aeb`.
- Plan SHA-256:
  `5235dc1afec32ee4977d4aef241cd8f0026fc0631a13953dfe380b1a16cae28f`.
- Lease file SHA-256:
  `11b44858e2b43eaf33132af16e8ddbceea9cd8d7046939397d364692dd56c9cf`.
- Expected duration/cost: four hours / `$8.940816`.
- TTL/deadline/ceiling: 24 hours / `2026-08-20T15:00:00Z` /
  `$53.644899`.
- Hard cap/cleanup owner: `$60.000000` /
  `catalog-switch-resource-broker`.
- Cloud IDs, cluster ID, GPU group IDs, node IDs, and API server are all empty.

The plan has 16 graph vertices. Every candidate supervisor row is
`PLAN_ONLY_CREATE_NOT_ADMITTED`, has a null ID, explicitly makes no provider
absence claim, and requires no reconciliation because there is no create
intent. The local Ed25519 private signing authority is mode 0600, ignored by
Git, absent from every ledger/export, and scheduled for exact unlink after a
future full cleanup. Only its public key/path commitment appears in the plan.

## Blocker corrections

- Profile and exact identity are immutable and checked before every mutation.
- Cluster and both node-group payloads are strict against CLI 0.12.206 fields;
  boot disks use exact byte values, while Karpenter/endpoints are omitted.
- The cluster is private-only and credentials use the internal endpoint.
- Kubeconfig staging/content authority is signed before atomic promotion;
  unknown or dual-path crash files are preserved and block cleanup.
- Arm B reads and hashes an exact durable baseline JSONL event, derives its
  clocks, joins all request/attempt/model/input identities, binds the recorder
  and Linux boot, and signs the accepted-demand receipt.
- GPU receipts include live Kubernetes product/allocatable evidence joined to
  the exact provider Compute child and signed group intent.
- Signed create intents include payload/spec digests and the full requested
  spec. Resource rows are Ed25519 authenticated. Cleanup performs pre-delete
  exact-ID/name/parent/labels/spec verification.
- One exclusive per-lease mutation lock prevents concurrent creates.
- ACTIVE calls reconcile normal/preemptible replacements. Provider children
  are discovered through Compute APIs without kubeconfig.
- Delete intent, pre/post absence checks, and NotFound reconciliation make a
  crash after deletion idempotent. A child failure barriers all ancestors.
- Attempt receipts are rebuilt from all durable deletion evidence across
  retries. Supervisor rows expose pending/ambiguous creates instead of false
  absence.
- Lease ID, owner/task/prefix labels, creation/deadline times, cleanup owner,
  authority, and every other authorization field are covered by the immutable
  commitment.

## Offline execution evidence

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
  resource-broker/tests`: `42/42 PASS` — eight unchanged VM v1 tests and 34
  Kubernetes/combined-supervisor tests.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v` from
  `faststart-v2`: `55/55 PASS`.
- Draft 2020-12 validation passed for the v2 request and v3 lease; every
  resource-broker JSON document parsed; candidate `assert_integrity` passed.
- Python compilation and `git diff --check` passed. `broker.py` is byte-for-byte
  unchanged from `662666c7`.
- The strict fake rejects unknown provider fields. Tests also inspect installed
  CLI help and require `size_bytes`, reject `size_gibibytes`, and verify cluster
  omission of Karpenter/endpoints.
- Adversaries cover switched profile/identity, concurrent calls, same-name
  wrong-spec adoption, signed-row injection, live pre-delete spec substitution,
  unknown and receipted kubeconfig crash windows, missing/forged/stale T0,
  wrong identity/clock, system-node crash before kubeconfig, GPU product/count
  mismatch, preemptible replacement, delete-before-save crash, dependency
  barrier, supervisor ambiguity, immutable-field mutation, and crashes after
  each attempt deletion save.

## Supervisor and stop condition

The atomic Task Deck ledger at `docs/supervision/resources.json` has schema
`catalog-switch-supervisor-resource-ledger/v2`, four leases, 41 rows, all
manager-required fields, 16 v3 plan-only rows with no absence claim, zero
missing fields, and `contains_secrets=false`. Its current SHA-256 is
`c266540cb4984e626116a685f649951e1fe316616bc2c200a0f8b5d44839fb68`.

No network, subnet, security group, IAM object, registry, bucket, cluster,
control plane, node group, Compute node, GPU, kubeconfig, workload, or model was
created. The next action is a fresh independent review of the pushed exact
commit; live creation remains forbidden until that review accepts it.
