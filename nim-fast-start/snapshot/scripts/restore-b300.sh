#!/usr/bin/env bash
# CRIU 4.2 + cuda_plugin restore for Evo2-40B NIM on Nebius B300 SXM.
# Run inside a privileged restore pod (hostPID=true, no volumeMounts for checkpoint).
# Adapted from Phase 5 (H100/OpenFold2) — see snapshot/approach.md for full method.
#
# Usage: restore-b300.sh [CHECKPOINT_DIR [IMAGES_DIR]]
#   CHECKPOINT_DIR: host path to criu42-v{N}   (default: auto-discover latest under
#                   /snapshots/evo2-40b/criu42-v*)
#   IMAGES_DIR:     pod-local path for hardlinked pages (default: /tmp/checkpoint-b300)
#
# Phase 6 B300 differences vs Phase 5 H100:
#   CRIU binary    : /snapshots/criu-420-bin              (not /opt/criu/criu-patched)
#   cuda-checkpoint: /snapshots/cuda-checkpoint           (also /usr/local/bin/cuda-checkpoint)
#   libcuda isolate: /snapshots/cuda-libs/libcuda.so.1 → /tmp/cuda-libs/ before use
#   checkpoint root: /snapshots/evo2-40b/criu42-v{N}/
#   InfiniBand     : uverbs0 ext-fd restore via /tmp/criu_ext_fds.dat + --inherit-fd
#   post-CRIU      : cuda-checkpoint --action restore then --action unlock on Python PID
#   kubeconfig     : ~/.kube/archvteams-2407-evo2.yaml, ns nim-fast-start
#   node           : computeinstance-e03pmj01714zrdry1p
#
# Prerequisites (done once when restore pod starts):
#   1. /snapshots/ hostPath mounted in pod spec (read access to CRIU binary + checkpoint)
#   2. /dev/infiniband/uverbs0 accessible (privileged pod or hostPath device)
#   3. /tmp/criu_ext_fds.dat populated from checkpoint fdinfo.img inspection (see Step 4)
#   4. Restore pod spec: hostPID=true, privileged, NO volumeMounts for IMAGES_DIR
#      (so IMAGES_DIR lives on the pod's own overlay upper dir, hardlinks work)
set -euo pipefail

# ─── Args + globals ──────────────────────────────────────────────────────────
if [ -n "${1:-}" ]; then
  CHECKPOINT_DIR="$1"
else
  CHECKPOINT_DIR=$(ls -d /snapshots/evo2-40b/criu42-v* 2>/dev/null \
    | sort -t v -k2 -n | tail -1 || true)
  if [ -z "$CHECKPOINT_DIR" ]; then
    echo "ERROR: no checkpoint found at /snapshots/evo2-40b/criu42-v*/" \
         "— pass CHECKPOINT_DIR as first argument" >&2
    exit 1
  fi
fi

IMAGES_DIR="${2:-/tmp/checkpoint-b300}"
CRIU=/tmp/criu/criu
LOG_DIR=/tmp/criu-restore-logs
NIM_PID_FILE=/tmp/nim-b300-restored-pid
EXT_FDS_DAT="${CRIU_EXT_FDS_DAT:-/tmp/criu_ext_fds.dat}"

mkdir -p "$LOG_DIR" "$IMAGES_DIR"

# Wall-clock T0 — everything is measured from here, including staging.
T0=$(date +%s%3N)
echo "=== restore-b300.sh start $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "CHECKPOINT_DIR : $CHECKPOINT_DIR"
echo "IMAGES_DIR     : $IMAGES_DIR"

# ─── Step 0: stage CRIU binary, libs, plugins, dummy net wrappers ────────────
# /snapshots/criu-420-bin is the CRIU 4.2 binary with io_uring patches
# (same patches as Phase 5 — kernel 6.11 cannot sendmsg io_uring FDs via SCM_RIGHTS).
mkdir -p /tmp/criu/bin /tmp/criu/libs /tmp/criu/plugins

if [ ! -f "$CRIU" ]; then
  cp /snapshots/criu-420-bin "$CRIU"
  chmod +x "$CRIU"
fi

cp /snapshots/criu-plugins/cuda_plugin.so /tmp/criu/plugins/

# Dummy ip / iptables wrappers — CRIU calls these during --empty-ns net restore;
# they must exist and exit 0 (real loopback is raised via nsenter in Step 7).
for _w in ip iptables ip6tables iptables-restore ip6tables-restore; do
  cat > "/tmp/criu/bin/$_w" <<'WRAPPER'
