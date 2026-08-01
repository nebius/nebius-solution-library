#!/bin/bash
# =============================================================================
# GPU Soak Test Runner (PyTorchJob / torch.distributed)
# Equivalent to cloudmeter auto-loader for MK8s clusters.
# Runs sustained GPU compute + HBM fill + NCCL all_reduce (IB/NVLink) stress
# for a configurable duration, then emits a structured pass/fail report.
#
# Usage:
#   ./run-soak-test.sh [duration_seconds] [gpu_node_count]
#
# Examples:
#   ./run-soak-test.sh              # 1 hour, 2 nodes (defaults)
#   ./run-soak-test.sh 7200 2       # 2 hours, 2 nodes
#   ./run-soak-test.sh 3600 4       # 1 hour, 4 nodes
#
# Environment overrides:
#   SOAK_IMAGE          Container image (default is a Hopper/H100 CUDA 12.3 image;
#                       set a CUDA 12.6+ arm64 image for Blackwell B200/GB200/GB300)
#   HBM_FILL_FRACTION   Fraction of HBM to fill per GPU (default 0.75)
#   MAX_TEMP            Overtemp threshold in °C (default 83; raise for Blackwell)
#   AUTO_CLEANUP=y      Delete the namespace at the end without prompting
#
# What it tests (equivalent to auto-loader):
#   - Sustained GPU utilization across all GPU nodes
#   - Configurable HBM fill (dynamically sized to GPU type)
#   - InfiniBand/NVLink stress via repeated NCCL all_reduce (verified + busbw)
#   - GPU temperature monitoring (fail if > 83°C)
#   - XID error detection (best-effort; flagged UNVERIFIED if unavailable)
#   - Node health monitoring
#   - Structured pass/fail output
# =============================================================================
set -euo pipefail

DURATION="${1:-3600}"
NODE_COUNT="${2:-2}"
NAMESPACE="gpu-soak"
SLOTS=8
HBM_FILL_FRACTION="${HBM_FILL_FRACTION:-0.75}"
# Container image for the workload. The default is a Hopper-era PyTorch (CUDA
# 12.3) that works on H100/H200. It will NOT run on Blackwell (B200/GB200/GB300)
# — those need a newer CUDA 12.6+ image, and Grace-based GB200/GB300 also need an
# arm64/sbsa image. Override per platform, e.g.:
#   SOAK_IMAGE=nvcr.io/nvidia/pytorch:<blackwell-arm64-tag> ./run-soak-test.sh ...
SOAK_IMAGE="${SOAK_IMAGE:-nvcr.io/nvidia/pytorch:24.01-py3}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPORT_FILE="soak-report-$(date +%Y%m%d_%H%M%S).txt"
START_TIME=$(date -u)
START_EPOCH=$(date +%s)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Delete the test namespace. Guarded so it runs at most once.
CLEANED=0
cleanup_ns() {
  [ "$CLEANED" = "1" ] && return
  CLEANED=1
  echo ""
  echo "Cleaning up namespace $NAMESPACE ..."
  kubectl delete namespace "$NAMESPACE" --ignore-not-found=true --wait=false 2>/dev/null || true
}
# On Ctrl-C / termination, tear down so an aborted run never leaks GPU pods.
trap 'cleanup_ns; exit 130' INT TERM

echo "=== GPU Soak Test (PyTorchJob / torch.distributed) ==="
echo "Duration:     ${DURATION}s ($(( DURATION / 60 )) minutes)"
echo "GPU nodes:    $NODE_COUNT"
echo "GPUs/node:    $SLOTS"
echo "HBM fill:     $(awk "BEGIN{printf \"%.0f\", ${HBM_FILL_FRACTION}*100}")%"
echo "Image:        $SOAK_IMAGE"
echo "Namespace:    $NAMESPACE"
echo "Started:      $START_TIME"
echo ""

# Verify the Training Operator (PyTorchJob CRD) is installed
if ! kubectl get crd pytorchjobs.kubeflow.org &>/dev/null; then
  echo -e "${RED}ERROR: Kubeflow Training Operator (PyTorchJob) not installed${NC}"
  echo "Install it with:"
  echo "  kubectl apply -k 'github.com/kubeflow/training-operator/manifests/overlays/standalone?ref=v1.7.0'"
  exit 1
fi

