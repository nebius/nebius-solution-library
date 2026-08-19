# Live execution plan and gate

Date: 2026-08-19 UTC  
Task owner: `catalog-switch-storage-cache-matrix`  
Required prefix: `mlsp-csw-storage-cache-<request-hash>`  
Cleanup owner: `catalog-switch-storage-cache-matrix`

## Read-only preflight evidence

No resource was created, attached, modified, restarted, or deleted during this
preflight.

- Nebius CLI: `0.12.206`; explicitly audited profile: `sandbox`.
- Authenticated read-only identity: service account
  `serviceaccount-i00pafr0ydvbaxj952`, rooted in allowed project
  `project-i00xz31gpr00xp9jhp982v`.
- `project-e00z6b02t8ddk96c49` / `eu-north1` advertises
  `gpu-h100-sxm/1gpu-16vcpu-200gb` and
  `gpu-h200-sxm/1gpu-16vcpu-200gb`.
- `project-i00xz31gpr00xp9jhp982v` / `me-west1` advertises
  `gpu-b200-sxm-a/1gpu-20vcpu-224gb`.
- Capacity advice observed at the preflight showed available preemptible H100
  and B200 capacity. Capacity is not the current blocker.
- The installed instance API exposes
  `local_disks.passthrough_group.requested`, but the platform responses do not
  assert project entitlement or a local-disk layout.
- The reviewed resource broker therefore has `local_nvme.request=false` and
  `verified_supported=false` for every allowed H100, H200, and B200 profile. It
  fails closed if a profile requests local NVMe without prior proof.

The only locally documented verified configuration is
`uk-south1/gpu-b300-sxm/8gpu-192vcpu-2768gb`. `uk-south1` is not one of this
epic's three authorized project regions, so neither that configuration nor a
project switch is permitted.

## Frozen live matrix after entitlement is resolved

Run one variable per cohort on the same compatible GPU/platform and exact
artifact/input identities. Prefer a preemptible single-GPU instance; use normal
only if preemption invalidates the cohort. Before creation, produce a canonical
matrix plan with the current Git commit, artifact publication receipt, exact
request-SLO SHA-256, exact Boltz contract SHA-256, price snapshot, and these
minimum live cells:

| Tier | Cohorts | Minimum |
| --- | --- | ---: |
| local NVMe | hot, warm, cold, eviction/repopulation, corruption | 20 attempts each |
| attached block/PVC | hot, warm, cold, Boltz external-`/tmp` hit, Boltz clone/miss | 20 attempts each |
| remote immutable artifact | cold, repopulation, corruption | 20 attempts each |
| concurrent remote-to-local | two distinct models, overlapping fetch | 20 paired attempts |

Use a fresh immutable publication for each model and fresh mutable generation
names for every miss/repopulation attempt. Cache investment may occur before T0
only when it is explicitly non-request-specific and costed as node-cache
investment. Request-triggered image pull/unpack, fetch, attach/mount,
clone/copy/hash, and first read remain after T0. Each request runs the real
semantic model input through the canonical external recorder.

Planned task-owned footprint, all recorded by exact ID in the broker lease:

- one fresh private VPC, subnet, and task-specific security group;
- one fresh preemptible GPU VM with verified host-local NVMe;
- fresh boot and attached Network SSD disks;
- one fresh private artifact publication source with task-scoped credentials or
  a fresh private source VM (never an existing bucket or service account);
- a fresh registry only if an image cannot be pulled immutably from its public
  source; and
- no public/shared cluster, filesystem, registry, endpoint, secret, or service
  account dependency.

Expected active experiment duration: 4 hours. TTL/cleanup deadline: 8 hours.
The final budget must be recomputed from the broker's effective price snapshot
before creation. Cleanup deletes exact lease IDs in reverse dependency order,
verifies `NotFound`, scans all three authorized projects for unknown task
prefixes, and proves every dirty cache/clone generation absent.

## Stop condition

Live execution is blocked before billable creation because the required
allowed-project local-NVMe entitlement/platform is missing or unverified. To
continue without violating the epic, an operator must provide an authorized
project/platform combination in one of the three fixed projects and regions,
enable host-local NVMe for it, and confirm its device layout. Alternatively,
the task owner must explicitly revise the definition of done to remove the
local-NVMe cohort. Until then, attached/remote-only runs would be incomplete
and would not justify a finished matrix or a measured Boltz conclusion.
