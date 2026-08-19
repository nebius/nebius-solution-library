# Live evidence status

As of 2026-08-19T14:45:58Z, **no cloud, registry, cluster, Kubernetes, GPU,
model, endpoint, bucket, network, disk, service-account, or workload mutation
has been made by this task**. No performance sample or deployment is claimed.

This replacement was produced and tested offline in the isolated task
worktree. It performed no cloud/cluster authentication or read-only live
inventory, and it did not inspect credential environment variables.

The first campaign is frozen in `campaign/arm-a-first-campaign.json` as
`PLANNED`, with 60 Boltz2/OpenFold2 local A-to-B attempts (30 per NIM), two semantic calls,
preemptible H100 intent, an eighteen-hour expected duration, a twenty-four-hour TTL,
and a USD 60 hard cap. It has no resource request, lease, resource prefix, or
IDs because the versioned fresh-cluster/preemptible-node-group broker backend
is still being sealed. An earlier offline VM-only lease draft was removed and
was never provisioned; that path is forbidden for this campaign.

Live admission is blocked on:

1. reviewed broker v2 support matching
   `campaign/broker-cluster-interface-required.json`;
2. a reviewed request-SLO scenario representing successful new-node demand
   without a pre-T0 occupant (Arm B only);
3. task-owned NGC/NIM registry credentials plus exact hashed repository scope;
4. exact task-owned image/artifact/checkpoint bytes and digest-pinned OpenFold2 artifact;
5. a reviewed, broker-bound runtime-source manifest for exact target templates,
   semantic validators, allowed containers/init containers, support-image build
   receipts, cache/strategy-state sentinel, and GPU-zero sentinel;
6. a versioned broker pair-handoff/rearm backend for any baseline-versus-
   precreated-Service promotion; and
7. successful capacity, isolation, cost, TTL, and cleanup-plan preflight.

When those gates pass, record project, region, cluster/context/API server,
cluster/node-group/node IDs, H100 product, preemptible flag, image/artifact
digests and bytes, request payload hashes, raw ledgers, aggregates, cost,
cleanup operations, NotFound receipts, and final GPU-zero evidence here.
No promotion is possible from an ACTIVE lease, self-asserted cleanup JSON, or a
pair lacking the handoff receipt. Immutable workload staging must be followed
by provider evidence files, credential revocation, actual-cost reconciliation,
and a cleanup audit extension before a separate final seal is created.

Comparator scope is unchanged: this file will contain Kubernetes evidence
only. Cerebrium is the sole intended external comparator, but remains pending
and private-placement blocked with no sealed cohort receipt; direct/node-local
VM is a separate internal lane. Modal receives no authentication, deployment,
test, benchmark, or ranking from this task.
