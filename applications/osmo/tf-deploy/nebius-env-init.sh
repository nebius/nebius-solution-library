#!/bin/bash
#
# Nebius environment initialization for the tf-deploy workflow.
#
# Run with:
#   source ./nebius-env-init.sh
#
# This script is intentionally self-contained under applications/osmo/tf-deploy.
# It does not depend on anything under applications/osmo/deploy.
#

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Run this script with: source ./nebius-env-init.sh" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NEBIUS_TENANT_ID="${NEBIUS_TENANT_ID:-tenant-<your-tenant-id>}"
NEBIUS_PROJECT_ID="${NEBIUS_PROJECT_ID:-project-<your-project-id>}"
NEBIUS_REGION="${NEBIUS_REGION:-<your-region>}"

# For short-lived testing, prefer explicit nip.io hostnames:
#   OSMO_INGRESS_HOSTNAME="osmo.<ingress-lb-ip>.nip.io"
#   KEYCLOAK_HOSTNAME="auth-osmo.<ingress-lb-ip>.nip.io"
# If you own a real DNS zone, you can instead set OSMO_BASE_DOMAIN and let
# this script derive hostnames from the project id suffix.
OSMO_BASE_DOMAIN="${OSMO_BASE_DOMAIN:-nip.io}"
OSMO_INGRESS_HOSTNAME="${OSMO_INGRESS_HOSTNAME:-}"
KEYCLOAK_HOSTNAME="${KEYCLOAK_HOSTNAME:-}"

NEBIUS_NETWORK_ID="${NEBIUS_NETWORK_ID:-}"
NEBIUS_SUBNET_ID="${NEBIUS_SUBNET_ID:-}"

KUBECONFIG_CONTEXT="${KUBECONFIG_CONTEXT:-}"

_tf_deploy_info() {
    if [[ "${TF_DEPLOY_ENV_INIT_QUIET:-0}" == "1" ]]; then
        return 0
    fi
    printf '[INFO] %s\n' "$*"
}

_tf_deploy_warn() {
    printf '[WARN] %s\n' "$*" >&2
}

_tf_deploy_error() {
    printf '[ERROR] %s\n' "$*" >&2
}

_tf_deploy_require_id() {
    local name="$1"
    local value="$2"
    local pattern="$3"

    if [[ -z "$value" ]]; then
        _tf_deploy_error "${name} is not set. Edit the configuration block at the top of applications/osmo/tf-deploy/nebius-env-init.sh or export it before sourcing."
        return 1
    fi

    if [[ ! "$value" =~ $pattern ]]; then
        _tf_deploy_error "${name} has an unexpected format: ${value}"
        return 1
    fi

    return 0
}

_tf_deploy_export_optional_tf_var() {
    local name="$1"
    local value="$2"

    if [[ -n "$value" ]]; then
        export "${name}=${value}"
    else
        unset "${name}"
    fi
}

_tf_deploy_get_nebius_path() {
    if command -v nebius >/dev/null 2>&1; then
        command -v nebius
        return 0
    fi

    if [[ -x "$HOME/.nebius/bin/nebius" ]]; then
        printf '%s\n' "$HOME/.nebius/bin/nebius"
        return 0
    fi

    return 1
}

_tf_deploy_derive_hostnames() {
    if [[ "${OSMO_BASE_DOMAIN:-}" == "nip.io" && -z "${OSMO_INGRESS_HOSTNAME:-}" ]]; then
        return 0
    fi

    if [[ -z "${OSMO_INGRESS_HOSTNAME:-}" && -n "${NEBIUS_PROJECT_ID:-}" && -n "${OSMO_BASE_DOMAIN:-}" ]]; then
        OSMO_INGRESS_HOSTNAME="osmo-${NEBIUS_PROJECT_ID#project-}.${OSMO_BASE_DOMAIN}"
    fi

    if [[ -n "${OSMO_INGRESS_HOSTNAME:-}" && -z "${KEYCLOAK_HOSTNAME:-}" ]]; then
        KEYCLOAK_HOSTNAME="auth-${OSMO_INGRESS_HOSTNAME}"
    fi
}

_tf_deploy_discover_networking() {
    local nebius_bin="$1"
    local network_json=""
    local subnet_json=""

    if [[ -n "${NEBIUS_NETWORK_ID:-}" && -n "${NEBIUS_SUBNET_ID:-}" ]]; then
        return 0
    fi

    command -v jq >/dev/null 2>&1 || {
        _tf_deploy_warn "jq not found; skipping default network/subnet discovery"
        return 0
    }

    network_json="$("$nebius_bin" vpc v1 network list --parent-id "$NEBIUS_PROJECT_ID" --format json 2>/dev/null || true)"
    if [[ -z "${NEBIUS_NETWORK_ID:-}" && -n "${network_json}" ]]; then
        NEBIUS_NETWORK_ID="$(printf '%s' "$network_json" | jq -r '(.items // .) | map(select(.metadata.name | startswith("default"))) | .[0].metadata.id // empty' 2>/dev/null || true)"
    fi

    subnet_json="$("$nebius_bin" vpc v1 subnet list --parent-id "$NEBIUS_PROJECT_ID" --format json 2>/dev/null || true)"
    if [[ -z "${NEBIUS_SUBNET_ID:-}" && -n "${subnet_json}" ]]; then
        NEBIUS_SUBNET_ID="$(printf '%s' "$subnet_json" | jq -r '(.items // .) | map(select(.metadata.name | startswith("default"))) | .[0].metadata.id // empty' 2>/dev/null || true)"
    fi
}

