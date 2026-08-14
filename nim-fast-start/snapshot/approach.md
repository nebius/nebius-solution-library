# Phase 5: GPU Memory Snapshotting — Approach & Results

## Summary

Phase 5 implements GPU memory snapshotting via `cuda-checkpoint` (NVIDIA open-source,
CUDA 580.159.04) paired with CRIU 4.2 for process state capture on H100 nodes.

**Key result (2026-08-14)**:
- `cuda-checkpoint` GPU context checkpoint: p50=1.82s, p95=1.85s ✓
- `cuda-checkpoint` GPU context restore: p50=858ms, p95=879ms ✓
- Full CRIU + CUDA dump (176 images, 8.2GB): 66s total, exit=0 ✓
- CRIU restore: blocked by K8s network/mount namespace mismatch

## Environment

- **Node**: `computeinstance-e00t12crqg6tw0kz65` (H100, CUDA 580.159.04)
- **OpenFold2 NIM container**: `openfold2-556df4f968-*` (K8s deployment, namespace `nim-fast-start`)
- **CRIU agent pod**: `nim-criu-agent-hrczg` (hostPID=true, privileged)
- **CRIU version**: 4.2, built from source at `/opt/criu/criu-patched` (hostPath — persistent)
- **cuda-checkpoint version**: 580.159.04 at `/usr/local/bin/cuda-checkpoint`
- **cuda_plugin**: `/snapshots/criu-plugins/cuda_plugin.so`
- **Checkpoint images**: `/snapshots/openfold2/v8/` (176 files, 8.2GB)

## Step 1: cuda-checkpoint Installation

```bash
# In nim-criu-agent-hrczg:
git clone --depth 1 https://github.com/NVIDIA/cuda-checkpoint /tmp/cuda-checkpoint
cp /tmp/cuda-checkpoint/bin/x86_64_Linux/cuda-checkpoint /usr/local/bin/
chmod +x /usr/local/bin/cuda-checkpoint
cp /host/usr/lib/x86_64-linux-gnu/libcuda.so.580.159.04 /usr/lib/x86_64-linux-gnu/
ln -sf libcuda.so.580.159.04 /usr/lib/x86_64-linux-gnu/libcuda.so.1
ldconfig
```

## Step 2: CRIU 4.2 Build from Source

CRIU 3.16.1 (Ubuntu 22.04 default) does not support io_uring. CRIU 4.2 was built from
source at `/opt/criu/criu-src/` with the following patches:

### io_uring patches (kernel 6.11 restriction)

On kernel 6.11.0-1016-nvidia, io_uring FDs CANNOT be sent via `sendmsg` with `SCM_RIGHTS`
(returns EINVAL). Three patches were required:

**`criu/proc_parse.c`**: Classify `anon_inode:[io_uring]` VMA as `VMA_ANON_SHARED` instead
of failing with "Unknown shit 600":
```c
if ((buf.st_mode & S_IFMT) == 0 && strstr(fname, "[io_uring]")) {
    close_safe(vm_file_fd);
    vma->e->status = VMA_AREA_REGULAR | VMA_ANON_SHARED;
    vma->e->flags |= MAP_ANONYMOUS | MAP_SHARED;
    vma->e->shmid = (uint64_t)(uintptr_t)vma->e->start;
    return 0;
}
```

**`criu/pie/parasite.c`** (`fill_fds_fown`): Detect io_uring FDs inside the PIE parasite
via `readlinkat("/proc/self/fd/N")` (F_GETOWN_EX returns 0 not -EINVAL for io_uring),
set `fown.pid = (uint32_t)-1` as sentinel to skip SCM_RIGHTS send. PIE uses C90 — all
variable declarations must be at the top of each block.

**`criu/pie/parasite.c`** (`drain_fds`): Filter sentinel-marked FDs before `send_fds`,
update `args->nr_fds` with filtered count.

**`criu/eventpoll.c`**: Filter io_uring TFDs from epoll dumps via `readlink(proc/pid/fd/N)`
before `find_tfd_bsearch`.

**`criu/parasite-syscall.c`** (`parasite_drain_fds_seized`): After RPC, read updated
`args->nr_fds` from parasite, rebuild `lfds[]` mapping by matching actual sent FDs against
`dfds->fds[]` array (daemon/parasite count mismatch fix).

**`criu/files.c`** (`dump_task_files_seized`): Skip `lfds[i]==-1` (filtered FDs) and skip
`close(-1)`.

## Step 3: Full Checkpoint Sequence

