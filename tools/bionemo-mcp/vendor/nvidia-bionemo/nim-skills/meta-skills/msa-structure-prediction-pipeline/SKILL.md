---
name: msa-structure-prediction-pipeline
description: >
  Run a complete protein structure prediction pipeline using NVIDIA BioNeMo NIMs:
  search for MSA alignments with MSA-Search (ColabFold), then predict the structure
  with OpenFold3 using the retrieved alignments. Use this skill whenever the user wants
  to predict a protein structure with maximum accuracy using MSA context, run the
  full AlphaFold3-style pipeline, generate MSA-informed structure predictions, or
  improve structure prediction accuracy by providing evolutionary information.
  Triggers on: MSA structure prediction pipeline, structure prediction pipeline, MSA-informed prediction, OpenFold3,
  ColabFold MSA, AlphaFold3 pipeline, protein structure, homology search, a3m alignment,
  UniRef30, NIM microservice. This pipeline chains MSA-Search and OpenFold3.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# MSA Structure Prediction Pipeline

Predict protein structures with high accuracy by chaining two BioNeMo NIMs:

```
Step 1: MSA-Search  →  Step 2: OpenFold3
(Search homologs)       (Predict structure with MSA)
```

---

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `msa_structure_prediction_pipeline` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `msa_structure_prediction_pipeline`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Supply the sequence, database choices, MSA depth, and structure format.

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
but execute the request with `msa_structure_prediction_pipeline` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
