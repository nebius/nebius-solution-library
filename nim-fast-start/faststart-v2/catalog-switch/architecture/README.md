# Catalog-switch evidence index and conditional architecture baseline

This directory is the integration point for the catalog-switch program. Commit
`1db7703e` remains the preserved conditional architecture baseline. The current
revision reopens it **only as an evidence-index update**; it does not select a
backend, finalize the ADR, approve a product SLO, or authorize live work.

Kubernetes, plain node VM, and Cerebrium each have zero accepted matched
product-boundary cohorts. All-ten Arm A/Arm B coverage and an accepted safe
drain/reclaim replacement are missing. Cerebrium remains the sole intended
external comparator. Modal remains documentation-only and receives no measured
score.

The package's normative parts are:

- `architecture.json` is the machine-readable decision, evidence ledger,
  scenario routing, backend dispositions, budgets, API ownership, benchmark
  matrix, rollout gates, and open blockers.
- `evidence-index.v2.json` is the current exact-commit evidence authority;
  `evidence-index.v2.schema.json` closes its shape.
- `decision-matrix.v1.json` keeps every backend/scenario winner, score, and rank
  null until matched evidence exists; its schema makes that state executable.
- `budget-placeholders.v1.json` contains only null, unratified latency and cost
  ceilings. `OPEN_UNKNOWNS.md` records the exact exits blocking a decision.
- `ADR.md` explains the decision and the exact control/data-plane design.
- `IMPLEMENTATION_ROADMAP.md` assigns phases, owners, estimates, canaries, and
  rollback actions.
- `architecture.schema.json` closes the decision-document shape, while
  `control-plane-api.schema.json` defines the ten request/success fragments,
  a discriminated request envelope, typed failures, signed node commands, and
  response-commit/replay semantics.
- `attempt_context.py` validates append-only placement/fallback identity,
  task-owned leases, input, inference, semantic, response, terminal, and
  all-attempt failure receipt chains.
- `capacity_budget.py` executes the provisional capacity formula.
- `validate_architecture.py` and `tests/` fail closed when scope, evidence,
  provenance, API, scenario, budget, security, or promotion constraints are
  weakened.
- `validate_evidence_index.py` verifies exact Git commits/blobs, independent
  acceptance, negative review history, zero cohorts, no winner, and null
  budgets.

`EVIDENCE_INDEX.md` is the human review map. `MODAL_REFERENCE.md` is a strictly
separate documentation-only appendix. Modal is not an empirical backend, is
not present in any benchmark matrix row, and cannot receive a rank or rollout
weight.

## Current non-decision

No backend is selected or ranked. The structural material preserved from
`1db7703e` remains a conditional baseline for future experiments, not the
outcome of this pass. The current authoritative matrix has `winner: null`,
disabled scoring, and zero matched cohorts for Kubernetes, node VM, Cerebrium,
and the unscored Modal reference row.

The reviewed v1 ledger remains valid for pre-resolved benchmark cohorts, but
its T0 target already contains exact artifact identity. The product API accepts
`model_id` plus input and resolves artifact identity after T0.
`BLK-ACCEPTANCE-CONTRACT` keeps `G-CONTRACT` blocked until a reviewed v2 ledger
accepts only authenticated caller-known tenant/idempotency/model/input/deadline
facts at T0, then appends catalog, target-specific preconditions, placement,
resource inventory, and cleanup evidence. `BLK-CONTROL-CHAIN` separately
requires runtime/boot readiness attestation and causal failed-operation
receipts. Neither gap may be hidden by moving work before T0.

## Reproduce

From `nim-fast-start/faststart-v2`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 \
  catalog-switch/architecture/validate_architecture.py
PYTHONDONTWRITEBYTECODE=1 python3 \
  catalog-switch/architecture/validate_evidence_index.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  catalog-switch/architecture/tests
bash catalog-switch/architecture/run_checks.sh
```

The first two commands validate only this decision package. `run_checks.sh`
also runs every integrated contract/prototype suite used by the ADR. It is
offline and creates no cloud, cluster, GPU, endpoint, or provider resource.

## Promotion rule

This reopened revision makes no implementation recommendation. A future
positive item requires independent acceptance of its exact source commit and
bounded claim, an intentional validator allowlist update, and a matching Git
blob hash. Rejected `34d70fd0` and `f5f2706a`, all current replacement
rejections, prepared-stage evidence, projections, and references cannot become
design inputs by editing a label.
