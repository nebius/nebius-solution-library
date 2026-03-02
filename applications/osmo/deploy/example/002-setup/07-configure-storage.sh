#!/bin/bash
#
# Configure OSMO Storage
# https://nvidia.github.io/OSMO/main/deployment_guide/getting_started/configure_data_storage.html
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/defaults.sh"

echo ""
echo "========================================"
echo "  OSMO Storage Configuration"
echo "========================================"
echo ""

# Check prerequisites
check_kubectl || exit 1

# -----------------------------------------------------------------------------
# Get Storage Configuration from Terraform
# -----------------------------------------------------------------------------
log_info "Retrieving storage configuration from Terraform..."

S3_BUCKET=$(get_tf_output "storage_bucket.name" "../001-iac" 2>/dev/null || echo "")
S3_ENDPOINT=$(get_tf_output "storage_bucket.endpoint" "../001-iac" 2>/dev/null || echo "")

# Require NEBIUS_REGION (set by nebius-env-init.sh)
if [[ -z "${NEBIUS_REGION:-}" ]]; then
    log_error "NEBIUS_REGION is not set. Run 'source ../000-prerequisites/nebius-env-init.sh' first."
    exit 1
fi

# Default endpoint if not set
if [[ -z "$S3_ENDPOINT" ]]; then
    S3_ENDPOINT="https://storage.${NEBIUS_REGION}.nebius.cloud"
fi

if [[ -z "$S3_BUCKET" ]]; then
    log_error "Could not retrieve storage bucket name from Terraform"
    echo ""
    echo "Make sure you have run 'terraform apply' in deploy/001-iac"
    echo "and that storage is enabled in your terraform.tfvars"
    exit 1
fi

log_success "Storage bucket: ${S3_BUCKET}"
log_success "Storage endpoint: ${S3_ENDPOINT}"

# -----------------------------------------------------------------------------
# Check/Create osmo-storage secret
# -----------------------------------------------------------------------------
log_info "Checking for osmo-storage secret..."

if ! kubectl get secret osmo-storage -n osmo &>/dev/null; then
    log_warning "osmo-storage secret not found - attempting to create from MysteryBox..."
    
    # Get credentials from Terraform/MysteryBox
    S3_ACCESS_KEY=$(get_tf_output "storage_credentials.access_key_id" "../001-iac" 2>/dev/null || echo "")
    S3_SECRET_REF_ID=$(get_tf_output "storage_secret_reference_id" "../001-iac" 2>/dev/null || echo "")
    S3_SECRET_KEY=""
    
    if [[ -n "$S3_SECRET_REF_ID" ]]; then
        log_info "Retrieving storage secret from MysteryBox..."
        # IAM access key secrets are stored with key "secret" in MysteryBox
        S3_SECRET_KEY=$(get_mysterybox_secret "$S3_SECRET_REF_ID" "secret" 2>/dev/null || echo "")
    fi
    
    if [[ -z "$S3_ACCESS_KEY" || -z "$S3_SECRET_KEY" ]]; then
        log_error "Could not retrieve storage credentials"
        echo ""
        echo "Either re-run 04-deploy-osmo-control-plane.sh or create the secret manually:"
        echo ""
        echo "  kubectl create secret generic osmo-storage \\"
        echo "    --namespace osmo \\"
        echo "    --from-literal=access-key-id=<your-access-key> \\"
        echo "    --from-literal=secret-access-key=<your-secret-key>"
        exit 1
    fi
    
    # Create the secret
    kubectl create secret generic osmo-storage \
        --namespace osmo \
        --from-literal=access-key-id="${S3_ACCESS_KEY}" \
        --from-literal=secret-access-key="${S3_SECRET_KEY}" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "osmo-storage secret created"
else
    log_success "osmo-storage secret exists"
fi

# -----------------------------------------------------------------------------
# Start port-forward and configure storage
# -----------------------------------------------------------------------------
log_info "Starting port-forward to OSMO service..."

OSMO_NS="${OSMO_NAMESPACE:-osmo}"

start_osmo_port_forward "${OSMO_NS}" 8080

# Cleanup function
cleanup_port_forward() {
    if [[ -n "${PORT_FORWARD_PID:-}" ]]; then
        kill $PORT_FORWARD_PID 2>/dev/null || true
        wait $PORT_FORWARD_PID 2>/dev/null || true
    fi
}
trap cleanup_port_forward EXIT

# Wait for port-forward to be ready (tunnel can take a few seconds to establish)
log_info "Waiting for port-forward to be ready..."
sleep 3
max_wait=60
elapsed=0
while ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/api/version" 2>/dev/null | grep -q "200\|401\|403"; do
    sleep 1
    ((elapsed += 1))
    if [[ $elapsed -ge $max_wait ]]; then
        log_error "Port-forward failed to start within ${max_wait}s"
        echo "  Check: kubectl get pods -n ${OSMO_NS} -l app=osmo-service"
        exit 1
    fi
done
log_success "Port-forward ready"

