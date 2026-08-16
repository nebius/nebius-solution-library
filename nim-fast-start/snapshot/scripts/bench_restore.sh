#!/usr/bin/env bash
# bench_restore.sh — run N timed CRIU restores of OpenFold2 NIM on H100.
# Must run inside a privileged pod (hostPID=true, /snapshots mounted, GPU resource).
#
# Usage: bench_restore.sh [N_RUNS]
#   N_RUNS: number of restore runs (default 5)
#
# Output: TSV lines + summary CSV at /tmp/bench_results.csv
set -uo pipefail

N_RUNS="${1:-5}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/snapshots/openfold2/criu42-v12}"
WORK_DIR="/tmp/bench_criu"
LOG_DIR="/tmp/bench_logs"
RESULTS_CSV="${RESULTS_CSV:-/tmp/bench_results.csv}"
VERBOSE_LOG="${VERBOSE_LOG:-/tmp/bench_verbose.log}"

mkdir -p "$WORK_DIR" "$LOG_DIR"

# ─── One-time setup ──────────────────────────────────────────────────────────
setup_once() {
  echo "[setup] Preparing CRIU tools..."

  # TOOLS_SRC: where criu-420-bin / criu-libs / criu-plugins live.
  # /snapshots (hostPath) on the original H100 node; /sfs/criu-tools on
  # SFS-attached scale-out nodes.
  local TOOLS_SRC="${TOOLS_SRC:-/snapshots}"
  mkdir -p "$WORK_DIR/criu/bin" "$WORK_DIR/criu/libs" "$WORK_DIR/criu/plugins"
  cp "$TOOLS_SRC/criu-420-bin" "$WORK_DIR/criu/criu"
  chmod 755 "$WORK_DIR/criu/criu"
  cp "$TOOLS_SRC"/criu-libs/* "$WORK_DIR/criu/libs/"
  cp "$TOOLS_SRC/criu-plugins/cuda_plugin.so" "$WORK_DIR/criu/plugins/"
  # cuda-checkpoint MUST be on PATH: cuda_plugin exec()s it during restore to
  # repopulate GPU state. Without it CRIU logs a warning, HTTP health still
  # returns ready, but the GPU is empty — health is a necessary-not-sufficient
  # gate (found by Phase 7 adversarial validation).
  cp "$TOOLS_SRC/cuda-checkpoint" "$WORK_DIR/criu/bin/cuda-checkpoint" 2>/dev/null \
    || cp /snapshots/cuda-checkpoint "$WORK_DIR/criu/bin/cuda-checkpoint"
  chmod 755 "$WORK_DIR/criu/bin/cuda-checkpoint"

  for cmd in ip iptables-restore ip6tables-restore; do
    printf '#!/bin/sh\nexit 0\n' > "$WORK_DIR/criu/bin/$cmd"
    chmod 755 "$WORK_DIR/criu/bin/$cmd"
  done

  # Paths needed for --external bind mounts
  mkdir -p /home/user/.cache/nim
  # Old CTK hook UUID from checkpoint; bench pod has a newer UUID, create the old dir
  mkdir -p /run/nvidia-ctk-hook9d74ab72-3599-4b34-9bd8-9936587a6575

  # JIT-compiled files: prefer REAL artifacts harvested from the donor at dump
  # time (JIT_TAR). Zero-truncated stubs satisfy CRIU's mount/file checks but
  # SEGFAULT at first kernel launch — CRIU restores only dirty pages; clean
  # executable pages are faulted back in from these files.
  if [ -n "${JIT_TAR:-}" ] && [ -f "$JIT_TAR" ]; then
    echo "[setup] Installing real JIT artifacts from $JIT_TAR"
    tar xf "$JIT_TAR" -C /
    return 0
  fi
  echo "[setup] WARNING: no JIT_TAR — using zero stubs; restore will NOT survive inference"
  mkdir -p /root/.cache/tvm-ffi
  truncate -s 212272 /root/.cache/tvm-ffi/libtorch_c_dlpack_addon_torch210-cuda.so
  chmod 0755 /root/.cache/tvm-ffi/libtorch_c_dlpack_addon_torch210-cuda.so

  for HASH in \
    ZDI6JWI5Z4RZ7GIRUDJ6SDSQFQGVNM7LCGJC7WPVWLBVZ6QJPZFA \
    F3PT4AYMVUT4FC5Y26UMLMHMFXZCXY6TSOAWU5K2YPPQX7UHL4AA \
    SZYSIZWIUEESFDNVENTPAJJ7KVLKMBDUYREWMS3M3M4Z6MSV4WQA \
    BT6Y3UMOYWWZM5JW6N7ZDQPHHVVF53OTLI5S3M4TGZNUXEODVS7Q; do
    mkdir -p "/tmp/root/bionemo_kernel_cache/triton/$HASH"
    truncate -s 21712 "/tmp/root/bionemo_kernel_cache/triton/$HASH/__triton_launcher.cpython-312-x86_64-linux-gnu.so"
  done
  HASH=XU5DT2AO5BD5AEHEYGLPP5LRDFHHCUEJT4LGDVLB4STXUGVGHFPA
  mkdir -p "/tmp/root/bionemo_kernel_cache/triton/$HASH"
  truncate -s 31944 "/tmp/root/bionemo_kernel_cache/triton/$HASH/cuda_utils.cpython-312-x86_64-linux-gnu.so"

  echo "[setup] Done."
}

# ─── Unmount K8s-injected mounts ─────────────────────────────────────────────
unmount_extra() {
  umount -l /run/secrets/kubernetes.io/serviceaccount 2>/dev/null || true
  NEW_HOOK=$(ls /run/ 2>/dev/null | grep nvidia-ctk-hook | grep -v 9d74ab72 | grep -v '^nvidia-ctk-hook$' || true)
  [ -n "$NEW_HOOK" ] && umount -l "/run/$NEW_HOOK" 2>/dev/null || true
  mount --make-rprivate /
  # NOTE: /snapshots NOT unmounted — CRIU reads pages from it
}

# ─── Between-run cleanup ─────────────────────────────────────────────────────
cleanup_nim() {
  local pids
  pids=$(pgrep -f 'start_server' 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "[cleanup] Killing NIM PIDs: $pids"
    kill -9 $pids 2>/dev/null || true
    sleep 2
  fi
  sync
  echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
}

# ─── Fix loopback + IP in a PID's network namespace using Python ioctl ────────
setup_netns() {
  local pid="$1"
  nsenter -t "$pid" -n -- python3 - <<'PYEOF'
import socket, struct, fcntl

# Bring lo UP via SIOCSIFFLAGS
SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 1
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ifreq = struct.pack("16sh", b"lo", 0)
flags_raw = fcntl.ioctl(s, SIOCGIFFLAGS, ifreq)
flags = struct.unpack("16sh", flags_raw)[1] | IFF_UP
fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sh", b"lo", flags))
s.close()

# Add 127.0.0.1/8 via RTM_NEWADDR netlink
RTM_NEWADDR = 20
NLM_F_REQUEST, NLM_F_CREATE, NLM_F_EXCL = 0x1, 0x400, 0x200
NLMSG_HDRLEN = 16
IFA_LOCAL = 2
IFA_ADDRESS = 1

def nlattr(t, data):
    pad = (len(data) + 3) & ~3
    return struct.pack("HH", 4+len(data), t) + data + b"\x00"*(pad-len(data))

ifaddrmsg = struct.pack("BBBBI", socket.AF_INET, 8, 0, 0, 1)
attrs = nlattr(IFA_LOCAL, socket.inet_aton("127.0.0.1")) + nlattr(IFA_ADDRESS, socket.inet_aton("127.0.0.1"))
payload = ifaddrmsg + attrs
hdr = struct.pack("IHHII", NLMSG_HDRLEN+len(payload), RTM_NEWADDR, NLM_F_REQUEST|NLM_F_CREATE|NLM_F_EXCL, 0, 0)
nl = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0)
nl.bind((0, 0))
nl.send(hdr + payload)
nl.recv(4096)
nl.close()
print("lo up + 127.0.0.1/8 configured")
PYEOF
}

# ─── Single timed restore run ─────────────────────────────────────────────────
run_restore() {
  local run_num="$1"
  local log="$LOG_DIR/restore-run${run_num}.log"

  cleanup_nim

  local T0 T_CRIU T_SETUP T_READY
  T0=$(date +%s%3N)

  # Optional parallel page-cache prefetch (PREFETCH=1): overlap storage reads
  # with CRIU's restore work. CRIU reads pages single-threaded, which caps a
  # single stream well below network-disk bandwidth limits; 4 parallel readers
  # per large pages file warm the page cache at full disk throughput while
  # CRIU proceeds. Deliberately not waited on — started inside the timed window.
  if [ -n "${PREFETCH:-}" ]; then
    for f in "$CHECKPOINT_DIR"/pages-*.img; do
      local SZ Q
      SZ=$(stat -c%s "$f")
      if [ "$SZ" -gt $((64*1024*1024)) ]; then
        Q=$((SZ/4))
        for p in 0 1 2 3; do
          dd if="$f" of=/dev/null bs=8M iflag=skip_bytes,count_bytes skip=$((p*Q)) count=$Q 2>/dev/null &
        done
      else
        cat "$f" > /dev/null &
      fi
    done
  fi

  export PATH="$WORK_DIR/criu/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

  # External mount list: per-checkpoint (mount ids are donor-pod-specific).
  # EXTERNALS_FILE: one "--external mnt[extN]:/path" pair per line, generated
  # from the checkpoint's mountpoints image. Falls back to the v12 list below.
  local EXT_ARGS=()
  if [ -n "${EXTERNALS_FILE:-}" ] && [ -f "$EXTERNALS_FILE" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] && EXT_ARGS+=(--external "$line")
    done < "$EXTERNALS_FILE"
    echo "[run $run_num] using ${#EXT_ARGS[@]} externals from $EXTERNALS_FILE"
    LD_LIBRARY_PATH="$WORK_DIR/criu/libs:/usr/lib/x86_64-linux-gnu" \
      "$WORK_DIR/criu/criu" restore \
        --images-dir "$CHECKPOINT_DIR" \
        --log-file "$log" \
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
        -L "$WORK_DIR/criu/plugins" \
        --empty-ns net \
        "${EXT_ARGS[@]}"
    local CRIU_EXIT=$?
    T_CRIU=$(date +%s%3N)
    local CRIU_MS=$(( T_CRIU - T0 ))
    if [ $CRIU_EXIT -ne 0 ]; then
      echo "[run $run_num] CRIU FAILED (exit=$CRIU_EXIT) after ${CRIU_MS}ms"
      tail -5 "$log" 2>/dev/null
      echo "$run_num	$CRIU_MS	-1	FAILED_CRIU_$CRIU_EXIT"
      return 1
    fi
    echo "[run $run_num] CRIU: ${CRIU_MS}ms"
    post_restore_and_wait "$run_num" "$T0" "$T_CRIU" "$CRIU_MS"
    return $?
  fi

  LD_LIBRARY_PATH="$WORK_DIR/criu/libs:/usr/lib/x86_64-linux-gnu" \
    "$WORK_DIR/criu/criu" restore \
      --images-dir "$CHECKPOINT_DIR" \
      --log-file "$log" \
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
      -L "$WORK_DIR/criu/plugins" \
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

  local CRIU_EXIT=$?
  T_CRIU=$(date +%s%3N)
  local CRIU_MS=$(( T_CRIU - T0 ))

  if [ $CRIU_EXIT -ne 0 ]; then
    echo "[run $run_num] CRIU FAILED (exit=$CRIU_EXIT) after ${CRIU_MS}ms"
    tail -5 "$log" 2>/dev/null
    echo "$run_num	$CRIU_MS	-1	FAILED_CRIU_$CRIU_EXIT"
    return 1
  fi

  echo "[run $run_num] CRIU: ${CRIU_MS}ms"
  post_restore_and_wait "$run_num" "$T0" "$T_CRIU" "$CRIU_MS"
  return $?
}

# ─── Shared post-CRIU sequence: stdio fix, netns, HTTP readiness ─────────────
post_restore_and_wait() {
  local run_num="$1" T0="$2" T_CRIU="$3" CRIU_MS="$4"
  local T_SETUP T_READY

  local NIM_PID
  NIM_PID=$(pgrep -f 'start_serve[r]' | head -1 || true)
  if [ -z "$NIM_PID" ]; then
    echo "[run $run_num] ERROR: No NIM PID"
    echo "$run_num	$CRIU_MS	-1	FAILED_NO_PID"
    return 1
  fi

  # Fix stdout/stderr broken pipes from --shell-job — on the WHOLE restored
  # process tree, not just the root: inference workers are children that crash
  # with EPIPE on their first progress print if their stdio is left broken.
  local ALL_PIDS
  ALL_PIDS=$(pgrep -f 'start_serve[r]|resource_track[e]r' 2>/dev/null || true)
  for p in $ALL_PIDS $NIM_PID; do
    python3 /tmp/fix_stdio.py "$p" >/dev/null 2>&1 || true
  done

  # Setup loopback in restored netns (Python ioctl — ip binary unreliable)
  setup_netns "$NIM_PID" >/dev/null 2>&1

  # Checkpoints dumped WITHOUT the CRIU cuda_plugin (manual cuda-checkpoint
  # lock/checkpoint before dump) come back with the CUDA context still in
  # 'checkpointed' state: HTTP health works, but the first kernel launch
  # blocks forever. Detect and finish the GPU restore manually.
  local CUDA_BIN="$WORK_DIR/criu/bin/cuda-checkpoint"
  local PY_PID CUDA_STATE T_CUDA0 T_CUDA1
  PY_PID=$(pgrep -f 'python.*start_serve[r]' | head -1 || true)
  [ -z "$PY_PID" ] && PY_PID="$NIM_PID"
  CUDA_STATE=$("$CUDA_BIN" --get-state --pid "$PY_PID" 2>/dev/null | tr '[:upper:]' '[:lower:]' || true)
  if [ "$CUDA_STATE" = "checkpointed" ] || [ "$CUDA_STATE" = "locked" ]; then
    T_CUDA0=$(date +%s%3N)
    [ "$CUDA_STATE" = "checkpointed" ] && "$CUDA_BIN" --action restore --pid "$PY_PID" --timeout 60000
    "$CUDA_BIN" --action unlock --pid "$PY_PID" --timeout 60000
    T_CUDA1=$(date +%s%3N)
    echo "[run $run_num] cuda-checkpoint restore+unlock: $((T_CUDA1-T_CUDA0))ms (state was: $CUDA_STATE)"
  fi

  T_SETUP=$(date +%s%3N)
  echo "[run $run_num] NIM PID=$NIM_PID post-restore setup: $((T_SETUP - T_CRIU))ms"

  # Poll for HTTP ready (90s max)
  for i in $(seq 1 90); do
    STATUS=$(nsenter -t "$NIM_PID" -n -- curl -sf --max-time 3 http://127.0.0.1:8000/v1/health/ready 2>/dev/null || true)
    if echo "$STATUS" | grep -q '"status":"ready"'; then
      T_READY=$(date +%s%3N)
      local TOTAL_MS=$(( T_READY - T0 ))
      echo "[run $run_num] HTTP 200 READY: total ${TOTAL_MS}ms (criu=${CRIU_MS}ms, setup=$((T_SETUP-T_CRIU))ms, http=$((T_READY-T_SETUP))ms)"
      echo "$run_num	$CRIU_MS	$TOTAL_MS	SUCCESS"
      return 0
    fi
    sleep 1
  done

  T_READY=$(date +%s%3N)
  local ELAPSED=$(( T_READY - T0 ))
  echo "[run $run_num] TIMEOUT after ${ELAPSED}ms"
  echo "$run_num	$CRIU_MS	$ELAPSED	TIMEOUT"
  return 1
}

# ─── Main ────────────────────────────────────────────────────────────────────
echo "run	criu_ms	total_ms	status" | tee "$RESULTS_CSV"

setup_once
unmount_extra

for i in $(seq 1 "$N_RUNS"); do
  echo ""
  echo "=== Run $i / $N_RUNS ==="
  # Continue loop even if a run fails
  run_restore "$i" 2>&1 | tee -a "$VERBOSE_LOG" || true
  tsv_line=$(grep -E "^${i}	" "$VERBOSE_LOG" 2>/dev/null | tail -1 || true)
  [ -n "$tsv_line" ] && echo "$tsv_line" >> "$RESULTS_CSV"
done

echo ""
echo "=== Final Results ==="
cat "$RESULTS_CSV"
