---
name: molmim-nim
description: >
  Use this skill for MolMIM, NVIDIA's BioNeMo NIM microservice for small-molecule latent-space generation and optimization. Invoke for MolMIM, molecular embeddings, hidden states, latent decoding, sampling around a seed SMILES, CMA-ES guided molecule generation, QED or plogP optimization, Nebius-hosted MCP calls, or Nebius-hosted MCP deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# MolMIM NIM

Generate, sample, embed, and decode small molecules with MolMIM. Use this
`SKILL.md` for first-pass hosted/local usage; load supplemental files only when
needed:

- `references/api.md`: endpoints, schema, Docker flags, response fields.
- `references/science.md`: use cases, strengths, limits, and handoffs.
- `references/parameters.md`: generation, sampling, and optimization effects.
- `references/validation.md`: SMILES/property/artifact checks.
- `references/examples.md`: compact hosted/local request patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `molmim_run` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `molmim_run`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Choose generate, embedding, hidden, decode, or sampling in the discriminated request.

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
but execute the request with `molmim_run` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