_tf_deploy_export_vars() {
    export NEBIUS_TENANT_ID
    export NEBIUS_PROJECT_ID
    export NEBIUS_REGION
    export OSMO_BASE_DOMAIN
    export OSMO_INGRESS_HOSTNAME
    export KEYCLOAK_HOSTNAME
    export NEBIUS_NETWORK_ID
    export NEBIUS_SUBNET_ID
    export KUBECONFIG_CONTEXT

    export TF_VAR_tenant_id="$NEBIUS_TENANT_ID"
    export TF_VAR_parent_id="$NEBIUS_PROJECT_ID"
    export TF_VAR_region="$NEBIUS_REGION"
    _tf_deploy_export_optional_tf_var "TF_VAR_network_id" "$NEBIUS_NETWORK_ID"
    _tf_deploy_export_optional_tf_var "TF_VAR_subnet_id" "$NEBIUS_SUBNET_ID"
    _tf_deploy_export_optional_tf_var "TF_VAR_ingress_hostname" "$OSMO_INGRESS_HOSTNAME"
    _tf_deploy_export_optional_tf_var "TF_VAR_keycloak_hostname" "$KEYCLOAK_HOSTNAME"
    _tf_deploy_export_optional_tf_var "TF_VAR_kubeconfig_context" "$KUBECONFIG_CONTEXT"
}

if [[ "${TF_DEPLOY_ENV_INIT_EXPORT_ONLY:-0}" == "1" ]]; then
    _tf_deploy_derive_hostnames

    if [[ "${OSMO_BASE_DOMAIN:-}" == "nip.io" && -z "${OSMO_INGRESS_HOSTNAME:-}" ]]; then
        _tf_deploy_info "OSMO_BASE_DOMAIN is nip.io and no explicit hostname is set. Step 4 (prepare-app-prereqs.sh) will bootstrap ingress-nginx, discover the public IP, and derive nip.io hostnames automatically."
    fi

    if nebius_bin=$(_tf_deploy_get_nebius_path); then
        _tf_deploy_discover_networking "$nebius_bin"
    fi

    _tf_deploy_export_vars
    return 0
fi

_tf_deploy_main() {
    local nebius_bin=""

    _tf_deploy_require_id "NEBIUS_TENANT_ID" "$NEBIUS_TENANT_ID" '^tenant-[a-z0-9]+$' || return 1
    _tf_deploy_require_id "NEBIUS_PROJECT_ID" "$NEBIUS_PROJECT_ID" '^project-[a-z0-9]+$' || return 1

    _tf_deploy_derive_hostnames

    if nebius_bin=$(_tf_deploy_get_nebius_path); then
        if ! command -v nebius >/dev/null 2>&1; then
            local nebius_bin_dir
            nebius_bin_dir="$(dirname "$nebius_bin")"
            export PATH="${nebius_bin_dir}:$PATH"
        fi

        if "$nebius_bin" profile list >/dev/null 2>&1; then
            local detected_iam_token
            detected_iam_token="$("$nebius_bin" iam get-access-token 2>/dev/null || true)"
            export NEBIUS_IAM_TOKEN="${detected_iam_token}"
            if [[ -n "${NEBIUS_IAM_TOKEN:-}" ]]; then
                _tf_deploy_info "Nebius CLI authenticated; NEBIUS_IAM_TOKEN exported"
            else
                _tf_deploy_warn "Nebius CLI is installed but no IAM token could be obtained"
            fi

            _tf_deploy_discover_networking "$nebius_bin"
        else
            _tf_deploy_warn "Nebius CLI is installed but not authenticated. Run: nebius profile create"
        fi
    else
        _tf_deploy_warn "Nebius CLI not found. Install it before running the infra Terraform root."
    fi

    _tf_deploy_export_vars

    echo ""
    echo "tf-deploy environment ready:"
    echo "  NEBIUS_TENANT_ID      = ${NEBIUS_TENANT_ID}"
    echo "  NEBIUS_PROJECT_ID     = ${NEBIUS_PROJECT_ID}"
    echo "  NEBIUS_REGION         = ${NEBIUS_REGION}"
    echo "  NEBIUS_NETWORK_ID     = ${NEBIUS_NETWORK_ID:-<unset>}"
    echo "  NEBIUS_SUBNET_ID      = ${NEBIUS_SUBNET_ID:-<unset>}"
    echo "  OSMO_BASE_DOMAIN      = ${OSMO_BASE_DOMAIN:-<unset>}"
    echo "  OSMO_INGRESS_HOSTNAME = ${OSMO_INGRESS_HOSTNAME:-<unset>}"
    echo "  KEYCLOAK_HOSTNAME     = ${KEYCLOAK_HOSTNAME:-<unset>}"
    if [[ -n "${KUBECONFIG_CONTEXT:-}" ]]; then
        echo "  KUBECONFIG_CONTEXT    = ${KUBECONFIG_CONTEXT}"
    fi
    echo ""
    echo "Next steps:"
    echo "  1. terraform -chdir=./infra init && terraform -chdir=./infra apply"
    echo "  2. ./prepare-app-prereqs.sh"
    echo "  3. source ./nebius-env-init.sh && source ./osmo-sso.env && terraform init && terraform apply"
    echo ""
}

_tf_deploy_main
