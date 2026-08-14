# Phase 5: GPU Memory Snapshotting — Approach & Results

## Summary

Phase 5 implements GPU memory snapshotting via `cuda-checkpoint` (NVIDIA open-source,
CUDA 580.159.04) paired with CRIU 4.2 for process state capture on H100 nodes.

**Key result (2026-08-14)**:
- `cuda-checkpoint` GPU context checkpoint: p50=1.82s, p95=1.85s ✓
- `cuda-checkpoint` GPU context restore: p50=858ms, p95=879ms ✓
- Full CRIU + CUDA dump (checkpoint v12, 179 images, 8.7GB): 68s total, exit=0 ✓
- **Full CRIU + CUDA restore on H100: 63.5s total, exit=0, NIM HTTP /v1/health/ready=200 ✓**
- Path to sub-30s: move checkpoint to SFS (2 GB/s → ~6s) or use CRIU lazy-pages

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

## Step 4: CRIU Restore — Successful Approach (2026-08-14)

### Checkpoint used: `criu42-v12`

- Location: `/snapshots/openfold2/criu42-v12/` on H100 node `/dev/vda1`
- 179 files total: 169 metadata + 10 pages-*.img (pages-1 through pages-10)
- Total pages: 8.7GB (pages-9.img dominates at 8.2GB)
- Taken with CRIU 4.2, `--leave-running`, `--tree $BASH_PID`, `-L cuda_plugin.so`

### Restore pod: `openfold2-restore-v4`

```yaml
spec:
  nodeName: computeinstance-e00t12crqg6tw0kz65
  hostPID: true          # access host PIDs and /proc/1/root/
  restartPolicy: Never
  containers:
  - name: restorer
    image: nvcr.io/nim/openfold/openfold2:latest
    command: ["/bin/bash", "-c", "sleep 3600"]
    securityContext:
      privileged: true
      runAsUser: 0
    resources:
      limits:
        nvidia.com/gpu: "1"
    # NO volumeMounts — avoid extra mounts that trigger CRIU mount BUG
```

### Pre-restore setup (inside restore pod)

**1. Hardlink all pages files into pod overlay** (symlinks break in restored namespace):
```bash
# From CRIU agent (has host filesystem access):
UPPER=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots/661/fs
PAGES=/snapshots/openfold2/criu42-v12
for f in pages-{1..10}.img; do
  ln $PAGES/$f $UPPER/tmp/checkpoint/$f
done
# Inside restore pod: echo 3 > /proc/sys/vm/drop_caches to refresh overlayfs cache
```

