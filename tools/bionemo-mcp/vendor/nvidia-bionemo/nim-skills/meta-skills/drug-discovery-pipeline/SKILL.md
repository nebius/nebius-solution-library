---
name: drug-discovery-pipeline
description: >
  Run a complete computational drug discovery pipeline using NVIDIA BioNeMo NIMs:
  generate drug-like molecules with GenMol, dock them to a protein target with DiffDock,
  then predict binding affinity with Boltz2. Use this skill whenever the user wants to
  generate and screen small molecule drug candidates, perform hit discovery, optimize
  leads against a protein target, or do virtual screening combining molecule generation,
  docking, and affinity prediction. Triggers on: drug discovery pipeline, hit discovery,
  lead optimization, virtual screening, molecule generation, molecular docking, binding
  affinity, GenMol, DiffDock, Boltz2, SMILES, SAFE notation, NIM microservice. This is
  a multi-step pipeline composing three BioNeMo NIMs.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# Drug Discovery Pipeline

Screen drug candidates end-to-end using three BioNeMo NIMs in sequence:

```
Step 1: GenMol    →  Step 2: DiffDock  →  Step 3: Boltz2
(Generate mols)      (Dock to target)      (Predict affinity)
```

---

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `drug_discovery_pipeline` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `drug_discovery_pipeline`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Supply the target sequence and PDB plus generation, docking, and affinity limits.

If the tool is absent, call `fleet_health` and report the disabled or unready
catalog model. Do not fall back to NVIDIA-hosted inference or a workstation
container. The customer-owned Nebius fleet is the only execution target.

## Scientific references

The NVIDIA-authored reference and evaluation files below are preserved byte for
byte. Use the references for model selection, scientific limitations, parameter
interpretation, and output validation; use MCP for all execution.

- This pipeline composes the individually vendored NIM references.

## Upstream evaluation intent

The unmodified upstream eval prompts may mention NVIDIA-hosted endpoints or
local containers. Preserve their scientific request and validation criteria,
but execute the request with `drug_discovery_pipeline` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
