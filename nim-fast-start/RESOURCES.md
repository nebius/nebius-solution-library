# nim-fast-start Resource Inventory

All resources created for ARCHVTEAMS-2407 Phase 1 (NIM Conventional-Start Baselines).
Do NOT tear down — Phase 2 will reuse these environments.

## MK8s Clusters

### archvteams-2407-baselines (primary)

| Field           | Value                                  |
|-----------------|----------------------------------------|
| Name            | archvteams-2407-baselines              |
| ID              | mk8scluster-e00en4dkk80w2d09c0        |
| Project         | project-e00z6b02t8ddk96c49            |
| Region          | eu-north1                             |
| K8s version     | 1.33                                  |
| Subnet          | vpcsubnet-e00p701fa30cj5f7wq          |
| Kubeconfig      | `~/.kube/archvteams-2407-baselines.yaml` |
| Labels          | workload=archvteams-2407, task=nim-fast-start |
| Created         | 2026-08-14T06:52:19Z                  |

### archvteams-2407-evo2 (auxiliary — B300, uk-south1)

| Field           | Value                                  |
|-----------------|----------------------------------------|
| Name            | archvteams-2407-evo2                   |
| ID              | mk8scluster-e03x6jg7qx89fpsjyg        |
| Project         | project-e03ptk5npr00tddhzjp263        |
| Region          | uk-south1                             |
| K8s version     | 1.33                                  |
| Kubeconfig      | `~/.kube/archvteams-2407-evo2.yaml`   |
| Note            | B300 cluster; Evo2-40B NIM incompatible (ptxas sm_103 not in container) |

## Node Groups

### archvteams-2407-baselines cluster

| Name       | ID                               | Platform      | Preset              | GPU      | Purpose         | State   |
|------------|----------------------------------|---------------|---------------------|----------|-----------------|---------|
| h100-1gpu  | mk8snodegroup-e00zz532fgxr7gbfwm | gpu-h100-sxm | 1gpu-16vcpu-200gb   | 1× H100 80GB | OpenFold2 cold/warm | RUNNING |
| h200-1gpu  | mk8snodegroup-e00v5fx6r6p6a6hyjp | gpu-h200-sxm | 1gpu-16vcpu-200gb   | 1× H200 141GB | Evo2-40B cold/warm | RUNNING |
| h200-8gpu  | mk8snodegroup-e00thw7k44pfaq5sqr | gpu-h200-sxm | 8gpu-128vcpu-1600gb | 8× H200 | Attempted — NotEnoughResources | PROVISIONING (failed) |

### archvteams-2407-evo2 cluster

| Name       | ID                               | Platform      | Preset              | GPU      | State   |
|------------|----------------------------------|---------------|---------------------|----------|---------|
| b300-1gpu  | mk8snodegroup-e03rc75cpertbvns0c | gpu-b300-sxm | 1gpu-24vcpu-346gb   | 1× B300 346GB | RUNNING |

## GPU Baseline Coverage

| NIM        | GPU   | Node Group | Runs  | Notes |
|------------|-------|------------|-------|-------|
| OpenFold2  | H100  | h100-1gpu  | 5 cold + 5 warm | Complete |
| Evo2-40B   | H200  | h200-1gpu  | 5 cold + 4 warm | Warm run 5 pending (GPU conflict with Phase 2) |
| Evo2-40B   | B300  | b300-1gpu  | 0     | NIM incompatible: ptxas does not support sm_103 (B300 Blackwell) |

## Kubernetes Namespace

Namespace `nim-fast-start` exists in both clusters.

## Secrets (per cluster)

| Name         | Type                            | Contents               |
|--------------|---------------------------------|------------------------|
| nvcrio-cred  | kubernetes.io/dockerconfigjson  | NGC registry pull auth |
| ngc-api-key  | Opaque                          | NGC_API_KEY env var    |

NGC key source: Nebius Lockbox `mbsec-e00n1kv926bm41jrff` (profile: sandbox)

## Storage (PVCs) — baselines cluster

| Name                | Size    | NIM       | Mount Path        | Purpose                          |
|---------------------|---------|-----------|-------------------|----------------------------------|
| openfold2-nim-cache | 50 Gi   | openfold2 | /home/user/.cache/nim | Warm cache (weights)         |
| evo2-40b-nim-cache  | 150 Gi  | evo2-40b  | /root/.cache/ngc  | Warm cache (hub/model weights)   |

Storage class: `compute-csi-default-sc`

## Phase Notes

- Phase 1 environments left running for Phase 2 (checkpoint/restore feasibility spike).
- Phase 2 has deployed `nim-criu-agent` DaemonSet and restore test pods in the baselines cluster.
- Phase 4 (codex) is responsible for final cleanup of all resources.
- All resources tagged `workload=archvteams-2407`.
- B300 incompatibility: `nvcr.io/nim/arc/evo2-40b:latest` uses ptxas that does not recognize sm_103 (Blackwell B300). NIM loads model but crashes during Triton JIT kernel compilation. Requires updated NIM image with CUDA 12.8+ for B300 support.
