---
name: evo2-nim
description: >
  Generate and analyze DNA sequences using NVIDIA's Evo 2 BioNeMo NIM microservice. Use for Evo2/Evo 2, DNA generation, genomic sequence generation, hosted generation, Nebius-hosted MCP deployment, local forward passes, layer outputs, logits, sampled probabilities, and BioNeMo NIM workflows.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# Evo 2 NIM

Use Evo 2 for DNA generation and, locally, layer-output extraction. Use this
`SKILL.md` for basic hosted/local use; load supplemental files only when needed:

- `references/api.md`: exact schemas, layer names, Docker flags, hardware notes.
- `references/science.md`: genomic use cases, limits, and interpretation.
- `references/parameters.md`: generation/forward parameter effects.
- `references/validation.md`: DNA, probability, timing, and tensor checks.
- `references/examples.md`: compact hosted/local request patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `evo2_run` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `evo2_run`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Choose the generate or forward operation in the typed request.

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
but execute the request with `evo2_run` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
