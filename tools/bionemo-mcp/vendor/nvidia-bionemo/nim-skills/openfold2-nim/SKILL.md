---
name: openfold2-nim
description: >
  Use this skill for OpenFold2, NVIDIA's BioNeMo NIM microservice for monomer protein structure prediction. Invoke whenever the user mentions OpenFold2, AlphaFold2-like monomer folding, protein sequence-to-structure prediction, A3M MSAs, mmCIF templates, Nebius-hosted MCP calls, or Nebius-hosted MCP deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# OpenFold2 NIM

Predict a single protein-chain structure from an amino-acid sequence, with
optional A3M multiple sequence alignments and mmCIF templates. Use this
`SKILL.md` for basic hosted/local NIM use; load supplemental files only when
the task needs deeper context:

- `references/api.md`: exact endpoints, schemas, Docker flags, response fields.
- `references/science.md`: model scope, strengths, limitations, and handoffs.
- `references/parameters.md`: MSA, template, model-selection, and relax effects.
- `references/validation.md`: artifact and scientific sanity checks.
- `references/examples.md`: compact hosted/local payload patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `openfold2_predict` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `openfold2_predict`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Supply a protein sequence and optional A3M alignments or mmCIF templates.

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
but execute the request with `openfold2_predict` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
