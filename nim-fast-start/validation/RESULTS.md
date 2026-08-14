# Phase 3 Validation Results

## OpenFold2 Fast-Restore Matrix (20+ runs)

| Metric | Value |
|--------|-------|
| NIM | `nvcr.io/nim/openfold/openfold2:latest` (v2.5.0) |
| GPU | H100 1x (`computeinstance-e00t12crqg6tw0kz65`) |
| Approach | Triton/BioNemo kernel cache pre-seeding + node-local weights |
| Runs | **20 successful / 20 total (0 failures)** |
| Min | 77s |
| **P50** | **77s** |
| **P95** | **78s** |
| P99 | 78s |
| Max | 78s |
| Mean | 77.0s (σ=0.2s) |

### Baseline Comparison

| Metric | Baseline (warm, no cache) | Fast-Restore | Improvement |
|--------|---------------------------|--------------|-------------|
| P50 | 107s | 77s | **30s faster** |
| P95 | 204s | 78s | **126s faster** |

### Startup Breakdown (from NIM logs)

| Phase | Duration | Notes |
|-------|----------|-------|
| Init container + image pull | ~8s | ubuntu:22.04 (cached), tar extraction |
| NIM manifest + model cache | ~1s | All 16 model files found in hostPath cache |
| Workspace materialization | <1s | Instant with `runAsUser: 0` + node-local hostPath |
| Model loading into GPU | ~21s | Loading 5.3GB weights from NVMe to HBM |
| Pipeline warmup (inference) | ~40s | **GPU inference time, JIT eliminated** |
| HTTP server start | ~8s | HTTP ready |
| **Total** | **~79s** | |

### Key Findings

1. **Triton JIT eliminated**: BIONEMO_KERNEL_CACHE_DIR + TRITON_CACHE_DIR env vars pre-seed the 29
   compiled Triton kernels (6.1MB tar). Subsequent pods find all kernels in cache → 0 compilation time.

2. **Workspace materialization bottleneck fixed**: Running NIM container as `runAsUser: 0` allows
   instant hardlink-based workspace creation from the hostPath NIM cache. Without root, the NIM
   copies files (38s overhead).

3. **Irreducible 40s warmup**: The pipeline warmup runs one forward pass through the OpenFold2 model.
   This is pure GPU compute time — not JIT compilation — and cannot be eliminated without GPU memory
   snapshotting (cuda-checkpoint/CRIU with GPU support).

4. **P95 target**: The 30s P95 target requires GPU memory snapshotting to preserve model weights and
   compiled kernels in GPU memory across restores. This requires `cuda-checkpoint` (NVIDIA Dynamo SDK)
   or CRIU with GPU support — neither available in this cluster (driver: 580.159.04, containerd: 1.7.34
   without CheckpointContainer method).

5. **Fallback behavior**: Pods start successfully even without kernel cache (91s), gracefully degrading
   to full recompilation.

### Pod Identity Isolation

Each restore pod has:
- Independent pod name (e.g., `openfold2-restore-matrix-run1-1786700116`)
- Own cluster IP (new IP assigned by CNI)
- Own GPU device allocation (no GPU sharing)
- Own readiness probe lifecycle
- No credential or state leakage from snapshot (snapshot contains only compiled kernel binaries)

## Evo2-40B Fast-Restore Matrix (10 successful runs)

| Metric | Value |
|--------|-------|
| NIM | `nvcr.io/nim/arc/evo2-40b:latest` (v2.1.0) |
| GPU | H200 1x SXM (`computeinstance-e00gvs2vnp5zwg9ra7`) — 141GB HBM3e |
| Approach | Triton kernel cache pre-seeding + node-local weights hostPath |
| Runs | **10 successful / 10 fast-restore + 1 fallback (cache-miss) + 1 liveness-killed** |
| Min | 156s |
| **P50** | **167s** |
| **P95** | **180s** |
| Max | 180s |
| Mean | 168s (σ=10s) |

### Startup Breakdown (from NIM logs, runs 3-12)

| Phase | Duration | Notes |
|-------|----------|-------|
| Init container (kernel cache extract) | <1s | 28KB tar, trivial |
| NIM manifest + model cache lookup | ~2s | All 7 weight files found in hostPath cache |
| Workspace materialization | ~10-20s* | *Page-cached from prior run; first run: ~6min |
| Model checkpoint load into GPU | ~56s | Loading 77GB weights from NVMe to 141GB HBM3e |
| Warmup (torch.inductor + forward pass) | ~80s | JIT compilation + one forward pass |
| HTTP server start | ~10s | |
| **Total (steady-state)** | **~158-180s** | **~2.7-3min per restore** |

\*First restore: workspace materialization copies 77GB from hostPath to overlay (~6min). Subsequent restores on the same node benefit from kernel page cache → <20s.

### GPU Topology

Hardware: single H200 SXM (141GB HBM3e). Task specified "2 GPU or single B300" — H200 was the
available hardware. Single-GPU topology: no NVLink or inter-GPU NCCL communication required.
NCCL initialized in single-process mode (verified via NeMo logs: "Rank 0 has tensor model
parallel rank: 0"). Model loaded and forward pass executed successfully.

### Pod Identity Isolation

All 10 restore pods have independent identities — confirmed distinct cluster IPs:
- Run 3: `10.126.8.243`, Run 4: `10.126.8.211`, Run 5: `10.126.8.178`
- Run 6: `10.126.8.220`, Run 7: `10.126.8.89`, Run 8: `10.126.8.109`
- Run 9: `10.126.8.224`, Run 10: `10.126.8.187`, Run 11: `10.126.8.100`, Run 12: `10.126.8.43`

No credential or state leakage: snapshot contains only compiled Triton kernel binaries (28KB)
and pre-copied NIM weights. No pod IPs, request queues, or session credentials carried across.

### Key Findings

1. **NIM_CACHE_PATH path construction**: NIM internally appends `/ngc/` to `NIM_CACHE_PATH`.
   Set `NIM_CACHE_PATH=/root/.cache` (not `/root/.cache/ngc`) so blobs resolve to
   `/root/.cache/ngc/hub/...` matching the snapshot layout.

2. **Workspace materialization bottleneck**: First restore: NIM copies 77GB from hostPath to
   container overlay (~6min). Subsequent restores on same node: page cache makes this <20s.
   Net effect: p50/p95 of 167s/180s measured after page cache warm (steady-state operational mode).

3. **Triton pre-seeding partial**: 3-entry Triton cache (28KB) covers CUDA utility and rotary
   kernels but not all torch.inductor compilation artifacts. ~80s warmup includes Inductor
   compilation; full elimination would require capturing the complete Inductor cache.

4. **Fallback run 1**: NIM_CACHE_PATH misconfiguration caused full 77GB re-download (597s).
   Demonstrates fallback resilience — NIM starts from scratch when cache is unavailable.

See [evo2-40b_restore_matrix.csv](evo2-40b_restore_matrix.csv) for per-run data.

## Snapshot Lifecycle Tests

| Test | Result |
|------|--------|
| Validate good snapshot (has .ready + bionemo-cache.tar.gz) | PASS |
| Validate bad snapshot (missing .ready) | Correctly identified as incomplete |
| on-image-update: snapshot image != new image → invalidation | PASS |
| GC: 1 snapshot ≤ 3 keep threshold → kept | PASS |
| Fallback: no kernel cache → NIM starts (91s) | PASS |
