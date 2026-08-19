# Catalog-switch snapshot eligibility

Deterministic, evidence-bound classification of every model catalog row
into one of four snapshot classes, so that no one-size-fits-all CRIU
architecture can be assumed and every catalog model has a safe,
fail-closed startup path.

## Classes

- **direct-snapshot-safe** — native snapshot restore of this exact
  digest is proven by measured-local lane evidence with strict semantic
  validation.
- **snapshot-after-state-externalization** — safe only after an
  explicit, verified externalization of mutable state; the externalized
  variant needs its own digest-bound qualification. (Currently zero
  rows: no catalog row has direct evidence that externalization is both
  required and sufficient. The candidate external-/tmp Boltz2 variant
  is tracked by a sibling task and would land here once qualified.)
- **conventional-only** — snapshot rejected on current evidence (for
  example a correctable capture-artifact topology mismatch) or by
  nature (non-serving row); reclassification requires new exact capture
  and qualification evidence through the shared canary process.
- **unresolved** — insufficient evidence; fail-closed to the
  conventional fallback until the named blockers are resolved through
  the shared canary process.

## Outputs

- `eligibility.json` — schema-validated (`schema/eligibility.schema.json`)
  classification: one row per catalog row, plus gate/blocker/rule
  registries, fallback policy, and the canary plan.
- `eligibility.tsv` — one flat line per row.
- `ELIGIBILITY_POLICY.md` — the human-readable policy: gates,
  fail-closed rules, fallback ladder, and canary process.

`eligibility.json` additionally carries `meta.bionemo_nims`: explicit,
evidence-first coverage of all ten ARCHVTEAMS-2407 BioNeMo NIMs (Boltz2
and OpenFold2 first, with their fresh fail-closed n=20 cohorts), each
recording exact snapshot eligibility, the conventional fallback,
storage/topology blockers, the provisioned-node cohort with its SLO
outcome and outstanding evidence gaps, and the required — currently
nonexistent — new-preemptible-node cohort (at least 20 accepted samples
per scenario, per the authoritative new-node contract). Cohort statuses
are derived, not hand-asserted: the builder maps them from the vendored
catalog's measured evidence class, resolves every evidence ref to
committed bytes with SHA-256 binding, verifies the n=20 cohorts
structurally (20 uniquely identified samples in a NIM-bound cohort, all
runner-qualification/cleanup PASS, semantic requests exercised,
nearest-rank percentiles recomputed, the file's own cohort_outcome
column consistent), extracts the n=3 results by exact field paths
(status PASS, three float samples whose recomputed median equals the
file's median and the catalog p50, exact image reference, exact
response-timing contract — token presence is never sufficient), and
binds each promoted n=3 row to its *selected cohort's own* record:
selected status, semantic request/pass counts, unique run ids,
qualification (image residency), and cleanup fields are asserted by
exact path and exact typed value (`LANE_BINDINGS`). Every promoted
cohort carries an explicit `image_binding` (`in-file` exact reference;
`checkpoint-join` for OpenFold3, whose digest binds through the
checkpoint identity shared between its results and prior-evidence
files; `cohort-bound-n20` for the TSV cohorts) — a snapshot-safe class
with `image_binding: none` refuses the build. ProteinMPNN's
digest-bearing results file and OpenFold3's prior-evidence file are
cited and hash-bound as supplementary evidence; OpenFold3's and
RFdiffusion's missing per-trial cleanup records are disclosed as gaps,
not assumed. The builder also proves
the zero-current-contract new-node state from the committed audit, and
recomputes every SLO verdict from verified samples with the catalog
boolean only cross-checked. MolMIM is downgraded to `unresolved`
(medium confidence, `complete-n3-unsealed`) because its citation is a
harness tree without committed per-run receipts — unsealed evidence
never supports a snapshot-safe class. `inputs/bionemo_cohorts.json`
holds only the hand-encoded blockers and notes. The builder refuses to
emit output when any Modal reference exists outside the scope notes, so
Modal can never become an execution class.

## Pinned inputs (never edited here)

- `inputs/catalog.json` + `inputs/catalog.schema.json` — byte-identical
  vendored copies of the model inventory at commit `9abd4920`
  (branch `agent/catalog-switch-model-inventory`); SHA-256 pins are
  enforced by the builder and the tests, and the vendored catalog is
  re-validated against the vendored schema on every test run.
- `inputs/threat_model.json` — byte-identical vendored copy of the
  reviewed threat model at commit `9cfbc1b1` (branch
  `agent/catalog-switch-security-reliability`), SHA-256 pinned; every
  gate binding (INV-*/CTL-*) is resolved against its exact content at
  build time and drifted/renamed refs fail the build, so a clean clone
  verifies the bindings offline.
- `inputs/lane_evidence.json` — hand-encoded dispositions for the ten
  measured faststart-v2 lanes, citing only committed lane evidence.
- The requested_via interfaces resolve in-ancestry: the reviewed
  resource-broker contract (`229101bb`) and request-SLO harness
  (`ba49c9e2`) are merged into this branch, and the builder verifies
  their v1 schema ids and hashes (`meta.interfaces`).

## Rebuild and test

```bash
python3 build_eligibility.py
python3 -m unittest discover -v tests
```

Everything is offline; no credentials, live clusters, or GPUs are
touched. Live canaries are *requests* to the shared resource-broker and
request-SLO harness process, never runs performed by this task.

## Scope

Per the 2026-08-19 scope correction: Modal is reference material only —
no live dependency, test, or empirical/synthetic ranking appears in
this lane. The sole external measured comparator is Cerebrium; measured
internal candidates are Kubernetes and the direct/node-local VM
runtime.

## Publishing constraints

No credentials, private registry organization identifiers, Nebius
resource IDs, kubeconfig material, or local filesystem paths may enter
these artifacts; the tests re-scan every committed artifact, including
this README, with the inventory's forbidden-pattern scanner.
