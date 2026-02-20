#!/bin/bash
#
# Configure Nebius SSO as Identity Provider in Keycloak
# ARCHVTEAMS-1506: Replace default credentials with Nebius corporate SSO
#
# This script adds Nebius as an OIDC Identity Provider in the Keycloak osmo
# realm, enabling users to authenticate with their Nebius corporate credentials
# instead of local Keycloak username/password.
#
# Prerequisites:
#   - Keycloak deployed and accessible (run 04-deploy-osmo-control-plane.sh first)
#   - An OIDC client registered with Nebius IAM for this OSMO instance
#     (contact your Nebius account team or IAM admin)
#   - NEBIUS_SSO_CLIENT_ID and NEBIUS_SSO_CLIENT_SECRET environment variables set
#
# Usage:
#   export NEBIUS_SSO_CLIENT_ID="your-nebius-client-id"
#   export NEBIUS_SSO_CLIENT_SECRET="your-nebius-client-secret"
#   ./06-configure-nebius-sso.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
source "${SCRIPT_DIR}/defaults.sh"

echo ""
echo "========================================"
echo "  Nebius SSO Integration for OSMO"
echo "  (ARCHVTEAMS-1506)"
echo "========================================"
echo ""

check_kubectl || exit 1

OSMO_NAMESPACE="${OSMO_NAMESPACE:-osmo}"

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

NEBIUS_SSO_DISCOVERY_URL="${NEBIUS_SSO_DISCOVERY_URL:-https://auth.eu.nebius.com/.well-known/openid-configuration}"
NEBIUS_SSO_CLIENT_ID="${NEBIUS_SSO_CLIENT_ID:-}"
NEBIUS_SSO_CLIENT_SECRET="${NEBIUS_SSO_CLIENT_SECRET:-}"
NEBIUS_SSO_ALIAS="${NEBIUS_SSO_ALIAS:-nebius-sso}"
NEBIUS_SSO_DISPLAY_NAME="${NEBIUS_SSO_DISPLAY_NAME:-Nebius SSO}"
NEBIUS_SSO_DEFAULT_ROLE="${NEBIUS_SSO_DEFAULT_ROLE:-osmo-user}"
NEBIUS_SSO_DISABLE_LOCAL_LOGIN="${NEBIUS_SSO_DISABLE_LOCAL_LOGIN:-false}"

# Validate required inputs
if [[ -z "$NEBIUS_SSO_CLIENT_ID" ]]; then
    log_error "NEBIUS_SSO_CLIENT_ID is required."
    echo ""
    echo "  To obtain a client ID, register an OIDC client with your Nebius IAM admin."
    echo "  The redirect URI to register is:"
    echo ""
    AUTH_DOMAIN="${KEYCLOAK_HOSTNAME:-}"
    if [[ -z "$AUTH_DOMAIN" && -n "${OSMO_INGRESS_HOSTNAME:-}" ]]; then
        AUTH_DOMAIN="auth-${OSMO_INGRESS_HOSTNAME}"
    fi
    if [[ -n "$AUTH_DOMAIN" ]]; then
        echo "    https://${AUTH_DOMAIN}/realms/osmo/broker/${NEBIUS_SSO_ALIAS}/endpoint"
    else
        echo "    https://<your-keycloak-host>/realms/osmo/broker/${NEBIUS_SSO_ALIAS}/endpoint"
    fi
    echo ""
    echo "  Then set:"
    echo "    export NEBIUS_SSO_CLIENT_ID=<client-id>"
    echo "    export NEBIUS_SSO_CLIENT_SECRET=<client-secret>"
    echo ""
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Discover Nebius OIDC endpoints
# ─────────────────────────────────────────────────────────────────────────────
log_info "Fetching Nebius OIDC discovery document..."
OIDC_CONFIG=$(curl -sf "$NEBIUS_SSO_DISCOVERY_URL" 2>/dev/null || echo "")

