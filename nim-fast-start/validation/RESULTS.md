# Validation results

These runs measure cache-preseeded NIM startup. They are not process or GPU-memory
restores. Each run created a new Pod with its own UID, IP address, container, GPU
allocation, and readiness lifecycle.

## OpenFold2 on H100

Twenty cache-preseeded Pods became Ready successfully. Startup was 77 seconds at
p50 and 78 seconds at p95, compared with 109 seconds at p50 and 204 seconds at p95
for the PVC-backed warm baseline.

The preseed artifact contained 29 compiled BioNeMo/Triton kernels (6.1 MiB). The
node-local model cache contained about 5.3 GiB. Logs showed approximately 21 seconds
for loading weights into HBM, 40 seconds for the warmup forward pass, and 8 seconds
for the HTTP server. The remaining warmup compute prevents sub-30-second startup
without GPU-memory checkpointing.

All 20 measured runs succeeded. A separate cache-miss run also started normally in
91 seconds, validating conventional-start fallback.

Raw data: [openfold2_preseed_matrix.csv](openfold2_preseed_matrix.csv).

## Evo2-40B on H200

Ten steady-state cache-preseeded Pods became Ready successfully on one H200. Startup
was 167 seconds at p50 and 180 seconds at p95. The cold baseline was 622 seconds at
p50 and 842 seconds at p95; the PVC-backed warm baseline was 158 seconds at p50 and
173 seconds at p95.

The 28 KiB Triton artifact covered three kernels, while the node-local model cache
held roughly 77 GiB. A first attempt with an incorrect cache path fell back to a
597-second model download. A second setup attempt was killed by a liveness probe set
shorter than first-time workspace materialization. After correcting both settings,
all ten measured runs succeeded.

This path improves cold startup substantially but does not improve the steady-state
PVC warm baseline. It is useful when nodes are pre-staged and image/model downloads
would otherwise dominate startup.

Raw data: [evo2_40b_preseed_matrix.csv](evo2_40b_preseed_matrix.csv).

## Scope not validated

- No process state or GPU VRAM was checkpointed.
- No multi-GPU or concurrent restore was run.
- The Evo2-40B NIM used one H200. The tested image failed on B300 because its `ptxas`
  did not recognize `sm_103`.
- First-response latency was recorded for the conventional baselines but not for the
  cache-preseed matrices.
- Cache distribution over a shared filesystem or Object Storage was not benchmarked.
