# Healthcare NIM Server

This Terraform root provisions a dedicated Nebius Managed Kubernetes cluster in
project `project-e00z6b02t8ddk96c49` and deploys the healthcare/life-science
NIM workloads from `modules/nims` into that new cluster.

It does not reuse Forge clusters or any pre-existing kube context.

Default target:

- Project: `project-e00z6b02t8ddk96c49`
- Tenant: `tenant-e00f3wdfzwfjgbcyfv`
- Region: `eu-north1`
- Subnet: `vpcsubnet-e00p701fa30cj5f7wq`
- Cluster name: `nims-healthcare`
- Namespace: `nims-healthcare`
- CPU nodes: 0 x `cpu-d3` `16vcpu-64gb`
- GPU nodes: 2 x `gpu-h200-sxm` `8gpu-128vcpu-1600gb`
- Shared model cache: 5 TiB mounted at `/mnt/data/nim`

The root enables OpenFold3, Boltz2, MSA Search, OpenFold2, GenMol, MolMIM,
DiffDock, ProteinMPNN, RFdiffusion, Evo2-40B, and Qwen3 Next 80B. BioNeMo
notebooks and Cosmos/Nemotron physical-AI models are intentionally excluded
from this healthcare server preset.

The default two 8-GPU nodes provide 16 GPUs. The enabled NIM set requests 13
GPUs by default, leaving headroom for scheduling and cluster add-ons.
The default omits CPU-only workers because the tenant non-GPU vCPU quota is
currently exhausted; Kubernetes system workloads run on the GPU workers.

## Deploy

Set sensitive values outside source control:

```bash
export TF_VAR_iam_token="$(nebius iam get-access-token)"
export TF_VAR_ngc_key="REPLACE_WITH_NGC_API_KEY"
```

The NGC Kubernetes secrets use write-only Terraform attributes so the key is
not retained in state. Increment `ngc_key_revision` when rotating the key.

Preview from the repository root:

```bash
terraform -chdir=applications/nims-healthcare-server init
terraform -chdir=applications/nims-healthcare-server validate
terraform -chdir=applications/nims-healthcare-server plan
```

Apply only after reviewing the plan and the GPU/storage cost exposure:

```bash
terraform -chdir=applications/nims-healthcare-server apply
```

After apply, inspect the new cluster and NIM service:

```bash
terraform -chdir=applications/nims-healthcare-server output cluster_id
terraform -chdir=applications/nims-healthcare-server output nims_lb_ip
```

## Sizing Notes

`enable_two_gpu_nims` controls Evo2-40B and Qwen3 Next 80B. Keep it enabled
with the default two 8-GPU H200 nodes. Set it to `false` only when using smaller
GPU capacity.

Use `nim_resource_overrides` to tune individual NIM CPU, memory, GPU, and
shared-memory requests without editing `modules/nims`.
