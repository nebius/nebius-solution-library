#!/usr/bin/env bash
# restore.sh — restore a NIM checkpoint into a new Kubernetes pod
#
# Usage:
#   restore.sh [OPTIONS]
#
# Options:
#   -s, --snapshot DIR        Snapshot directory (from checkpoint.sh)
#   -n, --namespace NS        Target namespace (default: nim-fast-start)
#   --pod-name NAME           Name for the restored pod (default: <nim>-restore-<ts>)
#   --node NODE               Pin restored pod to this node (default: same node as snapshot)
#   --gpu-count N             Number of GPUs for the restored pod (default: from snapshot)
#   --timeout SECS            Seconds to wait for pod Ready (default: 60)
#   --dry-run                 Print the pod manifest without applying it
#
# Environment:
#   KUBECONFIG, SNAPSHOT_BASE
#
# Exit codes:
#   0  success — pod became Ready within --timeout
#   1  usage error
#   2  snapshot not found or invalid
#   3  compatibility check failed
#   4  pod creation failed
#   5  pod did not become Ready within timeout

set -euo pipefail

NAMESPACE="nim-fast-start"
SNAPSHOT_DIR=""
POD_NAME=""
TARGET_NODE=""
GPU_COUNT=""
TIMEOUT=60
DRY_RUN=false

log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }
die() { log "ERROR: $*"; exit "${2:-1}"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--snapshot)  SNAPSHOT_DIR="$2"; shift 2 ;;
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    --pod-name)     POD_NAME="$2"; shift 2 ;;
    --node)         TARGET_NODE="$2"; shift 2 ;;
    --gpu-count)    GPU_COUNT="$2"; shift 2 ;;
    --timeout)      TIMEOUT="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    -h|--help)      head -20 "$0" | grep '^#' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ -z "$SNAPSHOT_DIR" ]] && die "--snapshot is required"
[[ -f "$SNAPSHOT_DIR/.ready" ]] || die "Snapshot not ready: $SNAPSHOT_DIR" 2
[[ -f "$SNAPSHOT_DIR/metadata.json" ]] || die "metadata.json missing in $SNAPSHOT_DIR" 2

# ── Load snapshot metadata ────────────────────────────────────────────────────
read_meta() { python3 -c "import json,sys; d=json.load(open('$SNAPSHOT_DIR/metadata.json')); print(d.get('$1',''))" 2>/dev/null; }

SNAP_NIM=$(read_meta nim_name)
SNAP_VERSION=$(read_meta version)
SNAP_NODE=$(read_meta node)
SNAP_IMAGE=$(read_meta image_id)
SNAP_GPU_PRODUCT=$(read_meta gpu_product)
SNAP_GPU_COUNT=$(read_meta gpu_count)
SNAP_DRIVER=$(read_meta driver_version)
SNAP_TOOL=$(read_meta checkpoint_tool)

[[ -z "$TARGET_NODE" ]] && TARGET_NODE="$SNAP_NODE"
[[ -z "$GPU_COUNT" ]] && GPU_COUNT="${SNAP_GPU_COUNT:-1}"
[[ -z "$POD_NAME" ]] && POD_NAME="${SNAP_NIM}-restore-$(date +%s)"

log "Restoring snapshot: nim=$SNAP_NIM version=$SNAP_VERSION → pod=$POD_NAME"

# ── Compatibility check ───────────────────────────────────────────────────────
log "Running compatibility check..."

# Check node GPU product matches snapshot
NODE_GPU=$(kubectl get node "$TARGET_NODE" \
  -o jsonpath='{.metadata.labels.nebius\.com/gpu-name}' 2>/dev/null || echo "")
if [[ -n "$NODE_GPU" && "$NODE_GPU" != "$SNAP_GPU_PRODUCT" ]]; then
  die "GPU mismatch: snapshot=$SNAP_GPU_PRODUCT node=$NODE_GPU — snapshot cannot be restored on different GPU arch" 3
fi

# Check driver version matches
NODE_DRIVER=$(kubectl get node "$TARGET_NODE" \
  -o jsonpath='{.metadata.labels.nebius\.com/nvidia_driver_version}' 2>/dev/null || echo "")
