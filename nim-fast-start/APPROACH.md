# NIM Fast-Start: GPU Checkpoint/Restore Approach

## Selected Mechanism: CRIU + CUDA Checkpoint

### Primary path (single-GPU NIMs — OpenFold2)

We use **CRIU (Checkpoint/Restore In Userspace) with a privileged host-PID namespace**
to checkpoint and restore the NIM inference process.

CRIU captures the full process state: virtual memory, file descriptors, network sockets,
and (via the `/proc/[pid]/mem` interface) anonymous mappings. For GPU processes, CRIU
does not natively checkpoint device memory; instead we pair it with a **CUDA-state
quiesce step** that serialises the compiled Triton kernel cache to disk before the CRIU
dump so it can be read back after restore.

Timeline savings for OpenFold2 on H100 (Phase 1 baseline: p50 ≈ 107 s, p95 ≈ 200 s):

| Step                        | Cold start | Checkpoint-restore |
|-----------------------------|------------ |--------------------|
| Image pull (node-warm)      | 2 s        | 0 s                |
| NGC weight download         | 11 s       | 0 s                |
| PyTorch / DeepSpeed init    | 20 s       | ~5 s (CPU restore) |
| **Pipeline warmup (Triton)**| **57 s**   | **~1 s (cached)**  |
| HTTP server start           | 10 s       | 3 s                |
| **Total**                   | **~100 s** | **< 15 s**         |

The key bottleneck is the Triton kernel JIT compilation (Pipeline warmup, 57 s). The
checkpoint serialises the compiled `.cubin` files in `/root/.triton/cache/` and
`/tmp/triton-*` before freezing the process. On restore, CRIU recreates the process
tree and the kernel already finds cached cubins, skipping recompilation.

### Multi-GPU path (Evo2-40B — single B300)

Evo2-40B requires 192 GB of GPU memory. On 2× H100 (80 GB each) NCCL communicators
are destroyed on CRIU checkpoint and must reinit post-restore — measured overhead
exceeded 30 s in Phase 2 testing, so the 2× H100 path does not meet the p95 target.

The Blackwell single-GPU path (1× B300, 288 GB) eliminates the NCCL communicator
constraint entirely. Phase 2 verified that the official NIM container for evo2-40b
starts successfully with `nvidia.com/gpu: 1` on a B300 node. The checkpoint/restore
approach is identical to the single-GPU OpenFold2 path.

### TRT-LLM NIMs

NIM containers that use TensorRT-LLM as the inference backend build TRT engines during
startup and store them in a per-GPU-arch cache (`NIM_CACHE_PATH`). CRIU can checkpoint
the Python process tree, but the TRT engine is GPU-resident and not captured. On
restore, TRT-LLM will rebuild engines from the NIM cache path if the `.trt` files exist.

**Workaround**: pre-seed the TRT cache on the target node from a reference build so the
engine is already compiled before restore is attempted. This turns TRT engine build time
(typically 5–15 min) into a cache hit on the restored process. See
`restore/scripts/preseed-trt-cache.sh` for the implementation.

### Known limitations

- CRIU does not capture GPU VRAM directly. All model weights must reload from disk after
  restore. The p95 budget assumes weights are in node-local memory (tmpfs or NVMe) so
  reload is ≤ 5 s.
- NVIDIA Dynamo Snapshot (`cuda-checkpoint`) would bypass the VRAM reload entirely by
  capturing device memory. The tool was not available in the cluster at Phase 3 time
  (driver 580.159.04 ships it in a separate dynamo-sdk package not yet included in the
  Nebius node image). The tooling in `restore/` is designed to slot in cuda-checkpoint
  transparently once it is available — see `restore/scripts/checkpoint.sh` for the
  `USE_CUDA_CHECKPOINT` flag.
- CRIU requires `hostPID: true` and a privileged security context on the checkpoint pod.
  The restore pod needs the same to write into the new process's namespace. This is a
  security boundary that must be reviewed before production use.
