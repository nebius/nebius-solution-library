#!/usr/bin/env bash
# CRIU 4.2 + cuda_plugin restore for OpenFold2 NIM on H100.
# Run inside a privileged restore pod (hostPID=true, no volumeMounts).
# See snapshot/approach.md for the full method and timing breakdown.
#
# Usage: restore.sh <CHECKPOINT_DIR> <IMAGES_DIR>
#   CHECKPOINT_DIR: host path to criu42-v12 (e.g. /snapshots/openfold2/criu42-v12)
#   IMAGES_DIR:     pod-local path to metadata + hardlinked pages (e.g. /tmp/checkpoint)
#
# Prerequisites (done once when pod starts):
#   1. Copy CRIU binary + libs + cuda_plugin to /tmp/criu/
#   2. Hardlink all pages-*.img from CHECKPOINT_DIR into IMAGES_DIR via overlay upper dir
#   3. Place dummy ip/iptables wrappers in /tmp/criu/bin/ (CRIU calls them for net ns)
#   4. Create /home/user/.cache/nim (target for ext20 bind-mount)
set -euo pipefail

CHECKPOINT_DIR="${1:-/snapshots/openfold2/criu42-v12}"
IMAGES_DIR="${2:-/tmp/checkpoint}"
CRIU=/tmp/criu/criu
LOG_DIR=/tmp/criu-restore-logs
NIM_PID_FILE=/tmp/nim-restored-pid

mkdir -p "$LOG_DIR"
T0=$(date +%s%3N)

# ─── Step 1: stub JIT-compiled files that CRIU validates by size/mode ──────────
# These are MAP_PRIVATE mmap'd .so files compiled at NIM startup; content is
# restored from pages-*.img. CRIU only needs the file to exist with correct size.
stub() {
  local path="$1" size="$2" mode="${3:-0755}"
  mkdir -p "$(dirname "$path")"
  truncate -s "$size" "$path"
  chmod "$mode" "$path"
}

stub /root/.cache/tvm-ffi/libtorch_c_dlpack_addon_torch210-cuda.so 212272 0755

for HASH in \
  ZDI6JWI5Z4RZ7GIRUDJ6SDSQFQGVNM7LCGJC7WPVWLBVZ6QJPZFA \
  F3PT4AYMVUT4FC5Y26UMLMHMFXZCXY6TSOAWU5K2YPPQX7UHL4AA \
  SZYSIZWIUEESFDNVENTPAJJ7KVLKMBDUYREWMS3M3M4Z6MSV4WQA \
  BT6Y3UMOYWWZM5JW6N7ZDQPHHVVF53OTLI5S3M4TGZNUXEODVS7Q; do
  stub "/tmp/root/bionemo_kernel_cache/triton/$HASH/__triton_launcher.cpython-312-x86_64-linux-gnu.so" 21712
done
stub /tmp/root/bionemo_kernel_cache/triton/XU5DT2AO5BD5AEHEYGLPP5LRDFHHCUEJT4LGDVLB4STXUGVGHFPA/cuda_utils.cpython-312-x86_64-linux-gnu.so 31944

# ─── Step 2: unmount K8s-injected mounts not in checkpoint ───────────────────
# K8s injects a new CTK hook UUID and serviceaccount; CRIU fails on extra mounts.
umount -l /run/secrets/kubernetes.io/serviceaccount 2>/dev/null || true
NEW_HOOK=$(ls /run/ | grep nvidia-ctk-hook | grep -v 9d74ab72 | grep -v '^nvidia-ctk-hook$' || true)
[ -n "$NEW_HOOK" ] && umount -l "/run/$NEW_HOOK" 2>/dev/null || true
mount --make-rprivate /

# ─── Step 3: CRIU restore ────────────────────────────────────────────────────
LOG="$LOG_DIR/restore-$(date +%s).log"
export PATH=/tmp/criu/bin:$PATH

