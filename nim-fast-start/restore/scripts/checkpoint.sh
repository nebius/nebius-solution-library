#!/usr/bin/env bash
# checkpoint.sh — create a quiesced checkpoint of a running NIM pod
#
# Usage:
#   checkpoint.sh [OPTIONS]
#
# Options:
#   -n, --namespace NS        Kubernetes namespace (default: nim-fast-start)
#   -p, --pod POD             Pod name to checkpoint
#   -c, --container CTR       Container name (default: first container)
#   -o, --output DIR          Snapshot output directory (default: /snapshots/<nim>/<ts>)
#   -s, --storage CLASS       Storage type: local-nvme|local-tmpfs|sfs (default: local-nvme)
#   --use-cuda-checkpoint     Use cuda-checkpoint instead of CRIU (requires dynamo-sdk)
#   --nim NAME                NIM identifier used in snapshot path (default: pod name)
#   --version VER             Explicit version tag for this snapshot
#
# Environment:
#   KUBECONFIG                K8s config file
#   SNAPSHOT_BASE             Base path for snapshots (default: /snapshots)
#
# Exit codes:
#   0  success
#   1  missing dependency
#   2  pod not found or not Ready
#   3  checkpoint failed
#   4  validation failed

set -euo pipefail

NAMESPACE="nim-fast-start"
POD=""
CONTAINER=""
STORAGE="local-nvme"
USE_CUDA_CHECKPOINT=false
NIM_NAME=""
VERSION=""
SNAPSHOT_BASE="${SNAPSHOT_BASE:-/snapshots}"

usage() {
  grep '^#' "$0" | head -20 | sed 's/^# \{0,1\}//'
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    -p|--pod)       POD="$2"; shift 2 ;;
    -c|--container) CONTAINER="$2"; shift 2 ;;
    -o|--output)    OUTPUT_DIR="$2"; shift 2 ;;
    -s|--storage)   STORAGE="$2"; shift 2 ;;
    --use-cuda-checkpoint) USE_CUDA_CHECKPOINT=true; shift ;;
    --nim)          NIM_NAME="$2"; shift 2 ;;
    --version)      VERSION="$2"; shift 2 ;;
    -h|--help)      usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$POD" ]] && { echo "ERROR: --pod is required"; usage; }

log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }
die() { log "ERROR: $*"; exit "${2:-1}"; }

# Resolve container if not set
if [[ -z "$CONTAINER" ]]; then
  CONTAINER=$(kubectl get pod -n "$NAMESPACE" "$POD" \
    -o jsonpath='{.spec.containers[0].name}' 2>/dev/null) || \
    die "Pod $POD not found in namespace $NAMESPACE" 2
fi

[[ -z "$NIM_NAME" ]] && NIM_NAME="$POD"
[[ -z "$VERSION" ]] && VERSION=$(date -u +%Y%m%d-%H%M%S)

SNAP_DIR="${OUTPUT_DIR:-${SNAPSHOT_BASE}/${NIM_NAME}/${VERSION}}"
mkdir -p "$SNAP_DIR"

log "Checkpoint target: $NAMESPACE/$POD/$CONTAINER → $SNAP_DIR"

