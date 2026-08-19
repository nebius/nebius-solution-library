# Kubernetes lease backend v4

`kubernetes_broker.py` is the sole Managed Kubernetes creation path for the
catalog-switch program. It is additive: VM backend v1 is unchanged. Modal is
excluded. This v4 replacement was prepared without creating a cloud resource.

## Frozen authority and plan

The v3 request freezes the `sandbox` profile and the exact `iam whoami`
identity type, ID, and parent project. Every mutating entry point rechecks both
before its first mutation; profile or identity drift is an authentication stop.
The project/region allowlist, Kubernetes version, private-control-plane policy,
CPU/H100 shapes, preemptibility, duration, cost, TTL, cleanup owner/deadline,
metric/trace/model-input identities, accepted-event validation authority, and
private-API runner receipt are also frozen.

The v4 plan commitment covers the request and profile hashes plus lease ID,
schema/backend versions, prefix, project, region, creation/expiry timestamps,
all ownership labels, signing authority, cost, resource graph, kubeconfig path
and context, GPU policy, and cleanup policy. Changing any authorization-bearing
field invalidates the plan.

Planning creates a mode-0600 task-local Ed25519 private key under ignored
`lease-keys/` and commits only its public key/path metadata. Create intents and
resource ownership rows are signed. The key is never emitted to the ledger or
supervisor and is unlinked after full verified cleanup; public-key verification
of the historical rows remains possible.

## Exact graph and provider schemas

The graph owns a fresh VPC/network, subnet, deny-all security-group sentinel,
node service account, custom IAM group and membership, registry and exact
permit, capped artifact bucket and exact permit, Managed Kubernetes cluster,
normal CPU system group/node, kubeconfig authority, and a preemptible H100
group/node. Provider-created pools, route table, and Compute node children are
discovered and ledgered by exact ID.

Nebius CLI `0.12.206` is the serialization authority. Strict validation rejects
unknown cluster/node-group fields before calling the provider. In particular:

- boot disk GiB values are converted to exact `boot_disk.size_bytes` integers;
- disabled Karpenter is represented by omitting `control_plane.karpenter`;
- private control-plane access is represented by omitting
  `control_plane.endpoints`; and
- kubeconfig retrieval uses `--internal`, never `--external`.

The cluster response must expose one internal/private endpoint and no public
endpoint. Worker templates use only the fresh private subnet and omit public IP
requests. Managed Kubernetes v1 has no node-group security-group attachment
field, so the graph records the fresh zero-rule security group as a lifecycle
sentinel and does not falsely claim it enforces node traffic.

## Collision, interruption, and replacement handling

One advisory mutation lock covers the entire lease operation, not only registry
writes. Before every cloud create, the broker persists a signed intent containing
the exact payload/spec digests and full requested spec. A same-name result may be
accepted only from the synchronous create response. The installed Nebius create
API supplies no request correlation token or audit receipt that can distinguish
an interrupted broker create from another actor copying the exact name, labels,
and spec. Therefore any exact-name object first seen after an unreceipted intent
is marked `AMBIGUOUS_FOREIGN_PRESERVED`, is never adopted or deleted, and blocks
ancestor cleanup. Matching labels/spec/time are deliberately insufficient.

Compute children are discovered with provider APIs independently of kubeconfig.
This closes the crash window after node creation but before credentials exist.
Every call against an `ACTIVE` system or GPU lease reruns child reconciliation;
provider replacements are added, replaced IDs receive exact NotFound evidence,
and GPU replacements undergo a new live attestation.

GPU readiness is not copied from the plan. The broker joins the Kubernetes
providerID to the exact Compute instance, verifies the node-group marker,
platform, preset, preemptible state, Kubernetes `nvidia.com/gpu.product`,
allocatable `nvidia.com/gpu`, Ready condition, node UID, and exact one-node/one-GPU
cardinality. The attestation is retained in the attempt receipt.

## Kubeconfig authority

Credentials are generated at a unique staging path after a signed intent. The
broker validates the exact context, cluster entry, user entry, private server,
embedded CA digest, cluster ID, file digest, current-user ownership, and mode
0600. It signs and durably saves that content-authority receipt before atomically
renaming the staging file to the planned path and signing the resource row.
Both the staged file and its parent directory are fsynced. All atomic JSON state
replacement and local-secret unlink paths likewise fsync the affected parent
directory before reporting success.

After a crash, a final or staging file is adopted only if it matches that exact
signed receipt. A file appearing after intent but before a signed receipt is
unknown: it is preserved and cleanup fails. Both paths existing is ambiguous
and also fails closed. Cleanup revalidates the signed structure and digest
before unlinking.

