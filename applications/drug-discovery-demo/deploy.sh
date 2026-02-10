#!/usr/bin/env bash
# ============================================================================
# Drug Discovery Demo - Build & Deploy to K8s
#
# Prerequisites:
#   - Docker (or podman) installed and running
#   - kubectl configured and connected to the target cluster
#   - Authenticated to Nebius Container Registry:
#       docker login cr.me-west1.nebius.cloud
#
# Usage:
#   ./deploy.sh              # Build, push, deploy
#   ./deploy.sh --build-only # Build and push image only
#   ./deploy.sh --deploy-only # Apply K8s manifests only (skip build)
# ============================================================================

set -euo pipefail

# --- Configuration ---
IMAGE="cr.me-west1.nebius.cloud/i00sk4xvrcvbg80rm6/drug-discovery-demo"
TAG="${DEPLOY_TAG:-$(git -C "$(dirname "$0")" rev-parse --short HEAD 2>/dev/null || date +%s)}"
NAMESPACE="nims"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[x]${NC} $*" >&2; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

# Parse flags
BUILD=true
DEPLOY=true
for arg in "$@"; do
  case "$arg" in
    --build-only)  DEPLOY=false ;;
    --deploy-only) BUILD=false ;;
    --help|-h)
      echo "Usage: $0 [--build-only|--deploy-only]"
      exit 0
      ;;
  esac
done

# ============================================================================
# Pre-flight checks
# ============================================================================

log "Pre-flight checks..."

if $BUILD; then
  if ! command -v docker &>/dev/null; then
    err "docker not found. Install Docker or set up podman alias."
    exit 1
  fi
fi

if $DEPLOY; then
  if ! command -v kubectl &>/dev/null; then
    err "kubectl not found."
    exit 1
  fi

  # Verify kubectl connectivity
  if ! kubectl cluster-info &>/dev/null; then
    err "kubectl cannot connect to cluster. Check your kubeconfig."
    exit 1
  fi
  info "Connected to cluster: $(kubectl config current-context)"

  # Ensure namespace exists
  if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    warn "Namespace '$NAMESPACE' does not exist. Creating..."
    kubectl create namespace "$NAMESPACE"
  fi
fi

# ============================================================================
# Build & Push Docker Image
# ============================================================================

if $BUILD; then
  log "Building Docker image: ${IMAGE}:${TAG}"
  cd "$SCRIPT_DIR"

  docker build \
    --platform linux/amd64 \
    -t "${IMAGE}:${TAG}" \
    .

  log "Pushing image to Nebius Container Registry..."
  docker push "${IMAGE}:${TAG}"

  log "Image pushed: ${IMAGE}:${TAG}"
fi

# ============================================================================
# Deploy to K8s
# ============================================================================

if $DEPLOY; then
  log "Applying K8s manifests..."
  cd "$SCRIPT_DIR"

  kubectl apply -f k8s/deployment.yaml
  kubectl apply -f k8s/service.yaml

  # Update the container image to the specific tagged version
  log "Setting image to ${IMAGE}:${TAG}..."
  kubectl set image deployment/drug-discovery-demo \
    app="${IMAGE}:${TAG}" \
    -n "$NAMESPACE"

  log "Waiting for rollout..."
  kubectl rollout status deployment/drug-discovery-demo \
    -n "$NAMESPACE" \
    --timeout=120s

  # Show pod status
  echo ""
  log "Pod status:"
  kubectl get pods -n "$NAMESPACE" -l app=drug-discovery-demo

  # Get external IP
  echo ""
  log "Service:"
  kubectl get svc drug-discovery-demo -n "$NAMESPACE"

  EXTERNAL_IP=""
  for i in $(seq 1 30); do
    EXTERNAL_IP=$(kubectl get svc drug-discovery-demo -n "$NAMESPACE" \
      -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
    if [[ -n "$EXTERNAL_IP" ]]; then
      break
    fi
    if [[ $i -eq 1 ]]; then
      info "Waiting for external IP assignment..."
    fi
    sleep 2
  done

  echo ""
  if [[ -n "$EXTERNAL_IP" ]]; then
    log "App is live at: http://${EXTERNAL_IP}"
    info "Enter your NIM gateway URL in the sidebar to connect to services."
  else
    warn "External IP not yet assigned. Check with:"
    echo "  kubectl get svc drug-discovery-demo -n $NAMESPACE -w"
  fi
fi

echo ""
log "Done."
