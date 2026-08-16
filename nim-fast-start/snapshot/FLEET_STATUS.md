# BioNeMo Fleet Fast-Startup — Status & Per-Model Results

**Goal:** run the BioNeMo agent's NIM fleet on full GPU nodes (8×B300 / H100 pool)
and scale them onto new/preemptible nodes in seconds via CRIU + cuda-checkpoint
GPU snapshot/restore, instead of minutes of cold start.

**Bottom line:** the architecture and method are proven end-to-end. 5 of 10 NIMs
are fully validated (checkpoint → restore → real inference), all distributed on
object storage for cross-node scale-out. The remaining 5 each hit a *distinct,
identified, systems-level blocker* — 3 in CRIU's io_uring handling, 1 in CRIU's
fanotify handling, 1 in the vendor NIM's Blackwell (SM103) compiler support.

## Fully validated (checkpoint + restore + real inference)

| NIM | Arch/pool | Restore→serving | First real inference | Checkpoint |
|-----|-----------|-----------------|----------------------|-----------|
| OpenFold2 | sm90 / H100 | 8.4s warm (NRD+prefetch), 17.1s fresh preemptible | fold, 2.3–2.6s (497KB PDB) | 8.8GB |
| DiffDock | sm90 / H100 | ~10s NRD-class | docking, 1.3s (81KB poses) | 7.8GB |
| RFdiffusion | sm90 / H100 (preemptible) | ~30s NRD-class | backbone, 6.1s (17.7KB) | 23.4GB |
| ProteinMPNN | sm90 / H100 | 15.0s | sequence design, 0.7s (34KB) | 1.9GB |
| GenMol | **sm100 / B300** | ~33s (node-local) | molecule gen, HTTP 200 | 5.7GB |

All checkpoints + JIT artifacts + model caches are on object storage
`s3://mlspec-archvteams-2407-ckpt/` for cross-node distribution.

## Proven infrastructure

- **Full 8-GPU node:** 8×B300 (2,768GB) node group `mlspec-archvteams-2407-b300full`
  in cluster `mk8scluster-e03x6jg7qx89fpsjyg`; H100 pool (baselines cluster) runs
  the sm_90-only NIMs. (8×H200 was capacity-blocked: `NotEnoughResources`.)
- **Preemptible scale-out:** node group `mlspec-archvteams-2407-preempt-ng`
  (`--template-preemptible true`) with the checkpoint SFS attached at boot; a fresh
  preemptible node restored OpenFold2 to a real fold in 17.1s + 2.3s after image pull.
- **Distribution:** S3 bucket + 4TiB SFS (virtiofs, attached at boot via
  `--template-filesystems`) + NRD block PVCs. One shared checkpoint, zero per-node copies.
- **Dominant cold-node cost is the container image pull** (10.7GB ≈ 4–5 min), not
  the checkpoint. Mitigations: pre-baked boot-disk images, in-VPC registry mirror,
  containerd lazy-pull (stargz/nydus).

## The critical arch constraint

**Checkpoints are GPU-architecture-bound.** An sm_90 (H100/H200) checkpoint will not
restore on sm_100 (B300) and vice versa — each NIM is checkpointed once per arch.
Separately, four NIM *images* (DiffDock, RFdiffusion, ProteinMPNN, MolMIM v1.0.0)
ship **sm_90-only kernels** and cannot run on B300 at all — they live on the H100
pool. The newer `/predict`-generation NIMs (OpenFold2/3, Boltz2, GenMol, MSA-Search)
are sm_100-capable and run on B300.

## Reusable pipeline (committed)

- `scripts/checkpoint_nim.sh` — inference-validate donor → harvest JIT caches →
  cgroup PID discovery → cuda-checkpoint lock+checkpoint → patched-CRIU dump
  (`--skip-mnt` PVC/CSI, iptables stubs, `--force-irmap`) → donor kept serving →
  post-dump inference re-check. Env: KC, per-model payloads built in.
- `scripts/restore_nim.sh` — recreate donor CTK-hook dirs (from checkpoint images),
  restore with prefetch, cuda-checkpoint restore+unlock, gate on **real inference**
  (HTTP `/v1/health/ready` can lag/404 while the model already serves).
- `scripts/bench_restore.sh` — timed restore with PREFETCH (parallel page-cache
  warming), the cuda-restore/unlock step, stdio + loopback fixups.

## Remaining 5 — precise blockers (not quick fixes)

| NIM | Blocker | What it needs |
|-----|---------|---------------|
| OpenFold3 | CRIU io_uring + epoll: the async server holds io_uring FDs referenced by an epoll instance. Parasite FD-drain aborts `-22` ("can't retrieve FDs from socket") with FDs open; closing them (inject_close) breaks the epoll dump instead. | A CRIU patch making parasite-skip + daemon FD-count + eventpoll io_uring-filter mutually consistent, then rebuild. |
| Boltz2 | Same io_uring + epoll (4-worker uvicorn). | Same CRIU patch. |
| MSA-Search | Same class (io_uring); codex actively working it. | Same CRIU patch. |
| MolMIM | CRIU fanotify: 17-process supervisord holds an fanotify handle CRIU cannot dump, even with `--force-irmap`. Also sm_90-only + non-root cache perms (both fixed). Tiny model, fast conventionally. | CRIU fanotify-handle support (or disabling the watch). Low priority. |
| Evo2-40B | Vendor: the pinned Evo2 NIM's CUDA 12.8 `ptxas` rejects SM103 (Blackwell). The Phase-6 B300 artifact used a host CUDA-13 override and is quarantined as non-production. | An NVIDIA Evo2 NIM with native SM103 / CUDA ≥12.9. Upstream. |

**Findings that unblocked the validated 5** (each cost real debugging): cuda-checkpoint
must be on the restore PATH and re-run (restore+unlock, no `--timeout`); JIT stub
files must be *real* harvested artifacts (zero-stubs segfault at first kernel); the
donor cache must be PVC/hostPath-backed (emptyDir loses it); HTTP-ready ≠
inference-ready — only a real inference proves a restore.

## Recommendation

Ship the 5 validated NIMs + the pipeline + the scale-out architecture as the
solution now. The 3 io_uring NIMs are unblocked by one CRIU patch (a focused
1–2 day CRIU-dev task, currently in progress); MolMIM and Evo2 wait on upstream
CRIU-fanotify and NVIDIA-SM103 support respectively and should not gate delivery.