if [[ -z "$OIDC_CONFIG" ]]; then
    log_error "Failed to fetch OIDC discovery from: $NEBIUS_SSO_DISCOVERY_URL"
    exit 1
fi

NEBIUS_ISSUER=$(echo "$OIDC_CONFIG" | jq -r '.issuer')
NEBIUS_AUTH_URL=$(echo "$OIDC_CONFIG" | jq -r '.authorization_endpoint')
NEBIUS_TOKEN_URL=$(echo "$OIDC_CONFIG" | jq -r '.token_endpoint')
NEBIUS_JWKS_URI=$(echo "$OIDC_CONFIG" | jq -r '.jwks_uri')

log_success "Nebius OIDC endpoints discovered:"
echo "  Issuer:    $NEBIUS_ISSUER"
echo "  Auth:      $NEBIUS_AUTH_URL"
echo "  Token:     $NEBIUS_TOKEN_URL"
echo "  JWKS:      $NEBIUS_JWKS_URI"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Get Keycloak admin token
# ─────────────────────────────────────────────────────────────────────────────
log_info "Obtaining Keycloak admin token..."

KC_ADMIN_PASS=$(kubectl get secret keycloak-admin-secret -n "${OSMO_NAMESPACE}" \
    -o jsonpath='{.data.password}' 2>/dev/null | base64 -d 2>/dev/null || echo "")

if [[ -z "$KC_ADMIN_PASS" ]]; then
    log_error "Could not retrieve Keycloak admin password from secret 'keycloak-admin-secret'"
    exit 1
fi

# Determine Keycloak URL (prefer external, fall back to port-forward)
AUTH_DOMAIN="${KEYCLOAK_HOSTNAME:-}"
if [[ -z "$AUTH_DOMAIN" && -n "${OSMO_INGRESS_HOSTNAME:-}" ]]; then
    AUTH_DOMAIN="auth-${OSMO_INGRESS_HOSTNAME}"
fi

if [[ -n "$AUTH_DOMAIN" ]]; then
    KC_BASE_URL="https://${AUTH_DOMAIN}"
else
    # Fall back to in-cluster via port-forward
    log_info "No external Keycloak hostname found, starting port-forward..."
    kubectl port-forward -n "${OSMO_NAMESPACE}" svc/keycloak 8081:80 &>/dev/null &
    KC_PF_PID=$!
    sleep 3
    KC_BASE_URL="http://localhost:8081"
    trap "kill $KC_PF_PID 2>/dev/null || true" EXIT
fi

KC_TOKEN=$(curl -sf -X POST "${KC_BASE_URL}/realms/master/protocol/openid-connect/token" \
    -d "client_id=admin-cli" \
    -d "username=admin" \
    -d "password=${KC_ADMIN_PASS}" \
    -d "grant_type=password" | jq -r '.access_token' 2>/dev/null || echo "")

if [[ -z "$KC_TOKEN" || "$KC_TOKEN" == "null" ]]; then
    log_error "Failed to obtain Keycloak admin token from ${KC_BASE_URL}"
    exit 1
fi
log_success "Keycloak admin token obtained"

# ─────────────────────────────────────────────────────────────────────────────
# Check if IdP already exists
# ─────────────────────────────────────────────────────────────────────────────
EXISTING_IDP=$(curl -sf "${KC_BASE_URL}/admin/realms/osmo/identity-provider/instances/${NEBIUS_SSO_ALIAS}" \
    -H "Authorization: Bearer $KC_TOKEN" 2>/dev/null || echo "")

if [[ -n "$EXISTING_IDP" && "$EXISTING_IDP" != *"error"* ]]; then
    log_warning "Identity provider '${NEBIUS_SSO_ALIAS}' already exists. Updating..."
    IDP_METHOD="PUT"
    IDP_URL="${KC_BASE_URL}/admin/realms/osmo/identity-provider/instances/${NEBIUS_SSO_ALIAS}"
