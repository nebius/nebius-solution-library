#!/bin/bash
#
# Common functions for setup scripts
#

# Colors
export RED='\033[0;31m'
export GREEN='\033[0;32m'
export YELLOW='\033[1;33m'
export BLUE='\033[0;34m'
export NC='\033[0m'

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Read input with a prompt into a variable (bash/zsh compatible).
read_prompt_var() {
    local prompt=$1
    local var_name=$2
    local default=$3
    local value=""
    local read_from="/dev/tty"
    local write_to="/dev/tty"

    if [[ ! -r "/dev/tty" || ! -w "/dev/tty" ]]; then
        read_from="/dev/stdin"
        write_to="/dev/stdout"
    fi

    if [[ -n "$default" ]]; then
        printf "%s [%s]: " "$prompt" "$default" >"$write_to"
    else
        printf "%s: " "$prompt" >"$write_to"
    fi

    IFS= read -r value <"$read_from"
    if [[ -z "$value" && -n "$default" ]]; then
        value="$default"
    fi

    eval "$var_name='$value'"
}

# Read a secret value into a variable (no echo).
read_secret_var() {
    local prompt=$1
    local var_name=$2
    local value=""
    local read_from="/dev/tty"
    local write_to="/dev/tty"

    if [[ ! -r "/dev/tty" || ! -w "/dev/tty" ]]; then
        read_from="/dev/stdin"
        write_to="/dev/stdout"
    fi

    printf "%s: " "$prompt" >"$write_to"
    stty -echo <"$read_from"
    IFS= read -r value <"$read_from"
    stty echo <"$read_from"
    printf "\n" >"$write_to"

    eval "$var_name='$value'"
}

# Check if command exists
check_command() {
    command -v "$1" &>/dev/null
}

# Retry with exponential backoff
retry_with_backoff() {
    local max_attempts=${1:-5}
    local delay=${2:-2}
    local max_delay=${3:-60}
    shift 3
    local cmd=("$@")
    
    local attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        log_info "Attempt $attempt/$max_attempts: ${cmd[*]}"
        if "${cmd[@]}"; then
            return 0
        fi
        
        if [[ $attempt -lt $max_attempts ]]; then
            log_warning "Failed, retrying in ${delay}s..."
            sleep "$delay"
            delay=$((delay * 2))
            if [[ $delay -gt $max_delay ]]; then
                delay=$max_delay
            fi
        fi
        ((attempt++))
    done
    
    log_error "All $max_attempts attempts failed"
    return 1
}

# Wait for a condition with timeout
wait_for_condition() {
    local description=$1
    local timeout=${2:-300}
    local interval=${3:-10}
    shift 3
    local cmd=("$@")
    
    log_info "Waiting for $description (timeout: ${timeout}s)..."
    
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if "${cmd[@]}" &>/dev/null; then
            log_success "$description"
            return 0
        fi
        sleep "$interval"
        ((elapsed += interval))
        echo -n "."
    done
    
    echo ""
    log_error "Timeout waiting for $description"
    return 1
}

# Check kubectl connection and verify we're targeting the correct cluster
check_kubectl() {
    if ! check_command kubectl; then
        log_error "kubectl not found"
        return 1
    fi

    if ! kubectl cluster-info &>/dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        return 1
    fi

    # Verify current context matches the expected cluster from Terraform
    local expected_cluster
    expected_cluster=$(get_tf_output "cluster_name" "../001-iac" 2>/dev/null || true)
    if [[ -n "$expected_cluster" ]]; then
        local current_context
        current_context=$(kubectl config current-context 2>/dev/null || true)
        if [[ -n "$current_context" && "$current_context" != *"$expected_cluster"* ]]; then
            log_error "Wrong Kubernetes context!"
            log_error "  Current context: $current_context"
            log_error "  Expected cluster: $expected_cluster"
            log_info "Switch context with: nebius mk8s cluster get-credentials --id \$(terraform -chdir=../001-iac output -raw cluster_id) --external"
            return 1
        fi
        log_success "kubectl connected to cluster ($expected_cluster)"
    else
        log_success "kubectl connected to cluster"
    fi
    return 0
}

# Check Helm
check_helm() {
    if ! check_command helm; then
        log_error "helm not found"
        return 1
    fi
    
    log_success "helm available"
    return 0
}

# Install Helm chart with retry
helm_install() {
    local name=$1
    local chart=$2
    local namespace=$3
    shift 3
    local extra_args=("$@")
    
    log_info "Installing Helm chart: $name"
    
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
    
    retry_with_backoff 3 5 30 helm upgrade --install "$name" "$chart" \
        --namespace "$namespace" \
        --wait --timeout 10m \
        "${extra_args[@]}"
}

# Wait for pods to be ready
wait_for_pods() {
    local namespace=$1
    local label_selector=$2
    local timeout=${3:-300}
    
    wait_for_condition "pods with label $label_selector in $namespace" \
        "$timeout" 10 \
        kubectl wait --for=condition=Ready pods \
            -n "$namespace" \
            -l "$label_selector" \
            --timeout=10s
}

