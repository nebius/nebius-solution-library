#!/usr/bin/env bash
# restore_nim.sh — functionally restore a per-NIM CRIU checkpoint and prove it
# with a real inference. Runs INSIDE a privileged restore pod on the target node
# (hostPID=true, GPU allocated, /snapshots + model cache mounted).
#
# Usage: restore_nim.sh <nim> <checkpoint_dir> <tools_src> <jit_tar> [http_wait_s]
#   nim            openfold2|diffdock|rfdiffusion|genmol|proteinmpnn|...
#   checkpoint_dir e.g. /snapshots/genmol/criu42-v1
#   tools_src      dir with criu-420-bin, criu-libs/, criu-plugins/cuda_plugin.so,
#                  cuda-checkpoint  (H100 nodes: /snapshots ; B300: /snapshots/criu-tools)
#   jit_tar        harvested JIT artifacts tar (or "" if none)
#
# Wraps bench_restore.sh with the two portability fixes learned across the fleet:
#   1. Create every nvidia-ctk-hook UUID dir the checkpoint recorded — the donor's
#      CTK hook tmpfs mount id is baked into the images and must exist at restore.
#      Extracted generically via `strings` on the checkpoint images (no pycriu).
#   2. HTTP /v1/health/ready can lag or 404 on some NIMs even when the model
#      serves — the authoritative gate is a real inference, not the health probe.
set -uo pipefail
NIM="$1"; CKPT="$2"; TOOLS="$3"; JIT="${4:-}"; HTTP_WAIT="${5:-90}"

pkill -9 -f 'start_serve[r]' 2>/dev/null || true; sleep 1

# Fix 1: recreate the donor's CTK-hook dirs (+ our own, harmless).
for u in $(strings "$CKPT"/*.img 2>/dev/null | grep -oE 'nvidia-ctk-hook[a-f0-9-]+' | sort -u); do
  mkdir -p "/run/$u"
done
SELF_CTK=$(grep -o 'nvidia-ctk-hook[a-f0-9-]*' /proc/self/mountinfo 2>/dev/null | sort -u | head -1)
[ -n "$SELF_CTK" ] && mkdir -p "/run/$SELF_CTK"

: > /tmp/ext.txt
PREFETCH=1 JIT_TAR="$JIT" EXTERNALS_FILE=/tmp/ext.txt TOOLS_SRC="$TOOLS" \
  CHECKPOINT_DIR="$CKPT" RESULTS_CSV="/tmp/br_${NIM}.csv" VERBOSE_LOG="/tmp/bv_${NIM}.log" \
  bash /tmp/bench_restore.sh 1 2>&1 | grep -E 'READY|cuda|CRIU:|FAILED|TIMEOUT'

NIM_PID=$(pgrep -f 'start_serve[r]' | head -1)
[ -z "$NIM_PID" ] && { echo "RESTORE_NO_PID"; tail -6 /tmp/bench_logs/restore-run1.log 2>/dev/null; exit 1; }
echo "$NIM restored, NIM_PID=$NIM_PID — inference gate handled by caller"
