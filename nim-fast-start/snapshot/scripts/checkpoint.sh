#!/usr/bin/env bash
# GPU checkpoint script: cuda-checkpoint + CRIU dump
# Run from inside nim-criu-agent pod (privileged, hostPID=true)
# Usage: checkpoint.sh <NIM_PID> <CHECKPOINT_DIR>
set -euo pipefail

NIM_PID="${1:?Usage: $0 <NIM_PID> <CHECKPOINT_DIR>}"
CHECKPOINT_DIR="${2:-/snapshots/openfold2/gpu-checkpoint}"
CUDA_CHKPT=/usr/local/bin/cuda-checkpoint

# Verify cuda-checkpoint is installed
if ! command -v "$CUDA_CHKPT" >/dev/null 2>&1; then
  echo "ERROR: cuda-checkpoint not found at $CUDA_CHKPT" >&2
  echo "Install: cp /path/to/cuda-checkpoint/bin/x86_64_Linux/cuda-checkpoint $CUDA_CHKPT && chmod +x $CUDA_CHKPT" >&2
  exit 1
fi

# Verify process state
STATE=$("$CUDA_CHKPT" --get-state --pid "$NIM_PID" 2>&1)
echo "[$(date -u +%H:%M:%S)] NIM PID=$NIM_PID CUDA state=$STATE"
if [[ "$STATE" != "running" ]]; then
  echo "ERROR: Expected state=running, got: $STATE" >&2
  exit 1
fi

mkdir -p "$CHECKPOINT_DIR"

T0=$(date +%s%3N)

# Step 1: Lock CUDA context (freeze GPU execution)
echo "[$(date -u +%H:%M:%S)] Locking CUDA context..."
"$CUDA_CHKPT" --action lock --pid "$NIM_PID" --timeout 30000
echo "[$(date -u +%H:%M:%S)] State: $("$CUDA_CHKPT" --get-state --pid "$NIM_PID")"

# Step 2: Checkpoint CUDA context (prepare GPU memory for CRIU)
echo "[$(date -u +%H:%M:%S)] Checkpointing CUDA context..."
"$CUDA_CHKPT" --action checkpoint --pid "$NIM_PID"
echo "[$(date -u +%H:%M:%S)] State: $("$CUDA_CHKPT" --get-state --pid "$NIM_PID")"

T_CUDA=$(date +%s%3N)
echo "[$(date -u +%H:%M:%S)] CUDA checkpoint time: $((T_CUDA - T0))ms"

# Step 3: Build skip-mnt args for all host-injected bind mounts
# (253:1 = host root ext4, 0:26/0:392 = NVIDIA-specific tmpfs)
SKIP_ARGS=''
while IFS= read -r mnt; do
  SKIP_ARGS="$SKIP_ARGS --skip-mnt $mnt"
done < <(cat /proc/"$NIM_PID"/mountinfo | awk '
  {dev=$3; mp=$5}
  dev=="253:1" {print mp}
  dev=="0:26"  {print mp}
  dev=="0:392" {print mp}
')

# Step 4: CRIU dump (requires CRIU 3.17+ for io_uring support)
echo "[$(date -u +%H:%M:%S)] Running CRIU dump..."
/opt/criu/criu.sh dump \
  --tree "$NIM_PID" \
  --images-dir "$CHECKPOINT_DIR" \
  --log-file "$CHECKPOINT_DIR/criu.log" \
  --leave-running \
  --tcp-established \
  --ext-unix-sk \
  --shell-job \
  $SKIP_ARGS \
  2>&1 | tee "$CHECKPOINT_DIR/dump.log"

T_CRIU=$(date +%s%3N)

echo "[$(date -u +%H:%M:%S)] CRIU dump time: $((T_CRIU - T_CUDA))ms"
echo "[$(date -u +%H:%M:%S)] Total checkpoint time: $((T_CRIU - T0))ms"
echo "[$(date -u +%H:%M:%S)] Checkpoint size: $(du -sh "$CHECKPOINT_DIR" | cut -f1)"
echo "[$(date -u +%H:%M:%S)] State after dump: $("$CUDA_CHKPT" --get-state --pid "$NIM_PID")"

# Note: With --leave-running, process resumes after dump.
# cuda-checkpoint --action restore --pid <PID> then --action unlock to fully resume.
