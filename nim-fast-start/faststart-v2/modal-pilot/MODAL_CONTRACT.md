# Modal official-source contract pin

Task: `catalog-switch-modal-pilot` (parent `catalog-fast-switch-architecture-program`).
All statements below were taken from official Modal primary sources on
**2026-08-19** via direct fetch of the listed URLs. Nothing here comes from
marketing pages, blogs, or third-party benchmarks. Quotes are verbatim from the
documentation on the access date. Anything the docs did not state is listed in
"Unpinned / unresolved" and is treated as unknown until measured or re-pinned.

## Sources (accessed 2026-08-19)

| ID | URL |
|----|-----|
| S1 | https://modal.com/docs/guide/gpu |
| S2 | https://modal.com/docs/guide/memory-snapshot |
| S3 | https://modal.com/docs/guide/cold-start |
| S4 | https://modal.com/docs/guide/volumes |
| S5 | https://modal.com/docs/guide/images |
| S6 | https://modal.com/docs/guide/existing-images |
| S7 | https://modal.com/pricing |
| S8 | https://modal.com/docs/guide/region-selection |
| S9 | https://modal.com/docs/guide/scale |
| S10 | https://modal.com/docs/guide/retries |
| S11 | https://modal.com/docs/guide/webhooks |
| S12 | https://modal.com/docs/guide/timeouts |

## GPU SKUs and pinning (S1)

- Offered GPU strings: `T4`, `L4`, `A10`, `L40S`, `A100`, `A100-40GB`,
  `A100-80GB`, `RTX-PRO-6000`, `H100`, `H100!`, `H200`, `B200`, `B200+`, `B300`.
- Multi-GPU: `gpu="H100:8"`; up to 8 GPUs per container for
  B300/B200/H200/H100/A100/L4/T4/L40S, up to 4 for A10. Docs warn that
  "requesting more than 2 GPUs per container will usually result in larger
  wait times."
- SKU pinning is **not strict by default**: allocations may auto-upgrade
  (H100 → H200, A100 → 80 GB). Strict pinning requires the bang form
  (`gpu="H100!"`). Fallback lists: `gpu=["H100", "A100-40GB:2"]`.
- B300 requires "CUDA version 13.1+"; Blackwell has fewer pre-compiled
  kernels than H100/H200.

Pilot consequence: every measurement must record the *allocated* GPU, not the
requested one, and strict runs must use the `!` form or record the upgrade.

## Memory snapshots (S2)

- Enabled with `enable_memory_snapshot=True`; "Memory Snapshots are created
  only for deployed Apps" (`modal deploy`, not ephemeral `modal run`).
- CPU snapshots capture global-scope state; `@modal.enter(snap=True)` marks
  init code included in the snapshot. During `snap=True` execution **GPUs are
  unavailable**; probing CUDA there can wedge CUDA with zero devices.
- GPU memory snapshots are **alpha**: `enable_memory_snapshot=True` plus
  `experimental_options={"enable_gpu_snapshot": True}`. Documented caveats:
  "Generally incompatible with multi-GPU code", "Generally incompatible with
  non-CUDA GPU code", "Do not speed up model loading from storage", and
  possible `torch.compile` failures (`TORCHINDUCTOR_COMPILE_THREADS=1`
  workaround).
- Invalidation: snapshots are rebuilt when function code or configuration
  (e.g. GPU type) changes, and "Modal recaptures Memory Snapshots to keep up
  with the platform's latest runtime and security changes" — i.e. snapshot
  generation is **not fully under customer control** and must be recorded per
  run. Volume content changes do not invalidate snapshots, but "deleting files
  in a Volume used during restore will cause restore failures."
- Determinism hazard: state captured in a snapshot (e.g. random seeds) "will
  be identical after every restore."

## Cold start and warm pool (S3, S9)

- Cold start = queueing delay + initialization delay. "Containers boot in
  about one second"; initialization (model load) dominates tails.
- Warm-pool controls: `min_containers` (floor, prevents scale-to-zero),
  `buffer_containers` (extra idle capacity while active),
  `scaledown_window` (default 60 s; configurable 2 s – 20 min),
  `max_containers` (ceiling).
- Warm idle capacity **is billed**: "billed for any resources used while the
  container is idle (e.g., GPU reservation or residual memory occupancy)."
- Queue hard limits: "2,000 pending inputs" and "25,000 total inputs"
  (1,000,000 for async `.spawn()`); exceeding them raises
  `Resource Exhausted`.

## Volumes (S4)

- Last-write-wins; explicit `.commit()` / `.reload()` visibility model with
  background commits every few seconds.
- Throughput "up to 2.5 GB/s" but "actual throughput is not guaranteed and
  may be lower depending on network conditions" — storage-bound model loads
  must be measured, never assumed.
- v1: ≤ ~50,000 files recommended, 500,000 inode hard limit. v2: 1 TiB max
  per file, 262,144 files per directory, one writer per file at a time.