else
    log_info "Creating identity provider '${NEBIUS_SSO_ALIAS}'..."
    IDP_METHOD="POST"
    IDP_URL="${KC_BASE_URL}/admin/realms/osmo/identity-provider/instances"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Configure Nebius as OIDC Identity Provider
# ─────────────────────────────────────────────────────────────────────────────
# Nebius requires PKCE (S256) and only supports authorization_code grant.
# Token endpoint auth: client_secret_basic

IDP_PAYLOAD=$(cat <<IDPEOF
{
  "alias": "${NEBIUS_SSO_ALIAS}",
  "displayName": "${NEBIUS_SSO_DISPLAY_NAME}",
  "providerId": "oidc",
  "enabled": true,
  "trustEmail": true,
  "storeToken": false,
  "addReadTokenRoleOnCreate": false,
  "firstBrokerLoginFlowAlias": "first broker login",
  "config": {
    "issuer": "${NEBIUS_ISSUER}",
    "authorizationUrl": "${NEBIUS_AUTH_URL}",
    "tokenUrl": "${NEBIUS_TOKEN_URL}",
    "jwksUrl": "${NEBIUS_JWKS_URI}",
    "clientId": "${NEBIUS_SSO_CLIENT_ID}",
    "clientSecret": "${NEBIUS_SSO_CLIENT_SECRET}",
    "clientAuthMethod": "client_secret_basic",
    "syncMode": "IMPORT",
    "validateSignature": "true",
    "useJwksUrl": "true",
    "pkceEnabled": "true",
    "pkceMethod": "S256",
    "defaultScope": "openid",
    "guiOrder": "1",
    "backchannelSupported": "false"
  }
}
IDPEOF
)

IDP_HTTP=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X "$IDP_METHOD" "$IDP_URL" \
    -H "Authorization: Bearer $KC_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$IDP_PAYLOAD" 2>/dev/null || echo "000")

if [[ "$IDP_HTTP" == "201" || "$IDP_HTTP" == "204" ]]; then
    log_success "Identity provider '${NEBIUS_SSO_ALIAS}' configured (HTTP $IDP_HTTP)"
else
    log_error "Failed to configure identity provider (HTTP $IDP_HTTP)"
    curl -sf -X "$IDP_METHOD" "$IDP_URL" \
        -H "Authorization: Bearer $KC_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$IDP_PAYLOAD" 2>&1 || true
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Configure attribute mappers
# ─────────────────────────────────────────────────────────────────────────────
log_info "Configuring attribute mappers..."

MAPPER_BASE_URL="${KC_BASE_URL}/admin/realms/osmo/identity-provider/instances/${NEBIUS_SSO_ALIAS}/mappers"

create_mapper() {
    local name="$1"
    local claim="$2"
    local attribute="$3"
    local mapper_type="${4:-oidc-user-attribute-idp-mapper}"

    local payload
    payload=$(cat <<MAPEOF
{
  "name": "${name}",
  "identityProviderAlias": "${NEBIUS_SSO_ALIAS}",
  "identityProviderMapper": "${mapper_type}",
  "config": {
    "syncMode": "INHERIT",
    "claim": "${claim}",
    "user.attribute": "${attribute}"
  }
}
MAPEOF
)

    local http_code
    http_code=$(curl -sf -o /dev/null -w "%{http_code}" \
        -X POST "$MAPPER_BASE_URL" \
        -H "Authorization: Bearer $KC_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null || echo "000")

    if [[ "$http_code" == "201" || "$http_code" == "204" ]]; then
        echo "  [OK] ${name}"
    elif [[ "$http_code" == "409" ]]; then
        echo "  [SKIP] ${name} (already exists)"
    else
        echo "  [WARN] ${name} (HTTP $http_code)"
    fi
}

create_mapper "email"      "email"              "email"
create_mapper "firstName"  "given_name"         "firstName"
create_mapper "lastName"   "family_name"        "lastName"
create_mapper "username"   "preferred_username"  "username"

# Hardcoded role mapper: assign default OSMO role to all SSO users
ROLE_MAPPER_PAYLOAD=$(cat <<RMEOF
{
  "name": "default-osmo-role",
  "identityProviderAlias": "${NEBIUS_SSO_ALIAS}",
  "identityProviderMapper": "hardcoded-role-idp-mapper",
  "config": {
    "syncMode": "INHERIT",
    "role": "${NEBIUS_SSO_DEFAULT_ROLE}"
  }
}
RMEOF
)

ROLE_HTTP=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X POST "$MAPPER_BASE_URL" \
    -H "Authorization: Bearer $KC_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$ROLE_MAPPER_PAYLOAD" 2>/dev/null || echo "000")

