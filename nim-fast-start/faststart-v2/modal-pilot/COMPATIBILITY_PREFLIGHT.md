# Modal pilot — credential and NIM-compatibility preflight

Executed 2026-08-19 on the task host (`/home/tux`), before any live spend.
Result: **offline preflight complete; live phase is BLOCKED on Modal
credentials** (reported to the user, no workaround attempted, per task rule
"Authentication/billing absence is reported as a blocker; no credential
workaround").

## 1. Credential preflight (exact checks and outcomes)

| Check | Command | Outcome |
|-------|---------|---------|
| Modal CLI on PATH | `which modal` | not found |
| Modal SDK importable | `python3 -c "import modal"` | `ModuleNotFoundError` |
| Modal token file | `ls ~/.modal.toml` | absent |
| Modal env tokens | `env \| grep -i '^MODAL'` | none set (`MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET` absent) |
| Modal refs in config/state/profiles | `grep -rli modal ~/.config ~/.local/state ~/.bashrc ~/.profile` | no credential material (only unrelated source-tree hits) |
| NGC config | `ls ~/.ngc` | present (`meta_data`, no API key line) |
| Docker registry auth | `~/.docker/config.json` auths | `nvcr.io`, `cr.me-west1.nebius.cloud`, `cr.us-central1.nebius.cloud` present |

Conclusions:

- **Modal workspace credentials and billing: ABSENT.** No `modal token`,
  no workspace, no plan/billing state. Every live item in the experiment plan
  is gated on the user providing a Modal workspace with an agreed spend cap.
- **NGC pull credentials for NIM images: PRESENT** (docker auth for
  `nvcr.io`). Once a Modal workspace exists, this credential can be copied
  into a Modal Secret (`REGISTRY_USERNAME=$oauthtoken`,
  `REGISTRY_PASSWORD=<NGC key>`) without creating any new NVIDIA credential.
  No Nebius resources are needed for the Modal-side pilot itself.

## 2. NIM lifecycle → Modal mapping and adapter boundary

The pilot's first-class deliverable is exact NIM/Modal lifecycle
compatibility plus a clean **adapter boundary**: everything Modal-specific
(app template, deploy modes, pool configuration, Modal observability
scraping) stays behind `harness/modal_nim_app.py` and the provisional event
emitter, so that when `catalog-switch-request-slo-harness` publishes the
shared external-client ledger, only the emitter is swapped — the workload,
validators, and T0 discipline do not change.

The candidate wrapper keeps the NIM workload byte-identical (same nvcr.io
image digest, same internal server, same API), which the task requires
("Never rewrite the workload merely to obtain a faster number"):

- Image: `modal.Image.from_registry("<nvcr.io NIM image>@sha256:<digest>", secret=...)`,
  pinned by digest so artifact-version binding is provable per run.
- Serving: `@modal.web_server(8000)` in front of the NIM's own entrypoint
  launched unmodified inside the container; requests hit the NIM's native
  HTTP API, so semantic parity can be judged with the existing faststart-v2
  validators (`validate_openfold2.py`, `boltz2-native/validate_boltz2.py`).
- GPU: explicit SKU with strict pin (`gpu="H100!"` or exact A100 variant),
  allocated SKU recorded per run.
- Weights: two lanes — (a) NIM's own download path on first boot (true remote
  miss), (b) pre-populated Modal Volume mounted at the NIM cache path
  (local-artifact hit). Bytes moved recorded per lane.

## 3. Known parity deviations (recorded up front, from official docs)

These are inherent to Modal's runtime and must be reported with any result;
any of them may individually justify rejection if it changes NIM behavior:

1. **uid 0 execution.** "Modal containers always run as root"; NIM images
   define a non-root user and NGC docs assume it. Cache-path ownership and
   any uid-dependent behavior must be smoke-checked live.
2. **ENTRYPOINT/CMD not honored as in plain OCI.** The NIM entrypoint must be
   re-invoked explicitly by the wrapper; the command line used will be
   captured and diffed against the image's ENTRYPOINT/CMD so the deviation is
   exact, not assumed.
3. **`HEALTHCHECK`/`EXPOSE`/`VOLUME` ignored.** Readiness must be driven by
   the NIM's own `/v1/health/ready`, polled by the harness.
4. **CPU snapshot semantics conflict with NIM boot order.** CPU-snapshot mode
   requires init under `@modal.enter(snap=True)` **without GPU access**; a
   stock NIM initializes CUDA during boot. If the NIM cannot reach a
   pre-CUDA snapshot point without modifying its startup, CPU-snapshot mode
   is recorded as **incompatible-as-is** for that NIM rather than hacked
   around.
5. **GPU snapshot alpha limits.** Officially "generally incompatible with
   multi-GPU code" and "do not speed up model loading from storage" — the
   multi-GPU pilot is therefore expected to be snapshot-ineligible, and
   storage-bound models (Boltz2 lane experience) should expect no
   load-time win; both are hypotheses the live phase tests, not assumptions.
6. **Managed drain/placement is invisible.** Modal exposes no per-request
   causal timestamps for placement, image/artifact readiness, or GPU release.
   Client-observed T0→first-valid-response is the primary metric; interior
   phases are attributed only from container-side logs emitted by the NIM and
   wrapper, with provenance labels. Phases Modal does not expose are reported
   as `unobservable(managed)`, never estimated.

## 4. Go/no-go criteria fixed before live spend

Reject Modal (for a lane) if any of the following is observed and
reproducible:

- The pinned NIM image digest cannot run unmodified (entrypoint, uid, CUDA,
  or license flow breaks) — record as **NIM parity rejection**.
- Semantic validation of responses fails the existing faststart-v2
  validators on any accepted run.
- Requested strict GPU SKU is not honored.
- Per-request attempt accounting cannot be made exact (retries invisible to
  the client), which would make T0 boundaries unauditable.

Escalate to "unresolved caveat" (not silently dropped) if: GPU Snapshot Alpha
is inaccessible to the workspace, multi-GPU capacity is unavailable, or queue
limits prevent the burst matrix.
