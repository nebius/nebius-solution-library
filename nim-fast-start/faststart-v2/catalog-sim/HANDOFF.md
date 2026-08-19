# Handoff to router/runtime tasks: candidate policies and required telemetry

Status: **provisional**. Per manager guidance (2026-08-19), the 190 synthetic
catalog rows and every inferred phase distribution are placeholder-only, and
no production policy is ranked or recommended until the catalog inventory
(`catalog-switch-model-inventory`) and the shared request-SLO harness schema
(`catalog-switch-request-slo-harness`) land. What follows is the candidate
set the simulator supports, the placeholder-sensitivity observations that
motivated it, and the online telemetry the router/runtime must emit so these
policies can be validated and re-simulated on measured inputs.

## Candidate policy set (implemented and simulated)

- **Placement:** `shortest-switch-cost` (queue-drain estimate plus expected
  teardown + fetch + prewarm + restore cost given the node's actual cache
  state) as the primary candidate; `least-loaded` retained as the control.
  Across all five trace families and all sensitivity levels run so far,
  ignoring switch cost (`least-loaded`) inflated p95 by roughly 2-3x — this
  is the single largest policy effect the simulator observes, and it is
  robust across the placeholder range.
- **L1 eviction:** `lru`, `lfu`, `size-aware`, and `gdsf` (frequency x
  setup-cost / size with aging) are all implemented; observed differences are
  second-order compared with placement and demand shape, and ranking them is
  deferred to measured inputs. `gdsf` is the structurally motivated candidate
  because artifact sizes span ~0.1 GB (MSA) to ~100 GB (Evo2-40B class) and
  restore costs span ~5 s to ~450 s, which is exactly the asymmetry GDSF
  encodes.
- **Warm capacity:** `topk-adaptive` (trailing-window top-K pinned to
  distinct nodes, proactively restored when idle) helps most under
  adversarial working-set alternation and after preemption wipes; its cost is
  visible as reserved-but-not-serving warm-setup GPU-hours.
- **Admission:** `bounded-queue` converts saturation tails into explicit,
  counted rejections. With failed/rejected requests sorted after successes in
  the percentile denominator, this is fail-visible, not a tail-hiding trick.
- **Prefetch:** `pipeline-next` (fetch the next pipeline stage's artifact to
  L1 during the current stage) — only meaningful on correlated/session
  demand; needs a measured pipeline-transition matrix before it can be
  weighed.

## Structural observations that survive the placeholder ranges

1. **Artifact localization dominates the tail.** With measured full-read
   times, a first-touch of a Boltz2-class model on a node costs ~423 s of
   prewarm alone — an order of magnitude above its 27 s restore. Policies
   that avoid first-touches (affinity-aware placement, warm pins, prefetch)
   matter more than micro-optimizing restore.
2. **Conventional loading cannot hold the same offered load.** Under
   identical traces the conventional-load strategy saturates at load levels
   the snapshot strategy absorbs; only MSA Search's measured conventional
   route is competitive (small artifact, cached start).
3. **Preemption couples capacity and cache policy.** A preemption is not
   just lost compute: it wipes L0/L1, so post-recovery demand pays L2 + full
   prewarm again unless warm pinning restores hot models proactively.

## Online telemetry the router/runtime must emit

To validate any of the above and to replace this simulator's placeholders,
the router/runtime tasks need to record, per request (causally ordered,
monotonic clock, shared schema with the request-SLO harness):

1. `t0_accepted` (external acceptance boundary), `model_id`, and the routing
   decision with its inputs (per-node queue depth, L0/L1 residency, and the
   estimated switch cost used).
2. Phase boundaries: queue exit / service start, drain/GPU-release complete,
   artifact-fetch start/end with **bytes moved and source tier**, prewarm
   start/end (or explicit direct-I/O marker), restore-or-load start / HTTP
   ready, first-token-or-response boundary of the first semantic call.
3. Cache events: L1 insert/evict with model id, bytes, digest, and the
   policy's bookkeeping value (recency/frequency/priority) at decision time.
4. Node lifecycle: preemption and recovery timestamps, cache-wipe markers,
   and warm-setup intervals (reserved-not-serving time per model).
5. Terminal outcome per request: completed / rejected / failed-after-retries,
   with retry count — no dropped requests outside these three buckets.
6. Rolling per-model demand counts over a configurable window (the top-K warm
   input) and pipeline-transition pairs (`prev_model -> next_model` within a
   session) for prefetch evaluation.
7. Artifact identity (digest) actually served, so staleness is checkable
   end-to-end.

Given telemetry items 1-2 and 5, every placeholder in
`catalog_sim/catalog.py::PLACEHOLDERS` becomes measurable, and
`catalog_sim/adapters.py` already accepts the resulting per-model
distributions without simulator changes.

## What this handoff explicitly does not claim

- No product SLO numbers: prepared-node measured lanes remain internal-stage
  evidence; synthetic rows are placeholders.
- No production eviction-policy ranking (differences observed so far are
  within placeholder sensitivity).
- No claim about multi-GPU models, heterogeneous GPU classes (the Evo2-40B
  H200 requirement is flattened to the homogeneous fleet), or bandwidth
  contention between prefetch and foreground fetches.
