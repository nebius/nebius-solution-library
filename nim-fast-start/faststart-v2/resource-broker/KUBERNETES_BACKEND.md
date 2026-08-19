# Kubernetes lease backend v2

`kubernetes_broker.py` is the sole Managed Kubernetes creation path for the
catalog-switch program. It is additive: the VM contract in `broker.py` remains
v1 and its manifests, state machine, and cleanup behavior are unchanged.
Modal is outside this backend.

No live resources were created while preparing this candidate. The committed
`k8s-baseline-new-node-candidate` lease is `PLANNED` and exists for independent
review of the graph, cost cap, policy, commands, and consumer interface.

## Fixed boundary

The backend is pinned to:

- Nebius profile `sandbox`.
- The three project/region pairs in the epic allowlist.
- Managed Kubernetes 1.34, Ubuntu 24.04, one normal `cpu-e2` system node, and
  at most one preemptible `gpu-h100-sxm` / `1gpu-16vcpu-200gb` node at a time.
- Fresh `mlsp-csw-<task>-<request-hash>` resources only. Existing VPCs,
  subnets, clusters, identities, registries, buckets, node groups, and model
  resources are neither adopted nor changed.
- Fixed-size node groups. Karpenter and autoscaling are disabled so the broker,
  not an independently acting controller, owns the capacity/create boundary.

Every cloud create is preceded by a persisted intent. A resumed call first
lists the exact parent/name, validates all ownership labels and the creation
time against that intent, and either reconciles the single exact result or
stops. An object with the right name but no matching intent, labels, parent, or
creation time is foreign and is preserved.

## Immutable plan and states

`plan` validates `kubernetes-request.schema.json`, normalizes it, hashes the
complete request, snapshots and hashes the profile, and writes a v2 lease. The
request freezes campaign arm, project/region/profile, Kubernetes version,
expected duration, TTL, cleanup deadline/owner, hard cost cap, metric and trace
hashes, model-input hashes, artifact quota, purpose, and cleanup plan.

The principal states are:

```text
PLANNED
  -> CONTROL_PLANE_CREATING
  -> SUPPORT_ACTIVE_NO_GPU_NODE_GROUP
       Arm A -> ACTIVE
       Arm B -> DEMAND_RECORDED
              -> ACTIVE_ATTEMPT
              -> ATTEMPT_CLEANING
              -> SUPPORT_ACTIVE_NO_GPU_NODE_GROUP
  -> CLEANING -> RELEASED
```

Failures are durable states (`CONTROL_PLANE_FAILED`, `GPU_CAPACITY_FAILED`,
`GPU_CREATE_FAILED`, `ATTEMPT_CLEANUP_FAILED`, or `CLEANUP_FAILED`). The lease
keeps every failure, causal event, create intent, capacity snapshot, partial
resource ID, and retry/reconciliation result. Retrying never erases a failed
attempt or creates a second exact-name resource.

## Exact resource graph

The v2 lease contains a machine-readable graph with these owned vertices:

| Vertex | Parent/dependency | Lifecycle |
| --- | --- | --- |
| Network | Project | Fresh private pools; no public pool |
| Subnet | Network | Private pool only |
| Security group | Network | Fresh deny-all lifecycle sentinel |
| Node service account | Project | Used by both node groups |
| Custom IAM group | Tenant | Never reuses a default group |
| Group membership | Custom group + service account | Exact task membership |
| Container Registry | Project | Fresh artifact/image dependency |
| Registry access permit | Custom group + registry | Exact-resource `viewer` |
| Object Storage bucket | Project | Fresh, capped, audited artifact dependency |
| Bucket access permit | Custom group + bucket | Exact-resource `storage.editor` |
| Managed Kubernetes cluster | Subnet | 1.34, audit logs, Karpenter off |
| System node group/node | Cluster + private subnet + task service account | One normal CPU node |
| Kubeconfig authority | Cluster + invoking identity | Exact local 0600 file; content never ledgered |
| GPU node group/node | Cluster + post-T0 demand for Arm B | One preemptible H100 node |
| VPC pools/route table | Network | Provider-cascade children reconciled by exact ID |

Managed Kubernetes v1 does not expose a security-group attachment field on a
node-group network interface. The broker therefore does not claim the deny-all
security group enforces worker traffic. Worker isolation is instead proved by
the fresh private subnet, an empty VPC public-pool list, and node-group
interfaces with no `public_ip_address`. The task-owned security group remains
in the exact graph, has zero rules, and is cleaned up, but its proof explicitly
records `NOT_SUPPORTED_BY_MANAGED_K8S_NODE_GROUP_V1_API`.

The control plane has a provider-managed public HTTPS endpoint so the isolated
runner can obtain scoped credentials. Worker nodes have no public IPs. The
kubeconfig path is broker-owned, fixed by the lease, required to be a regular
file owned by the current user with mode 0600, and represented only by path,
SHA-256, identity ID, cluster ID, endpoint, and context. Cleanup refuses to
unlink it if its hash or ownership changed.

