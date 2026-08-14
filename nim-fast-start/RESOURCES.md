# Validation resource inventory

Live state was checked with the `sandbox` profile on 14 August 2026 at 13:23 UTC.
These resources are retained temporarily because the Phase 2 Dynamo Snapshot build
and validation are still in progress. They must be deleted after that work finishes.

## Managed Kubernetes

| Cluster | ID | Project | Region | State | Purpose |
|---|---|---|---|---|---|
| `archvteams-2407-baselines` | `mk8scluster-e00en4dkk80w2d09c0` | `project-e00z6b02t8ddk96c49` | `eu-north1` | Running | H100/H200 baselines and cache-preseed validation |
| `archvteams-2407-p2-snapshot` | `mk8scluster-e00h7jeqm0hc89kx4q` | `project-e00z6b02t8ddk96c49` | `eu-north1` | Running | Isolated Dynamo Snapshot build/installation |
| `archvteams-2407-evo2` | `mk8scluster-e03x6jg7qx89fpsjyg` | `project-e03ptk5npr00tddhzjp263` | `uk-south1` | Running | B300 compatibility test |

All three control planes run Kubernetes 1.33.

## GPU node groups

| Cluster | Node group | ID | Platform / preset | Capacity | State |
|---|---|---|---|---|---|
| baselines | `h100-1gpu` | `mk8snodegroup-e00zz532fgxr7gbfwm` | `gpu-h100-sxm` / `1gpu-16vcpu-200gb` | 1× H100 | Running |
| baselines | `h200-1gpu` | `mk8snodegroup-e00v5fx6r6p6a6hyjp` | `gpu-h200-sxm` / `1gpu-16vcpu-200gb` | 1× H200 | Running |
| baselines | `h200-8gpu` | `mk8snodegroup-e00thw7k44pfaq5sqr` | `gpu-h200-sxm` / `8gpu-128vcpu-1600gb` | 8× H200 requested | Provisioning after `NotEnoughResources` |
| Phase 2 | `p2-h100-1gpu-preemptible` | `mk8snodegroup-e00zc0r4a131base08` | `gpu-h100-sxm` / `1gpu-16vcpu-200gb` | 1× H100, preemptible | Running |
| Evo2 | `b300-1gpu` | `mk8snodegroup-e03rc75cpertbvns0c` | `gpu-b300-sxm` / `1gpu-24vcpu-346gb` | 1× B300 | Running |

The baseline H100 and H200 nodes run Ubuntu 24.04.4, kernel
6.11.0-1016-nvidia, driver 580.159.04, and containerd 1.7.34.

## Storage and workloads

The baseline cluster has Bound RWO PVCs `openfold2-nim-cache` (50 GiB) and
`evo2-40b-nim-cache` (150 GiB) using `compute-csi-default-sc`. OpenFold2 and
Evo2-40B are Ready on their respective one-GPU nodes. A privileged Ubuntu CRIU helper
from the exploratory Phase 3 work is still present; it is not part of this solution
and should be removed during cleanup.

The Phase 2 preview has Pending cache PVCs and a Pending Dynamo operator. It has no
snapshot CRD or running snapshot agent as of the audit.

Registry `registry-e03dneryzh058ymkwb` in the UK South project was created for the
Phase 2 source build. Its contents and retention must be checked before deleting it.

## Cleanup evidence

No Phase 1–3 resource was deleted during Phase 4 because the supervisor explicitly
left Phase 2 running. Phase 4 test resources, if created, are listed below with their
cleanup result.

| Resource | Result |
|---|---|
| Phase 1–3 clusters, node groups, PVCs, workloads, and registry | Retained for active Phase 2; owner: ARCHVTEAMS-2407 |
| P4 namespace and RBAC | Deleted; live API returned NotFound after cleanup |
| P4 node group `mk8snodegroup-e00af5r69k48z38kjb` | Deleted by operation `opmk8snodegroup-e00j3697ta0kc8d8qf`; absent at 13:57:27 UTC |
| P4 node `computeinstance-e00ph14vdkdt8ym5qa` | Deleted with node group; label selection returned zero nodes |

Final cleanup must remove namespace workloads and PVCs, then GPU node groups,
clusters, registry images/registry, shared filesystems, and Object Storage artifacts
in dependency order. Verify each deletion from live APIs rather than relying on the
delete request alone.
