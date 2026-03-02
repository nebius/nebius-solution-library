#!/bin/bash
#
# Deploy OSMO Backend Operator
# https://nvidia.github.io/OSMO/main/deployment_guide/install_backend/deploy_backend.html
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/defaults.sh"

echo ""
echo "========================================"
echo "  OSMO Backend Operator Deployment"
echo "========================================"
echo ""

# Check prerequisites
check_kubectl || exit 1
check_helm || exit 1

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
OSMO_OPERATOR_NAMESPACE="osmo-operator"
OSMO_WORKFLOWS_NAMESPACE="osmo-workflows"
OSMO_IMAGE_TAG="${OSMO_IMAGE_TAG:-6.0.0}"
OSMO_CHART_VERSION="${OSMO_CHART_VERSION:-}"
BACKEND_NAME="${OSMO_BACKEND_NAME:-default}"

# Check for OSMO Service URL (in-cluster URL for the backend operator pods)
# IMPORTANT: Backend operators connect via WebSocket to osmo-agent, NOT osmo-service!
# The osmo-service handles REST API, osmo-agent handles WebSocket connections for backends
if [[ -z "${OSMO_SERVICE_URL:-}" ]]; then
    log_info "Auto-detecting in-cluster OSMO Agent URL..."
    
    # Backend operators MUST connect to osmo-agent for WebSocket connections
    # The osmo-service WebSocket routes only exist in dev mode
    OSMO_AGENT=$(kubectl get svc -n osmo osmo-agent -o jsonpath='{.metadata.name}' 2>/dev/null || echo "")
    
    if [[ -n "$OSMO_AGENT" ]]; then
        OSMO_SERVICE_URL="http://osmo-agent.osmo.svc.cluster.local:80"
        log_success "In-cluster Agent URL: ${OSMO_SERVICE_URL}"
    else
        # Fallback: try to detect from any osmo-agent service
        OSMO_AGENT=$(kubectl get svc -n osmo -l app.kubernetes.io/name=agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
        if [[ -n "$OSMO_AGENT" ]]; then
            OSMO_SERVICE_URL="http://${OSMO_AGENT}.osmo.svc.cluster.local:80"
            log_success "In-cluster Agent URL: ${OSMO_SERVICE_URL}"
        else
            echo ""
            log_error "Could not detect OSMO Agent service. Deploy OSMO first: ./05-deploy-osmo-control-plane.sh"
            log_error "Note: Backend operators require osmo-agent service for WebSocket connections"
            exit 1
        fi
    fi
fi

# Check for OSMO Service Token
if [[ -z "${OSMO_SERVICE_TOKEN:-}" ]]; then
    # First, ensure namespace exists so we can check for existing secret
    kubectl create namespace "${OSMO_OPERATOR_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f - 2>/dev/null || true
    
    # Check if token secret already exists in cluster
    EXISTING_TOKEN=$(kubectl get secret osmo-operator-token -n "${OSMO_OPERATOR_NAMESPACE}" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || echo "")
    
    if [[ -n "$EXISTING_TOKEN" ]]; then
        log_info "Using existing token from secret osmo-operator-token"
        OSMO_SERVICE_TOKEN="$EXISTING_TOKEN"
    elif command -v osmo &>/dev/null; then
        # Check if osmo CLI is already logged in (don't try to login with in-cluster URL)
        log_info "Checking if OSMO CLI is already logged in..."
        
        # Try to generate token - this only works if CLI is already logged in
        TOKEN_NAME="backend-token-$(date -u +%Y%m%d%H%M%S)"
        EXPIRY_DATE=$(date -u -d "+1 year" +%F 2>/dev/null || date -u -v+1y +%F 2>/dev/null || echo "2027-01-01")
        
        TOKEN_JSON=$(osmo token set "$TOKEN_NAME" \
            --expires-at "$EXPIRY_DATE" \
            --description "Backend Operator Token" \
            --service --roles osmo-backend -t json 2>/dev/null || echo "")
        
        if [[ -n "$TOKEN_JSON" ]]; then
            OSMO_SERVICE_TOKEN=$(echo "$TOKEN_JSON" | jq -r '.token // empty' 2>/dev/null || echo "")
        fi
        
        if [[ -n "$OSMO_SERVICE_TOKEN" ]]; then
            log_success "Service token generated: $TOKEN_NAME (expires: $EXPIRY_DATE)"
        fi
    fi
    
    # If still no token, automatically create one using port-forward
    if [[ -z "$OSMO_SERVICE_TOKEN" ]]; then
        log_info "No token found - automatically creating service token..."

        TOKEN_NAME="backend-token-$(date -u +%Y%m%d%H%M%S)"
        EXPIRY_DATE=$(date -u -d "+1 year" +%F 2>/dev/null || date -u -v+1y +%F 2>/dev/null || echo "2027-01-01")

        # Cleanup function to kill port-forwards on exit
        PF_PIDS=()
        cleanup_port_forwards() {
            for pid in "${PF_PIDS[@]}"; do
                kill "$pid" 2>/dev/null || true
                wait "$pid" 2>/dev/null || true
            done
        }
        trap cleanup_port_forwards EXIT

        # Detect if Keycloak auth is enabled
        KEYCLOAK_ENABLED="false"
        if [[ "${DEPLOY_KEYCLOAK:-false}" == "true" ]]; then
            KEYCLOAK_ENABLED="true"
        elif kubectl get svc -n "${OSMO_NAMESPACE:-osmo}" keycloak &>/dev/null; then
            KEYCLOAK_ENABLED="true"
        fi

        if [[ "$KEYCLOAK_ENABLED" == "true" ]]; then
            # ---------------------------------------------------------------
            # Keycloak-enabled: use Resource Owner Password Grant to get JWT,
            # then call OSMO REST API with Bearer token
            # ---------------------------------------------------------------
            log_info "Keycloak detected - using password grant for token creation..."

            # Derive Keycloak URL: KEYCLOAK_HOSTNAME env (from osmo-deploy.env) > ingress host > port-forward fallback
            KC_INGRESS_HOST=$(kubectl get ingress -n "${OSMO_NAMESPACE:-osmo}" keycloak -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || echo "")
            KC_PF_PID=""
            if [[ -n "${KEYCLOAK_HOSTNAME:-}" ]]; then
                KEYCLOAK_TOKEN_URL="https://${KEYCLOAK_HOSTNAME}/realms/osmo/protocol/openid-connect/token"
                log_info "Keycloak token endpoint (KEYCLOAK_HOSTNAME): ${KEYCLOAK_TOKEN_URL}"
            elif [[ -n "$KC_INGRESS_HOST" ]]; then
                KEYCLOAK_TOKEN_URL="https://${KC_INGRESS_HOST}/realms/osmo/protocol/openid-connect/token"
                log_info "Keycloak token endpoint (ingress): ${KEYCLOAK_TOKEN_URL}"
            else
                # No ingress and no KEYCLOAK_HOSTNAME: use port-forward so 05 can complete
                KC_PF_PORT="${KC_PF_PORT:-8082}"
                log_info "No Keycloak ingress found; using port-forward to Keycloak on localhost:${KC_PF_PORT}..."
                kubectl port-forward -n "${OSMO_NAMESPACE:-osmo}" svc/keycloak "${KC_PF_PORT}:80" &>/dev/null &
                KC_PF_PID=$!
                PF_PIDS+=($KC_PF_PID)
                for i in $(seq 1 15); do
                    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:${KC_PF_PORT}/realms/osmo" 2>/dev/null | grep -q 200; then
                        break
                    fi
                    sleep 1
                    if [[ $i -eq 15 ]]; then
                        log_error "Keycloak port-forward failed to respond in time"
                        exit 1
                    fi
                done
                KEYCLOAK_TOKEN_URL="http://localhost:${KC_PF_PORT}/realms/osmo/protocol/openid-connect/token"
                log_info "Keycloak token endpoint (port-forward): ${KEYCLOAK_TOKEN_URL}"
            fi

            # Port-forward to OSMO service (for the token creation API)
            log_info "Starting port-forward to OSMO service..."
            kubectl port-forward -n "${OSMO_NAMESPACE:-osmo}" svc/osmo-service 8080:80 &>/dev/null &
            PF_PIDS+=($!)

            # Wait for port-forward to be ready
            log_info "Waiting for port-forward to be ready..."
            max_wait=30
            elapsed=0
            while true; do
                SVC_READY=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/api/version" 2>/dev/null || echo "000")
                if [[ "$SVC_READY" =~ ^(200|401|403)$ ]]; then
                    break
                fi
                sleep 1
                elapsed=$((elapsed + 1))
                if [[ $elapsed -ge $max_wait ]]; then
                    log_error "Port-forward failed to start within ${max_wait}s (service=$SVC_READY)"
                    exit 1
                fi
            done
            log_success "Port-forward ready"

            # Get Keycloak JWT via Resource Owner Password Grant
            # Uses osmo-device client (public, directAccessGrantsEnabled=true)
            # MUST use external Keycloak URL so the JWT issuer matches what Envoy expects
            KC_ADMIN_USER="${OSMO_KC_ADMIN_USER:-osmo-admin}"
            KC_ADMIN_PASS="${OSMO_KC_ADMIN_PASS:-osmo-admin}"
            # When Nebius SSO is primary, the default osmo-admin user is not created; set CREATE_OSMO_TEST_USER=true
            # in 04-deploy-osmo-control-plane.sh or set OSMO_KC_ADMIN_USER/OSMO_KC_ADMIN_PASS to a valid local user.

            log_info "Authenticating with Keycloak as '${KC_ADMIN_USER}'..."
            KC_RESPONSE=$(curl -s -X POST "${KEYCLOAK_TOKEN_URL}" \
                -d "grant_type=password" \
                -d "client_id=osmo-device" \
                -d "username=${KC_ADMIN_USER}" \
                -d "password=${KC_ADMIN_PASS}")

            KC_JWT=$(echo "$KC_RESPONSE" | jq -r '.access_token // empty' 2>/dev/null || echo "")
            if [[ -z "$KC_JWT" ]]; then
                KC_ERROR=$(echo "$KC_RESPONSE" | jq -r '.error_description // .error // empty' 2>/dev/null || echo "unknown error")
                log_error "Keycloak authentication failed: $KC_ERROR"
                log_error "Ensure OSMO_KC_ADMIN_USER and OSMO_KC_ADMIN_PASS are set. If using Nebius SSO, create a local user (e.g. CREATE_OSMO_TEST_USER=true) or see AUTHENTICATION.md"
                exit 1
            fi
            log_success "Keycloak authentication successful"

            # Create service token via OSMO REST API
            # NOTE: Must use "x-osmo-auth" header (not Authorization), because:
            #   1. Envoy's OAuth2 filter runs first and would redirect to Keycloak
            #      if it doesn't see OAuth cookies. The "x-osmo-auth" header triggers
            #      the pass_through_matcher, bypassing the OAuth2 redirect.
            #   2. Envoy's JWT filter reads from "x-osmo-auth" (not Authorization).
            #   3. No "Bearer " prefix -- the JWT filter has no value_prefix configured,
            #      so it expects the raw JWT directly.
            log_info "Creating service token: $TOKEN_NAME (expires: $EXPIRY_DATE)..."
            TOKEN_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
                "http://localhost:8080/api/auth/access_token/service/${TOKEN_NAME}?expires_at=${EXPIRY_DATE}&roles=osmo-backend" \
                -H "x-osmo-auth: ${KC_JWT}" \
                -H "Content-Type: application/json")

            # Separate response body from HTTP status code
            HTTP_CODE=$(echo "$TOKEN_RESPONSE" | tail -1)
            TOKEN_BODY=$(echo "$TOKEN_RESPONSE" | sed '$d')

            if [[ "$HTTP_CODE" != "200" && "$HTTP_CODE" != "201" ]]; then
                log_error "Token creation API returned HTTP $HTTP_CODE"
                log_error "Response: $TOKEN_BODY"
                exit 1
            fi

            # Response is the raw token string (quoted JSON string)
            OSMO_SERVICE_TOKEN=$(echo "$TOKEN_BODY" | jq -r '. // empty' 2>/dev/null || echo "")
            # If jq fails (response might be a plain string, not JSON), use raw
            if [[ -z "$OSMO_SERVICE_TOKEN" ]]; then
                OSMO_SERVICE_TOKEN=$(echo "$TOKEN_BODY" | tr -d '"' | tr -d '\r' | xargs)
            fi

        else
            # ---------------------------------------------------------------
            # No Keycloak: use dev auth method (original approach)
            # ---------------------------------------------------------------
            # Check if osmo CLI is available
            if ! command -v osmo &>/dev/null; then
                log_error "osmo CLI not found. Please install it first."
                exit 1
            fi

            # Start port-forward in background
            log_info "Starting port-forward to OSMO service..."
            kubectl port-forward -n "${OSMO_NAMESPACE:-osmo}" svc/osmo-service 8080:80 &>/dev/null &
            PF_PIDS+=($!)

            # Wait for port-forward to be ready
            log_info "Waiting for port-forward to be ready..."
            max_wait=30
            elapsed=0
            while ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/api/version" 2>/dev/null | grep -q "200\|401\|403"; do
                sleep 1
                elapsed=$((elapsed + 1))
                if [[ $elapsed -ge $max_wait ]]; then
                    log_error "Port-forward failed to start within ${max_wait}s"
                    exit 1
                fi
            done
            log_success "Port-forward ready"

            # Login with dev method (auth is disabled)
            log_info "Logging in to OSMO (dev method)..."
            if ! osmo login http://localhost:8080 --method dev --username admin 2>/dev/null; then
                log_error "Failed to login to OSMO. If Keycloak is enabled, set DEPLOY_KEYCLOAK=true"
                exit 1
            fi
            log_success "Logged in successfully"

            # Create service token
            log_info "Creating service token: $TOKEN_NAME (expires: $EXPIRY_DATE)..."
            TOKEN_OUTPUT=$(osmo token set "$TOKEN_NAME" \
                --expires-at "$EXPIRY_DATE" \
                --description "Backend Operator Token (auto-generated)" \
                --service --roles osmo-backend 2>&1)

            # Extract token from output (format: "Access token: <token>")
            OSMO_SERVICE_TOKEN=$(echo "$TOKEN_OUTPUT" | sed -n 's/.*Access token: //p' | tr -d '\r' | xargs)
        fi

        if [[ -z "$OSMO_SERVICE_TOKEN" ]]; then
            log_error "Failed to create service token"
            echo "Response: ${TOKEN_RESPONSE:-$TOKEN_OUTPUT}"
            exit 1
        fi

        log_success "Service token created: $TOKEN_NAME (expires: $EXPIRY_DATE)"

        # Stop port-forwards
        cleanup_port_forwards
        trap - EXIT
    fi
