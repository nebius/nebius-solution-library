# Healthcare NIM Server

This root deploys the healthcare/life-science NIM workloads from `modules/nims`
into Nebius project `project-e00z6b02t8ddk96c49`.

Default target:

- Project: `project-e00z6b02t8ddk96c49`
- Region: `eu-north1`
- Cluster context: `nebius-mk8s-forge-eu-e00tjerrz0axkghmbm`
- Namespace: `nims-healthcare`

The root enables OpenFold3, Boltz2, MSA Search, OpenFold2, GenMol, MolMIM,
DiffDock, ProteinMPNN, RFdiffusion, Evo2-40B, and Qwen3 Next 80B. BioNeMo
notebooks and Cosmos/Nemotron physical-AI models are intentionally excluded
from this healthcare server preset.

## Deploy

Set the NGC key outside source control:

```bash
export TF_VAR_ngc_key="..."
```

Preview from the repository root:

```bash
terraform -chdir=applications/nims-healthcare-server init
terraform -chdir=applications/nims-healthcare-server plan
```

Apply only after checking the target context and capacity:

```bash
kubectl --context nebius-mk8s-forge-eu-e00tjerrz0axkghmbm get nodes
terraform -chdir=applications/nims-healthcare-server apply
```

## Current Target Capacity Note

Read-only discovery on 2026-06-15 found the target project has running
`forge-eu` and `forge-control` clusters. The `forge-eu` cluster has many
ready GPU nodes, but each GPU node reports one allocatable GPU. Evo2-40B and
Qwen3 Next 80B request two GPUs by default, so they need either two-GPU nodes
or `enable_two_gpu_nims = false`.

The module defaults now request `15000m` CPU for one-GPU NIMs so they fit on
16-vCPU nodes that expose about `15900m` allocatable CPU.
