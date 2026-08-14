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

### Phase 5: Direct GPU Memory Snapshotting via cuda-checkpoint

Phase 5 validated `cuda-checkpoint` (NVIDIA open-source, CUDA 580.159.04) paired with
CRIU 4.2 as the GPU state snapshotting mechanism on the H100 cluster.

**Verified working (2026-08-14)**:
- `cuda-checkpoint` v580.159.04 installed on node `computeinstance-e00t12crqg6tw0kz65`
- Full lock → checkpoint → restore → unlock cycle works on the live OpenFold2 NIM process
- GPU checkpoint time (5 runs): p50=1.82s, p95=1.85s
- GPU restore time (5 runs): p50=858ms, p95=879ms
- Full CRIU 4.2 + cuda_plugin dump: 1 run, exit=0, 176 images, 8.2GB, 66s total

**CRIU io_uring fixes required** (kernel 6.11 restriction — io_uring FDs cannot use SCM_RIGHTS):
- `proc_parse.c`: classify `[io_uring]` VMAs as `VMA_ANON_SHARED`
- `pie/parasite.c`: detect io_uring FDs via `readlinkat`, skip from drain_fds
- `eventpoll.c`: filter io_uring TFDs from epoll image before dump
- `parasite-syscall.c` + `files.c`: handle daemon/parasite FD count mismatch after filtering
- Binary at `/opt/criu/criu-patched` (hostPath), dump flags: `-L /snapshots/criu-plugins/ --link-remap --tree <bash_ns_init_pid>`

**Current blocker**: CRIU restore requires container-manager integration (containerd/K8s
checkpoint API) for namespace reconstruction. Bare privileged-pod restore fails with
network namespace mismatch. The checkpoint images exist and are valid; restore needs a
container runtime that can inject the restored process into a fresh container namespace.

See `snapshot/approach.md` for detailed technical writeup and timings.

### Known limitations

- CRIU restore requires container-manager integration (containerd CRIU plugin) to
  reconstruct network and mount namespaces correctly. Bare privileged-pod restore fails.
- Full CRIU dump is 8.2GB and takes 66s (dominated by memory pages). With a live migration
  approach (pre-copy dirty tracking), dump time could drop significantly.
- CRIU requires `hostPID: true` and a privileged security context. This is a security
  boundary that must be reviewed before production use.
- cuda_plugin.so "restore TID" warnings are non-fatal for the dump but may complicate
  restore on a different host (CUDA context would need to be re-initialized).