```bash
BASH_PID=242550   # Container namespace init (NSpid 1 inside container)
PYTHON_PID=242651 # Python NIM process

# 1. Build skip-mnt for all host bind mounts (253:1, 0:26, 0:392, vdpau, nvidia)
SKIP_ARGS=$(awk '{dev=$3;mp=$5} dev=="253:1"{print mp} ...' /proc/$PYTHON_PID/mountinfo \
  | sort -u | xargs -I{} echo "--skip-mnt {}")

# 2. Lock + checkpoint CUDA (serializes GPU memory to host memory)
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu cuda-checkpoint --action lock --pid $PYTHON_PID
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu cuda-checkpoint --action checkpoint --pid $PYTHON_PID

# 3. CRIU dump with cuda_plugin (handles NVIDIA device VMAs)
/opt/criu/criu-patched dump \
  --tree $BASH_PID \
  --images-dir /snapshots/openfold2/v8 \
  --leave-running \
  --link-remap \
  --tcp-established \
  --ext-unix-sk \
  --shell-job \
  -L /snapshots/criu-plugins/ \
  $SKIP_ARGS

# 4. Restore CUDA (leave-running mode: NIM continues after dump)
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu cuda-checkpoint --action restore --pid $PYTHON_PID
LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu cuda-checkpoint --action unlock --pid $PYTHON_PID
```

**Timings (single successful run)**:
| Step | Time |
|------|------|
| CUDA lock+checkpoint | 1905ms |
| CRIU dump (176 images, 8.2GB) | 64288ms |
| Total checkpoint | ~66s |

**Key flags**:
- `--tree $BASH_PID`: Must use container namespace init (PID 1 inside container), not Python PID
- `-L /snapshots/criu-plugins/`: Load cuda_plugin.so for NVIDIA device VMA handling
- `--link-remap`: Required for `/dev/shm/sem.*` shared memory remaps
- `$SKIP_ARGS`: 62 skip-mnt entries for host bind mounts

## Step 4: Restore Blocker

CRIU restore (`/opt/criu/criu-patched restore --images-dir /snapshots/openfold2/v8 ...`)
fails when run inside a bare privileged pod:

```
Error (criu/net.c:1469): net: Unknown peer net namespace
Error: ipv4: Address already assigned.
Error (criu/mount.c:48): mnt: BUG at criu/mount.c:48
Error (criu/cr-restore.c:1262): 246104 killed by signal 11: Segmentation fault
```

**Root cause**: CRIU restore requires the restored process to enter the SAME network and
mount namespaces as the original container. Running restore from outside the container
fails because:
1. The veth pair peer is in a different network namespace
2. IP addresses already exist in the node's routing table
3. Mount points don't match the container's pivot-root layout

**Required solution**: Container-manager-integrated CRIU restore. Options:
- **containerd CRIU plugin** (`containerd.io/snapshot/checkpoint-restore`): Native support
  in containerd v2.0+ with CRIU 4.x — creates the container namespace and restores into it
- **NVIDIA Fast-Restore**: If available for the NIM image, may provide a pre-integrated path
- **K8s Checkpoint API** (alpha): `kubectl checkpoint` → restore from checkpoint image

## Results Summary

| Metric | Value | Target |
|--------|-------|--------|
| cuda-checkpoint GPU checkpoint p50 | 1.82s | — |
| cuda-checkpoint GPU checkpoint p95 | 1.85s | — |
| cuda-checkpoint GPU restore p50 | 858ms | — |
| cuda-checkpoint GPU restore p95 | 879ms | — |
| Full CRIU + CUDA dump (1 run) | 66s | — |
| Full CRIU restore | Blocked | <30s |
| **End-to-end restore p95** | **Cannot measure** | **<30s** |

**Assessment**: The GPU state capture mechanism works. The CRIU + cuda_plugin pipeline
produces a complete checkpoint (176 images, 8.2GB for OpenFold2 on H100). The blocker is
CRIU restore requiring container-manager integration for namespace reconstruction, which is
outside the scope of a privileged DaemonSet approach.

## Files

- `scripts/checkpoint.sh` — full checkpoint script (lock → checkpoint → CRIU dump)
- `scripts/restore.sh` — restore script (needs K8s container integration to work)
- `k8s/gpu-restore-pod.yaml` — K8s pod spec for CRIU-based restore (proof of concept)
- `results/gpu_checkpoint_restore.csv` — timing measurements (cuda-checkpoint + CRIU)
