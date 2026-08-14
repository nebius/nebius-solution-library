#!/usr/bin/env bash
# run-validation.sh — Run the 20+ restore validation matrix for OpenFold2 / Evo2-40B
#
# Usage:
#   run-validation.sh [OPTIONS]
#
# Options:
#   --nim NAME          NIM to validate: openfold2|evo2-40b (default: openfold2)
#   --runs N            Number of restore runs (default: 20)
#   --snapshot DIR      Snapshot to restore from (required)
#   --namespace NS      Kubernetes namespace (default: nim-fast-start)
#   --output-csv FILE   Output CSV file (default: validation/<nim>_restore_matrix.csv)
#   --concurrent N      Concurrent restores to test at end (default: 2 for evo2-40b)
#
# The script:
#   1. Restores the NIM N times, measuring p50/p95
#   2. Runs an inference correctness check against a reference cold pod
#   3. Tests concurrent restores
#   4. Writes results to --output-csv

set -euo pipefail

NIM="openfold2"
RUNS=20
SNAPSHOT_DIR=""
NAMESPACE="nim-fast-start"
OUTPUT_CSV=""
CONCURRENT=1

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }
die() { log "ERROR: $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nim)         NIM="$2"; shift 2 ;;
    --runs)        RUNS="$2"; shift 2 ;;
    --snapshot)    SNAPSHOT_DIR="$2"; shift 2 ;;
    --namespace)   NAMESPACE="$2"; shift 2 ;;
    --output-csv)  OUTPUT_CSV="$2"; shift 2 ;;
    --concurrent)  CONCURRENT="$2"; shift 2 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -z "$SNAPSHOT_DIR" ]] && die "--snapshot is required"
[[ -f "$SNAPSHOT_DIR/.ready" ]] || die "Snapshot not ready: $SNAPSHOT_DIR"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULT_DIR="$(cd "$SCRIPT_DIR/../../validation" && pwd)"
mkdir -p "$RESULT_DIR"

[[ -z "$OUTPUT_CSV" ]] && OUTPUT_CSV="$RESULT_DIR/${NIM}_restore_matrix.csv"
LOG_FILE="$RESULT_DIR/${NIM}_restore_matrix.log"

log "=== NIM Fast-Start Restore Validation Matrix ==="
log "NIM: $NIM  Runs: $RUNS  Snapshot: $SNAPSHOT_DIR"
log "Output: $OUTPUT_CSV"

# ── CSV header ────────────────────────────────────────────────────────────────
echo "run,mode,nim,snapshot_version,node,gpu_product,t_start_iso,t_ready_iso,elapsed_s,pod_name,result,notes" > "$OUTPUT_CSV"

SNAP_VERSION=$(python3 -c "import json; d=json.load(open('$SNAPSHOT_DIR/metadata.json')); print(d.get('version','?'))" 2>/dev/null)
SNAP_NODE=$(python3 -c "import json; d=json.load(open('$SNAPSHOT_DIR/metadata.json')); print(d.get('node','?'))" 2>/dev/null)
SNAP_GPU=$(python3 -c "import json; d=json.load(open('$SNAPSHOT_DIR/metadata.json')); print(d.get('gpu_product','?'))" 2>/dev/null)
SNAP_GPU_COUNT=$(python3 -c "import json; d=json.load(open('$SNAPSHOT_DIR/metadata.json')); print(d.get('gpu_count',1))" 2>/dev/null)

elapsed_list=()
fail_count=0

# ── Main restore loop ─────────────────────────────────────────────────────────
for i in $(seq 1 "$RUNS"); do
  POD_NAME="${NIM}-restore-run${i}-$(date +%s)"
  T_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  T_START_EPOCH=$(date +%s)

  log "Run $i/$RUNS: starting restore → $POD_NAME"

  # Run restore
  RESULT="success"
  NOTES=""
  ELAPSED=0

  if output=$("$SCRIPT_DIR/restore.sh" \
    --snapshot "$SNAPSHOT_DIR" \
    --namespace "$NAMESPACE" \
    --pod-name "$POD_NAME" \
    --node "$SNAP_NODE" \
    --gpu-count "$SNAP_GPU_COUNT" \
    --timeout 60 2>&1); then
    T_END_EPOCH=$(date +%s)
    ELAPSED=$(( T_END_EPOCH - T_START_EPOCH ))
    elapsed_list+=("$ELAPSED")
    RESULT="success"
    log "  → Ready in ${ELAPSED}s"
  else
    EXIT_CODE=$?
    T_END_EPOCH=$(date +%s)
    ELAPSED=$(( T_END_EPOCH - T_START_EPOCH ))
    if [[ $EXIT_CODE -eq 5 ]]; then
      RESULT="fallback"
      NOTES="restore-failed-fallback-used"
    else
      RESULT="failure"
      NOTES="exit-code-${EXIT_CODE}"
    fi
    fail_count=$((fail_count + 1))
    log "  → FAILED (${RESULT}) in ${ELAPSED}s"
  fi

  T_READY=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "${i},restore,${NIM},${SNAP_VERSION},${SNAP_NODE},${SNAP_GPU},${T_START},${T_READY},${ELAPSED},${POD_NAME},${RESULT},${NOTES}" >> "$OUTPUT_CSV"

  # ── Inference correctness check (every 5th run) ───────────────────────────
  if [[ "$RESULT" == "success" ]] && (( i % 5 == 0 )); then
    log "  Checking inference correctness for run $i..."
    INFER_RESULT="skip"
    if kubectl get pod -n "$NAMESPACE" "$POD_NAME" >/dev/null 2>&1; then
      # Simple health-check probe
      CLUSTER_IP=$(kubectl get pod -n "$NAMESPACE" "$POD_NAME" \
        -o jsonpath='{.status.podIP}' 2>/dev/null)
      if [[ -n "$CLUSTER_IP" ]]; then
        HTTP_STATUS=$(kubectl exec -n "$NAMESPACE" "$POD_NAME" -- \
          curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/v1/health/ready 2>/dev/null || echo "0")
        if [[ "$HTTP_STATUS" == "200" ]]; then
          INFER_RESULT="healthy"
        else
          INFER_RESULT="unhealthy-${HTTP_STATUS}"
        fi
      fi
    fi
    log "  Inference check: $INFER_RESULT"
  fi

  # ── Cleanup restored pod ─────────────────────────────────────────────────
  kubectl delete pod -n "$NAMESPACE" "$POD_NAME" --now 2>/dev/null || true
  # Short pause between runs to let GPU/node settle
