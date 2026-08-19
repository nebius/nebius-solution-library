# Independent architecture review

Review date: 2026-08-19

Reviewer: independent architecture review agent (separate review context)

Verdict: **conditional sign-off**

Scope note: this verdict applies only to preserved baseline `1db7703e`.
Evidence-index v2 commit `7dc39ea7` was subsequently rejected for self-asserted
review provenance, an incomplete negative snapshot, and an unjoined Boltz
observation. Review-record bundle commit `0c470620` and evidence-index v3 do not
inherit this sign-off. `G-INDEPENDENT-REVIEW` remains pending.

The v3 handoff has 30 content-bound entries, zero positive decision inputs,
18 rejected entries, and four pending successors. Its complete offline
reproduction currently passes 376/376 tests, but that green suite is not a
review verdict. A fresh exact review of the final descendant commit is still
required.

The reviewer signs off on this package as an independently reviewable,
conditional ADR and implementation roadmap. This is not sign-off on a
production backend, product SLO, traffic rollout, or deployment.

## Conditions

1. `G-CONTRACT` remains blocked by `BLK-ACCEPTANCE-CONTRACT` and
   `BLK-CONTROL-CHAIN`. A reviewed v2 ingress must preserve external T0 while
   appending target-specific catalog/precondition/resource facts; the control
   chain must bind tenant/deadline/idempotency, boot/runtime readiness, and
   typed failed-operation receipts.
2. No backend may be promoted until the named live-GPU, drain, snapshot,
   broker, storage, cost, chaos, and Cerebrium-security gates close with
   independently reviewed evidence.
3. The provisional 30-second objective is not a product SLO. Product owners
   must ratify or replace it and define p99; the cost/capacity owners must close
   the remaining budget inputs.
4. A new production review is required after the blockers close and before any
   traffic rollout or shared-service deployment.

## Reproduction and adversarial evidence

- `bash catalog-switch/architecture/run_checks.sh`: 349/349 tests passed (85
  architecture tests and 264 integrated child-contract tests).
- Architecture validator: PASS with 18 evidence entries, 8 recommendations,
  and 11 explicit blockers.
- Threat-model validator: PASS.
- `git diff --check`: PASS.
- Adversarial mutations for invalid terminal receipts, non-ACTIVE leases,
  foreign instances/resources, unbound placement snapshots, mismatched typed
  failures, and Modal hidden behind Cerebrium now fail closed.

The reviewer found the evidence limits, all six scenario dispositions,
backend dispositions, telemetry, security/cleanup model, canary and rollback
roadmap, ownership, and reproduction instructions materially complete and
honestly bounded for this conditional decision.
