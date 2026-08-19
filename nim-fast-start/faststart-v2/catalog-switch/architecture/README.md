# Catalog-switch production architecture decision package

This directory is the integration point for the catalog-switch program. It is
an independently checkable, **conditional** architecture decision, not a claim
that a production backend has won. The reviewed contracts and offline
prototypes are integrated in this branch; the product-boundary GPU cohorts,
capacity/cost model, corrected A-to-B state machine, corrected snapshot
classification, v2 model-id-plus-input acceptance contract, and chaos
qualification are still promotion blockers.

The package's normative parts are:

- `architecture.json` is the machine-readable decision, evidence ledger,
  scenario routing, backend dispositions, budgets, API ownership, benchmark
  matrix, rollout gates, and open blockers.
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

`EVIDENCE_INDEX.md` is the human review map. `MODAL_REFERENCE.md` is a strictly
separate documentation-only appendix. Modal is not an empirical backend, is
not present in any benchmark matrix row, and cannot receive a rank or rollout
weight.

## Decision in one paragraph

Adopt a catalog-aware control plane with one external request boundary and one
causal ledger. Keep Kubernetes as the fleet/control-plane and baseline path.
Evaluate a generation-fenced node-local OCI supervisor as the internal
single-GPU data-plane hot path, without bypassing admission, isolation,
accounting, or cleanup. Use immutable L0/L1/L2 cache identities, a conventional
local-start fallback for every snapshot route, and switch-cost-aware placement
with a queue-depth bound as an experiment-backed policy candidate. Treat
Cerebrium only as the matched external comparator and possible capacity-miss
fallback after its own entitlement, identity, semantic, cost, and raw-cohort
gates pass. No backend is promoted today.

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
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  catalog-switch/architecture/tests
python3 catalog-switch/architecture/capacity_budget.py \
  --arrival-rate-p95 0.5 --occupancy-p95 20 \
  --preemptible-failover-slots 2
bash catalog-switch/architecture/run_checks.sh
```

The first two commands validate only this decision package. `run_checks.sh`
also runs every integrated contract/prototype suite used by the ADR. It is
offline and creates no cloud, cluster, GPU, endpoint, or provider resource.

## Promotion rule

Only `approved` recommendations may be implemented without another decision.
Items marked `experiment-required`, `blocked`, `rejected`, or `reference-only`
are not production claims. Closing a blocker requires a new evidence entry
with a content hash and review; editing prose is insufficient.
