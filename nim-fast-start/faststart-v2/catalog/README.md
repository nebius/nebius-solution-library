# Catalog-switch model inventory

A source-proven, machine-readable model catalog and runtime compatibility
matrix for the fast-switch architecture program. The router, policy
simulator, and experiment selector consume `catalog.json` (full fidelity)
or `catalog.tsv` (flat). Rows are never invented: every row carries
provenance to an authorized source, and availability is classified rather
than assumed.

## Outputs

- `catalog.json` — schema-validated inventory (`schema/catalog.schema.json`),
  with meta: source provenance, row counts, family taxonomy, deterministic
  pilot selection, and storage feasibility with uncertainty bounds.
- `catalog.tsv` — one flat line per row for spreadsheets and quick joins.
- `GAP_REPORT.md` — what is missing, contradictory, or heuristic.

The committed outputs are an immutable snapshot: `meta.catalog_version` is
the SHA-256 of the row set, and the tests fail if the committed files do
not byte-match a rebuild. To change the catalog, change a source snapshot
and rebuild; superseding snapshots get a new `catalog_version`.

## Sources (four, reconciled by canonical model identity)

1. **`sources/faststart-lanes.json`** — the ten measured BioNeMo NIM lanes
   in this subtree (digest-pinned images, measured T0-to-response timings,
   artifact/cache byte counts, snapshot-restore evidence, strict semantic
   validators). Evidence tier `measured-local`.
2. **`sources/forge-models.json`** — a sanitized snapshot of the Forge
   model manifests (191 models at the pinned commit recorded in its meta),
   regenerated with `extract_forge_source.py --forge-repo <checkout>`.
   Whitelisted fields only: private registry paths, container environment
   blocks, and free-text onboarding blockers never enter the snapshot, and
   extraction fails closed on any forbidden pattern. Evidence tier
   `measured-source` for `status=active` rows (the Forge catalog records
   them as live-serving), `catalog-listed` otherwise.
3. **`sources/nims-terraform.json`** — the 17 entries of
   `modules/nims/catalog.tf` (`local.default_model_catalog`), hand-encoded
   with provenance; a test cross-checks every image and version string
   against the Terraform file. Evidence tier `catalog-listed`.
4. **`sources/documented-candidates.json`** — models named only in
   repository documentation/examples (currently the two SkyPilot Llama-2
   references). Evidence tier `referenced-only`.

## Classification rules (deterministic, encoded in `build_catalog.py`)

- **Availability class**: `hypothetical` if the row exists only as a
  documentation reference; else `gated` if a gate this program cannot
  satisfy from the catalog alone is recorded (HF token/license acceptance,
  upstream artifact gating, non-commercial license, disabled listing, image
  only in a private mirror, or a pending hardware release decision); else
  `verified` if an authorized source records real serving for this exact
  profile; else `discoverable`.
- **Snapshot eligibility**: evidence-based for faststart lanes (`proven`,
  `excluded`, `blocked-pending-capture`); heuristic elsewhere —
  `candidate-family-proven` when the same canonical model has a proven
  lane, `unproven-multi-gpu` for multi-GPU rows, `candidate-unproven`
  otherwise. Heuristic values always carry low/medium confidence.
- **Canonical identity**: Hugging Face repo id when the source records
  one, else the public image repository, else the source model family.
  Rows sharing a canonical key cross-link via `related_ids` instead of
  being lossily merged.
- **Pilots**: the three program-mandated classes are selected by fixed
  arithmetic rules (minimize/maximize known local bytes among verified
  snapshot-proven rows; strongest-evidence-then-largest among multi-GPU or
  ≥50 GB/≥20 B-parameter rows) — never by hand. Gates on a selected pilot
  are surfaced as caveats, and each pilot names an alternate with a
  different canonical model.

## Rebuild and test

```bash
python3 extract_forge_source.py --forge-repo /path/to/forge   # optional refresh
python3 build_catalog.py
python3 -m unittest discover -v tests
```

Everything is offline; no credentials, live clusters, or GPUs are touched.

## Publishing constraints

No credentials, private registry organization identifiers, Nebius resource
IDs, kubeconfig material, or local filesystem paths may enter these
artifacts. Both the extractor and the builder fail closed on a forbidden
pattern, and `tests/test_catalog.py::Sanitization` re-scans every
committed artifact, including this README.
