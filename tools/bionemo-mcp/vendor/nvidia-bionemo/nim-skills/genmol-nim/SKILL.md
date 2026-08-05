---
name: genmol-nim
description: >
  Generate novel drug-like molecules using the GenMol NIM microservice. Use for de novo generation, scaffold decoration, motif extension, lead optimization, SAFE notation, QED or LogP ranking, Nebius-hosted MCP calls, or Nebius-hosted MCP deployment. GenMol takes SAFE notation in the smiles field, not ordinary SMILES.
license: Apache-2.0 AND CC-BY-4.0
compatibility: "Requires nebius-bionemo-mcp >=0.1"
---

# GenMol NIM

Generate drug-like molecules with GenMol. Use this `SKILL.md` for first-pass
hosted/local usage; load supplemental files only when needed:

- `references/api.md`: endpoints, schema, Docker flags, response fields.
- `references/science.md`: use cases, strengths, limits, and handoffs.
- `references/parameters.md`: SAFE patterns and tuning effects.
- `references/validation.md`: chemical and artifact checks.
- `references/examples.md`: compact request patterns.

## Execute on Nebius through MCP

1. Call `list_models` and confirm that `genmol_generate` is registered. Its presence
   proves every required catalog model was enabled and ready when the server
   started.
2. Call `genmol_generate`. Use the JSON schema published by MCP; do not construct an
   endpoint URL, authentication header, shell command, or container command.
3. Inspect `response_summary`, then download the returned artifacts before
   their presigned URLs expire. Verify the advertised SHA-256 checksums.

The `smiles` field carries SAFE notation; temperature and noise remain strings as required by NIM.

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
but execute the request with `genmol_generate` and retrieve files from its artifact
references. Never reproduce the obsolete shell/API execution path.

## Attribution and modifications

Adapted by Nebius from NVIDIA BioNeMo Agent Toolkit. The source content is
licensed `Apache-2.0 OR CC-BY-4.0`; see the vendored `NOTICE`, license files,
`UPSTREAM.json`, and `MODIFICATIONS.md`. Nebius replaced the original execution
sections with this MCP workflow. References and eval files are unmodified.