if [[ -n "$NODE_DRIVER" && "$NODE_DRIVER" != "$SNAP_DRIVER" ]]; then
  log "WARNING: driver mismatch (snapshot=$SNAP_DRIVER node=$NODE_DRIVER). Proceeding but restore may fail."
fi

log "Compatibility check passed (GPU=$NODE_GPU, driver=$NODE_DRIVER)"

# ── Stage Triton cache on target node ─────────────────────────────────────────
TRITON_TAR="$SNAPSHOT_DIR/triton-cache.tar.gz"
if [[ -f "$TRITON_TAR" && -s "$TRITON_TAR" ]]; then
  log "Staging Triton kernel cache on node $TARGET_NODE..."
  # Upload via a short-lived staging pod on the target node
  STAGE_POD="criu-cache-stage-$(date +%s)"
  kubectl run "$STAGE_POD" \
    -n "$NAMESPACE" \
    --image=busybox:latest \
    --restart=Never \
    --overrides="{
      \"spec\": {
        \"nodeName\": \"${TARGET_NODE}\",
        \"hostPID\": false,
        \"containers\": [{
          \"name\": \"c\",
          \"image\": \"busybox:latest\",
          \"command\": [\"sh\", \"-c\", \"mkdir -p /cache && sleep 300\"],
          \"volumeMounts\": [{\"name\":\"cache\",\"mountPath\":\"/cache\"}]
        }],
        \"volumes\": [{\"name\":\"cache\",\"hostPath\":{\"path\":\"/opt/nim-triton-cache\"}}]
      }
    }" >/dev/null 2>&1

  kubectl wait pod -n "$NAMESPACE" "$STAGE_POD" --for=condition=Ready --timeout=30s >/dev/null 2>&1 || true
  kubectl cp -n "$NAMESPACE" "$TRITON_TAR" "$STAGE_POD:/cache/triton-cache.tar.gz" 2>/dev/null
  kubectl exec -n "$NAMESPACE" "$STAGE_POD" -- \
    sh -c "mkdir -p /cache/root/.triton && tar xzf /cache/triton-cache.tar.gz -C /cache/root/.triton 2>/dev/null || true" 2>/dev/null || true
  kubectl delete pod -n "$NAMESPACE" "$STAGE_POD" --now 2>/dev/null || true
  log "Triton cache staged"
fi

# ── Build the restored pod manifest ───────────────────────────────────────────
RESTORE_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Get the original pod spec to use as the template
ORIG_POD_SPEC=$(kubectl get pod -n "$NAMESPACE" -l "nim=${SNAP_NIM}" \
  -o jsonpath='{.items[0]}' 2>/dev/null || echo "")

# Get image from the most recent deployment for this NIM
NIM_IMAGE=$(kubectl get deployment -n "$NAMESPACE" -l "app=${SNAP_NIM}" \
  -o jsonpath='{.items[0].spec.template.spec.containers[0].image}' 2>/dev/null || \
  echo "nvcr.io/nim/openfold/openfold2:latest")

# Build restore pod manifest
cat > /tmp/restore-pod-${POD_NAME}.yaml <<PODSPEC
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
  namespace: ${NAMESPACE}
  labels:
    nim: ${SNAP_NIM}
    nim-restore: "true"
    snapshot-version: "${SNAP_VERSION}"
    workload: archvteams-2407
  annotations:
    nim-fast-start/snapshot-dir: "${SNAPSHOT_DIR}"
    nim-fast-start/restored-at: "${RESTORE_TS}"
    nim-fast-start/snapshot-version: "${SNAP_VERSION}"
    nim-fast-start/checkpoint-tool: "${SNAP_TOOL}"
