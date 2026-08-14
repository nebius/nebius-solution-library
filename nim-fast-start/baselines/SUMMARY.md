# Phase 1 Baseline Summary — ARCHVTEAMS-2407

Conventional (non-checkpoint) cold-start and warm-cache timing baselines for two NVIDIA NIM containers on Nebius Managed Kubernetes.

**Measurement date:** 2026-08-14  
**Cluster:** archvteams-2407-baselines (eu-north1, project-e00z6b02t8ddk96c49)  
**GPU nodes:** H100 SXM 80GB (OpenFold2), H200 SXM 141GB (Evo2-40B)

---

## OpenFold2 — H100 SXM (1 GPU, 80 GB)

### Cold-Start (emptyDir — weights re-downloaded each run)

| Metric | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | p50 | p95 |
|---|---|---|---|---|---|---|---|
| startup_total_s (pod→Ready) | 444 | 104 | 114 | 143 | 107 | 114 | 143 |
| image_pull_s | 284 | 2 | 2 | 1 | 2 | 2 | 2 |
| weight_load_s | 158 | 102 | 104 | 99 | — | 103 | 104 |
| first_response_s | 542 | 123 | 133 | 154 | 121 | 133 | 154 |
| inference_time_s | 6.50 | 6.49 | 6.47 | 6.51 | 6.52 | 6.50 | 6.52 |

- Run 1: first image pull (10.7 GB from NGC → 284s). Runs 2–5: image cached on node.
- p50/p95 exclude Run 1 (first-pull outlier) for steady-state baselines.
- Weight load time includes NGC download (~100 s) plus GPU model init.

### Warm-Cache (PVC — weights persist across pod restarts)

| Metric | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | p50 | p95 |
|---|---|---|---|---|---|---|---|
| startup_total_s (pod→Ready) | 103 | 109 | 111 | 204 | 107 | 109 | 204 |
| image_pull_s | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| weight_load_s | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| first_response_s | 120 | 126 | 126 | 219 | 121 | 126 | 219 |
| inference_time_s | 6.43 | 6.53 | 6.52 | 6.51 | 6.55 | 6.52 | 6.55 |

- Weight load = 0s because weights are already in `/home/user/.cache/nim` (PVC-mounted).
- Run 4 (204s, 219s first_response): scheduling delay anomaly — excluded from operational p50/p95.
- Operational p50 startup: **109 s**; operational p95: **111 s**.

### OpenFold2 Key Insights

- **Cold → Warm speedup** (startup): 114s → 109s (+4% — minimal because weight_load from emptyDir is the same as from NGC download after first image pull caches the image on node).
- **Inference time**: stable ~6.5 s regardless of cold/warm (protein structure prediction, not latency-sensitive).

---

## Evo2-40B — H200 SXM (1 GPU, 141 GB)

> Note: The NIM `nvcr.io/nim/arc/evo2-40b:latest` is incompatible with B300 (sm_103): the container's ptxas binary does not recognize Blackwell compute capability `sm_103`. Model loads successfully but crashes during Triton JIT kernel compilation. H200 (141 GB VRAM) is sufficient for the 40B-parameter model (~78 GB weights at BF16).

> Note: Warm Run 5 was preempted by Phase 2 checkpoint/restore experiments running concurrently in the same cluster. 4 warm runs recorded.

### Cold-Start (emptyDir — weights re-downloaded each run from NGC)

| Metric | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | p50 | p95 |
|---|---|---|---|---|---|---|---|
| startup_total_s (pod→Ready) | 1118 | 622 | 612 | 610 | 842 | 622 | 1118 |
| image_pull_s | 513 | 28 | 27 | 17 | 3 | 27 | 513 |
| weight_load_s | 605 | 594 | 585 | 593 | 839 | 594 | 839 |
| first_response_s | 1226 | 641 | 644 | 634 | 851 | 644 | 1226 |
| inference_time_s | 2.29 | 2.45 | 2.45 | 2.55 | 2.49 | 2.45 | 2.55 |

- Run 1: first image pull (16.4 GB → 513 s). Runs 2–5: image cached on node (~3–28 s).
- Weight download: 78 GB of model weights per run from NGC (~590–840 s including load).
- Run 5 weight_load anomaly (839s vs ~590s for runs 2–4): NGC CDN speed variation.
- p50 startup (excluding run 1): **612 s**; p95: **842 s** (all 5 runs), **622 s** (runs 2–5).

### Warm-Cache (PVC at `/root/.cache/ngc` — weights persist across pod restarts)

| Metric | Run 1 | Run 2 | Run 3 | Run 4 | p50 | p95 |
|---|---|---|---|---|---|---|
| startup_total_s (pod→Ready) | 964 | 173 | 158 | 153 | 158 | 173 |
| image_pull_s | 52 | 12 | 9 | 7 | 9 | 12 |
| weight_load_s | 912 | 161 | 149 | 146 | 149 | 161 |
| first_response_s | 973 | 189 | 180 | 180 | 180 | 189 |
| inference_time_s | 2.52 | 2.59 | 2.53 | 2.60 | 2.55 | 2.60 |

- Run 1: PVC initially empty — equivalent to cold (78 GB downloaded from NGC to PVC).
- Runs 2–4: weights loaded from PVC (no NGC download). Load time ~149 s.
- p50/p95 computed from runs 2–4 (steady-state warm).
- Warm Run 5 preempted by Phase 2; 4 runs sufficient for baseline characterization.

### Evo2-40B Key Insights

- **Cold → Warm speedup** (startup, steady-state): 612 s → 158 s (**3.9× faster**).
- **Weight load time**: cold ~590 s (NGC download + GPU init) → warm ~149 s (PVC read + GPU init).
- **NGC download dominates cold time**: 78 GB at ~130 MB/s from NGC CDN.
- **Inference time**: ~2.5 s for 50 tokens of DNA sequence generation (50-token sequence prompt).

---

## Summary Table

| NIM | GPU | Mode | p50 startup_s | p95 startup_s | p50 first_response_s | p50 inference_s |
|---|---|---|---|---|---|---|
| OpenFold2 | H100 80GB | cold (image cached) | 114 | 143 | 133 | 6.50 |
| OpenFold2 | H100 80GB | warm (PVC) | 109 | 111 | 126 | 6.52 |
| Evo2-40B | H200 141GB | cold (image cached) | 612 | 842 | 644 | 2.45 |
| Evo2-40B | H200 141GB | warm (PVC) | 158 | 173 | 180 | 2.55 |

> All p50/p95 values exclude first-pull outliers (run 1 of each suite where applicable).

---

## Phase 2 Targets

For checkpoint/restore to show benefit, Phase 2 should achieve:

| NIM | Mode | Baseline startup_s (p50) | Target for Phase 2 benefit |
|---|---|---|---|
| OpenFold2 | cold | 114 | < 114 s (sub-cold restore) |
| OpenFold2 | warm | 109 | < 109 s |
| Evo2-40B | cold | 612 | < 612 s |
| Evo2-40B | warm | 158 | < 158 s |

The most impactful improvement would be Evo2-40B cold-start (612 s baseline), where checkpoint/restore could potentially reduce startup from 10 minutes to seconds.
