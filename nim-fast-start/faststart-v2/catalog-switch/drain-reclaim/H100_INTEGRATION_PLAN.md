# Fresh single-H100 integration plans

This is the immutable pre-creation design for two independent live lanes. It
does not authorize an existing resource, does not claim that either run has
occurred, and must be refreshed with exact immutable lease files immediately
before live work.

Both lanes are gated on fresh independent acceptance of the v3 state-machine
candidate and on task-owned pilot images/artifacts with pinned semantic
validators. No live resource is created in this commit.

## Common boundary and ownership

- Owner and cleanup owner:
  `catalog-switch-drain-reclaim-state-machine`.
- Allowed target: `project-e00z6b02t8ddk96c49`, `eu-north1`. Stop before
  creation if the active profile resolves anywhere else.
- Sole creation path: catalog-switch resource broker commit `662666c7` (which
  contains VM contract commit `229101bb`). The eventual execution branch must
  first integrate that exact reviewed broker source and retain its schemas and
  tests. Do not copy commands out of an unintegrated worktree for a live run.
- Names: a collision-resistant `mlsp-csw-catalog-switch-drain-reclaim-*`
  prefix and ownership/expiry labels on every resource.
- Fresh dependencies only: no existing network, subnet, security group,
  service account, IAM group, registry, bucket, disk, VM, cluster, node group,
  node, endpoint, model deployment, dataset, image cache, artifact cache,
  kubeconfig, or node-agent authority may be reused, attached, or modified.
- Preferred scheduling: preemptible one-H100. A separately planned on-demand
  retry is allowed only after a preemption makes the experiment invalid; the
  failed preemptible attempt remains in the denominator and its exact resources
  are cleaned first.
- Shared product boundary: durable external `request.accepted` is T0. Drain,
  reclaim, capacity wait, node creation, image/artifact localization, launch,
  semantic calls, failures, rollback, accounting, and cleanup remain after T0
  and in the same causal record. No idle TTL hides reclaim.
- Switch mutation gate: after T0, the bridge must mirror the exact acceptance,
  append its acceptance terminal, persist that predecessor-hash segment to the
  fresh immutable off-node authority, and pass its canonical receipt through
  the mandatory verifier before `DRAINING_A`. A scalar timestamp is rejected.
- Modal is excluded: no authentication, deployment, command, synthetic score,
  empirical rank, or provider adapter.

Before provisioning, each immutable request must contain the candidate commit,
`contract.json` SHA-256, source broker commit, resource graph, project/region,
preemptible flag, expected duration, maximum TTL, hard cost cap, cleanup owner,
model/artifact/input/validator hashes, image digests, command-policy hash,
node-agent digest/key authority, request-SLO contract/trace hashes, and the
fresh off-node audit authority. Authentication, authorization, quota, or
capacity failure is a stop condition; do not change profile, account, project,
region, or credentials.

## Lane N: fresh direct/node-local VM

Use the broker VM v1 interface contained in `662666c7` to create one fresh
private network/subnet, deny-all security group, task service account, registry
and immutable off-node evidence storage, encrypted boot/artifact disks, and one
single-H100 VM. The node-local controller communicates only with the pinned
node agent over the authenticated task-local channel.

- Expected active duration: 3 hours.
- TTL/cleanup deadline: 6 hours after lease creation.
- Hard cost cap: USD 20, with the broker's plan required to show its exact
  dated price inputs and a TTL ceiling below the cap.
- Identity gate: exact VM/resource ID, node UID, boot ID, GPU UUID/total bytes,
  node-agent source digest, public-key ID, and attestation chain.
- Action gate: every stop, scrub, cleanup, launch, revoke, and recycle command
  carries the signed `CommandEnvelope`; the agent returns its source-bound
  `ActionReceipt` and independently refuses stale generation, replay, policy
  drift, or second occupancy.
