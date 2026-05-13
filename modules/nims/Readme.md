# NIMs Kubernetes Terraform Module

This Terraform module provisions a Kubernetes namespace, secrets, and LoadBalancer services for NVIDIA NIMs used in drug discovery and bio/chem workflows. It is designed for GPU‑enabled clusters and is used by the demo app under `applications/nims-drug-discovery-demo/`.

---

## What This Module Deploys

- **Dedicated namespace** for NIM workloads.
- **NGC secrets**:
  - Docker registry secret for pulling images from `nvcr.io`.
  - NGC API key secret for NVIDIA services.
- **LoadBalancer services** that expose multiple NIMs on fixed ports.
- **Model cache** on a shared filesystem (for faster cold starts).
- **BioNeMo stack** on a separate LoadBalancer.

---

## Exposed NIMs and Ports (Default)

The module exposes NIMs using a shared LoadBalancer per group. The demo UI expects these port mappings by default (editable in the UI):

### Protein / Structure / Sequence (Main LB)
- **OpenFold3** → `8000`
- **Boltz2** → `8001`
- **Evo2‑40B** → `8002`
- **MSA Search** → `8003`
- **OpenFold2** → `8004`
- **GenMol** → `8005` *(if enabled in this module)*
- **MolMIM** → `8006` *(if enabled in this module)*
- **DiffDock** → `8007` *(if enabled in this module)*
- **Qwen3** → `8008` *(if enabled in this module)*
- **ProteinMPNN** → `8009` *(if enabled in this module)*
- **RFdiffusion** → `8010` *(if enabled in this module)*

### Cosmos / World Foundation Models (Separate LB)
- **Cosmos-Reason1-7B** → `8000`
- **Cosmos-Reason2-8B** → `8001`
- **Cosmos-Reason2-2B** → `8002`
- **Cosmos-Embed1** → `8003`
- **Nemotron Nano 12B v2 VL (NAno2 VL)** → `8004` *(if enabled in this module)*

### BioNeMo (Separate LB)
- Deployed via `bionemo.tf` (ports and services defined there).

> If your cluster uses different ports, update the demo UI’s LoadBalancer configuration.

---

## File‑by‑File Documentation

### Core Module
- `main.tf`  
  Creates the namespace, secrets, and base LoadBalancer service(s).

- `provider.tf`  
  Kubernetes provider configuration.

- `variables.tf`  
  All configurable inputs (namespace, NGC keys, images, resource limits, etc.).

- `output.tf`  
  Outputs LoadBalancer IPs and service details.

### NIM Deployments
- `openfold2.tf`  
  Deploys OpenFold2 (monomer structure prediction).

- `openfold3.tf`  
  Deploys OpenFold3 (complex structure prediction).

- `boltz2.tf`  
  Deploys Boltz2 (structure prediction with ligands/constraints).

- `evo2_40.tf`  
  Deploys Evo2‑40B (sequence generation/reasoning).

- `msa-search.tf`  
  Deploys an MSA search service used to build alignments.

- `genmol.tf`  
  Deploys GenMol (molecule generation).

- `proteinmpnn.tf`  
  Deploys ProteinMPNN (sequence design from a given backbone).

- `rfdiffusion.tf`  
  Deploys RFdiffusion (generative backbone design).

- `qwen3-next-80b-a3b-instruct.tf`
  Deploys Qwen3 (LLM copilot for workflow adoption).

- `cosmos-reason1-7b.tf`
  Deploys Cosmos-Reason1-7B (world foundation model for physical AI reasoning).

- `cosmos-reason2-8b.tf`
  Deploys Cosmos-Reason2-8B (world foundation model for physical AI reasoning, 8B parameters).

- `cosmos-reason2-2b.tf`
  Deploys Cosmos-Reason2-2B (world foundation model for physical AI reasoning, 2B parameters).

- `cosmos-embed1.tf`
  Deploys Cosmos-Embed1 (world foundation model for embeddings).

- `cosmos-proxy.tf`
  Nginx TCP proxy and LoadBalancer for Cosmos World Foundation Models (separate external IP).

- `bionemo.tf`
  Deploys BioNeMo NIMs on a separate LoadBalancer.

- `nemotron-nano-12b-v2-vl.tf`
  Deploys Nemotron Nano 12B v2 VL (Nano2 VL), a vision-language model for document intelligence, video understanding, and multimodal reasoning.

---

## How the Demo App Uses This Module

The demo app connects directly to the LoadBalancer IP created by this module and expects:

- **Health checks** on each service port:
  - `GET /v1/health/ready`
  - `GET /v1/health/live`
  - `GET /v1/metrics`
- **Inference endpoints** per NIM (paths defined in the demo UI).

See `applications/nims-drug-discovery-demo/README.md` for the demo workflow.

---

## Notes
- Requires CUDA 13 on GPU nodes. If your cluster uses a custom driver, enable it (e.g., `custom_driver = true` in your infrastructure setup).
- A shared filestore is required for model cache; plan for **5 TB+**.
- Ensure GPU nodes and runtime class are available before applying.
- Update resource limits/requests as needed for your cluster size.
- Secrets are required for pulling NGC images and using NIM services.

---

## Example Usage

Add the module to your root `main.tf` (adjust paths and flags as needed):

```hcl
module "nims" {
  source = "../modules/nims"

  ngc_key   = "REPLACE_WITH_YOUR_NGC_KEY"
  parent_id = var.parent_id

  # Protein structure prediction
  openfold2  = true
  openfold3  = true
  boltz2     = true
  msa_search = true

  # Molecule generation & docking
  genmol      = true
  molmim      = true
  diffdock    = true
  diffdock_replicas = 3

  # Protein design
  proteinmpnn = true
  rfdiffusion = true

  # Sequence models
  evo2_40b = true

  # LLM copilot
  qwen3-next-80b-a3b-instruct = true

  # Cosmos World Foundation Models
  cosmos_reason1_7b = true
  cosmos_reason2_8b = true
  cosmos_reason2_2b = true
  cosmos_embed1     = true

  # Vision-language (Nano2 VL)
  nemotron_nano_12b_v2_vl = true
}
```
