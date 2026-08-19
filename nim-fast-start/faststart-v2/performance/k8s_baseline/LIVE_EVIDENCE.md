# Live evidence status

As of 2026-08-19T14:45:58Z, **no cloud, registry, cluster, Kubernetes, GPU,
model, endpoint, bucket, network, disk, service-account, or workload mutation
has been made by this task**. No performance sample or deployment is claimed.

Read-only preflight observed:

- isolated task branch/worktree `agent/catalog-switch-k8s-baseline`;
- Nebius CLI `0.12.206`, active audited profile `sandbox`, API endpoint
  `api.nebius.cloud`;
- authenticated service-account identity rooted in allowed project
  `project-i00xz31gpr00xp9jhp982v` (the identity ID is retained only in the
  local Task Deck evidence, not in this publishable subtree);
- `kubectl` `1.36.3` and Terraform `1.15.8`; and
- no `NGC_API_KEY` or `NVIDIA_API_KEY` present (presence only was checked; no
  secret value was read or printed).

The first campaign is frozen in `campaign/arm-a-first-campaign.json` as
`PLANNED`, with 30 Boltz2/OpenFold2 local A-to-B attempts, two semantic calls,
preemptible H100 intent, an eight-hour expected duration, a twelve-hour TTL,
and a USD 27 hard cap. It has no resource request, lease, resource prefix, or
IDs because the versioned fresh-cluster/preemptible-node-group broker backend
is still being sealed. An earlier offline VM-only lease draft was removed and
was never provisioned; that path is forbidden for this campaign.

Live admission is blocked on:

1. reviewed broker v2 support matching
   `campaign/broker-cluster-interface-required.json`;
2. task-owned NGC/NIM registry credentials;
3. exact task-owned image/artifact bytes and digest-pinned OpenFold2 artifact;
4. reviewed target templates, cache-state sentinel, GPU-zero sentinel, and
   semantic validators; and
5. successful capacity, isolation, cost, TTL, and cleanup-plan preflight.

When those gates pass, record project, region, cluster/context/API server,
cluster/node-group/node IDs, H100 product, preemptible flag, image/artifact
digests and bytes, request payload hashes, raw ledgers, aggregates, cost,
cleanup operations, NotFound receipts, and final GPU-zero evidence here.

Comparator scope is unchanged: this file will contain Kubernetes evidence
only. Cerebrium is measured in its separately owned lane; direct/node-local VM
is a separate internal lane. Modal receives no authentication, deployment,
test, benchmark, or ranking from this task.