- Volumes are "distributed by default" (not region-pinned).

## Existing OCI images (S5, S6)

- `modal.Image.from_registry("<image>")` loads public images "such as
  Nvidia's `nvcr.io`, AWS ECR, and GitHub's `ghcr.io`"; private registries use
  a `modal.Secret` with `REGISTRY_USERNAME` / `REGISTRY_PASSWORD`
  (for nvcr.io: `$oauthtoken` / NGC API key — to be proven live).
- Images must be `linux/amd64`. If the image lacks Python, `add_python="3.11"`
  installs "a reproducible standalone build of Python".
- **Parity-relevant deviations from plain OCI runtime:**
  - "Modal containers always run as root (uid 0)" — Dockerfile `USER` ignored.
  - `EXPOSE`, `HEALTHCHECK`, `LABEL`, `ONBUILD`, `STOPSIGNAL`, `VOLUME`
    directives unsupported/ignored.
  - ENTRYPOINT "must also `exec` the arguments passed to it" when used with a
    Modal Function; Modal effectively drives the container through its own
    runtime rather than the image CMD.
  - `ENV` default interpolation (`${VAR:-default}`) unsupported.

## Web endpoints (S11)

- `@modal.web_server(port)` exposes an HTTP server already running in the
  container; "you need to make sure that the application binds to the external
  network interface, not just localhost."
- Scaled-to-zero endpoint hit: "it will boot up the container, which might
  take a few seconds" (unbounded above by init work).
- Workspace rate limit: "200 Function calls or HTTP requests per second, with
  a burst multiplier of 5 seconds" for new accounts — bounds burst testing.

## Retries and preemption (S10)

- `@app.function(retries=3)` = fixed 1 s delay; `modal.Retries` for
  exponential backoff.
- Deployed apps: "Container crashes will be retried indefinitely … with
  crash-loop backoff"; crashed containers' assigned work is rescheduled and
  re-executed → the harness must record `attempt` per request and treat
  re-execution as part of the same T0 window, never as a fresh sample.

## Timeouts (S12)

- Default function execution timeout 300 s; configurable 1 s – 24 h. The
  timeout "measures a Function's *execution* time" and excludes scheduling;
  container startup has a separate `startup_timeout` (default/max not stated
  in the fetched content).
- Retries each get a fresh timeout window; functions "may run a handful of
  seconds longer" than the timeout.

## Pricing (S7, accessed 2026-08-19; USD, per second)

| Resource | Price/s | ≈ Price/h |
|----------|---------|-----------|
| B300 | $0.001972 | $7.10 |
| B200 | $0.001736 | $6.25 |
| H200 SXM | $0.001261 | $4.54 |
| H100 SXM5 | $0.001097 | $3.95 |
| A100 80GB | $0.000694 | $2.50 |
| A100 40GB | $0.000583 | $2.10 |
| L40S | $0.000542 | $1.95 |
| A10 | $0.000306 | $1.10 |
| L4 | $0.000222 | $0.80 |
| T4 | $0.000164 | $0.59 |

- CPU $0.0000131/core/s (min 0.125 cores); memory $0.00000222/GiB/s;
  Volume storage $0.09/GiB/month with 1 TiB free. Per-second billing;
  "You never pay for idle resources" *except* explicitly billed warm pools
  (S3). Starter plan includes $30/month credit; Team $100/month.
- **Region multipliers (S8): broad region (e.g. `region="eu"`) = 1.5× base
  rate; narrow region (e.g. `region="eu-west"`) = 1.75×.** Default placement
  routes inputs "through our servers in Virginia, USA (`us-east`)".
- EU region strings: `eu`, `eu-west` (Dublin), `eu-north`, `eu-south`.
  `routing_region=` (beta) is fixed at first deployment.

## Unpinned / unresolved (must be measured live or re-pinned)

1. Whether nvcr.io **private** NIM repositories authenticate through the
   generic `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` secret path (docs name
   nvcr.io only among public registries).
2. HTTP request timeout ceiling for `@modal.web_server` endpoints (not stated
   in fetched content) — bounds the synchronous T0-to-response window for
   cold NIM boots.
3. `startup_timeout` default and maximum.
4. Egress pricing (not stated on the pricing page content fetched).
5. GPU snapshot alpha access gating (whether a workspace flag/request is
   required), supported GPU SKUs for GPU snapshots, and interaction with
   pinned (`!`) SKUs.
6. Actual Volume throughput for 5–25 GiB NIM model artifacts (docs only give
   a non-guaranteed 2.5 GB/s ceiling).
7. Whether cached image layers persist across scale-to-zero (image pull cost
   on the Nth cold start) — Modal documents image caching only indirectly.

Any live result that contradicts a pinned quote above must be recorded as a
contract deviation with the raw evidence, not silently reconciled.
