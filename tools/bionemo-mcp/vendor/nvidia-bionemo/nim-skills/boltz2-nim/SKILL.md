---
name: boltz2-nim
description: >
  Use Boltz2 NIM for biomolecular structure prediction and binding affinity. Invoke for Boltz2, protein structures, protein-ligand/DNA/RNA complexes, SMILES or CCD ligands, pIC50/IC50 affinity scoring, mmCIF output, Nebius-hosted MCP calls, or Nebius-hosted MCP deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# Boltz2 NIM

Predict biomolecular structures and optional ligand affinity. Use this
`SKILL.md` for first-pass hosted/local usage; load supplemental files only when
needed:

- `references/api.md`: exact endpoints, schemas, Docker flags, response fields.
- `references/science.md`: purpose, strengths, limitations, and handoffs.
- `references/parameters.md`: prediction, sampling, MSA, template, affinity tuning.
- `references/validation.md`: mmCIF, confidence, affinity, and chemistry checks.
- `references/examples.md`: compact hosted/local payload patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `boltz2_predict` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `boltz2_predict`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Supply polymers, optional ligands, constraints, and sampling controls in the typed request object.

If the tool is absent, call `fleet_health` and report the disabled or unready
catalog model. Do not fall back to NVIDIA-hosted inference or a workstation
container. The customer-owned Nebius fleet is the only execution target.

## Scientific references

The NVIDIA-authored reference and evaluation files below are preserved byte for
byte. Use the references for model selection, scientific limitations, parameter
interpretation, and output validation; use MCP for all execution.

- `references/api.md`
- `references/examples.md`
- `references/parameters.md`
- `references/science.md`
- `references/validation.md`

## Upstream evaluation intent

The unmodified upstream eval prompts may mention NVIDIA-hosted endpoints or
local containers. Preserve their scientific request and validation criteria,
but execute the request with `boltz2_predict` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