# =============================================================================
# DYNAMIC GPU NODE DETECTION
# =============================================================================
echo "Detecting GPU node type in cluster..."

GPU_INSTANCE_TYPE=$(kubectl get nodes \
  -o jsonpath='{.items[*].metadata.labels.node\.kubernetes\.io/instance-type}' \
  2>/dev/null | tr ' ' '\n' | grep -v "cpu" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}' || echo "")

if [ -z "$GPU_INSTANCE_TYPE" ]; then
  echo -e "${RED}ERROR: No GPU nodes found in cluster${NC}"
  echo "Ensure GPU nodes are Ready and have the node.kubernetes.io/instance-type label"
  exit 1
fi

echo "Detected GPU type: $GPU_INSTANCE_TYPE"

case "$GPU_INSTANCE_TYPE" in
  gpu-h100-sxm)  GPU_NAME="H100 SXM (80GB HBM3)" ;;
  gpu-h200-sxm)  GPU_NAME="H200 SXM (141GB HBM3e)" ;;
  gpu-b200-sxm)  GPU_NAME="B200 SXM (192GB HBM3e)" ;;
  gpu-b300-sxm)  GPU_NAME="B300 SXM" ;;
  *)             GPU_NAME="$GPU_INSTANCE_TYPE" ;;
esac

echo "GPU name: $GPU_NAME"

# Verify enough Ready GPU nodes are available.
# NOTE: `grep -c Ready` is wrong — "NotReady" contains the substring "Ready",
# so it would count degraded nodes as available. Match the STATUS column exactly.
AVAILABLE_GPU_NODES=$(kubectl get nodes -l "node.kubernetes.io/instance-type=${GPU_INSTANCE_TYPE}" \
  --no-headers 2>/dev/null | awk '$2=="Ready"' | wc -l | tr -d ' ')

if [ "$AVAILABLE_GPU_NODES" -lt "$NODE_COUNT" ]; then
  echo -e "${RED}ERROR: Requested $NODE_COUNT GPU nodes but only $AVAILABLE_GPU_NODES available${NC}"
  exit 1
fi

echo "GPU nodes available: $AVAILABLE_GPU_NODES ✓"
echo ""

# Clean up any previous run
kubectl delete namespace $NAMESPACE --ignore-not-found=true
kubectl wait --for=delete namespace/$NAMESPACE --timeout=120s 2>/dev/null || true

# Create namespace + mount the workload script as a ConfigMap
kubectl create namespace $NAMESPACE
kubectl create configmap soak-script -n $NAMESPACE \
  --from-file=soak.py="$SCRIPT_DIR/scripts/soak.py"

# Patch the PyTorchJob template. Worker replicas = total nodes - 1 (master is
# rank 0 and also runs GPUs), so total pods == NODE_COUNT.
WORKER_REPLICAS=$(( NODE_COUNT - 1 ))
MANIFEST=$(sed \
  -e "s/__GPU_INSTANCE_TYPE__/${GPU_INSTANCE_TYPE}/g" \
  -e "s/__WORKER_REPLICAS__/${WORKER_REPLICAS}/g" \
  -e "s/__DURATION__/${DURATION}/g" \
  -e "s/__FILL_FRACTION__/${HBM_FILL_FRACTION}/g" \
  -e "s/__SLOTS__/${SLOTS}/g" \
  -e "s|__SOAK_IMAGE__|${SOAK_IMAGE}|g" \
  "$SCRIPT_DIR/templates/pytorchjob.yaml")

echo "$MANIFEST" | kubectl apply -f -

echo ""
echo "PyTorchJob submitted. Waiting for master pod to start..."

kubectl wait --namespace $NAMESPACE \
  --for=condition=Ready \
  --timeout=300s \
  -l training.kubeflow.org/replica-type=master \
  pod 2>/dev/null || true

echo "Pods started. Beginning monitoring..."
echo ""
echo "To watch master logs in another terminal:"
echo "  kubectl logs -f -n $NAMESPACE -l training.kubeflow.org/replica-type=master"
echo ""

# Run monitor. set +e so a FAILED soak still produces a report and cleans up
# (bash monitor.sh returning non-zero must NOT abort this script under set -e).
set +e
bash "$SCRIPT_DIR/scripts/monitor.sh"
MONITOR_EXIT=$?
set -e