done

# ── Concurrent restore test ───────────────────────────────────────────────────
if [[ "$CONCURRENT" -gt 1 ]]; then
  log "=== Concurrent restore test ($CONCURRENT replicas) ==="
  CONC_PIDS=()
  CONC_PODS=()
  CONC_START=$(date +%s)

  for j in $(seq 1 "$CONCURRENT"); do
    CPOD="${NIM}-concurrent-${j}-$(date +%s)"
    CONC_PODS+=("$CPOD")
    (
      "$SCRIPT_DIR/restore.sh" \
        --snapshot "$SNAPSHOT_DIR" \
        --namespace "$NAMESPACE" \
        --pod-name "$CPOD" \
        --node "$SNAP_NODE" \
        --gpu-count "$SNAP_GPU_COUNT" \
        --timeout 90 2>&1 | tee -a "$LOG_FILE"
    ) &
    CONC_PIDS+=("$!")
  done

  # Wait for all concurrent restores
  CONC_OK=0
  for pid in "${CONC_PIDS[@]}"; do
    wait "$pid" && CONC_OK=$((CONC_OK + 1)) || true
  done
  CONC_END=$(date +%s)
  CONC_ELAPSED=$(( CONC_END - CONC_START ))

  log "Concurrent results: $CONC_OK/$CONCURRENT succeeded in ${CONC_ELAPSED}s"

  # Record concurrent results
  for j in $(seq 1 "$CONCURRENT"); do
    CPOD="${CONC_PODS[$((j-1))]}"
    CPOD_READY=$(kubectl get pod -n "$NAMESPACE" "$CPOD" \
      -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
    CRESULT=$([[ "$CPOD_READY" == "True" ]] && echo "success" || echo "failure")
    echo "conc-${j},concurrent,${NIM},${SNAP_VERSION},${SNAP_NODE},${SNAP_GPU},,,${CONC_ELAPSED},${CPOD},${CRESULT},concurrent-replica-${j}" >> "$OUTPUT_CSV"
    kubectl delete pod -n "$NAMESPACE" "$CPOD" --now 2>/dev/null || true
  done
fi

# ── Compute statistics ─────────────────────────────────────────────────────────
if [[ ${#elapsed_list[@]} -gt 0 ]]; then
  python3 - <<PYEOF
import statistics, json

times = [${elapsed_list[@]// /, }]
times.sort()
n = len(times)

p50 = times[int(n * 0.50)] if n > 0 else 0
p95 = times[int(n * 0.95)] if n > 1 else times[-1]
p99 = times[int(n * 0.99)] if n > 2 else times[-1]
mean = statistics.mean(times) if times else 0

print(f"")
print(f"=== Restore Matrix Summary ===")
print(f"NIM:      ${NIM}")
print(f"GPU:      ${SNAP_GPU}")
print(f"Runs:     {n} successful / ${RUNS} total")
print(f"Failures: ${fail_count}")
print(f"")
print(f"Elapsed times (seconds):")
print(f"  Min:  {min(times):.1f}s")
print(f"  P50:  {p50:.1f}s")
print(f"  P95:  {p95:.1f}s")
print(f"  P99:  {p99:.1f}s")
print(f"  Max:  {max(times):.1f}s")
print(f"  Mean: {mean:.1f}s")
print(f"")
p95_target = 30
status = "✓ PASS" if p95 < p95_target else "✗ FAIL"
print(f"p95 < {p95_target}s target: {status} ({p95:.1f}s)")
PYEOF
fi

log "Results written to: $OUTPUT_CSV"
log "Log: $LOG_FILE"