# Login (no-op when bypassing Envoy -- curl headers handle auth)
osmo_login 8080 || exit 1

# -----------------------------------------------------------------------------
# Get Storage Credentials
# -----------------------------------------------------------------------------
log_info "Retrieving storage credentials..."

# Get access key from Terraform
S3_ACCESS_KEY=$(get_tf_output "storage_credentials.access_key_id" "../001-iac" 2>/dev/null || echo "")

# Get secret key from osmo-storage secret (already created)
S3_SECRET_KEY=$(kubectl get secret osmo-storage -n osmo -o jsonpath='{.data.secret-access-key}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

if [[ -z "$S3_ACCESS_KEY" || -z "$S3_SECRET_KEY" ]]; then
    log_error "Could not retrieve storage credentials"
    exit 1
fi

# Nebius Object Storage uses S3-compatible API
# OSMO uses TOS (Torch Object Storage) scheme for S3-compatible storage with custom endpoints
# Format: tos://<endpoint>/<bucket>
S3_HOST=$(echo "$S3_ENDPOINT" | sed 's|https://||')
BACKEND_URI="tos://${S3_HOST}/${S3_BUCKET}"
REGION="${NEBIUS_REGION}"

log_success "Storage credentials retrieved"

# -----------------------------------------------------------------------------
# Configure Workflow Log Storage in OSMO
# -----------------------------------------------------------------------------
log_info "Configuring workflow log storage..."

# Create workflow log config JSON
WORKFLOW_LOG_CONFIG=$(cat <<EOF
{
  "workflow_log": {
    "credential": {
      "endpoint": "${BACKEND_URI}",
      "access_key_id": "${S3_ACCESS_KEY}",
      "access_key": "${S3_SECRET_KEY}",
      "region": "${REGION}"
    }
  }
}
EOF
)

# Write to temp file for osmo CLI
echo "$WORKFLOW_LOG_CONFIG" > /tmp/workflow_log_config.json

if osmo_config_update WORKFLOW /tmp/workflow_log_config.json "Configure workflow log storage"; then
    log_success "Workflow log storage configured"
else
    log_error "Failed to configure workflow log storage"
    rm -f /tmp/workflow_log_config.json
    exit 1
fi

# -----------------------------------------------------------------------------
# Configure Workflow Data Storage in OSMO
# -----------------------------------------------------------------------------
log_info "Configuring workflow data storage..."

# Create workflow data config JSON
WORKFLOW_DATA_CONFIG=$(cat <<EOF
{
  "workflow_data": {
    "credential": {
      "endpoint": "${BACKEND_URI}",
      "access_key_id": "${S3_ACCESS_KEY}",
      "access_key": "${S3_SECRET_KEY}",
      "region": "${REGION}"
    }
  }
}
EOF
)

# Write to temp file for osmo CLI
echo "$WORKFLOW_DATA_CONFIG" > /tmp/workflow_data_config.json

if osmo_config_update WORKFLOW /tmp/workflow_data_config.json "Configure workflow data storage"; then
    log_success "Workflow data storage configured"
else
    log_error "Failed to configure workflow data storage"
    rm -f /tmp/workflow_log_config.json /tmp/workflow_data_config.json
    exit 1
fi

# Cleanup temp files
rm -f /tmp/workflow_log_config.json /tmp/workflow_data_config.json

# -----------------------------------------------------------------------------
# Configure Workflow Limits
# -----------------------------------------------------------------------------
log_info "Configuring workflow limits (max_num_tasks=200)..."

WORKFLOW_LIMITS_CONFIG=$(cat <<EOF
{
  "max_num_tasks": 200
}
EOF
)

echo "$WORKFLOW_LIMITS_CONFIG" > /tmp/workflow_limits_config.json

if osmo_config_update WORKFLOW /tmp/workflow_limits_config.json "Configure workflow limits"; then
    log_success "Workflow limits configured (max_num_tasks=200)"
else
    log_warning "Failed to configure workflow limits (may require newer OSMO version)"
fi

rm -f /tmp/workflow_limits_config.json

# -----------------------------------------------------------------------------
# Verify Configuration
# -----------------------------------------------------------------------------
log_info "Verifying storage configuration..."

echo ""
echo "Workflow configuration:"
osmo_curl GET "http://localhost:8080/api/configs/workflow" 2>/dev/null | jq '.' || \
    log_warning "Could not retrieve workflow config for verification"

# Cleanup
cleanup_port_forward
trap - EXIT

echo ""
echo "========================================"
log_success "OSMO Storage configuration complete!"
echo "========================================"
echo ""
echo "Storage Details:"
echo "  Bucket: ${S3_BUCKET}"
echo "  Endpoint: ${S3_ENDPOINT}"
echo "  Backend URI: ${BACKEND_URI}"
echo "  Region: ${REGION}"
echo ""
echo "Configured:"
echo "  - workflow_log: For storing workflow logs"
echo "  - workflow_data: For storing intermediate task data"
echo ""
echo "OSMO can now store workflow artifacts in Nebius Object Storage."
echo ""