# Collect final master logs (rank 0 prints the summary + BUSBW lines)
MASTER_LOGS=$(kubectl logs -n $NAMESPACE -l training.kubeflow.org/replica-type=master 2>/dev/null | tail -40)

END_TIME=$(date -u)
END_EPOCH=$(date +%s)
ACTUAL_DURATION=$(( END_EPOCH - START_EPOCH ))

# =============================================================================
# GENERATE REPORT
# =============================================================================
generate_report() {
  local LOG_FILE
  LOG_FILE=$(ls -t "$SCRIPT_DIR"/soak-monitor-*.log 2>/dev/null | head -1)

  # NOTE: `grep -c` prints "0" AND exits 1 when there are no matches, so a
  # trailing `|| echo 0` would DOUBLE it to "0\n0" and break the "= 0" tests
  # below. Use `|| true` (keeps grep's own "0") and default empties to 0.
  local TOTAL_POLLS OVERTEMP LOW_UTIL XID XID_UNVERIFIED
  TOTAL_POLLS=$(grep -c "Poll #" "$LOG_FILE" 2>/dev/null || true); TOTAL_POLLS=${TOTAL_POLLS:-0}
  OVERTEMP=$(grep -c "OVERTEMP" "$LOG_FILE" 2>/dev/null || true); OVERTEMP=${OVERTEMP:-0}
  LOW_UTIL=$(grep -c "LOW UTIL" "$LOG_FILE" 2>/dev/null || true); LOW_UTIL=${LOW_UTIL:-0}
  XID=$(grep "XID errors detected:" "$LOG_FILE" 2>/dev/null | grep -oP 'detected: \K[0-9]+' | tail -1 || true); XID=${XID:-0}
  XID_UNVERIFIED=$(grep -c "XID_UNVERIFIED" "$LOG_FILE" 2>/dev/null || true); XID_UNVERIFIED=${XID_UNVERIFIED:-0}

  local MAX_TEMP MAX_UTIL MAX_POWER AVG_UTIL AVG_TEMP
  MAX_TEMP=$(grep "temp=" "$LOG_FILE" 2>/dev/null | grep -oP 'temp=\K[0-9]+' | sort -n | tail -1 || echo "N/A")
  MAX_UTIL=$(grep "util=" "$LOG_FILE" 2>/dev/null | grep -oP 'util=\K[0-9]+' | sort -n | tail -1 || echo "N/A")
  MAX_POWER=$(grep "power=" "$LOG_FILE" 2>/dev/null | grep -oP 'power=\K[0-9.]+' | sort -n | tail -1 || echo "N/A")
  AVG_UTIL=$(grep "util=" "$LOG_FILE" 2>/dev/null | grep -oP 'util=\K[0-9]+' | awk '{s+=$1;c++} END {if(c)printf "%.0f", s/c; else print "N/A"}')
  AVG_TEMP=$(grep "temp=" "$LOG_FILE" 2>/dev/null | grep -oP 'temp=\K[0-9]+' | awk '{s+=$1;c++} END {if(c)printf "%.0f", s/c; else print "N/A"}')

  # NCCL evidence straight from the master (rank 0) logs
  local PEAK_BUSBW AVG_BUSBW ITERS FAILED_ITERS
  PEAK_BUSBW=$(echo "$MASTER_LOGS" | grep -oP 'BUSBW_GBPS: \K[0-9.]+' | tail -1 || echo "N/A")
  AVG_BUSBW=$(echo "$MASTER_LOGS" | grep -oP 'BUSBW_AVG_GBPS: \K[0-9.]+' | tail -1 || echo "N/A")
  ITERS=$(echo "$MASTER_LOGS" | grep -oP 'Total iterations: \K[0-9]+' | tail -1 || echo "N/A")
  FAILED_ITERS=$(echo "$MASTER_LOGS" | grep -oP 'Failed iterations \(all ranks\): \K[0-9]+' | tail -1 || echo "N/A")

  local RESULT="PASSED"
  if [ "$MONITOR_EXIT" != "0" ]; then RESULT="FAILED"; fi

  cat > "$SCRIPT_DIR/$REPORT_FILE" << REPORT
================================================================================
  GPU SOAK TEST REPORT
================================================================================

  Cluster:        Nebius MK8s
  GPU Type:       $GPU_NAME
  GPU Instance:   $GPU_INSTANCE_TYPE
  GPU Nodes:      $NODE_COUNT
  Total GPUs:     $(( NODE_COUNT * SLOTS ))
  Orchestration:  PyTorchJob + torchrun (torch.distributed, NCCL)
  Duration:       ${DURATION}s ($(( DURATION / 60 )) minutes)
  Actual runtime: ${ACTUAL_DURATION}s ($(( ACTUAL_DURATION / 60 )) minutes)

  Started:        $START_TIME
  Finished:       $END_TIME

================================================================================
  GPU PERFORMANCE
================================================================================

  Peak temperature:     ${MAX_TEMP}°C    (threshold: 83°C)
  Average temperature:  ${AVG_TEMP}°C
  Peak utilization:     ${MAX_UTIL}%
  Average utilization:  ${AVG_UTIL}%
  Peak power draw:      ${MAX_POWER}W    (expected: 650-700W under load)

================================================================================
  MEMORY STRESS
================================================================================

  HBM fill:       $(awk "BEGIN{printf \"%.0f\", ${HBM_FILL_FRACTION}*100}")% of total GPU memory per GPU (leaves NCCL headroom)
  Method:         Resident FP16 hog tensor + continuous matmul

================================================================================
  NCCL ALL_REDUCE (InfiniBand / NVLink stress)
================================================================================

  Total iterations:         ${ITERS}
  Failed iterations:        ${FAILED_ITERS}
  Peak bus bandwidth:       ${PEAK_BUSBW} GB/s
  Average bus bandwidth:    ${AVG_BUSBW} GB/s
  (A blank/N/A bandwidth means NCCL produced no valid result — treat as a red
   flag even if other checks pass.)

================================================================================
  HEALTH CHECKS
================================================================================

  Total monitor polls:       $TOTAL_POLLS
  Overtemperature events:    $OVERTEMP    (threshold: >83°C)
  Low utilization events:    $LOW_UTIL    (threshold: <80%)
  XID errors detected:       $XID
  XID check unverified:      $([ "$XID_UNVERIFIED" -gt 0 ] 2>/dev/null && echo "YES — see note below" || echo "no")

================================================================================
  PASS / FAIL SUMMARY
================================================================================

$(if [ "$OVERTEMP" = "0" ]; then echo "  [PASS] No overtemperature events"; else echo "  [FAIL] $OVERTEMP overtemperature event(s) detected"; fi)
$(if [ "${XID_UNVERIFIED:-0}" -gt 0 ] 2>/dev/null; then echo "  [WARN] XID check could not run — GPUs NOT certified XID-clean"; elif [ "$XID" = "0" ]; then echo "  [PASS] No XID errors"; else echo "  [FAIL] $XID XID error(s) detected"; fi)
$(if [ "$MONITOR_EXIT" = "0" ]; then echo "  [PASS] All NCCL all_reduce iterations completed successfully"; else echo "  [FAIL] Soak workload reported failures (see master logs)"; fi)
$(if [ "$LOW_UTIL" -lt "10" ] 2>/dev/null; then echo "  [PASS] GPU utilization stayed healthy"; else echo "  [WARN] $LOW_UTIL low utilization events detected"; fi)

  OVERALL RESULT: $RESULT

================================================================================
  Raw log file: $LOG_FILE
================================================================================
REPORT

  echo ""
  echo -e "${BLUE}============================================================${NC}"
  echo -e "${BLUE}  SOAK TEST REPORT${NC}"
  echo -e "${BLUE}============================================================${NC}"
  cat "$SCRIPT_DIR/$REPORT_FILE"
  echo ""
  echo "Report saved to: $SCRIPT_DIR/$REPORT_FILE"
}

generate_report

# Cleanup — auto (CI), interactive prompt (tty), or leave-and-instruct (piped).
echo ""
if [ "${AUTO_CLEANUP:-}" = "y" ]; then
  cleanup_ns
  echo "Cleaned up."
elif [ -t 0 ]; then
  read -p "Delete namespace $NAMESPACE and all test resources? (y/n): " CLEANUP || CLEANUP=n
  if [ "$CLEANUP" = "y" ]; then
    cleanup_ns
    echo "Cleaned up."
  fi
else
  echo "Non-interactive shell — leaving namespace $NAMESPACE in place."
  echo "Delete with: kubectl delete namespace $NAMESPACE   (or re-run with AUTO_CLEANUP=y)"
fi

exit $MONITOR_EXIT
