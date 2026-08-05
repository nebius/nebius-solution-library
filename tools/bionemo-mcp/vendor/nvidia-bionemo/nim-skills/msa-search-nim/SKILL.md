---
name: msa-search-nim
description: >
  Generate multiple sequence alignments (MSAs) for protein sequences using the ColabFold MSA-Search NIM. Use for homolog search, UniRef30/ColabFold env searches, A3M or FASTA alignments, paired MSA search for complexes, PDB70 structural templates, Nebius-hosted MCP calls, or Nebius-hosted MCP deployment.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# MSA-Search NIM

Generate protein MSAs with GPU-accelerated MMSeqs2. Use this `SKILL.md` for
first-pass hosted/local usage; load supplemental files only when needed:

- `references/api.md`: exact endpoints, schemas, Docker flags, response fields.
- `references/science.md`: MSA purpose, pairing/templates, limits, handoffs.
- `references/parameters.md`: database, pairing, depth, and template tuning.
- `references/validation.md`: alignment, template, and artifact checks.
- `references/examples.md`: compact hosted/local request patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `msa_search` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `msa_search`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

Choose standard, paired, or templates and provide the corresponding typed fields.

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
but execute the request with `msa_search` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