- Occupancy gate: the receiving agent must fsync GPU UUID, operation ID,
  generation, reservation digest, and command digest before launch dispatch.
  Submit a second distinct, correctly signed launch while the first remains
  occupied; the second physical runner invocation count must remain zero.

The controller must never run `/proc`, cgroup, container, or NVML checks on its
own host. Those probes execute on the attested target node and return signed
evidence bound to the exact node and boot.

## Lane K: fresh Managed Kubernetes cluster and H100 node group

Use only the Kubernetes v2 interface at broker commit `662666c7`:

- request schema `catalog-switch-kubernetes-lease-request/v1`;
- lease schema `catalog-switch-kubernetes-resource-lease/v2`;
- post-T0 demand schema `catalog-switch-kubernetes-node-demand/v1`;
- backend `nebius-managed-kubernetes/v1` and campaign arm
  `B_new_preemptible_node`.

The immutable support plan creates a new network/subnet, service account and
custom IAM group, fresh registry and off-node artifact/evidence bucket, Managed
Kubernetes 1.34 cluster, one normal CPU system group, and broker-owned mode-0600
kubeconfig. It must reach `SUPPORT_ACTIVE_NO_GPU_NODE_GROUP` with both top-level
GPU node/group arrays empty before a measured request.

After the bridge has fsynced `request.accepted`, write the exact demand object
containing `lease_id`, `attempt_id`, accepted-event SHA-256, and both accepted
T0 clocks. Invoke `record-demand`, then `provision-gpu-node-group --execute`.
Capacity advice and every create timestamp/failure are part of the attempt.
The broker may create exactly one fixed-size preemptible
`gpu-h100-sxm/1gpu-16vcpu-200gb` group and node. Model-specific Pod work remains
after T0.

- Expected support plus active GPU duration: 4 hours.
- TTL/cleanup deadline: 24 hours after plan creation.
- Hard cost cap: USD 60; the reviewed example ceiling was USD 53.644899 on
  2026-08-19, but the live plan must recompute current prices.
- API identity gate: absolute kubeconfig path and SHA-256, exact context, API
  server URL, decoded server-CA SHA-256, cluster UID from `kube-system`, task
  namespace, Kubernetes node UID/provider ID, node boot ID, Pod UID, full
  container ID, GPU UUID/total bytes, and signed node-agent authority.
- Command gate: `kubectl` is an absolute non-symlink executable with its exact
  content SHA-256 bound into runtime authority; it is never resolved through
  `PATH`. API-side actions use that executable and the pinned kubeconfig/
  context. Host cleanup/scrub/NVML actions still execute through the exact
  signed node agent. The receiving agent enforces the operation/executable,
  artifact, and privilege allowlist before dispatch. Both paths return source-
  bound receipts.
- Repeat the receiving-agent occupancy adversary through the Kubernetes
  adapter: both envelopes and both exact-cluster preflights are valid, but only
  the first launch command may reach the physical runner.

Before the next independent request, `cleanup-attempt --execute` must prove the
exact GPU node group and provider node absent and restore
`SUPPORT_ACTIVE_NO_GPU_NODE_GROUP`. After the cohort, full broker cleanup must
remove the support graph too.

## Required switch and fault matrix in each lane

Every admitted attempt ends in a complete success closure or explicit failure,
accounting, and cleanup; no row is discarded. Run at least:

1. idle A -> B;
2. A request completing inside the drain window -> B;
3. hung A crossing the deadline, timeout persistence, kill, and late-response
   rejection;
4. duplicate B and competing controller commands, proving one physical launch;
5. lost launch response before bind and controller crash after launch;
6. B failure after a GPU process exists, exact B cleanup, separate B failure
   terminal, then a causally linked rollback-A trace;
7. cancellation during drain and during B startup;
8. wrong-node authority (both lanes) and wrong kubeconfig/context/cluster UID/
   server CA/namespace/node UID (Kubernetes), all rejected;
9. observed compute and graphics processes blocking release; successful empty
   and header-only `nvidia-smi pmon` output must also fail rather than prove
   zero graphics contexts;