# ── Verify pod is Ready ────────────────────────────────────────────────────────
PHASE=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.status.phase}' 2>/dev/null)
READY=$(kubectl get pod -n "$NAMESPACE" "$POD" \
  -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
[[ "$PHASE" == "Running" && "$READY" == "True" ]] || \
  die "Pod $POD is not Ready (phase=$PHASE, ready=$READY)" 2

# ── Capture snapshot metadata ─────────────────────────────────────────────────
NODE=$(kubectl get pod -n "$NAMESPACE" "$POD" -o jsonpath='{.spec.nodeName}')
IMAGE=$(kubectl get pod -n "$NAMESPACE" "$POD" \
  -o jsonpath='{.status.containerStatuses[?(@.name=="'"$CONTAINER"'")].imageID}')
DRIVER_VER=$(kubectl get node "$NODE" \
  -o jsonpath='{.metadata.labels.nebius\.com/nvidia_driver_version}' 2>/dev/null || echo "unknown")
GPU_PRODUCT=$(kubectl get node "$NODE" \
  -o jsonpath='{.metadata.labels.nebius\.com/gpu-name}' 2>/dev/null || echo "unknown")
GPU_COUNT=$(kubectl get pod -n "$NAMESPACE" "$POD" \
  -o jsonpath='{.spec.containers[0].resources.limits.nvidia\.com/gpu}' 2>/dev/null || echo "1")

cat > "$SNAP_DIR/metadata.json" <<METAJSON
{
  "version": "$VERSION",
  "nim_name": "$NIM_NAME",
  "pod": "$POD",
  "namespace": "$NAMESPACE",
  "container": "$CONTAINER",
  "node": "$NODE",
  "image_id": "$IMAGE",
  "gpu_product": "$GPU_PRODUCT",
  "gpu_count": $GPU_COUNT,
  "driver_version": "$DRIVER_VER",
  "storage": "$STORAGE",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "checkpoint_tool": "$(${USE_CUDA_CHECKPOINT} && echo cuda-checkpoint || echo criu)"
}
METAJSON

log "Metadata saved: $SNAP_DIR/metadata.json"

# ── Get the PID of the main NIM process inside the container ──────────────────
CONTAINER_PID=$(kubectl exec -n "$NAMESPACE" "$POD" -c "$CONTAINER" -- \
  bash -c 'cat /proc/1/status | grep "^Pid:" | awk "{print \$2}"' 2>/dev/null)
[[ -z "$CONTAINER_PID" ]] && die "Could not get container PID" 3

log "Container root PID (in pod): $CONTAINER_PID"

# ── Quiesce: save compiled Triton kernel cache from container ─────────────────
log "Saving Triton kernel cache..."
TRITON_CACHE_TAR="$SNAP_DIR/triton-cache.tar.gz"
kubectl exec -n "$NAMESPACE" "$POD" -c "$CONTAINER" -- \
  bash -c 'tar czf - /root/.triton/cache 2>/dev/null || tar czf - /tmp/triton-* 2>/dev/null || echo ""' \
  > "$TRITON_CACHE_TAR" 2>/dev/null && \
  log "Triton cache saved ($(du -sh "$TRITON_CACHE_TAR" | cut -f1))" || \
  log "No Triton cache found (first checkpoint)"

# ── Checkpoint via cuda-checkpoint or CRIU ────────────────────────────────────
if $USE_CUDA_CHECKPOINT; then
  log "Checkpointing via cuda-checkpoint..."
  # cuda-checkpoint writes device memory snapshot alongside CRIU images
  kubectl exec -n "$NAMESPACE" "$POD" -c "$CONTAINER" -- \
    cuda-checkpoint --action checkpoint --pid "$CONTAINER_PID" \
      --dir /tmp/cuda-ckpt 2>&1 || die "cuda-checkpoint failed" 3
  kubectl cp -n "$NAMESPACE" "$POD:/tmp/cuda-ckpt" "$SNAP_DIR/cuda-images/" 2>/dev/null
else
  log "Checkpointing via CRIU (CPU+memory; VRAM will reload from weights on restore)..."
  # CRIU must run on the node with hostPID access to see the container process
  # We call into a privileged ephemeral pod on the same node
  NODE_POD=$(kubectl get pods -n nim-fast-start -l "nim-fast-start-criu-agent=true" \
    -o jsonpath='{.items[?(@.spec.nodeName=="'"$NODE"'")].metadata.name}' 2>/dev/null | head -1)

  if [[ -z "$NODE_POD" ]]; then
    die "No CRIU agent pod running on node $NODE. Deploy restore/k8s/criu-agent-ds.yaml first." 3
  fi

  CRIU_IMAGES_DIR="$SNAP_DIR/criu-images"
  mkdir -p "$CRIU_IMAGES_DIR"

  # Find the host PID that corresponds to the container PID 1
  HOST_PID=$(kubectl exec -n nim-fast-start "$NODE_POD" -- \
    bash -c "grep -l 'NStgid.*[[:space:]]${CONTAINER_PID}[[:space:]]' /proc/*/status 2>/dev/null | head -1 | grep -o '[0-9]*' | head -1" 2>/dev/null)

  [[ -z "$HOST_PID" ]] && \
    HOST_PID=$(kubectl exec -n nim-fast-start "$NODE_POD" -- \
      bash -c "ls /proc/*/ns/pid 2>/dev/null | xargs -I{} sh -c 'p=\$(echo {} | grep -o \"[0-9]*\"); [ -f /proc/\$p/status ] && grep -q \"NStgid.*${CONTAINER_PID}\" /proc/\$p/status && echo \$p' 2>/dev/null | head -1" 2>/dev/null)

  [[ -z "$HOST_PID" ]] && die "Cannot find host PID for container PID $CONTAINER_PID" 3
  log "Host PID for container PID 1: $HOST_PID"

  # Run CRIU dump on the CRIU agent pod
  CRIU_SNAP="/tmp/criu-snap-$(date +%s)"
  kubectl exec -n nim-fast-start "$NODE_POD" -- \
    bash -c "mkdir -p ${CRIU_SNAP} && \
      /opt/criu/criu.sh dump \
        --tree $HOST_PID \
        --images-dir ${CRIU_SNAP} \
        --shell-job \
        --leave-running \
        --tcp-established \
        --ext-unix-sk \
        --log-file criu.log \
        2>&1" 2>&1 | tee -a "$SNAP_DIR/checkpoint.log" || \
    die "CRIU dump failed. See $SNAP_DIR/checkpoint.log" 3

  # Copy CRIU images from the agent pod to the snapshot directory
  kubectl cp -n nim-fast-start "$NODE_POD:${CRIU_SNAP}/" "$CRIU_IMAGES_DIR/" 2>/dev/null
  log "CRIU images saved ($(du -sh "$CRIU_IMAGES_DIR" | cut -f1))"

  # Cleanup temp dir on agent pod
  kubectl exec -n nim-fast-start "$NODE_POD" -- rm -rf "${CRIU_SNAP}" 2>/dev/null || true
fi

# ── Write success marker ───────────────────────────────────────────────────────
echo "ok" > "$SNAP_DIR/.ready"
log "Snapshot complete: $SNAP_DIR"
echo "$SNAP_DIR"
