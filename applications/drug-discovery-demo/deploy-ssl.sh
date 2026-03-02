#!/usr/bin/env bash
# ============================================================================
# Drug Discovery Demo - Build & Deploy to K8s with SSL (HTTPS)
#
# This script extends the standard deployment with:
#   - nginx-ingress controller (via Helm)
#   - cert-manager with Let's Encrypt (via Helm)
#   - TLS-terminated Ingress for bionemo.eu-north1.osmo.nebius.cloud
#
# Prerequisites:
#   - Docker (or podman) installed and running
#   - kubectl configured and connected to the target cluster
#   - helm v3 installed
#   - Authenticated to Nebius Container Registry:
#       docker login cr.eu-north1.nebius.cloud
#   - Firewall allows inbound 80/443 on the ingress-nginx LoadBalancer IP
#   - DNS A record for bionemo.eu-north1.osmo.nebius.cloud points to the
#     ingress-nginx external IP
#
# Usage:
#   ./deploy-ssl.sh               # Build, push, deploy (skip SSL infra if already up)
#   ./deploy-ssl.sh --build-only  # Build and push image only
#   ./deploy-ssl.sh --deploy-only # Apply K8s manifests only (skip build)
#   ./deploy-ssl.sh --setup-ssl   # Force (re)install SSL infrastructure
# ============================================================================

set -euo pipefail

# --- Configuration ---
IMAGE="cr.eu-north1.nebius.cloud/e00nqjpcd9s536rfga/drug-discovery-demo"
TAG="${DEPLOY_TAG:-$(git -C "$(dirname "$0")" rev-parse --short HEAD 2>/dev/null || date +%s)}"
NAMESPACE="nims"
DOMAIN="bionemo.eu-north1.osmo.nebius.cloud"
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
FORCE_SSL=false
for arg in "$@"; do
  case "$arg" in
    --build-only)  DEPLOY=false ;;
    --deploy-only) BUILD=false ;;
    --setup-ssl)   FORCE_SSL=true ;;
    --help|-h)
      echo "Usage: $0 [--build-only|--deploy-only|--setup-ssl]"
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

  if ! command -v helm &>/dev/null; then
    err "helm not found. Install Helm v3: https://helm.sh/docs/intro/install/"
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
  cd "$SCRIPT_DIR"

  # --------------------------------------------------------------------------
  # SSL infrastructure (ingress-nginx + cert-manager)
  # Only install if not already present or --setup-ssl is passed.
  # --------------------------------------------------------------------------
  NEED_SSL=false
  if $FORCE_SSL; then
    NEED_SSL=true
  elif ! helm status ingress-nginx -n ingress-nginx &>/dev/null; then
    NEED_SSL=true
  elif ! helm status cert-manager -n cert-manager &>/dev/null; then
    NEED_SSL=true
  fi

  if $NEED_SSL; then
    log "Setting up SSL infrastructure..."

    # ingress-nginx
    if helm status ingress-nginx -n ingress-nginx &>/dev/null; then
      info "ingress-nginx already installed, upgrading..."
      helm upgrade ingress-nginx ingress-nginx/ingress-nginx \
        --namespace ingress-nginx \
        --set controller.service.type=LoadBalancer \
        --set controller.progressDeadlineSeconds=600
    else
      log "Installing ingress-nginx controller..."
      helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
      helm repo update
      helm install ingress-nginx ingress-nginx/ingress-nginx \
        --namespace ingress-nginx --create-namespace \
        --set controller.service.type=LoadBalancer \
        --set controller.progressDeadlineSeconds=600
    fi

    log "Waiting for ingress-nginx controller to be ready..."
    kubectl wait --namespace ingress-nginx \
      --for=condition=ready pod \
      --selector=app.kubernetes.io/component=controller \
      --timeout=120s

    # cert-manager
    if helm status cert-manager -n cert-manager &>/dev/null; then
      info "cert-manager already installed, upgrading..."
      helm upgrade cert-manager jetstack/cert-manager \
        --namespace cert-manager \
        --set crds.enabled=true
    else
      log "Installing cert-manager..."
      helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
      helm repo update
      helm install cert-manager jetstack/cert-manager \
        --namespace cert-manager --create-namespace \
        --set crds.enabled=true
    fi

    log "Waiting for cert-manager pods to be ready..."
    kubectl wait --namespace cert-manager \
      --for=condition=ready pod --all \
      --timeout=120s
  else
    info "SSL infrastructure already running (skip with --setup-ssl to force)."
  fi

  # --------------------------------------------------------------------------
  # Apply app manifests (always — kubectl apply is idempotent)
  # --------------------------------------------------------------------------
  log "Applying K8s manifests..."
  kubectl apply -f k8s/deployment.yaml
  kubectl apply -f k8s/service-clusterip.yaml
  kubectl apply -f k8s/cluster-issuer.yaml
  kubectl apply -f k8s/ingress.yaml

  # Update the container image to the specific tagged version
  log "Setting image to ${IMAGE}:${TAG}..."
  kubectl set image deployment/drug-discovery-demo \
    app="${IMAGE}:${TAG}" \
    -n "$NAMESPACE"

  log "Waiting for rollout..."
  kubectl rollout status deployment/drug-discovery-demo \
    -n "$NAMESPACE" \
    --timeout=120s

  # --------------------------------------------------------------------------
  # Status output
  # --------------------------------------------------------------------------
  echo ""
  log "Pod status:"
  kubectl get pods -n "$NAMESPACE" -l app=drug-discovery-demo

  echo ""
  log "Ingress:"
  kubectl get ingress drug-discovery-demo -n "$NAMESPACE"

  # Get ingress-nginx external IP
  INGRESS_IP=""
  for i in $(seq 1 30); do
    INGRESS_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx \
      -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
    if [[ -n "$INGRESS_IP" ]]; then
      break
    fi
    if [[ $i -eq 1 ]]; then
      info "Waiting for ingress-nginx external IP..."
    fi
    sleep 2
  done

  echo ""
  log "Certificate status:"
  kubectl get certificate -n "$NAMESPACE" 2>/dev/null || info "Certificate not yet created (cert-manager may still be processing)."

  echo ""
  if [[ -n "$INGRESS_IP" ]]; then
    log "Ingress external IP: ${INGRESS_IP}"
    info "Ensure DNS A record for ${DOMAIN} points to ${INGRESS_IP}"

    # Check if DNS already matches
    RESOLVED_IP=$(dig +short "$DOMAIN" 2>/dev/null || true)
    if [[ "$RESOLVED_IP" == "$INGRESS_IP" ]]; then
      log "DNS already points to the correct IP."
    else
      warn "DNS currently resolves to: ${RESOLVED_IP:-<unresolvable>}"
      warn "Update the A record for ${DOMAIN} -> ${INGRESS_IP}"
    fi

    echo ""
    log "App will be live at: https://${DOMAIN}"
    info "Certificate may take a few minutes to be issued after DNS is configured."
    info "Monitor with: kubectl get certificate -n ${NAMESPACE} -w"
  else
    warn "Ingress external IP not yet assigned. Check with:"
    echo "  kubectl get svc -n ingress-nginx ingress-nginx-controller -w"
  fi
fi

echo ""
log "Done."