10. partial cleanup or evidence write loss entering quarantine, then exact
    lease revocation, recycle/new resource, fresh boot, and requalification.

Every accepted B and rollback-A recovery uses two distinct real model requests
and two complete raw semantic responses. Call 2 starts strictly after call 1
completes. Validator execution is derived from its exact pinned canonical
source artifact, with no separately supplied callback; a
health/readiness response, self-asserted boolean, duplicate body, altered
validator, prior call, or restart is failure. Call 1 alone remains the product
terminal.

## Executable security-control matrix

Run every row separately in Lane N and Lane K and keep the signed receipts in
that lane's audit segment.

| Test | Injection and acceptance rule |
| --- | --- |
| TST-01 GPU residue | A allocates sentinel VRAM. After exact runtime absence, run a full-total-byte scrub and two zero-process/zero-graphics/zero-byte NVML samples. B allocates all available VRAM and scans for the sentinel. Repeat after partial B launch. Any hit, short scrub, foreign context, or nonzero byte fails and quarantines. |
| TST-02 host residue | A writes sentinels to every writable path, opens a socket, spawns a child, and creates labeled runtime objects. B plus the node agent prove no PID/cgroup/container/Pod, mount, namespace, socket, scratch, keyring, log, core, or readable sentinel remains; verify swap/core/dmesg/log-policy controls. Repeat after failed B. |
| TST-11 occupancy and privilege | Assert the pinned capability/seccomp/namespace/mount/egress profile. While A serves, submit a second launch through placement and a different validly signed direct command. The node agent must refuse both and issue a single-occupancy receipt. |
| TST-12 audit continuity | Drop a middle event, then a terminal event, and separately fail the off-node immutable write. The verifier must reject each segment, admission must remain closed, and the gap/failure must remain in the denominator. A later complete switch uses a new linked segment rather than rewriting history. |
| TST-16 quarantine/recycle | Independently inject NVML failure, scrub failure, unkillable labeled process, unremovable mount, and receipt-write loss. Prove placement lease revocation, no new placement, old-resource deletion, replacement creation within the 30-minute control budget, changed resource and boot IDs, then full requalification before GPU_FREE. |
| TST-17 command auth/replay | Send unsigned, altered-policy, wrong-generation, wrong-lease, wrong-node, expired, captured replay, and lower-sequence commands. None may call the physical runner. Then create agent/controller divergence and require detection within one controller lease plus a receipted drain to consistency. |

The Kubernetes run additionally demonstrates that an otherwise valid absence
result from a second fresh test cluster cannot satisfy the first cluster's
authority. The node-local run additionally demonstrates that locally querying
the controller host cannot satisfy a target-node proof.

## Evidence and cleanup

Preserve exact commands and exit codes; immutable request/lease/demand files;
project, region, resource names and IDs; cluster/context/API/CA/namespace/node/
boot/Pod/container identities; GPU type/UUID/total bytes; scheduling mode;
image/model/artifact/input/validator/source hashes; both raw semantic calls;
all shared and chained ledger events; immutable off-node URI/version/digest and
receipt; action/absence/scrub/NVML/recycle/requalification receipts; failures;
drain and release times; bytes moved/scrubbed; GPU active/idle seconds; billed
seconds and cost; and every cleanup receipt.

Cleanup is dry-run first and exact-ID only. Delete the Kubernetes attempt before
the support graph, and delete VM resources in broker reverse dependency order.
Require provider `NotFound`/absence for every created ID, verify broker-owned
local authorities are absent, then run the read-only orphan scan. Foreign or
unregistered resources are reported and preserved. No resource is intentionally
retained.

## Current gate

Neither lane has run. Live work may begin only after independent review accepts
this direct-child candidate and both task-owned pilots supply exact images,
artifacts, validators, and adapter integration. Until then, creating an H100,
cluster, node group, or support resource would produce no admissible evidence.
