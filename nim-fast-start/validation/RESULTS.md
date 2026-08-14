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

## Evo2-40B Fast-Restore Matrix

See [evo2-40b_restore_matrix.csv](evo2-40b_restore_matrix.csv) for 10+ restore results.

## Snapshot Lifecycle Tests

| Test | Result |
|------|--------|
| Validate good snapshot (has .ready + bionemo-cache.tar.gz) | PASS |
| Validate bad snapshot (missing .ready) | Correctly identified as incomplete |
| on-image-update: snapshot image != new image → invalidation | PASS |
| GC: 1 snapshot ≤ 3 keep threshold → kept | PASS |
| Fallback: no kernel cache → NIM starts (91s) | PASS |