#!/bin/sh
exit 0
WRAPPER
  chmod +x "/tmp/criu/bin/$_w"
done

T_STAGE=$(date +%s%3N)
echo "[+${T_STAGE}ms] CRIU staged to /tmp/criu/"

# ─── Step 1: isolate libcuda to /tmp/cuda-libs/ ──────────────────────────────
# B300 uses a driver-matched libcuda shipped in /snapshots/cuda-libs/ to avoid
# ABI conflicts with anything in /usr/lib. Copy before any cuda-checkpoint call.
mkdir -p /tmp/cuda-libs
if [ ! -f /tmp/cuda-libs/libcuda.so.1 ]; then
  cp /snapshots/cuda-libs/libcuda.so.1 /tmp/cuda-libs/
  # Also copy the full versioned .so if present alongside the symlink target
  for _vso in /snapshots/cuda-libs/libcuda.so.*; do
    [[ "$_vso" == */libcuda.so.1 ]] && continue
    [[ -f "$_vso" ]] && cp "$_vso" /tmp/cuda-libs/ && break
  done
fi

# Resolve cuda-checkpoint binary: prefer /snapshots/ version, fall back to installed.
CUDA_CKPT=/snapshots/cuda-checkpoint
if [ ! -x "$CUDA_CKPT" ]; then
  CUDA_CKPT=/usr/local/bin/cuda-checkpoint
fi
if [ ! -x "$CUDA_CKPT" ]; then
  echo "ERROR: cuda-checkpoint not found at /snapshots/cuda-checkpoint" \
       "or /usr/local/bin/cuda-checkpoint" >&2
  exit 1
fi

T_LIBS=$(date +%s%3N)
echo "[+$((T_LIBS - T0))ms] libcuda isolated, cuda-checkpoint=$CUDA_CKPT"

# ─── Step 2: hardlink pages-*.img from CHECKPOINT_DIR into IMAGES_DIR ────────
# Hardlinks survive mount-namespace remapping during CRIU restore; symlinks do not.
# Phase 5 approach: link into the pod's overlay upper dir so they appear at
# IMAGES_DIR inside the pod without a separate bind-mount.
OVERLAY_UPPER=$(awk '$2=="/" && $3=="overlay" {
  match($4,/upperdir=([^,]+)/,a); if (a[1]) {print a[1]; exit}
}' /proc/mounts)

