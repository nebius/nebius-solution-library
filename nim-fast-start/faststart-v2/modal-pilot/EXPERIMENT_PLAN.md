# Modal pilot — recorded experiment plan (pre-spend)

Written 2026-08-19, **before any live Modal spend**, as required by the task
("live spend follows a recorded experiment plan"). Execution is blocked until
the user provides a Modal workspace token and confirms the budget cap below.

## Metric boundary (frozen, inherited from the program contract)

- **T0** = external acceptance of a request carrying `model_id` + input,
  timestamped by the client harness immediately before the request leaves the
  client (wall UTC + monotonic).
- **Completion** = first complete, semantically valid response, validated by
  the existing faststart-v2 validators for the model.
- No request-specific work moves before T0 (no per-request pre-warming, no
  pre-posted payloads). Warm-pool configuration is a *mode*, declared per
  cohort, never per request.
- All attempts are reported; retries/preemptions stay inside the original T0
  window; failed runs count as failures, never resampled away.
- Aggregation gates (enforced by `harness/aggregate.py`, fail-closed):
  p50 needs n≥5, p95 needs n≥20, p99 needs n≥100; promoted cold/switch
  claims need n≥30 independent repetitions.

## Pilots

| Pilot | Image (pin by digest at run time) | GPU request | Rationale |
|-------|-----------------------------------|-------------|-----------|
| P1 OpenFold2 | `nvcr.io/nim/deepmind/openfold2` (same tag as faststart-v2 lanes) | `A100-80GB!` primary, `H100!` secondary | snapshot-friendly small model, direct comparison to the CRIU lane |
| P2 Boltz2 | `nvcr.io/nim/mit/boltz2` (same tag as `boltz2-native/`) | `H100!` | storage-heavy load path, matches the SLO-failing internal lane |
| P3 large/multi-GPU representative | an LLM NIM requiring ≥2 GPUs (exact image chosen when access is confirmed) | `H100:2!` (fallback recorded) | multi-GPU + capacity behavior; expected GPU-snapshot-ineligible per contract |

Inputs are the exact payloads used by the internal lanes (OpenFold2 validator
sequence; Boltz2 1UBQ-class payload) so responses can be judged by the same
validators.

## Mode matrix (per pilot, one variable at a time)

| Mode | Modal configuration | Cohort |
|------|---------------------|--------|
| M0 cold, snapshots off | `enable_memory_snapshot=False`, scale-from-zero, `scaledown_window` minimum | n≥30 |
| M1 CPU snapshot | `enable_memory_snapshot=True`, init split at the pre-CUDA point **if the stock NIM permits one**; otherwise recorded incompatible | n≥30 or rejection record |
| M2 GPU snapshot (alpha) | M1 + `experimental_options={"enable_gpu_snapshot": True}` where the workspace has access; single-GPU pilots only | n≥30 or unresolved record |
| M3 bounded warm | `min_containers=1`, `buffer_containers=0` — exactly one bounded warm configuration, idle billing recorded | n≥30 |
| SW A→B switch | model A app receiving traffic; T0 = first request for model B; measure B's first valid response while A stays deployed | n≥30 per promoted pilot |
| BURST | k=10 simultaneous cold requests to one scaled-to-zero app (within the documented 200 rps workspace limit) | ≥3 bursts |
| CAP capacity probe | strict-SKU request during observed contention; record queue time / Resource Exhausted behavior | opportunistic, all attempts logged |

Snapshot generation, allocated GPU, region, image digest, pool state, attempt
count, and Modal request IDs are recorded per run (see
`harness/event_schema.py`). Cache state per run is classified
{remote-miss, volume-hit, image-cached, snapshot-restored, warm}.

## Region and routing

Primary cohorts run with `region="eu"` (broad, 1.5× rate) for comparability
with the Nebius eu lanes; one M0 sub-cohort (n≥10) runs with default
placement to quantify the us-east routing penalty. Region strings and
multipliers are recorded per run.

## Budget and cost accounting

- Worst-case per cold run: ≤ 900 s wall on one H100 at $0.001097/s × 1.5 (eu)
  ≈ **$1.48/run**; OF2 on A100-80GB ≈ $0.94/run.
- Matrix ceiling: 3 pilots × ~4 modes × 30 runs at worst-case ≈ $310 upper
  bound if literally every run were a 15-minute H100 cold start; realistic
  estimate is $120–$180 because warm/snapshot runs are short.
- **Hard budget cap proposed: $250** of Modal spend, enforced by per-run
  `timeout` (≤ 1800 s), `max_containers=1..2` per app, immediate
  `modal app stop` after each cohort, and a running cost ledger (billed
  seconds × pinned price × region multiplier) checked between cohorts.
  P3 (multi-GPU) starts only if ≥ $80 of the cap remains.
- Idle-warm billing for M3 is bounded: warm window ≤ 2 h per pilot.

## Resource naming, tagging, and teardown

- Modal app names: `mlspec-catswitch-<pilot>-<mode>` (e.g.
  `mlspec-catswitch-of2-m0`); Volumes: `mlspec-catswitch-<pilot>-cache`;
  Secrets: `mlspec-catswitch-ngc`.
- Everything lives in a dedicated Modal environment `catalog-switch-pilot`.
- Teardown after the matrix: `modal app stop` + `modal app delete` for every
  app, Volume and Secret deletion, final `modal app list` / `modal volume
  list` receipts captured. Retention only with a written reason.
- No Nebius resources are created for this pilot. If a Nebius-side echo test
  is later needed, it goes through `catalog-switch-resource-broker`.

## Execution gates (in order)

1. **G0 (blocked)**: user provides Modal workspace token + billing and
   confirms the $250 cap. GPU Snapshot Alpha access is requested/confirmed at
   the same time.
2. **G1 compatibility smoke** (≤ $10): pull pinned OF2 image via Secret,
   boot unmodified NIM under `@modal.web_server`, one semantic request,
   capture uid/entrypoint/readiness evidence. Any parity rejection stops the
   affected lanes here.
3. **G2 M0 baseline** for P1/P2 (n≥30 each).
4. **G3 snapshot modes** M1, then M2 (one variable at a time).
5. **G4 M3 bounded warm**, then SW switch cohorts, then BURST/CAP.
6. **G5 teardown + report**: feasibility/result matrix, cost ledger,
   contract deviations, rejection records, unresolved caveats.