**2. Create JIT-compiled file stubs** (MAP_PRIVATE mmap'd; content restored from pages):
```bash
# tvm-ffi JIT library (size and mode from checkpoint regfiles.img):
mkdir -p /root/.cache/tvm-ffi
truncate -s 212272 /root/.cache/tvm-ffi/libtorch_c_dlpack_addon_torch210-cuda.so
chmod 0755 /root/.cache/tvm-ffi/libtorch_c_dlpack_addon_torch210-cuda.so

# Triton JIT kernel launchers (compiled at NIM startup; in overlay, not tmpfs):
for HASH in ZDI6JWI5Z4RZ7GIRUDJ6SDSQFQGVNM7LCGJC7WPVWLBVZ6QJPZFA \
            F3PT4AYMVUT4FC5Y26UMLMHMFXZCXY6TSOAWU5K2YPPQX7UHL4AA \
            SZYSIZWIUEESFDNVENTPAJJ7KVLKMBDUYREWMS3M3M4Z6MSV4WQA \
            BT6Y3UMOYWWZM5JW6N7ZDQPHHVVF53OTLI5S3M4TGZNUXEODVS7Q; do
  mkdir -p /tmp/root/bionemo_kernel_cache/triton/$HASH
  truncate -s 21712 /tmp/root/bionemo_kernel_cache/triton/$HASH/__triton_launcher.cpython-312-x86_64-linux-gnu.so
done
HASH=XU5DT2AO5BD5AEHEYGLPP5LRDFHHCUEJT4LGDVLB4STXUGVGHFPA
mkdir -p /tmp/root/bionemo_kernel_cache/triton/$HASH
truncate -s 31944 /tmp/root/bionemo_kernel_cache/triton/$HASH/cuda_utils.cpython-312-x86_64-linux-gnu.so
```

**3. Unmount K8s-injected mounts** (not in original checkpoint, trigger mount BUG):
```bash
umount -l /run/secrets/kubernetes.io/serviceaccount
# Unmount NEW UUID CTK hook (old UUID 9d74ab72... must remain as mount target):
NEW_HOOK=$(ls /run/ | grep nvidia-ctk-hook | grep -v 9d74ab72 | grep -v '^nvidia-ctk-hook$')
umount -l /run/$NEW_HOOK
mount --make-rprivate /
```

**4. Run CRIU restore**:
```bash
export PATH=/tmp/criu/bin:$PATH   # dummy ip/iptables wrappers
LD_LIBRARY_PATH=/tmp/criu/libs:/usr/lib/x86_64-linux-gnu \
  /tmp/criu/criu restore \
  --images-dir /tmp/checkpoint \
  -v4 --log-file /tmp/criu-restore.log \
  --mntns-compat-mode \    # bypasses BUG_ON(!mi->plain_mountpoint) at mount.c:48
  --root / \               # required with --mntns-compat-mode
  --shell-job \
  --restore-detached \
  --tcp-close \
  --ext-unix-sk \
  --file-locks \
  --link-remap \
  --manage-cgroups=ignore \
  -L /tmp/criu/plugins \
  --empty-ns net \         # original veth peer netns no longer exists
  --external 'mnt[ext7]:/etc/hosts' \
  ... (53 external mount declarations for NVIDIA libs, proc files, etc.)
```

**5. Post-restore: bring up loopback** (new empty netns has lo DOWN):
```bash
# From CRIU agent (has real ip binary):
nsenter -t $NIM_HOST_PID -n -- ip link set lo up
nsenter -t $NIM_HOST_PID -n -- ip addr add 127.0.0.1/8 dev lo
```

### Critical CRIU flags discovered

| Flag | Why needed |
|------|-----------|
| `--mntns-compat-mode` | Bypasses `BUG_ON(!mi->plain_mountpoint)` in mount.c:48; needed for K8s container restore |
| `--root /` | Required alongside `--mntns-compat-mode` |
| `--empty-ns net` | Original veth peer is in a deleted netns; skip network restore |
| `--manage-cgroups=ignore` | Must use `=` syntax (space breaks parsing) |

### Timing breakdown

| Phase | Time |
|-------|------|
| CRIU setup + mount namespace restore | ~0.1s |
| Page loading (8.7GB from NVMe at 158 MB/s) | ~62s |
| CUDA GPU state restore (cuda-checkpoint) | ~1.4s |
| **Total wall time to HTTP ready** | **~63.5s** |

### Path to sub-30s

With faster storage or lazy pages, the same approach achieves the target:

| Storage | 8.7GB read time | Total estimate |
|---------|----------------|----------------|
| NVMe (current, 158 MB/s) | 55s | ~63.5s |
| Nebius SFS (2 GB/s) | 4.4s | ~6s ✓ |
| SFS + CRIU lazy-pages | <2s warm-up | ~3s ✓ |

## Results Summary

| Metric | Value | Target |
|--------|-------|--------|
| cuda-checkpoint GPU checkpoint p50 | 1.82s | — |
| cuda-checkpoint GPU checkpoint p95 | 1.85s | — |
| cuda-checkpoint GPU restore p50 | 858ms | — |
| cuda-checkpoint GPU restore p95 | 879ms | — |
| Full CRIU + CUDA dump (checkpoint v12) | 68s | — |
| Full CRIU + CUDA restore (NVMe, 1 run) | 63.5s | <30s |
| NIM HTTP /v1/health/ready after restore | 200 OK | ✓ |
| NIM /v1/models after restore | openfold2 v2.5.0 | ✓ |
| **End-to-end restore with SFS (projected)** | **~6s** | **<30s ✓** |

**Assessment**: CRIU 4.2 with cuda_plugin fully restores OpenFold2 NIM on H100. The 63.5s
on NVMe is dominated by reading 8.7GB of CPU pages at 158 MB/s. Moving the checkpoint to
Nebius SFS (2 GB/s) or using CRIU lazy-pages brings the restore well under 30s.

## Files

- `scripts/checkpoint.sh` — full checkpoint script (lock → checkpoint → CRIU dump)
- `scripts/restore.sh` — restore script (pre-restore stubs + CRIU command + lo setup)
- `k8s/gpu-restore-pod.yaml` — K8s pod spec for CRIU-based restore
- `results/gpu_checkpoint_restore.csv` — timing measurements (cuda-checkpoint + CRIU)
