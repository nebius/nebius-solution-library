#!/usr/bin/env bash
# GPU restore script: CRIU restore + cuda-checkpoint restore
# Run from inside nim-criu-agent pod (privileged, hostPID=true)
# Usage: restore.sh <CHECKPOINT_DIR>
set -euo pipefail

CHECKPOINT_DIR="${1:-/snapshots/openfold2/gpu-checkpoint}"
CUDA_CHKPT=/usr/local/bin/cuda-checkpoint
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/v1/health/ready}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"

T0=$(date +%s%3N)

echo "[$(date -u +%H:%M:%S)] Restoring from $CHECKPOINT_DIR"

# Step 1: CRIU restore
echo "[$(date -u +%H:%M:%S)] Running CRIU restore..."
/opt/criu/criu.sh restore \
  --images-dir "$CHECKPOINT_DIR" \
  --restore-detached \
  --daemon \
  --tcp-established \
  --ext-unix-sk \
  --shell-job \
  2>&1 | tee /tmp/restore.log

T_CRIU=$(date +%s%3N)
echo "[$(date -u +%H:%M:%S)] CRIU restore time: $((T_CRIU - T0))ms"

# Step 2: Find restored PID
RESTORED_PID=$(cat /tmp/restore.log | grep -oP 'pid \K[0-9]+' | tail -1 || true)
if [[ -z "$RESTORED_PID" ]]; then
  echo "WARNING: Could not determine restored PID from log. Searching..."
  RESTORED_PID=$(pgrep -f 'start_server' | head -1)
fi
echo "[$(date -u +%H:%M:%S)] Restored PID: $RESTORED_PID"

# Step 3: Restore CUDA context
if [[ -n "$RESTORED_PID" ]]; then
  echo "[$(date -u +%H:%M:%S)] Restoring CUDA context for PID $RESTORED_PID..."
  "$CUDA_CHKPT" --action restore --pid "$RESTORED_PID" 2>&1 || true
  "$CUDA_CHKPT" --action unlock --pid "$RESTORED_PID" 2>&1 || true
  T_CUDA=$(date +%s%3N)
  echo "[$(date -u +%H:%M:%S)] CUDA restore time: $((T_CUDA - T_CRIU))ms"
fi

# Step 4: Wait for NIM to be ready
echo "[$(date -u +%H:%M:%S)] Waiting for NIM health check..."
ELAPSED=0
while ! curl -sf "$HEALTH_URL" >/dev/null 2>&1; do
  sleep 1
  ELAPSED=$((ELAPSED + 1))
  if [[ $ELAPSED -ge $HEALTH_TIMEOUT ]]; then
    echo "ERROR: NIM not ready after ${HEALTH_TIMEOUT}s" >&2
    exit 1
  fi
done

T_READY=$(date +%s%3N)
echo "[$(date -u +%H:%M:%S)] NIM READY"
echo "[$(date -u +%H:%M:%S)] Total restore time: $((T_READY - T0))ms"