if [ -n "$OVERLAY_UPPER" ]; then
  UPPER_IMAGES="${OVERLAY_UPPER}/${IMAGES_DIR#/}"
  mkdir -p "$UPPER_IMAGES"
  N_LINKED=0
  for _img in "$CHECKPOINT_DIR"/*.img; do
    _base=$(basename "$_img")
    _target="${UPPER_IMAGES}/${_base}"
    [ -e "$_target" ] || ln "$_img" "$_target"
    N_LINKED=$(( N_LINKED + 1 ))
  done
  echo "Hardlinked $N_LINKED images: $CHECKPOINT_DIR → $UPPER_IMAGES"
  # Drop overlayfs page cache so the new hardlinks are visible inside the pod.
  echo 3 > /proc/sys/vm/drop_caches
else
  # Fallback: plain copy (slower; happens if storage driver is not overlay).
  echo "WARNING: overlay upper dir not found in /proc/mounts; copying images" >&2
  cp "$CHECKPOINT_DIR"/*.img "$IMAGES_DIR/"
fi

T_PAGES=$(date +%s%3N)
echo "[+$((T_PAGES - T0))ms] Pages staged to $IMAGES_DIR"

# ─── Step 3: create stubs for JIT-compiled files ─────────────────────────────
# Evo2-40B NIM JIT-compiles triton kernels and tvm-ffi libraries at startup;
# CRIU records them in regfiles.img by path, size, and mode. The files must
# exist at restore time (content is restored from pages-*.img; only size+mode
# are validated by the parasite).
#
# TODO (after first checkpoint): run the following to discover Evo2-40B stubs:
#   python3 -c "
#   import pycriu, glob
#   for fn in glob.glob('$CHECKPOINT_DIR/regfiles*.img'):
#     with open(fn,'rb') as f:
#       for e in pycriu.images.load(f).get('entries',[]):
#         n = e.get('name','')
#         if any(x in n for x in ('triton','tvm','bionemo','evo2','kernel_cache')):
#           print(e.get('size',0), oct(e.get('mode',0o755)), n)
#   "
# Then populate the stub() calls below with the discovered paths and sizes.
stub() {
  local path="$1" size="$2" mode="${3:-0755}"
  mkdir -p "$(dirname "$path")"
  truncate -s "$size" "$path"
  chmod "$mode" "$path"
}

# ── Evo2-40B JIT stubs — POPULATE AFTER CHECKPOINT ──────────────────────────
# Pattern mirrors Phase 5 (OpenFold2): likely under /tmp/root/bionemo_kernel_cache/triton/
# and /root/.cache/tvm-ffi/. Leave empty until first checkpoint is taken.
# Example (do NOT use OpenFold2 hashes — those kernels differ):
#
# stub /root/.cache/tvm-ffi/<evo2-tvm-lib>.so PLACEHOLDER_SIZE 0755
# for _h in HASH_A HASH_B HASH_C; do
#   stub "/tmp/root/bionemo_kernel_cache/triton/$_h/__triton_launcher.cpython-312-x86_64-linux-gnu.so" PLACEHOLDER_SIZE
# done

# ─── Step 4: pre-open InfiniBand devices for ext-fd inheritance ───────────────
# B300 SXM nodes expose IB (uverbs0) for NCCL NVLink fabric and GPU interconnect.
# CRIU cannot dump IB character device FDs; the restore process must pre-open them
# and hand the FD numbers to CRIU via --inherit-fd.
#
# /tmp/criu_ext_fds.dat format (one line per IB FD, comments with #):
#   <checkpoint_fd_num>  <host_device_path>
#   e.g.:
#   12   /dev/infiniband/uverbs0
#   15   /dev/infiniband/rdma_cm
#
# TODO (after checkpoint): identify IB FD numbers from fdinfo-*.img:
#   python3 -c "
#   import pycriu, glob
#   for fn in glob.glob('$CHECKPOINT_DIR/fdinfo*.img'):
#     with open(fn,'rb') as f:
#       for e in pycriu.images.load(f).get('entries',[]):
#         for fde in e.get('files',[]):
#           if fde.get('type') in ('EXT_FILE','CHR'):
#             n = fde.get('name','?')
#             if 'infiniband' in n or 'uverbs' in n or 'rdma' in n:
#               print(fde['id'], n)
#   "
# Populate /tmp/criu_ext_fds.dat with those fd numbers and device paths.

INHERIT_FD_ARGS=()
if [ -f "$EXT_FDS_DAT" ]; then
  echo "Loading IB ext-fd mappings from $EXT_FDS_DAT ..."
  while IFS=$' \t' read -r _ckpt_fd _dev_path || [ -n "${_ckpt_fd:-}" ]; do
    [[ -z "${_ckpt_fd:-}" || "${_ckpt_fd:-}" == \#* ]] && continue
    if [ -c "$_dev_path" ]; then
      exec {_IB_FD}<"$_dev_path"
      INHERIT_FD_ARGS+=(--inherit-fd "fd[${_ckpt_fd}]:${_IB_FD}")
      echo "  IB inherit-fd: fd[$_ckpt_fd] → $_dev_path (opened as fd=$_IB_FD)"
    else
      echo "WARNING: IB device '$_dev_path' not found or not char dev" \
           "(fd[$_ckpt_fd]); restore may fail" >&2
    fi
  done < "$EXT_FDS_DAT"
else
  echo "NOTE: $EXT_FDS_DAT absent — no IB FDs inherited." \
       "If checkpoint has IB FDs (uverbs0), CRIU restore will fail." >&2
fi

T_IB=$(date +%s%3N)
echo "[+$((T_IB - T0))ms] IB ext-fd setup (${#INHERIT_FD_ARGS[@]} args)"

# ─── Step 5: unmount K8s-injected mounts not present in checkpoint ────────────
# K8s injects a new nvidia-ctk-hook UUID and serviceaccount on each pod start;
# CRIU fails on extra mounts inside the restore namespace (BUG_ON in mount.c).
umount -l /run/secrets/kubernetes.io/serviceaccount 2>/dev/null || true

# Unmount only the NEW CTK hook UUID. The original UUID from checkpoint time
# must remain as a mount target for --mntns-compat-mode to map correctly.
# TODO (after checkpoint): replace grep pattern with the UUID captured at dump
#   time (visible in the CRIU agent dump log or /proc/$PID/mountinfo at checkpoint).
NEW_HOOK=$(ls /run/ 2>/dev/null \
  | grep nvidia-ctk-hook \
  | grep -v '^nvidia-ctk-hook$' \
  | head -1 || true)
[ -n "$NEW_HOOK" ] && umount -l "/run/$NEW_HOOK" 2>/dev/null || true
mount --make-rprivate /

# ─── Step 6: CRIU restore ────────────────────────────────────────────────────
LOG="$LOG_DIR/restore-b300-$(date +%s).log"
export PATH=/tmp/criu/bin:$PATH

# Discover host NVIDIA driver version from /proc (B300 driver version is not 580.159.04).
# The ext-mnt paths below must exactly match the libcuda bind-mounts recorded in the
# checkpoint's mntns.img — if the driver string differs, pass NVIDIA_DRV=<version> in env.
NVIDIA_DRV="${NVIDIA_DRV:-$(grep -oP 'Kernel Module\s+\K[0-9]+\.[0-9]+\.[0-9]+' \
  /proc/driver/nvidia/version 2>/dev/null | head -1 || echo UNKNOWN)}"
echo "Host NVIDIA driver: $NVIDIA_DRV"

# Build CRIU restore command as an array (preserves quoting through ${CRIU_CMD[@]}).
CRIU_CMD=("$CRIU" restore)

# Core restore flags (same as Phase 5 H100)
CRIU_CMD+=(
  --images-dir "$IMAGES_DIR"
  --log-file   "$LOG"
  -v4
  --mntns-compat-mode
  --root /
  --shell-job
  --restore-detached
  --tcp-close
  --ext-unix-sk
  --file-locks
  --link-remap
  --manage-cgroups=ignore
  -L /tmp/criu/plugins
  --empty-ns net
)

# K8s infrastructure ext-mounts (same pattern as Phase 5; ext keys may differ —
# verify against mntns.img after checkpoint).
# TODO: confirm ext{N} keys from B300 checkpoint mntns.img.
CRIU_CMD+=(
  --external 'mnt[ext7]:/etc/hosts'
  --external 'mnt[ext8]:/dev/termination-log'
  --external 'mnt[ext9]:/etc/hostname'
  --external 'mnt[ext10]:/etc/resolv.conf'
)

# NVIDIA runtime ext-mounts (persistenced socket + CTK binaries)
CRIU_CMD+=(
  --external 'mnt[ext12]:/run/nvidia-persistenced/socket'
  --external 'mnt[ext13]:/usr/bin/nvidia-cuda-mps-control'
  --external 'mnt[ext14]:/usr/bin/nvidia-cuda-mps-server'
  --external 'mnt[ext15]:/usr/bin/nvidia-debugdump'
  --external 'mnt[ext16]:/usr/bin/nvidia-imex'
  --external 'mnt[ext17]:/usr/bin/nvidia-imex-ctl'
  --external 'mnt[ext18]:/usr/bin/nvidia-persistenced'
  --external 'mnt[ext19]:/usr/bin/nvidia-smi'
)

# NIM model cache ext-mount
CRIU_CMD+=(
  --external 'mnt[ext20]:/home/user/.cache/nim'
)

# NVIDIA shared libraries — versioned by driver.
# B300 driver version differs from H100's 580.159.04; $NVIDIA_DRV is auto-detected above.
# TODO: cross-check these paths and ext keys against mntns.img from the B300 checkpoint.
CRIU_CMD+=(
  --external "mnt[ext21]:/usr/lib/x86_64-linux-gnu/libcuda.so.${NVIDIA_DRV}"
  --external "mnt[ext22]:/usr/lib/x86_64-linux-gnu/libcudadebugger.so.${NVIDIA_DRV}"
  --external "mnt[ext23]:/usr/lib/x86_64-linux-gnu/libnvcuvid.so.${NVIDIA_DRV}"
  --external "mnt[ext24]:/usr/lib/x86_64-linux-gnu/libnvidia-cfg.so.${NVIDIA_DRV}"
  --external "mnt[ext25]:/usr/lib/x86_64-linux-gnu/libnvidia-gpucomp.so.${NVIDIA_DRV}"
  --external "mnt[ext26]:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.${NVIDIA_DRV}"
  --external "mnt[ext27]:/usr/lib/x86_64-linux-gnu/libnvidia-nscq.so.${NVIDIA_DRV}"
  --external "mnt[ext28]:/usr/lib/x86_64-linux-gnu/libnvidia-nvvm.so.${NVIDIA_DRV}"
  --external "mnt[ext29]:/usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.${NVIDIA_DRV}"
  --external "mnt[ext30]:/usr/lib/x86_64-linux-gnu/libnvidia-opticalflow.so.${NVIDIA_DRV}"
  --external "mnt[ext31]:/usr/lib/x86_64-linux-gnu/libnvidia-pkcs11-openssl3.so.${NVIDIA_DRV}"
  --external "mnt[ext32]:/usr/lib/x86_64-linux-gnu/libnvidia-ptxjitcompiler.so.${NVIDIA_DRV}"
  --external "mnt[ext33]:/usr/lib/x86_64-linux-gnu/libnvidia-sandboxutils.so.${NVIDIA_DRV}"
)

# Firmware ext-mounts — B300 (Blackwell) uses gb20x.bin, not ga10x/tu10x (H100/A100).
# TODO: verify blob filename(s) from the B300 checkpoint's mntns.img; there may be
#   additional blobs (e.g. gsp_gb10x.bin) depending on the specific B300 SKU.
CRIU_CMD+=(
  --external "mnt[ext35]:/usr/lib/firmware/nvidia/${NVIDIA_DRV}/gsp_gb20x.bin"
  --external "mnt[ext37]:/usr/lib/x86_64-linux-gnu/vdpau/libvdpau_nvidia.so.${NVIDIA_DRV}"
)

# /proc bind-mounts (same as Phase 5)
CRIU_CMD+=(
  --external 'mnt[ext39]:/proc/driver/nvidia/params'
  --external 'mnt[ext46]:/proc/interrupts'
  --external 'mnt[ext47]:/proc/kcore'
  --external 'mnt[ext48]:/proc/keys'
  --external 'mnt[ext49]:/proc/latency_stats'
  --external 'mnt[ext50]:/proc/timer_list'
)

# InfiniBand ext-mounts (B300-specific) — the IB character device bind-mounts
# that were inside the NIM container at checkpoint time. Ext keys are assigned by
# CRIU during dump; read from mntns.img after checkpoint.
# TODO: add entries of the form:
#   --external 'mnt[ext<N>]:/dev/infiniband/uverbs0'
#   --external 'mnt[ext<N+1>]:/dev/infiniband/rdma_cm'
# after inspecting mntns.img from the B300 checkpoint.

# Append IB --inherit-fd args built in Step 4 (empty array if no dat file found).
if [ "${#INHERIT_FD_ARGS[@]}" -gt 0 ]; then
  CRIU_CMD+=("${INHERIT_FD_ARGS[@]}")
fi

LD_LIBRARY_PATH=/tmp/cuda-libs:/tmp/criu/libs:/usr/lib/x86_64-linux-gnu \
  "${CRIU_CMD[@]}"

T_CRIU=$(date +%s%3N)
echo "[+$((T_CRIU - T0))ms] CRIU restore exit=0"

# ─── Step 7: bring up loopback in restored network namespace ─────────────────
# --empty-ns net creates a new empty netns; lo starts DOWN.
# Evo2-40B NIM process name: try common NIM server patterns.
NIM_PID=$(pgrep -f 'start_server' 2>/dev/null | head -1 \
  || pgrep -f 'nim_server\|triton_server\|uvicorn.*nim\|python.*evo2' 2>/dev/null | head -1 \
  || true)
if [ -z "$NIM_PID" ]; then
  # Last resort: first Python process not in our own cgroup.
  NIM_PID=$(pgrep -f 'python' 2>/dev/null \
    | grep -v "^$$\$" | head -1 || true)
fi
[ -z "$NIM_PID" ] && { echo "ERROR: could not locate restored NIM PID" >&2; exit 1; }
echo "$NIM_PID" > "$NIM_PID_FILE"
echo "Restored NIM PID: $NIM_PID"

HOST_IP=$(ls /proc/1/root/sbin/ip \
             /proc/1/root/usr/sbin/ip \
             /proc/1/root/usr/bin/ip 2>/dev/null | head -1 || true)
if [ -n "$HOST_IP" ]; then
  nsenter -t "$NIM_PID" -n -- "$HOST_IP" link set lo up
  nsenter -t "$NIM_PID" -n -- "$HOST_IP" addr add 127.0.0.1/8 dev lo 2>/dev/null || true
  echo "lo UP in NIM netns"
else
  echo "WARNING: host ip binary not found; lo may be DOWN. From CRIU agent run:" >&2
  echo "  KUBECONFIG=~/.kube/archvteams-2407-evo2.yaml" >&2
  echo "  nsenter -t $NIM_PID -n -- ip link set lo up" >&2
fi

T_LO=$(date +%s%3N)
echo "[+$((T_LO - T0))ms] lo up"

# ─── Step 8: restore + unlock CUDA context on Evo2-40B Python PID ────────────
# B300 difference vs Phase 5: cuda-checkpoint is called from within this restore
# script (not from the pod initContainer). The Python process holding the GPU
# context was frozen by cuda-checkpoint --action lock + checkpoint at dump time.
# Sequence: restore (copies GPU memory from host RAM back to VRAM) → unlock
# (resumes GPU execution and releases the freeze).
#
# The GPU-holding process is the Evo2 inference Python PID, which may be a child
# of NIM_PID (if NIM_PID is a shell or supervisor). Try child first, else use NIM_PID.
PYTHON_PID=$(pgrep -P "$NIM_PID" -f python 2>/dev/null | head -1 \
  || pgrep -f 'python.*evo2\|python.*nim\|python.*server' 2>/dev/null \
       | grep -v "^$$\$" | head -1 \
  || echo "$NIM_PID")
echo "CUDA restore on Python PID: $PYTHON_PID"

LD_LIBRARY_PATH=/tmp/cuda-libs:/usr/lib/x86_64-linux-gnu \
  "$CUDA_CKPT" --action restore --pid "$PYTHON_PID"
T_CUDA_RESTORE=$(date +%s%3N)
echo "[+$((T_CUDA_RESTORE - T0))ms] cuda-checkpoint restore done"

LD_LIBRARY_PATH=/tmp/cuda-libs:/usr/lib/x86_64-linux-gnu \
  "$CUDA_CKPT" --action unlock --pid "$PYTHON_PID"
T_CUDA_UNLOCK=$(date +%s%3N)
echo "[+$((T_CUDA_UNLOCK - T0))ms] cuda-checkpoint unlock done"

# ─── Step 9: wait for HTTP /v1/health/ready → 200 ────────────────────────────
# Evo2-40B is larger than OpenFold2; allow 120s for post-restore warm-up.
# (Phase 5 H100 used 30s; Evo2-40B model head init may take longer.)
echo "Waiting for Evo2-40B NIM HTTP ready (port 8000, up to 120s)..."
for _i in $(seq 1 120); do
  _result=$(nsenter -t "$NIM_PID" -n -- bash -c \
    'exec 3<>/dev/tcp/127.0.0.1/8000
     printf "GET /v1/health/ready HTTP/1.0\r\nHost: localhost\r\n\r\n" >&3
     timeout 5 cat <&3
     exec 3>&-' 2>/dev/null || true)
  if echo "$_result" | grep -qE '"status":"ready"|HTTP/1\.[01] 200'; then
    T_READY=$(date +%s%3N)
    TOTAL_MS=$(( T_READY - T0 ))
    echo ""
    echo "=== NIM READY: ${TOTAL_MS}ms wall time to HTTP 200 ==="
    echo "Timing breakdown (ms from T0):"
    printf "  %-30s %dms\n" "CRIU binary staged"         "$((T_STAGE        - T0))"
    printf "  %-30s %dms\n" "libcuda isolated"           "$((T_LIBS         - T0))"
    printf "  %-30s %dms\n" "pages hardlinked"           "$((T_PAGES        - T0))"
    printf "  %-30s %dms\n" "IB ext-fd setup"            "$((T_IB           - T0))"
    printf "  %-30s %dms\n" "CRIU restore exit=0"        "$((T_CRIU         - T0))"
    printf "  %-30s %dms\n" "lo up"                      "$((T_LO           - T0))"
    printf "  %-30s %dms\n" "cuda-checkpoint restore"    "$((T_CUDA_RESTORE - T0))"
    printf "  %-30s %dms\n" "cuda-checkpoint unlock"     "$((T_CUDA_UNLOCK  - T0))"
    printf "  %-30s %dms  <<<\n" "HTTP 200 (total wall)"   "$TOTAL_MS"
    echo "NIM PID=$NIM_PID  Python PID=$PYTHON_PID"
    echo "$_result" | grep -oE '"status":"[^"]*"|HTTP[^ ]*' || true
    exit 0
  fi
  sleep 1
done

echo "ERROR: Evo2-40B NIM not ready after 120s" >&2
echo "CRIU log: $LOG" >&2
echo "NIM PID: $NIM_PID  Python PID: $PYTHON_PID" >&2
echo "Check: nsenter -t $NIM_PID -n -- curl -sf http://127.0.0.1:8000/v1/health/ready" >&2
exit 1