## Reviewed source-bound Arm B T0

The Arm B demand v3 does not trust caller-supplied clocks or a private file's
shape. It names both the exact durable JSONL event and a mode-0600 receipt signed
by a reviewed external recorder/validator authority. The immutable authority
entry pins the Ed25519 public key, validator implementation SHA-256, and reviewed
source commit. `record-demand` verifies that signature before reading the ledger
and then requires exactly one matching canonical event with:

- schema `archvteams.nebius.ai/catalog-switch-ledger-event/v1`;
- event `request.accepted`, attempt sequence zero, and boundary
  `external-client-request-accepted/v1`;
- an exact attempt/request/trace/ledger identity join;
- the frozen trace ID, trace-request SHA-256, metric-contract SHA-256, scenario,
  and complete target/artifact/input identity; and
- the frozen external recorder on the current Linux boot/monotonic clock.

The broker derives T0 clocks from that event, rejects future or support-stale
events, records file device/inode/mode/size/mtime/full-file digest/line index,
and signs the resulting demand receipt. Capacity advice and create clocks are
checked against that signed T0 before every provider call. Missing, forged,
ambiguous, wrong-contract/trace/scenario/target/input, wrong-clock, and stale
events are rejected.

Production live creation is additionally blocked until the baseline consumer
publishes a reviewed task-owned, private-subnet runner receipt proving internal
API reachability with no public IP or public ingress. The shipped candidate has
both this runner gate and the external receipt authority set to pending; it
cannot invoke a provider create.

## Cleanup and supervisor truth

Cleanup first reconciles all interrupted creates and all provider children. An
unknown create window blocks deletion. Every signed resource row is verified,
then a live pre-delete `get` must match its exact ID, name, parent, required
labels, and signed spec. A durable delete intent precedes deletion. Retry first
checks absence, so a crash after provider deletion never reissues the delete;
NotFound is success only with a recorded proof.

Deletion follows dependency order. A child failure installs a barrier over all
transitive parents and provider children of blocked parents, preserving what is
needed for recovery. Attempt cleanup reconstructs its final group/node receipt
from all durable resource-row evidence across retries, including crashes after
either deletion save.

An honest post-T0 `NO_PREEMPTIBLE_CAPACITY` result has no resource rows. Before
returning that failure, the broker lists the exact cluster parent and intended
node-group name, requires zero matches and zero create intents, and persists a
signed `catalog-switch-kubernetes-no-create-absence-receipt/v1`. Attempt cleanup
accepts only that exact signed no-create proof, retaining the capacity failure
while returning the support lease to a releasable state.

Supervisor rows distinguish:

- `PLAN_ONLY_CREATE_NOT_ADMITTED` — no create was admitted; no absence claim;
- `CREATE_PENDING_RECONCILIATION` — a signed intent has no exact ID;
- `CREATE_AMBIGUOUS_RECONCILIATION_REQUIRED` — failure/ambiguity needs provider
  reconciliation; and
- `ABSENCE_VERIFIED` — exact provider/local proof exists.

The atomic union ledger contains no tokens, kubeconfig contents, signing private
key, or signed URLs.

## Commands

Planning and inventory are non-mutating:

```bash
python3 kubernetes_broker.py inventory --output evidence/kubernetes-authorized-inventory-20260819.json
python3 kubernetes_broker.py plan \
  --request examples/k8s-baseline-new-node-request.json \
  --lease kubernetes-leases/k8s-baseline-new-node-candidate.json
```

After the consumer proofs are reviewed, a new immutable plan is sealed, and its
exact commit is accepted, support/GPU execution require explicit execute
commands. Arm B must first provide its source-bound demand file:

```bash
python3 kubernetes_broker.py provision-control-plane --lease kubernetes-leases/<lease>.json --execute
python3 kubernetes_broker.py record-demand --lease kubernetes-leases/<lease>.json --demand /task-owned/demand.json
python3 kubernetes_broker.py provision-gpu-node-group --lease kubernetes-leases/<lease>.json --execute
python3 kubernetes_broker.py cleanup-attempt --lease kubernetes-leases/<lease>.json --execute
python3 kubernetes_broker.py cleanup --lease kubernetes-leases/<lease>.json --execute
```

The candidate retains the prior cost contract: support `$0.056026/hour`, one
active preemptible H100 `$2.235204/hour`, four-hour estimate `$8.940816`,
24-hour ceiling `$53.644899`, and hard cap `$60.000000`. Pricing assumptions
and official sources remain frozen in `kubernetes_profiles.json`.