## Arm A and Arm B

Arm A may provision its exact preemptible GPU node group after target-neutral
support and before the campaign cohort T0. It becomes `ACTIVE`; request-specific
switching remains after each request T0.

Arm B enters its request boundary in
`SUPPORT_ACTIVE_NO_GPU_NODE_GROUP`. The benchmark must durably persist
`request.accepted` first, then submit a demand conforming to
`kubernetes-demand.schema.json`. `record-demand` verifies both clocks and the
accepted-event digest without contacting the cloud. Only after that record may
`provision-gpu-node-group`:

1. persist `gpu.capacity_advice.started`;
2. call Capacity Advisor and retain its complete exact-preset snapshot;
3. fail the attempt if fresh preemptible capacity is unavailable;
4. persist the node-group create boundary;
5. create/reconcile one unique fixed-size preemptible group;
6. record its exact group ID, Kubernetes UID/name, Compute provider ID, Ready
   timestamp, GPU product/count, and causal-order result.

Provider capacity and create failures are valid measured outcomes. They remain
in the attempt receipt and `failures`; they are not retried into a successful
denominator without the failed record. Model image pull, artifact localization,
checkpoint selection, model Pod creation, and semantic inference remain the
consumer's responsibility and are forbidden before T0 for Arm B.

## Commands

Planning and inventory are non-mutating:

```bash
python3 kubernetes_broker.py inventory \
  --output evidence/kubernetes-authorized-inventory-20260819.json

python3 kubernetes_broker.py plan \
  --request examples/k8s-baseline-new-node-request.json \
  --lease kubernetes-leases/k8s-baseline-new-node-candidate.json
```

After independent review, a live owner would explicitly execute support:

```bash
python3 kubernetes_broker.py provision-control-plane \
  --lease kubernetes-leases/<lease>.json --execute
```

For Arm B, after the consumer has durably written `request.accepted`:

```bash
python3 kubernetes_broker.py record-demand \
  --lease kubernetes-leases/<lease>.json --demand /task-owned/attempt-demand.json
python3 kubernetes_broker.py provision-gpu-node-group \
  --lease kubernetes-leases/<lease>.json --execute
```

The attempt must be removed before the next independent Arm B demand:

```bash
python3 kubernetes_broker.py cleanup-attempt --lease kubernetes-leases/<lease>.json
python3 kubernetes_broker.py cleanup-attempt --lease kubernetes-leases/<lease>.json --execute
```

Full cleanup is also dry-run first:

```bash
python3 kubernetes_broker.py cleanup --lease kubernetes-leases/<lease>.json
python3 kubernetes_broker.py cleanup --lease kubernetes-leases/<lease>.json --execute
```

Deletion uses recorded exact IDs in reverse dependency order. Provider nodes,
VPC pools, and the route table are verified absent after their owning node
group/network is deleted. Unregistered prefixed resources are scanner findings
for manual review and are never emergency-deleted.

## Cost contract

The profile uses Nebius public prices observed 2026-08-19. Managed Kubernetes
nodes are billed as Compute VMs, and the public Managed Kubernetes page lists no
separate control-plane fee. The candidate estimates:

- target-neutral support: `$0.056026/hour`;
- support plus one preemptible H100: `$2.235204/hour`;
- expected four-hour maximum: `$8.940816`;
- 24-hour TTL ceiling: `$53.644899`;
- immutable hard cap: `$60.000000`.

The ceiling assumes the GPU exists for the full TTL, all 364 GiB of declared
node boot disks exist, and all 10 GiB of the bucket quota is occupied. Taxes,
traffic, requests, logs, and discounts are excluded. Sources:

- <https://docs.nebius.com/kubernetes/resources/pricing>
- <https://docs.nebius.com/compute/resources/pricing>
- <https://docs.nebius.com/object-storage/resources/pricing>
- <https://docs.nebius.com/container-registry/resources/pricing> (the service
  is currently free of charge)

## Supervisor and tests

`supervisor_ledger.py` atomically unions VM v1 and Kubernetes v2 into the Task
Deck supervisor file. Every resource row has project, region, type, name, exact
ID or null, owner task, purpose, creation/expiry timestamps, desired final
state, cleanup owner/state, and explicit cleanup/absence evidence. It contains
no kubeconfig contents, access tokens, signed URLs, or other secrets.

```bash
python3 supervisor_ledger.py
python3 -m unittest discover -v tests
```

The mocked suite covers full support/GPU lifecycle, post-T0 gating, capacity
failure retention, request/plan idempotency, interruption immediately after a
provider create, exact-name reconciliation without duplication, foreign
collision preservation, kubeconfig tamper preservation, dependency-ordered
cleanup, exact-ID absence receipts, and the supervisor schema.