if [[ "$ROLE_HTTP" == "201" || "$ROLE_HTTP" == "204" ]]; then
    echo "  [OK] default-osmo-role -> ${NEBIUS_SSO_DEFAULT_ROLE}"
elif [[ "$ROLE_HTTP" == "409" ]]; then
    echo "  [SKIP] default-osmo-role (already exists)"
else
    echo "  [WARN] default-osmo-role (HTTP $ROLE_HTTP)"
fi

log_success "Attribute mappers configured"

# ─────────────────────────────────────────────────────────────────────────────
# Optionally disable local username/password login
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$NEBIUS_SSO_DISABLE_LOCAL_LOGIN" == "true" ]]; then
    log_info "Disabling local username/password login..."

    # Get current realm config, set loginWithEmailAllowed=false and
    # registrationAllowed=false to discourage local accounts.
    # The browser flow is left intact so SSO still works.
    REALM_UPDATE=$(cat <<RUEOF
{
  "registrationAllowed": false,
  "resetPasswordAllowed": false,
  "loginWithEmailAllowed": false,
  "duplicateEmailsAllowed": false
}
RUEOF
)

    REALM_HTTP=$(curl -sf -o /dev/null -w "%{http_code}" \
        -X PUT "${KC_BASE_URL}/admin/realms/osmo" \
        -H "Authorization: Bearer $KC_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$REALM_UPDATE" 2>/dev/null || echo "000")

    if [[ "$REALM_HTTP" == "204" ]]; then
        log_success "Local registration and password reset disabled"
    else
        log_warning "Could not update realm settings (HTTP $REALM_HTTP)"
    fi

    log_info "To fully remove the username/password form, configure the browser"
    log_info "authentication flow in Keycloak Admin > Authentication > Flows."
else
    log_info "Local username/password login remains enabled (set NEBIUS_SSO_DISABLE_LOCAL_LOGIN=true to disable)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Nebius SSO Configuration Complete"
echo "========================================"
echo ""
echo "  IdP Alias:       ${NEBIUS_SSO_ALIAS}"
echo "  Display Name:    ${NEBIUS_SSO_DISPLAY_NAME}"
echo "  Issuer:          ${NEBIUS_ISSUER}"
echo "  Client ID:       ${NEBIUS_SSO_CLIENT_ID}"
echo "  Default Role:    ${NEBIUS_SSO_DEFAULT_ROLE}"
echo "  Local Login:     $(if [[ "$NEBIUS_SSO_DISABLE_LOCAL_LOGIN" == "true" ]]; then echo "DISABLED"; else echo "enabled (fallback)"; fi)"
echo ""
echo "  Keycloak login page will now show a '${NEBIUS_SSO_DISPLAY_NAME}' button."
echo "  Users clicking it will be redirected to Nebius for authentication."
echo ""
echo "  Redirect URI registered with Nebius:"
if [[ -n "${AUTH_DOMAIN:-}" ]]; then
    echo "    https://${AUTH_DOMAIN}/realms/osmo/broker/${NEBIUS_SSO_ALIAS}/endpoint"
else
    echo "    <keycloak-url>/realms/osmo/broker/${NEBIUS_SSO_ALIAS}/endpoint"
fi
echo ""
log_success "Done"