# Detect OSMO service URL from the NGINX Ingress Controller's LoadBalancer.
#
# When OSMO_TLS_ENABLED=true and OSMO_INGRESS_HOSTNAME is set, returns
# https://<hostname>. Otherwise falls back to http://<ip>.
#
# Lookup order:
#   0. If TLS enabled + hostname set, return https://<hostname> immediately
#   1. LoadBalancer external IP   (cloud assigns a public/internal IP)
#   2. LoadBalancer hostname       (some clouds return a DNS name instead)
#   3. Controller ClusterIP        (fallback – works from inside the cluster)
#
# Usage:
#   url=$(detect_service_url)
#   [[ -n "$url" ]] && echo "OSMO reachable at $url"
detect_service_url() {
    local ns="${INGRESS_NAMESPACE:-ingress-nginx}"
    local tls_enabled="${OSMO_TLS_ENABLED:-false}"
    local hostname="${OSMO_INGRESS_HOSTNAME:-}"
    local scheme="http"

    if [[ "$tls_enabled" == "true" ]]; then
        scheme="https"
        # If hostname is configured, prefer it (TLS certs are issued for the domain)
        if [[ -n "$hostname" ]]; then
            echo "${scheme}://${hostname}"
            return 0
        fi
    fi

    # Find the controller service (works for the community ingress-nginx chart)
    local lb_ip lb_host cluster_ip svc_name
    svc_name=$(kubectl get svc -n "$ns" \
        -l app.kubernetes.io/name=ingress-nginx,app.kubernetes.io/component=controller \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

    if [[ -n "$svc_name" ]]; then
        # 1. LoadBalancer IP
        lb_ip=$(kubectl get svc "$svc_name" -n "$ns" \
            -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
        if [[ -n "$lb_ip" ]]; then
            echo "${scheme}://${lb_ip}"
            return 0
        fi

        # 2. LoadBalancer hostname (e.g. ELB on AWS)
        lb_host=$(kubectl get svc "$svc_name" -n "$ns" \
            -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)
        if [[ -n "$lb_host" ]]; then
            echo "${scheme}://${lb_host}"
            return 0
        fi

        # 3. ClusterIP of the controller
        cluster_ip=$(kubectl get svc "$svc_name" -n "$ns" \
            -o jsonpath='{.spec.clusterIP}' 2>/dev/null || true)
        if [[ -n "$cluster_ip" && "$cluster_ip" != "None" ]]; then
            echo "${scheme}://${cluster_ip}"
            return 0
        fi
    fi

    # Nothing found
    return 1
}

# Get Terraform output (supports nested values like "postgresql.host")
get_tf_output() {
    local name=$1
    local tf_dir=${2:-../001-iac}
    
    # Check if name contains a dot (nested value)
    if [[ "$name" == *.* ]]; then
        local base_name="${name%%.*}"
        local key="${name#*.}"
        terraform -chdir="$tf_dir" output -json "$base_name" 2>/dev/null | jq -r ".$key // empty"
    else
        terraform -chdir="$tf_dir" output -json "$name" 2>/dev/null | jq -r '. // empty'
    fi
}

# Get Nebius CLI path
get_nebius_path() {
    if command -v nebius &>/dev/null; then
        command -v nebius
    elif [[ -x "$HOME/.nebius/bin/nebius" ]]; then
        echo "$HOME/.nebius/bin/nebius"
    fi
}

# Read secret from Nebius MysteryBox
# Usage: get_mysterybox_secret <secret_id> <key>
# Returns the secret value or empty string if not found
get_mysterybox_secret() {
    local secret_id=$1
    local key=$2
    local nebius_path=$(get_nebius_path)
    
    if [[ -z "$nebius_path" ]]; then
        log_warning "Nebius CLI not found, cannot read from MysteryBox"
        return 1
    fi
    
    if [[ -z "$secret_id" ]]; then
        return 1
    fi
    
    local result=$("$nebius_path" mysterybox v1 payload get-by-key \
        --secret-id "$secret_id" \
        --key "$key" \
        --format json 2>/dev/null)
    
    if [[ -n "$result" ]]; then
        echo "$result" | jq -r '.data.string_value // empty' 2>/dev/null
    fi
}

# -----------------------------------------------------------------------------
# OSMO API helpers (for use when Envoy auth sidecar is present)
# -----------------------------------------------------------------------------
# Per OSMO documentation, the OSMO service authorises requests by reading
# the x-osmo-user and x-osmo-roles headers.  Envoy normally sets these from
# the JWT but when we bypass Envoy (port-forward to pod:8000) we must set
# them ourselves.
#
# Reference: https://nvidia.github.io/OSMO/main/deployment_guide/appendix/authentication/authentication_flow.html

# Detect if a pod has an Envoy sidecar container
# Usage: has_envoy_sidecar <namespace> <label-selector>
# Returns 0 (true) if envoy container is found, 1 (false) otherwise
has_envoy_sidecar() {
    local ns="$1"
    local label="$2"
    local pod_name
    pod_name=$(kubectl get pod -n "$ns" -l "$label" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [[ -z "$pod_name" ]]; then
        return 1
    fi
    kubectl get pod -n "$ns" "$pod_name" -o jsonpath='{.spec.containers[*].name}' 2>/dev/null | grep -q envoy
}

# Start a port-forward that bypasses Envoy when the sidecar is present.
# Sets PORT_FORWARD_PID and prints log messages.
# Usage: start_osmo_port_forward <namespace> [local_port]
start_osmo_port_forward() {
    local ns="${1:-osmo}"
    local local_port="${2:-8080}"

    if has_envoy_sidecar "$ns" "app=osmo-service"; then
        local pod_name
        # Prefer a Running pod so we don't port-forward to one stuck in ContainerCreating
        pod_name=$(kubectl get pod -n "$ns" -l app=osmo-service --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        [[ -z "$pod_name" ]] && pod_name=$(kubectl get pod -n "$ns" -l app=osmo-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        log_info "Envoy sidecar detected -- port-forwarding to pod/${pod_name}:8000 (bypassing auth)..."
        kubectl port-forward -n "$ns" "pod/${pod_name}" "${local_port}:8000" &>/dev/null &
        _OSMO_AUTH_BYPASS=true
    else
        log_info "No Envoy sidecar -- port-forwarding to svc/osmo-service:80..."
        kubectl port-forward -n "$ns" svc/osmo-service "${local_port}:80" &>/dev/null &
        _OSMO_AUTH_BYPASS=false
    fi
    PORT_FORWARD_PID=$!
    export _OSMO_AUTH_BYPASS
}

# Make an authenticated curl call to the OSMO API.
# When _OSMO_AUTH_BYPASS=true (Envoy bypassed), injects x-osmo-user and
# x-osmo-roles headers so the OSMO service authorises the request.
# Usage: osmo_curl <method> <url> [curl-args...]
# Example: osmo_curl GET "http://localhost:8080/api/configs/service"
# Example: osmo_curl PATCH "http://localhost:8080/api/configs/service" -d '{"configs_dict":{...}}'
osmo_curl() {
    local method="$1"; shift
    local url="$1"; shift

    local auth_args=()
    if [[ "${_OSMO_AUTH_BYPASS:-false}" == "true" ]]; then
        auth_args+=(-H "x-osmo-user: osmo-admin" -H "x-osmo-roles: osmo-admin,osmo-user")
    fi

    curl -s -X "$method" "$url" \
        -H "Content-Type: application/json" \
        "${auth_args[@]}" \
        "$@"
}

# Log in to OSMO using the appropriate method.
# When bypassing Envoy this is a no-op (curl headers handle auth).
# Otherwise uses `osmo login --method dev`.
# Usage: osmo_login [port]
osmo_login() {
    local port="${1:-8080}"
    if [[ "${_OSMO_AUTH_BYPASS:-false}" == "true" ]]; then
        log_info "Auth bypass active -- using direct API headers (osmo-admin role)"
    else
        log_info "Logging in to OSMO..."
        if ! osmo login "http://localhost:${port}" --method dev --username admin 2>/dev/null; then
            log_error "Failed to login to OSMO"
            return 1
        fi
        log_success "Logged in successfully"
    fi
}

# Update an OSMO config via the PATCH API (partial merge).
# When _OSMO_AUTH_BYPASS=true, uses curl; otherwise uses osmo CLI.
# Usage: osmo_config_update <CONFIG_TYPE> <json_file> <description>
# Example: osmo_config_update WORKFLOW /tmp/config.json "Configure storage"
osmo_config_update() {
    local config_type="$1"
    local json_file="$2"
    local description="${3:-Update config}"
    local port="${4:-8080}"

    if [[ "${_OSMO_AUTH_BYPASS:-false}" == "true" ]]; then
        local endpoint
        endpoint="api/configs/$(echo "$config_type" | tr '[:upper:]' '[:lower:]')"

        # Build PATCH request body: {"description": "...", "configs_dict": <file-contents>}
        local body
        body=$(jq -n --arg desc "$description" --slurpfile cfg "$json_file" \
            '{description: $desc, configs_dict: $cfg[0]}')

        local http_code
        http_code=$(osmo_curl PATCH "http://localhost:${port}/${endpoint}" \
            -d "$body" -o /tmp/_osmo_patch_resp.txt -w "%{http_code}")

        if [[ "$http_code" =~ ^2 ]]; then
            return 0
        else
            log_error "PATCH /${endpoint} returned HTTP ${http_code}"
            cat /tmp/_osmo_patch_resp.txt 2>/dev/null || true
            return 1
        fi
    else
        osmo config update "$config_type" --file "$json_file" --description "$description" 2>/dev/null
    fi
}
