# nim-fast-start Resource Inventory

All resources created for ARCHVTEAMS-2407 Phase 1 (NIM Conventional-Start Baselines).
Do NOT tear down — Phase 2 will reuse these environments.

## MK8s Cluster

| Field           | Value                                  |
|-----------------|----------------------------------------|
| Name            | archvteams-2407-baselines              |
| ID              | mk8scluster-e00en4dkk80w2d09c0        |
| Project         | project-e00z6b02t8ddk96c49            |
| Region          | eu-north1                             |
| K8s version     | 1.33                                  |
| Control plane   | HA (3 etcd nodes)                     |
| Subnet          | default-subnet-uou7qfuh (vpcsubnet-e00p701fa30cj5f7wq) |
| Public endpoint | https://pu.mk8scluster-e00en4dkk80w2d09c0.mk8s.eu-north1.nebius.cloud:443 |
| Labels          | workload=archvteams-2407, task=nim-fast-start, phase=baselines |
| Created         | 2026-08-14T06:52:19Z                  |

## Node Groups

| Name       | ID                             | Platform      | Preset                 | GPU Count | Purpose         | State        |
|------------|--------------------------------|---------------|------------------------|-----------|-----------------|--------------|
| h100-1gpu  | mk8snodegroup-e00zz532fgxr7gbfwm | gpu-h100-sxm | 1gpu-16vcpu-200gb     | 1         | OpenFold2       | PROVISIONING |
| h100-8gpu  | mk8snodegroup-e00khhdx84ebtnjgjn | gpu-h100-sxm | 8gpu-128vcpu-1600gb   | 8 (uses 2) | Evo2-40B      | PROVISIONING |

Node details:
- **h100-1gpu**: 1× H100 SXM (80 GB), 16 vCPU, 200 GiB RAM — for OpenFold2 single-GPU baseline
- **h100-8gpu**: 1× 8-GPU H100 SXM node, 128 vCPU, 1600 GiB RAM — Evo2-40B pod requests 2/8 GPUs

## Kubernetes Namespace

| Field     | Value          |
|-----------|----------------|
| Namespace | nim-fast-start |

## Secrets

| Name         | Type                            | Contents               |
|--------------|---------------------------------|------------------------|
| nvcrio-cred  | kubernetes.io/dockerconfigjson  | NGC registry pull auth |
| ngc-api-key  | Opaque                          | NGC_API_KEY env var    |

NGC key source: Nebius Lockbox `mbsec-e00n1kv926bm41jrff` (profile: sandbox)

## Storage (PVCs)

| Name                | Size   | NIM       | Purpose      |
|---------------------|--------|-----------|--------------|
| openfold2-nim-cache | 50 Gi  | openfold2 | Warm cache   |
| evo2-40b-nim-cache  | 150 Gi | evo2-40b  | Warm cache   |

Storage class: `nebius-network-ssd`

## Kubeconfig

Saved to: `~/.kube/archvteams-2407-baselines.yaml`
Context: `nebius-mk8s-archvteams-2407-baselines-e00en4dkk80w2d09c0`

## Phase Notes

- Phase 1 environments are left running for Phase 2 (checkpoint/restore feasibility spike).
- Phase 4 (codex) is responsible for final cleanup of all resources.
- All resources tagged `workload=archvteams-2407` and `task=nim-fast-start`.

## Phase 2 isolated feasibility resources

These resources were created separately from the Phase 1/Phase 3 environments.
They remain running for Phase 4 integration and cleanup.

| Resource | ID / name | Project / region | Notes |
|---|---|---|---|
| Kubernetes cluster | `mk8scluster-e00h7jeqm0hc89kx4q` | `project-e00z6b02t8ddk96c49` / `eu-north1` | Kubernetes 1.33.7; task preview |
| GPU node group | `mk8snodegroup-e00zc0r4a131base08` | `project-e00z6b02t8ddk96c49` / `eu-north1` | One preemptible H100, no local disk |
| GPU node | `computeinstance-e00f9mb4qxbb0jgp56` | `project-e00z6b02t8ddk96c49` / `eu-north1` | Driver 580.159.04 |
| Private pool | `vpcpool-e00h45yd2g89bt13p0` | `project-e00z6b02t8ddk96c49` / `eu-north1` | Preview network allocation |
| Network | `vpcnetwork-e00wyc57abkahgp7nb` | `project-e00z6b02t8ddk96c49` / `eu-north1` | Preview network |
| Subnet | `vpcsubnet-e00g7znr4y507hb991` | `project-e00z6b02t8ddk96c49` / `eu-north1` | Preview subnet |
| Container registry | `registry-e03dneryzh058ymkwb` | `project-e03ptk5npr00tddhzjp263` / `uk-south1` | `cr.uk-south1.nebius.cloud/e03dneryzh058ymkwb` |

Task-owned Helm releases:

| Release | Namespace | Image digest |
|---|---|---|
| `archvteams-2407-dynamo` | `nim-fast-start-system` | operator `sha256:b7f5a04e850bc9b22073cad871ad2c933d67c4c5f99d9c5906dde87dd86dc469` |
| `archvteams-2407-snapshot` | `nim-fast-start` | agent `sha256:c9df66930fbe31c2910752c6601ca4798f422c048f4df6d200df1624357729d9` |

The snapshot release owns Bound PVC `archvteams-2407-snapshot` (64 GiB,
`compute-csi-default-sc`, RWO). The isolated kubeconfig is
`~/.kube/archvteams-2407-p2.yaml`. Do not copy registry or NGC credential data
into this inventory.