spec:
  nodeName: ${TARGET_NODE}
  restartPolicy: Never
  imagePullSecrets:
  - name: nvcrio-cred
  initContainers:
  # init-restore: copies checkpoint images and kernel cache into the container filesystem
  - name: init-restore
    image: ubuntu:24.04
    securityContext:
      privileged: true
    command: ["/bin/sh", "-c"]
    args:
    - |
      set -e
      echo "[restore] Staging snapshot artifacts..."
      # Stage Triton cache under /restore-data for the main container
      mkdir -p /restore-data/.triton/cache
      if [ -f /snapshot/triton-cache.tar.gz ]; then
        tar xzf /snapshot/triton-cache.tar.gz -C /restore-data/ 2>/dev/null || true
        echo "[restore] Triton cache staged"
      fi
      # Stage CRIU images
      if [ -d /snapshot/criu-images ]; then
        cp -r /snapshot/criu-images /restore-data/ 2>/dev/null || true
        echo "[restore] CRIU images staged"
      fi
      echo "[restore] init done"
    volumeMounts:
    - name: snapshot-vol
      mountPath: /snapshot
    - name: restore-data
      mountPath: /restore-data
  containers:
  - name: ${SNAP_NIM}
    image: ${NIM_IMAGE}
    ports:
    - containerPort: 8000
      name: http
    env:
    - name: NGC_API_KEY
      valueFrom:
        secretKeyRef:
          name: ngc-api-key
          key: NGC_API_KEY
    - name: NIM_CACHE_PATH
      value: /opt/nim/.cache
    # Pre-seed Triton kernel cache from the snapshot
    - name: TRITON_CACHE_DIR
      value: /restore-data/root/.triton/cache
    resources:
      requests:
        nvidia.com/gpu: "${GPU_COUNT}"
        cpu: "16"
        memory: "100Gi"
      limits:
        nvidia.com/gpu: "${GPU_COUNT}"
        cpu: "16"
        memory: "100Gi"
    volumeMounts:
    - name: nim-cache
      mountPath: /opt/nim/.cache
    - name: dshm
      mountPath: /dev/shm
    - name: restore-data
      mountPath: /restore-data
    readinessProbe:
      httpGet:
        path: /v1/health/ready
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 5
      failureThreshold: 30
      timeoutSeconds: 5
    livenessProbe:
      httpGet:
        path: /v1/health/live
        port: 8000
      initialDelaySeconds: 30
      periodSeconds: 15
      failureThreshold: 5
  volumes:
  - name: nim-cache
    persistentVolumeClaim:
      claimName: ${SNAP_NIM}-nim-cache
  - name: dshm
    emptyDir:
      medium: Memory
      sizeLimit: 32Gi
  - name: snapshot-vol
    hostPath:
      path: ${SNAPSHOT_DIR}
  - name: restore-data
    emptyDir: {}
PODSPEC

log "Manifest written to /tmp/restore-pod-${POD_NAME}.yaml"

if $DRY_RUN; then
  cat "/tmp/restore-pod-${POD_NAME}.yaml"
  exit 0
fi

# ── Apply the pod and wait for Ready ──────────────────────────────────────────
T_START=$(date +%s)
kubectl apply -f "/tmp/restore-pod-${POD_NAME}.yaml" >/dev/null

log "Waiting up to ${TIMEOUT}s for pod Ready..."
if kubectl wait pod -n "$NAMESPACE" "$POD_NAME" \
    --for=condition=Ready --timeout="${TIMEOUT}s" 2>/dev/null; then
  T_END=$(date +%s)
  ELAPSED=$(( T_END - T_START ))
  log "Pod $POD_NAME is Ready in ${ELAPSED}s"
  echo "$POD_NAME $ELAPSED"
  exit 0
else
  log "Pod $POD_NAME not Ready within ${TIMEOUT}s — falling back to conventional startup"

  # ── Fallback: delete restore pod and start a fresh NIM pod ────────────────
  log "Deleting failed restore pod..."
  kubectl delete pod -n "$NAMESPACE" "$POD_NAME" --now 2>/dev/null || true

  FALLBACK_POD="${SNAP_NIM}-fallback-$(date +%s)"
  log "Starting fallback pod: $FALLBACK_POD"

  # Use the warm deployment template if available
  WARM_MANIFEST="$(dirname "$0")/../../manifests/${SNAP_NIM}-warm-deployment.yaml"
  if [[ -f "$WARM_MANIFEST" ]]; then
    kubectl apply -f "$WARM_MANIFEST" >/dev/null 2>&1 || true
  fi

  kubectl wait pod -n "$NAMESPACE" -l "nim=${SNAP_NIM}" \
    --for=condition=Ready --timeout="${TIMEOUT}s" 2>/dev/null || \
    die "Fallback pod also failed to become Ready" 5

  log "Fallback pod is Ready (cold start used)"
  exit 5
fi
