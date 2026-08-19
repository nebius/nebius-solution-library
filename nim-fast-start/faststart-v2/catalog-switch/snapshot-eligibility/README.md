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
- **conventional-only** — snapshot rejected by evidence (topology-
  mismatched runtime) or by nature (non-serving row).
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
storage/topology blockers, the provisioned-node cohort status, and the
required — currently nonexistent — new-preemptible-node cohort
(`inputs/bionemo_cohorts.json` is the hand-encoded evidence table). The
builder refuses to emit output when any Modal reference exists outside
the scope notes, so Modal can never become an execution class.

## Pinned inputs (never edited here)

- `inputs/catalog.json` + `inputs/catalog.schema.json` — byte-identical
  vendored copies of the model inventory at commit `9abd4920`
  (branch `agent/catalog-switch-model-inventory`); SHA-256 pins are
  enforced by the builder and the tests, and the vendored catalog is
  re-validated against the vendored schema on every test run.
- The reviewed threat model at commit `9cfbc1b1` (branch
  `agent/catalog-switch-security-reliability`) is pinned by content
  hash; gates bind to its invariants (INV-*) and controls (CTL-*).
- `inputs/lane_evidence.json` — hand-encoded dispositions for the ten
  measured faststart-v2 lanes, citing only committed lane evidence.

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