fi

# -----------------------------------------------------------------------------
# Add OSMO Helm Repository
# -----------------------------------------------------------------------------
log_info "Adding OSMO Helm repository..."
helm repo add osmo https://helm.ngc.nvidia.com/nvidia/osmo --force-update
helm repo update

# -----------------------------------------------------------------------------
# Create Namespaces
# -----------------------------------------------------------------------------
log_info "Creating namespaces..."
kubectl create namespace "${OSMO_OPERATOR_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace "${OSMO_WORKFLOWS_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# -----------------------------------------------------------------------------
# Create Secrets
# -----------------------------------------------------------------------------
log_info "Creating operator token secret..."
kubectl create secret generic osmo-operator-token \
    --namespace "${OSMO_OPERATOR_NAMESPACE}" \
    --from-literal=token="${OSMO_SERVICE_TOKEN}" \
    --dry-run=client -o yaml | kubectl apply -f -

# -----------------------------------------------------------------------------
# Create Values File
# -----------------------------------------------------------------------------
log_info "Creating Helm values file..."

# Note: services.backendListener/Worker are at root level, not under global
# See: osmo-helm-charts/backend-operator/values.yaml
cat > /tmp/backend_operator_values.yaml <<EOF
global:
  osmoImageTag: "${OSMO_IMAGE_TAG}"
  serviceUrl: "${OSMO_SERVICE_URL}"
  agentNamespace: "${OSMO_OPERATOR_NAMESPACE}"
  backendNamespace: "${OSMO_WORKFLOWS_NAMESPACE}"
  backendName: "${BACKEND_NAME}"
  accountTokenSecret: osmo-operator-token
  accountTokenSecretKey: token
  loginMethod: token
  
  # Node selector to prefer system/CPU nodes (not GPU nodes)
  nodeSelector:
    kubernetes.io/os: linux
  
  # Logging configuration
  logs:
    logLevel: DEBUG
    k8sLogLevel: WARNING

# Service-specific configurations (at root level, not under global)
services:
  backendListener:
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        memory: "1Gi"
  
  backendWorker:
    resources:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        memory: "1Gi"

# Disable test runner for initial deployment
backendTestRunner:
  enabled: false
EOF

# -----------------------------------------------------------------------------
# Deploy Backend Operator
# -----------------------------------------------------------------------------
log_info "Deploying OSMO Backend Operator..."

HELM_ARGS=(
    --namespace "${OSMO_OPERATOR_NAMESPACE}"
    -f /tmp/backend_operator_values.yaml
    --wait
    --timeout 10m
)

if [[ -n "${OSMO_CHART_VERSION}" ]]; then
    HELM_ARGS+=(--version "${OSMO_CHART_VERSION}")
fi

helm upgrade --install osmo-operator osmo/backend-operator "${HELM_ARGS[@]}"

log_success "OSMO Backend Operator deployed"

# Cleanup temp file
rm -f /tmp/backend_operator_values.yaml

# -----------------------------------------------------------------------------
# Verify Deployment
# -----------------------------------------------------------------------------
echo ""
log_info "Verifying deployment..."

kubectl get pods -n "${OSMO_OPERATOR_NAMESPACE}"
kubectl get pods -n "${OSMO_WORKFLOWS_NAMESPACE}" 2>/dev/null || true

echo ""
echo "========================================"
log_success "OSMO Backend Operator deployment complete!"
echo "========================================"
echo ""
echo "Backend Name: ${BACKEND_NAME}"
echo "Agent URL (WebSocket): ${OSMO_SERVICE_URL}"
echo ""
# Detect Ingress URL for verification instructions
INGRESS_URL=$(detect_service_url 2>/dev/null || true)

echo "To verify the backend registration:"
echo ""
if [[ -n "$INGRESS_URL" ]]; then
    echo "  Check backend status:"
    echo "    osmo config show BACKEND ${BACKEND_NAME}"
    echo ""
    echo "  Or via curl (using NGINX Ingress LoadBalancer):"
    echo "    curl ${INGRESS_URL}/api/configs/backend"
else
    echo "  Terminal 1 - Start port-forward (keep running):"
    echo "    kubectl port-forward -n osmo svc/osmo-service 8080:80"
    echo ""
    echo "  Terminal 2 - Check backend status:"
    echo "    osmo config show BACKEND ${BACKEND_NAME}"
    echo ""
    echo "  Or via curl:"
    echo "    curl http://localhost:8080/api/configs/backend"
fi
echo ""
echo "Next step - Configure Storage:"
echo "  ./07-configure-storage.sh"
echo ""