LD_LIBRARY_PATH=/tmp/criu/libs:/usr/lib/x86_64-linux-gnu \
  "$CRIU" restore \
    --images-dir "$IMAGES_DIR" \
    --log-file "$LOG" \
    -v4 \
    --mntns-compat-mode \
    --root / \
    --shell-job \
    --restore-detached \
    --tcp-close \
    --ext-unix-sk \
    --file-locks \
    --link-remap \
    --manage-cgroups=ignore \
    -L /tmp/criu/plugins \
    --empty-ns net \
    --external 'mnt[ext7]:/etc/hosts' \
    --external 'mnt[ext8]:/dev/termination-log' \
    --external 'mnt[ext9]:/etc/hostname' \
    --external 'mnt[ext10]:/etc/resolv.conf' \
    --external 'mnt[ext12]:/run/nvidia-persistenced/socket' \
    --external 'mnt[ext13]:/usr/bin/nvidia-cuda-mps-control' \
    --external 'mnt[ext14]:/usr/bin/nvidia-cuda-mps-server' \
    --external 'mnt[ext15]:/usr/bin/nvidia-debugdump' \
    --external 'mnt[ext16]:/usr/bin/nvidia-imex' \
    --external 'mnt[ext17]:/usr/bin/nvidia-imex-ctl' \
    --external 'mnt[ext18]:/usr/bin/nvidia-persistenced' \
    --external 'mnt[ext19]:/usr/bin/nvidia-smi' \
    --external 'mnt[ext20]:/home/user/.cache/nim' \
    --external 'mnt[ext21]:/usr/lib/x86_64-linux-gnu/libcuda.so.580.159.04' \
    --external 'mnt[ext22]:/usr/lib/x86_64-linux-gnu/libcudadebugger.so.580.159.04' \
    --external 'mnt[ext23]:/usr/lib/x86_64-linux-gnu/libnvcuvid.so.580.159.04' \
    --external 'mnt[ext24]:/usr/lib/x86_64-linux-gnu/libnvidia-cfg.so.580.159.04' \
    --external 'mnt[ext25]:/usr/lib/x86_64-linux-gnu/libnvidia-gpucomp.so.580.159.04' \
    --external 'mnt[ext26]:/usr/lib/x86_64-linux-gnu/libnvidia-ml.so.580.159.04' \
    --external 'mnt[ext27]:/usr/lib/x86_64-linux-gnu/libnvidia-nscq.so.580.159.04' \
    --external 'mnt[ext28]:/usr/lib/x86_64-linux-gnu/libnvidia-nvvm.so.580.159.04' \
    --external 'mnt[ext29]:/usr/lib/x86_64-linux-gnu/libnvidia-opencl.so.580.159.04' \
    --external 'mnt[ext30]:/usr/lib/x86_64-linux-gnu/libnvidia-opticalflow.so.580.159.04' \
    --external 'mnt[ext31]:/usr/lib/x86_64-linux-gnu/libnvidia-pkcs11-openssl3.so.580.159.04' \
    --external 'mnt[ext32]:/usr/lib/x86_64-linux-gnu/libnvidia-ptxjitcompiler.so.580.159.04' \
    --external 'mnt[ext33]:/usr/lib/x86_64-linux-gnu/libnvidia-sandboxutils.so.580.159.04' \
    --external 'mnt[ext35]:/usr/lib/firmware/nvidia/580.159.04/gsp_ga10x.bin' \
    --external 'mnt[ext36]:/usr/lib/firmware/nvidia/580.159.04/gsp_tu10x.bin' \
    --external 'mnt[ext37]:/usr/lib/x86_64-linux-gnu/vdpau/libvdpau_nvidia.so.580.159.04' \
    --external 'mnt[ext39]:/proc/driver/nvidia/params' \
    --external 'mnt[ext46]:/proc/interrupts' \
    --external 'mnt[ext47]:/proc/kcore' \
    --external 'mnt[ext48]:/proc/keys' \
    --external 'mnt[ext49]:/proc/latency_stats' \
    --external 'mnt[ext50]:/proc/timer_list'

T_CRIU=$(date +%s%3N)
echo "CRIU restore complete: $((T_CRIU - T0))ms"

# ─── Step 4: bring up loopback in restored network namespace ─────────────────
# --empty-ns net creates a new empty netns; lo starts DOWN.
NIM_PID=$(pgrep -f 'start_server' | head -1)
echo "$NIM_PID" > "$NIM_PID_FILE"

# ip binary must be on the host (not in /tmp/criu/bin which has a dummy wrapper)
HOST_IP=$(ls /proc/1/root/sbin/ip /proc/1/root/usr/sbin/ip /proc/1/root/usr/bin/ip 2>/dev/null | head -1)
if [ -n "$HOST_IP" ]; then
  nsenter -t "$NIM_PID" -n -- "$HOST_IP" link set lo up
  nsenter -t "$NIM_PID" -n -- "$HOST_IP" addr add 127.0.0.1/8 dev lo 2>/dev/null || true
else
  # Fallback: use CRIU agent's ip (run from host, not pod)
  echo "WARNING: host ip binary not found; lo may be DOWN. Run from CRIU agent:" >&2
  echo "  nsenter -t $NIM_PID -n -- ip link set lo up" >&2
fi

# ─── Step 5: wait for HTTP ready ─────────────────────────────────────────────
echo "Waiting for NIM HTTP ready..."
for i in $(seq 1 30); do
  result=$(nsenter -t "$NIM_PID" -n -- bash -c \
    'exec 3<>/dev/tcp/127.0.0.1/8000; echo -e "GET /v1/health/ready HTTP/1.0\r\nHost: localhost\r\n\r\n" >&3; timeout 5 cat <&3; exec 3>&-' 2>/dev/null || true)
  if echo "$result" | grep -q '"status":"ready"'; then
    T_READY=$(date +%s%3N)
    echo "NIM READY: $((T_READY - T0))ms total"
    echo "$result" | grep -o '"status":"[^"]*"'
    exit 0
  fi
  sleep 1
done

echo "ERROR: NIM not ready after 30s" >&2
exit 1
