# Cerebrium Qwen3 / GLM-5.2 comparator

This lane is a fail-closed scientific comparator for Cerebrium and fresh,
broker-owned Nebius resources. It deliberately does **not** claim to reproduce
a public Cerebrium Qwen3-8B result: no authoritative source for that exact
claim was found. The pinned Qwen3-8B arms are new matched-target benchmarks.

The only primary deployable GLM candidate is explicitly named
`GLM-5.2-FP8`. The official BF16 checkpoint remains an availability result and
cannot be silently substituted. Cold measurements use the reviewed shared
external-T0 harness in `performance/request_slo`; AIPerf is reserved for warm
and steady-state work.

## Frozen gates

No live deployment is permitted unless all of these gates pass:

1. `python3 comparator.py validate` passes against the committed contracts.
2. Cerebrium reports the exact approved project and requested private Nebius
   placement, with authentication enabled, `min_replicas=0`, and
   `replica_concurrency=1`. GLM additionally requires one exact 8xH200 replica
   with sufficient host RAM and storage. No region, provider, GPU, model, or
   revision fallback is admissible.
3. Internal resources have a PLANNED lease from the reviewed resource broker,
   exact project/region/profile/TTL/cost, and an ID-bound cleanup plan. The
   broker is the only permitted creation path.
4. The selected model/runtime/configuration passes parity smokes before timing:
   non-thinking streaming; thinking at high/default effort with separated
   reasoning/content; and the deterministic `glm47` tool call for GLM.
   Structured JSON is currently out of product scope and is not a gate.
5. Scout results are reviewed before freezing a homogeneous n>=30 cold cohort.
   Every admitted attempt, including capacity errors and failed semantic
   validation, stays in the denominator.

The internal Qwen v5 plan satisfies the offline portion of gate 3 but remains
at `PRE-CREATION REVIEW`; it cannot provision without a fresh clearance bound
to the exact clean candidate commit. Cerebrium still does not satisfy gate 2.
No live mutation has been performed. Pre-existing Cerebrium apps and all
existing Nebius resources are off-limits. Any task-created Cerebrium app must
be left at zero minimum replicas until explicit deletion approval is received.

## Files

- `CLAIM_AUDIT.md` records claim provenance and contradictions.
- `FEASIBILITY_MATRIX.md` records the pre-live architecture decision.
- `INDEPENDENT_REVIEW.md` records accepted independent findings and the
  remaining post-live review gate.
- `PRE_CREATION_REVIEW_V5.md` records the replacement authorization, exact
  hashes, network/GPU lifecycle, two-request semantic gate, and adversaries.
- `VERIFICATION.md` records commands, exact placement/capacity evidence, costs,
  and the zero-resource cleanup disposition.
- `contracts/` pins sources, models, prompts, arms, placement, and statistics.
- `schemas/attempt.schema.json` documents the supplemental receipt. This
  preserves TTFRB/TTFT/TTFO diagnostics and maps to, rather than replaces, the
  shared product-SLO ledger.
- `comparator.py` validates contracts, records streaming attempts, aggregates
  only homogeneous cohorts, and emits reviewed-harness traces/ledgers.
- `resource-requests/` contains offline broker requests and immutable planned
  leases; it does not authorize provisioning by itself.
- `authorizations/internal-qwen3-h100-scout-v5.json` is the publishable,
  hash-only authorization candidate. The independent clearance, bearer secret,
  and distinct broker gate-signing secret are deliberately external to Git.
- `live/` contains the no-package-install bootstrap and authenticated server.
  The server rejects inference until it validates an ACTIVE, zero-egress broker
  gate; uses exact 64-character running container IDs; and admits exactly the
  frozen smoke plus three scout runtime groups.
- `deploy/` contains digest-pinned app specifications. The GLM Cerebrium file
  is intentionally a non-deployable template until the current project exposes
  and confirms the exact H200 compute identifier and count.

Modal is out of scope: no Modal authentication, deployment, live request,
synthetic result, or ranking is permitted. Modal documentation may be used only
as reference material elsewhere. Cerebrium is the sole measured external
backend; measured internal candidates are fresh task-owned Kubernetes or
direct/node-local Nebius VM paths.

## Offline verification

```bash
cd nim-fast-start/faststart-v2/catalog-switch/cerebrium-comparator
python3 comparator.py validate
python3 -m unittest discover -v tests
python3 -m unittest discover -v ../../resource-broker/tests
```

Live commands are recorded only after their corresponding gate becomes true.
Never invoke `cerebrium deploy` or `resource-broker provision` merely from this
README.
