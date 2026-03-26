#!/bin/bash
#
# Terraform-driven post-install and app-configuration workflow for OSMO.
#

set -Eeuo pipefail

PORT_FORWARD_PID=""
PORT_FORWARD_LOG=""
PORT_FORWARD_PORT=""
OSMO_API_URL=""
OSMO_API_PORT=""
OSMO_AUTH_BYPASS="false"
CURRENT_PHASE="startup"
HANDLING_ERROR="false"

log() {
    printf '[INFO] %s\n' "$*"
}

warn() {
    printf '[WARN] %s\n' "$*" >&2
}

die() {
    printf '[ERROR] %s\n' "$*" >&2
    exit 1
}

handle_err() {
    local exit_code="$1"
    local line_no="$2"
    local cmd="$3"

    if [[ "${HANDLING_ERROR}" == "true" ]]; then
        exit "${exit_code}"
    fi

    HANDLING_ERROR="true"
    printf '[ERROR] Phase "%s" failed at line %s while running: %s\n' "${CURRENT_PHASE}" "${line_no}" "${cmd}" >&2
    exit "${exit_code}"
}

set_phase() {
    CURRENT_PHASE="$1"
    log "${CURRENT_PHASE}"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

make_temp_file() {
    local prefix="$1"
    local suffix="${2:-}"
    local tmp_dir="${TMPDIR:-/tmp}"
    local tmp_path=""

    tmp_dir="${tmp_dir%/}"
    tmp_path="$(mktemp "${tmp_dir}/${prefix}.XXXXXX")"
    if [[ -n "${suffix}" ]]; then
        mv "${tmp_path}" "${tmp_path}${suffix}"
        tmp_path="${tmp_path}${suffix}"
        : >"${tmp_path}"
    fi

    printf '%s\n' "${tmp_path}"
}

kubectl_cmd() {
    if [[ -n "${KUBECTL_CONTEXT:-}" ]]; then
        kubectl --context "${KUBECTL_CONTEXT}" "$@"
    else
        kubectl "$@"
    fi
}

normalize_bool() {
    case "${1:-false}" in
        true|TRUE|1|yes|YES|on|ON) echo "true" ;;
        *) echo "false" ;;
    esac
}

find_free_port() {
    local port="${1:-8080}"

    while :; do
        if ! lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "${port}"
            return 0
        fi
        port=$((port + 1))
    done
}

start_kubectl_port_forward() {
    local namespace="$1"
    local target="$2"
    local remote_port="$3"
    local preferred_local_port="${4:-8080}"
    local description="${5:-port-forward}"
    local local_port

    local_port="$(find_free_port "${preferred_local_port}")"
    PORT_FORWARD_LOG="$(make_temp_file "osmo-post-install-pf" ".log")"

    kubectl_cmd -n "${namespace}" port-forward "${target}" "${local_port}:${remote_port}" >"${PORT_FORWARD_LOG}" 2>&1 &
    PORT_FORWARD_PID=$!
    PORT_FORWARD_PORT="${local_port}"

    for _ in $(seq 1 50); do
        if ! kill -0 "${PORT_FORWARD_PID}" >/dev/null 2>&1; then
            cat "${PORT_FORWARD_LOG}" >&2 || true
            die "Failed to start ${description} on localhost:${local_port}"
        fi
        if grep -q "Forwarding from" "${PORT_FORWARD_LOG}" 2>/dev/null; then
            return 0
        fi
        sleep 0.2
    done

    cat "${PORT_FORWARD_LOG}" >&2 || true
    die "${description} did not become ready on localhost:${local_port}"
}

stop_port_forward() {
    if [[ -n "${PORT_FORWARD_PID}" ]] && kill -0 "${PORT_FORWARD_PID}" >/dev/null 2>&1; then
        kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
        wait "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
    fi

    if [[ -n "${PORT_FORWARD_LOG}" && -f "${PORT_FORWARD_LOG}" ]]; then
        rm -f "${PORT_FORWARD_LOG}"
    fi

    PORT_FORWARD_PID=""
    PORT_FORWARD_LOG=""
    PORT_FORWARD_PORT=""
}

cleanup() {
    stop_port_forward
}

trap 'handle_err $? "$LINENO" "$BASH_COMMAND"' ERR
trap cleanup EXIT

wait_for_http_ready() {
    local url="$1"
    local timeout="${2:-30}"
    local description="${3:-endpoint}"
    local end_time

    end_time=$((SECONDS + timeout))
    while (( SECONDS < end_time )); do
        if curl -fsS --max-time 5 "${url}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    die "${description} did not become ready at ${url}"
}

ensure_osmo_api_session() {
    if [[ -z "${OSMO_API_URL}" ]]; then
        start_osmo_api_session "${OSMO_NAMESPACE}"
        return 0
    fi

    if curl -fsS --max-time 5 "${OSMO_API_URL}/api/version" >/dev/null 2>&1; then
        return 0
    fi

    warn "Existing OSMO API session is no longer reachable; re-establishing port-forward"
    stop_port_forward
    start_osmo_api_session "${OSMO_NAMESPACE}"
}

wait_for_rollout() {
    local deployment="$1"

    if kubectl_cmd get deployment "$deployment" -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        kubectl_cmd rollout status "deployment/${deployment}" -n "${OSMO_NAMESPACE}" --timeout=180s >/dev/null 2>&1 || \
            warn "${deployment} rollout did not complete before timeout"
    fi
}

has_envoy_sidecar() {
    local namespace="$1"
    local pod_name

    pod_name="$(kubectl_cmd get pod -n "${namespace}" -l app=osmo-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    [[ -n "${pod_name}" ]] || return 1

    kubectl_cmd get pod -n "${namespace}" "${pod_name}" -o jsonpath='{.spec.containers[*].name}' 2>/dev/null | grep -q 'envoy'
}

start_osmo_api_session() {
    local namespace="${1:-osmo}"
    local pod_name

    if has_envoy_sidecar "${namespace}"; then
        pod_name="$(kubectl_cmd get pod -n "${namespace}" -l app=osmo-service --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
        [[ -n "${pod_name}" ]] || pod_name="$(kubectl_cmd get pod -n "${namespace}" -l app=osmo-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
        [[ -n "${pod_name}" ]] || die "Could not find an osmo-service pod for API access"
        start_kubectl_port_forward "${namespace}" "pod/${pod_name}" 8000 8080 "OSMO API"
        OSMO_AUTH_BYPASS="true"
    else
        start_kubectl_port_forward "${namespace}" "svc/osmo-service" 80 8080 "OSMO API"
        OSMO_AUTH_BYPASS="false"
    fi

    wait_for_http_ready "http://localhost:${PORT_FORWARD_PORT}/api/version" 60 "OSMO API"
    OSMO_API_PORT="${PORT_FORWARD_PORT}"
    OSMO_API_URL="http://localhost:${OSMO_API_PORT}"
}

osmo_curl() {
    local method="$1"
    local url="$2"
    shift 2

    ensure_osmo_api_session

    local auth_args=()
    if [[ "${OSMO_AUTH_BYPASS}" == "true" ]]; then
        auth_args+=(-H "x-osmo-user: osmo-admin" -H "x-osmo-roles: osmo-admin,osmo-user")
    fi

    curl -sS \
        --connect-timeout 5 \
        --max-time 180 \
        -X "${method}" "${url}" \
        -H "Content-Type: application/json" \
        "${auth_args[@]}" \
        "$@"
}

sql_escape_literal() {
    printf '%s' "$1" | sed "s/'/''/g"
}

run_osmo_postgres_sql() {
    local sql="$1"
    local run_name

    run_name="osmo-psql-${RANDOM}${RANDOM}"
    kubectl_cmd run "${run_name}" \
      --rm --restart=Never -i \
      -n "${OSMO_NAMESPACE}" \
      --image=postgres:16-alpine \
      --env="PGPASSWORD=${POSTGRES_PASSWORD}" \
      --command -- \
      psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -v ON_ERROR_STOP=1 \
        -qAtc "${sql}"
}

upsert_osmo_config_value_db() {
    local config_type="$1"
    local key="$2"
    local value="$3"
    local escaped_type
    local escaped_key
    local escaped_value

    escaped_type="$(sql_escape_literal "${config_type}")"
    escaped_key="$(sql_escape_literal "${key}")"
    escaped_value="$(sql_escape_literal "${value}")"

    run_osmo_postgres_sql "with updated as (
        update configs
           set value = '${escaped_value}'
         where type = '${escaped_type}'
           and key = '${escaped_key}'
     returning 1
    )
    insert into configs(key, value, type)
    select '${escaped_key}', '${escaped_value}', '${escaped_type}'
     where not exists (select 1 from updated);" >/dev/null
}

delete_osmo_config_value_db() {
    local config_type="$1"
    local key="$2"
    local escaped_type
    local escaped_key

    escaped_type="$(sql_escape_literal "${config_type}")"
    escaped_key="$(sql_escape_literal "${key}")"

    run_osmo_postgres_sql "delete from configs where type = '${escaped_type}' and key = '${escaped_key}';" >/dev/null
}

osmo_config_key_exists_db() {
    local config_type="$1"
    local key="$2"
    local escaped_type
    local escaped_key
    local value

    escaped_type="$(sql_escape_literal "${config_type}")"
    escaped_key="$(sql_escape_literal "${key}")"

    value="$(run_osmo_postgres_sql "select value from configs where type = '${escaped_type}' and key = '${escaped_key}' limit 1;" 2>/dev/null || true)"
    [[ -n "${value}" ]]
}

osmo_service_config_key_exists() {
    local key="$1"

    osmo_config_key_exists_db "SERVICE" "${key}"
}

delete_osmo_service_auth_db() {
    delete_osmo_config_value_db "SERVICE" "service_auth"
}

wait_for_service_auth_regeneration() {
    local end_time

    end_time=$((SECONDS + 120))
    while (( SECONDS < end_time )); do
        if osmo_service_config_key_exists "service_auth"; then
            return 0
        fi
        sleep 5
    done

    return 1
}

patch_vault_mounts() {
    local deploy
    local patch_file

    patch_file="$(make_temp_file "osmo-vault-patch" ".json")"
    trap 'rm -f "${patch_file}"' RETURN

    cat >"${patch_file}" <<'EOF'
[
  {"op": "add", "path": "/spec/template/spec/volumes/-", "value": {"name": "vault-secrets", "secret": {"secretName": "vault-secrets"}}},
  {"op": "add", "path": "/spec/template/spec/containers/0/volumeMounts/-", "value": {"name": "vault-secrets", "mountPath": "/home/osmo/vault-agent/secrets", "readOnly": true}}
]
EOF

    for deploy in osmo-service osmo-worker osmo-agent osmo-logger osmo-delayed-job-monitor osmo-router; do
        if ! kubectl_cmd get deployment "$deploy" -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
            continue
        fi

        if kubectl_cmd get deployment "$deploy" -n "${OSMO_NAMESPACE}" -o jsonpath='{.spec.template.spec.volumes[*].name}' 2>/dev/null | tr ' ' '\n' | grep -qx "vault-secrets"; then
            continue
        fi

        log "Patching ${deploy} with vault-secrets volume"
        kubectl_cmd patch deployment "$deploy" -n "${OSMO_NAMESPACE}" --type=json --patch-file="${patch_file}" >/dev/null
    done
}

ensure_service_ingress_timeouts() {
    if kubectl_cmd get ingress osmo-service -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        kubectl_cmd patch ingress osmo-service -n "${OSMO_NAMESPACE}" --type=merge \
          -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/proxy-read-timeout":"300","nginx.ingress.kubernetes.io/proxy-send-timeout":"300","nginx.ingress.kubernetes.io/proxy-connect-timeout":"60"}}}' >/dev/null 2>&1 || true
    fi
}

ensure_ui_trpc_rewrite() {
    local current_snippets
    local current_risk

    if [[ "${DEPLOY_UI}" != "true" ]]; then
        return 0
    fi

    if ! kubectl_cmd get configmap ingress-nginx-controller -n "${INGRESS_NAMESPACE}" >/dev/null 2>&1; then
        warn "ingress-nginx-controller ConfigMap not found; skipping UI ingress rewrite prep"
        return 0
    fi

    current_snippets="$(kubectl_cmd get configmap ingress-nginx-controller -n "${INGRESS_NAMESPACE}" -o jsonpath='{.data.allow-snippet-annotations}' 2>/dev/null || true)"
    current_risk="$(kubectl_cmd get configmap ingress-nginx-controller -n "${INGRESS_NAMESPACE}" -o jsonpath='{.data.annotations-risk-level}' 2>/dev/null || true)"

    if [[ "${current_snippets}" != "true" || "${current_risk}" != "Critical" ]]; then
        log "Enabling snippet annotations on ingress-nginx"
        kubectl_cmd patch configmap ingress-nginx-controller -n "${INGRESS_NAMESPACE}" \
          --type merge -p '{"data":{"allow-snippet-annotations":"true","annotations-risk-level":"Critical"}}' >/dev/null
        kubectl_cmd rollout restart deployment/ingress-nginx-controller -n "${INGRESS_NAMESPACE}" >/dev/null 2>&1 || true
        kubectl_cmd rollout status deployment/ingress-nginx-controller -n "${INGRESS_NAMESPACE}" --timeout=120s >/dev/null 2>&1 || true
    fi

    if kubectl_cmd get ingress osmo-ui-trpc -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        log "Patching osmo-ui-trpc ingress rewrite"
        # shellcheck disable=SC2016
        kubectl_cmd patch ingress osmo-ui-trpc -n "${OSMO_NAMESPACE}" --type merge \
          -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/configuration-snippet":"rewrite ^/api/trpc(/?.*)$ /trpc$1 break;\n"}}}' >/dev/null 2>&1 || true
    fi
}

ensure_ui_login_info_cache() {
    local scheme
    local tmp_body
    local body_path

    if [[ "${DEPLOY_UI}" != "true" ]]; then
        return 0
    fi

    if ! kubectl_cmd get deployment osmo-ui -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        return 0
    fi

    scheme="https"
    if [[ "${TLS_ENABLED}" != "true" ]]; then
        scheme="http"
    fi

    tmp_body="$(make_temp_file "osmo-login-info")"
    trap 'rm -f "${tmp_body}"' RETURN

    printf '%s' "{\"auth_enabled\":true,\"device_endpoint\":\"${scheme}://${AUTH_DOMAIN}/realms/osmo/protocol/openid-connect/auth/device\",\"device_client_id\":\"osmo-device\",\"browser_endpoint\":\"${scheme}://${AUTH_DOMAIN}/realms/osmo/protocol/openid-connect/auth\",\"browser_client_id\":\"osmo-browser-flow\",\"token_endpoint\":\"${scheme}://${AUTH_DOMAIN}/realms/osmo/protocol/openid-connect/token\",\"logout_endpoint\":\"${scheme}://${AUTH_DOMAIN}/realms/osmo/protocol/openid-connect/logout\"}" >"${tmp_body}"

    kubectl_cmd create configmap osmo-ui-login-info-cache \
      --from-file=login_info.body="${tmp_body}" \
      -n "${OSMO_NAMESPACE}" \
      --dry-run=client -o yaml | kubectl_cmd apply -f - >/dev/null

    body_path="/app/ui/standalone_server.runfiles/osmo_workspace+/ui/standalone_server/standalone/osmo_workspace+/ui/.next/server/app/auth/login_info.body"

    if ! kubectl_cmd get deployment osmo-ui -n "${OSMO_NAMESPACE}" -o jsonpath='{.spec.template.spec.volumes[*].name}' 2>/dev/null | tr ' ' '\n' | grep -qx "login-info-cache"; then
        log "Adding login_info cache mount to osmo-ui"
        kubectl_cmd patch deployment osmo-ui -n "${OSMO_NAMESPACE}" --type=strategic -p "{
          \"spec\":{\"template\":{\"spec\":{
            \"volumes\":[{\"name\":\"login-info-cache\",\"configMap\":{\"name\":\"osmo-ui-login-info-cache\"}}],
            \"containers\":[{\"name\":\"osmo-ui\",\"volumeMounts\":[{\"name\":\"login-info-cache\",\"mountPath\":\"${body_path}\",\"subPath\":\"login_info.body\"}]}]
          }}}}" >/dev/null 2>&1 || true
    fi
}

ensure_envoy_configmaps() {
    local cm
    local cfg
    local running_pod
    local tmp_cfg

    if [[ "${ENABLE_AUTH}" != "true" ]]; then
        return 0
    fi

    if ! kubectl_cmd get configmap osmo-service-envoy-config -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        running_pod="$(kubectl_cmd get pods -n "${OSMO_NAMESPACE}" -l app=osmo-service --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
        if [[ -n "${running_pod}" ]]; then
            tmp_cfg="$(make_temp_file "osmo-service-envoy")"
            trap 'rm -f "${tmp_cfg}"' RETURN
            kubectl_cmd exec -n "${OSMO_NAMESPACE}" "${running_pod}" -c envoy -- cat /var/config/config.yaml >"${tmp_cfg}" 2>/dev/null || true
            if [[ -s "${tmp_cfg}" ]]; then
                kubectl_cmd create configmap osmo-service-envoy-config -n "${OSMO_NAMESPACE}" --from-file=config.yaml="${tmp_cfg}" --dry-run=client -o yaml | kubectl_cmd apply -f - >/dev/null
            fi
        fi
    fi

    for cm in osmo-ui-envoy-config osmo-router-envoy-config osmo-service-envoy-config osmo-agent-envoy-config osmo-logger-envoy-config; do
        if ! kubectl_cmd get configmap "${cm}" -n "${OSMO_NAMESPACE}" -o json >/dev/null 2>&1; then
            continue
        fi

        cfg="$(kubectl_cmd get configmap "${cm}" -n "${OSMO_NAMESPACE}" -o json)"
        printf '%s' "${cfg}" | jq \
          --arg auth "${AUTH_DOMAIN}" \
          --arg host "${INGRESS_HOSTNAME}" \
          --arg early 'if (meta == nil or meta.verified_jwt == nil) then meta = { verified_jwt = {} } end' \
          --arg lua 'local roles = meta.verified_jwt.roles
                        if roles == nil then
                          local ra = meta.verified_jwt.realm_access
                          if ra ~= nil and ra.roles ~= nil then
                            roles = ra.roles
                          end
                        end
                        if roles == nil then
                          roles = {"osmo-user","osmo-admin"}
                        else
                          local has_osmo_user = false
                          local has_osmo_admin = false
                          for _, r in ipairs(roles) do
                            if r == "osmo-user" then has_osmo_user = true end
                            if r == "osmo-admin" then has_osmo_admin = true end
                          end
                          if not has_osmo_user then table.insert(roles, "osmo-user") end
                          if not has_osmo_admin then table.insert(roles, "osmo-admin") end
                        end
                        local roles_list = table.concat(roles, ",")
                        local user = request_handle:headers():get("x-osmo-user")
                        if user == nil or user == "" then
                          user = "osmo-admin"
                        end
                        request_handle:headers():replace("x-osmo-user", user)
                        request_handle:headers():replace("x-osmo-roles", roles_list)' \
          '.data["config.yaml"] |= (
            gsub("auth-osmo\\.local"; $auth) |
            gsub("osmo\\.local"; $host) |
            gsub("if \\(meta == nil or meta\\.verified_jwt == nil\\) then\\s+return\\s+end"; $early) |
            gsub("if \\(meta\\.verified_jwt == nil\\) then\\s+return\\s+end"; $early) |
            gsub("local roles_list = table.concat\\([^)]*\\)"; $lua)
          )' | kubectl_cmd apply -f - >/dev/null
    done
}

configure_service_base_url() {
    local run_name
    local sql
    local effective_service_base_url

    if [[ -z "${SERVICE_BASE_URL}" ]]; then
        warn "SERVICE_BASE_URL is empty; skipping service_base_url configuration"
        return 0
    fi

    effective_service_base_url="$(determine_workflow_service_base_url)"
    run_name="osmo-db-config-$(date +%s)"
    sql="with updated as (update configs set value = '${effective_service_base_url}' where type = 'SERVICE' and key = 'service_base_url' returning 1) insert into configs(key, value, type) select 'service_base_url', '${effective_service_base_url}', 'SERVICE' where not exists (select 1 from updated);"

    log "Configuring service_base_url=${effective_service_base_url}"
    kubectl_cmd delete pod "${run_name}" -n "${OSMO_NAMESPACE}" --ignore-not-found >/dev/null 2>&1 || true
    kubectl_cmd run "${run_name}" \
      --namespace "${OSMO_NAMESPACE}" \
      --image=postgres:16-alpine \
      --restart=Never \
      --env="PGPASSWORD=${POSTGRES_PASSWORD}" \
      --env="PGHOST=${POSTGRES_HOST}" \
      --env="PGPORT=${POSTGRES_PORT}" \
      --env="PGUSER=${POSTGRES_USER}" \
      --env="PGDATABASE=${POSTGRES_DB}" \
      --command -- sh -ceu "psql -v ON_ERROR_STOP=1 -c \"${sql}\"" >/dev/null

    if ! kubectl_cmd wait --for=jsonpath='{.status.phase}'=Succeeded "pod/${run_name}" -n "${OSMO_NAMESPACE}" --timeout=180s >/dev/null 2>&1; then
        kubectl_cmd logs "${run_name}" -n "${OSMO_NAMESPACE}" || true
        kubectl_cmd delete pod "${run_name}" -n "${OSMO_NAMESPACE}" --ignore-not-found >/dev/null 2>&1 || true
        die "Failed to configure service_base_url"
    fi

    kubectl_cmd delete pod "${run_name}" -n "${OSMO_NAMESPACE}" --ignore-not-found >/dev/null 2>&1 || true
}

determine_workflow_service_base_url() {
    if [[ -n "${WORKFLOW_SERVICE_BASE_URL:-}" ]]; then
        printf '%s\n' "${WORKFLOW_SERVICE_BASE_URL}"
        return 0
    fi

    printf '%s\n' "${SERVICE_BASE_URL}"
}

ensure_workflow_ingress_ca_secret() {
    local ca_secret_name="osmo-workflow-ingress-ca"
    local tmp_cert

    [[ "${TLS_ENABLED}" == "true" && "${TLS_MODE:-}" == "self-signed" ]] || return 0
    [[ -n "${WORKFLOWS_NAMESPACE:-}" ]] || die "WORKFLOWS_NAMESPACE is required for self-signed workflow TLS trust"
    [[ -n "${TLS_SECRET_NAME:-}" ]] || die "TLS_SECRET_NAME is required for self-signed workflow TLS trust"

    if ! kubectl_cmd get secret "${TLS_SECRET_NAME}" -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        die "TLS secret ${TLS_SECRET_NAME} was not found in namespace ${OSMO_NAMESPACE}"
    fi

    tmp_cert="$(make_temp_file "workflow-ingress-ca" ".crt")"
    kubectl_cmd get secret "${TLS_SECRET_NAME}" -n "${OSMO_NAMESPACE}" -o jsonpath='{.data.tls\.crt}' \
      | openssl base64 -d -A >"${tmp_cert}"

    if [[ ! -s "${tmp_cert}" ]]; then
        rm -f "${tmp_cert}"
        die "Failed to extract tls.crt from secret ${TLS_SECRET_NAME}"
    fi

    kubectl_cmd create secret generic "${ca_secret_name}" \
      --namespace "${WORKFLOWS_NAMESPACE}" \
      --from-file=ca.crt="${tmp_cert}" \
      --dry-run=client -o yaml | kubectl_cmd apply -f - >/dev/null

    rm -f "${tmp_cert}"
}

inject_workflow_ingress_ca_into_template() {
    local input_template="$1"
    local output_template="$2"
    local ca_secret_name="osmo-workflow-ingress-ca"
    local ca_mount_path="/opt/osmo/certs/osmo-ingress-ca.crt"

    if [[ "${TLS_ENABLED}" != "true" || "${TLS_MODE:-}" != "self-signed" ]]; then
        cp "${input_template}" "${output_template}"
        return 0
    fi

    ensure_workflow_ingress_ca_secret

    jq \
      --arg secret_name "${ca_secret_name}" \
      --arg mount_path "${ca_mount_path}" \
      '
      .configs.spec.volumes = (
        (.configs.spec.volumes // [])
        | map(select(.name != $secret_name))
        + [{
          name: $secret_name,
          secret: { secretName: $secret_name }
        }]
      )
      | .configs.spec.containers = (
          ((.configs.spec.containers // []) | map(
            if .name == "osmo-ctrl" then
              .env = (
                (.env // [])
                | map(select(.name != "SSL_CERT_FILE" and .name != "REQUESTS_CA_BUNDLE" and .name != "CURL_CA_BUNDLE"))
                + [
                  { name: "SSL_CERT_FILE", value: $mount_path },
                  { name: "REQUESTS_CA_BUNDLE", value: $mount_path },
                  { name: "CURL_CA_BUNDLE", value: $mount_path }
                ]
              )
              | .volumeMounts = (
                (.volumeMounts // [])
                | map(select(.name != $secret_name and .mountPath != $mount_path))
                + [{
                  name: $secret_name,
                  mountPath: $mount_path,
                  subPath: "ca.crt",
                  readOnly: true
                }]
              )
            else
              .
            end
          )) as $containers
          | if (($containers | map(.name) | index("osmo-ctrl")) == null) then
              $containers + [{
                name: "osmo-ctrl",
                env: [
                  { name: "SSL_CERT_FILE", value: $mount_path },
                  { name: "REQUESTS_CA_BUNDLE", value: $mount_path },
                  { name: "CURL_CA_BUNDLE", value: $mount_path }
                ],
                volumeMounts: [{
                  name: $secret_name,
                  mountPath: $mount_path,
                  subPath: "ca.crt",
                  readOnly: true
                }]
              }]
            else
              $containers
            end
        )
      ' "${input_template}" >"${output_template}"
}

normalize_storage_endpoint() {
    local endpoint="$1"

    endpoint="${endpoint%/}"
    [[ -n "${endpoint}" ]] || die "STORAGE_ENDPOINT must not be empty"

    if [[ "${endpoint}" =~ ^https://[^/:]+$ ]]; then
        printf '%s:443\n' "${endpoint}"
    else
        printf '%s\n' "${endpoint}"
    fi
}

probe_bucket_rw() {
    local bucket="$1"
    local endpoint="$2"
    local region="$3"
    local probe_key
    local run_name
    local probe_script
    local output

    probe_key="osmo-storage-probe-$(date +%s)-${RANDOM}"
    run_name="osmo-s3-probe-${RANDOM}${RANDOM}"
    probe_script=$(cat <<EOF
set -e
aws --endpoint-url "${endpoint}" s3api head-bucket --bucket "${bucket}" >/dev/null
aws --endpoint-url "${endpoint}" s3api put-object --bucket "${bucket}" --key "${probe_key}" --body /etc/hosts >/dev/null
aws --endpoint-url "${endpoint}" s3api delete-object --bucket "${bucket}" --key "${probe_key}" >/dev/null
echo S3_PROBE_OK
EOF
)

    if output="$(kubectl_cmd run "${run_name}" \
        --rm --restart=Never -i \
        -n "${OSMO_NAMESPACE}" \
        --image=amazon/aws-cli:2.15.0 \
        --env="AWS_ACCESS_KEY_ID=${STORAGE_ACCESS_KEY_ID}" \
        --env="AWS_SECRET_ACCESS_KEY=${STORAGE_SECRET_ACCESS_KEY}" \
        --env="AWS_DEFAULT_REGION=${region}" \
        --env="AWS_EC2_METADATA_DISABLED=true" \
        --command -- sh -lc "${probe_script}" 2>&1)"; then
        if grep -q "S3_PROBE_OK" <<<"${output}"; then
            return 0
        fi
    fi

    printf '%s\n' "${output}" >&2
    return 1
}

rollout_restart_if_present() {
    local deployment="$1"

    if kubectl_cmd get deployment "${deployment}" -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
        log "Restarting ${deployment} to reload updated config"
        kubectl_cmd rollout restart "deployment/${deployment}" -n "${OSMO_NAMESPACE}" >/dev/null
        kubectl_cmd rollout status "deployment/${deployment}" -n "${OSMO_NAMESPACE}" --timeout=300s >/dev/null || \
            warn "${deployment} rollout did not complete before timeout"
        if [[ "${RUN_APP_CONFIGURATION}" == "true" && "${deployment}" == "osmo-service" ]]; then
            ensure_osmo_api_session
        fi
    fi
}

refresh_service_auth_config() {
    local deploy

    log "Refreshing internal OSMO service auth config"
    if ! delete_osmo_service_auth_db; then
        warn "Could not refresh SERVICE service_auth; workflow runtime auth may still fail until rerun"
        return 1
    fi

    log "Restarting osmo-service so it can regenerate service_auth"
    kubectl_cmd rollout restart "deployment/osmo-service" -n "${OSMO_NAMESPACE}" >/dev/null
    kubectl_cmd rollout status "deployment/osmo-service" -n "${OSMO_NAMESPACE}" --timeout=300s >/dev/null || \
        warn "osmo-service rollout did not complete before timeout"

    if wait_for_service_auth_regeneration; then
        log "SERVICE service_auth regenerated"
    else
        warn "SERVICE service_auth was not observed in Postgres after osmo-service restart"
    fi

    for deploy in osmo-agent osmo-worker osmo-logger; do
        if kubectl_cmd get deployment "${deploy}" -n "${OSMO_NAMESPACE}" >/dev/null 2>&1; then
            log "Restarting ${deploy} to pick up fresh service auth config"
            kubectl_cmd rollout restart "deployment/${deploy}" -n "${OSMO_NAMESPACE}" >/dev/null
            kubectl_cmd rollout status "deployment/${deploy}" -n "${OSMO_NAMESPACE}" --timeout=300s >/dev/null || \
                warn "${deploy} rollout did not complete before timeout"
        fi
    done

    stop_port_forward
    OSMO_API_URL=""
    OSMO_API_PORT=""
    OSMO_AUTH_BYPASS="false"
    return 0
}

patch_config_endpoint() {
    local endpoint="$1"
    local json_file="$2"
    local description="$3"
    local body
    local response_file
    local http_code

    body="$(jq -n --arg desc "${description}" --slurpfile cfg "${json_file}" '{description: $desc, configs_dict: $cfg[0]}')"
    response_file="$(make_temp_file "osmo-config-resp")"

    http_code="$(osmo_curl PATCH "${OSMO_API_URL}/${endpoint}" -d "${body}" -o "${response_file}" -w "%{http_code}")"
    if [[ ! "${http_code}" =~ ^2 ]]; then
        cat "${response_file}" >&2 || true
        rm -f "${response_file}"
        die "PATCH ${endpoint} failed with HTTP ${http_code}"
    fi

    rm -f "${response_file}"
}

put_json_file() {
    local url="$1"
    local json_file="$2"
    local response_file
    local http_code

    response_file="$(make_temp_file "osmo-put-resp")"
    http_code="$(osmo_curl PUT "${url}" -d @"${json_file}" -o "${response_file}" -w "%{http_code}")"
    if [[ ! "${http_code}" =~ ^2 ]]; then
        cat "${response_file}" >&2 || true
        rm -f "${response_file}"
        die "PUT ${url} failed with HTTP ${http_code}"
    fi

    rm -f "${response_file}"
}

wait_for_backend_registration() {
    local end_time
    local backend_json
    local backend_object

    end_time=$((SECONDS + 600))
    while (( SECONDS < end_time )); do
        backend_json="$(osmo_curl GET "${OSMO_API_URL}/api/configs/backend" 2>/dev/null || true)"
        backend_object="$(printf '%s' "${backend_json}" | jq -c --arg name "${BACKEND_NAME}" '.backends[]? | select(.name == $name)' 2>/dev/null || true)"
        if [[ -n "${backend_object}" && "${backend_object}" != "null" ]]; then
            printf '%s\n' "${backend_object}"
            return 0
        fi
        sleep 10
    done

    return 1
}

configure_workflow_storage() {
    local endpoint
    local workflow_storage_value
    local workflow_limits_file

    endpoint="$(normalize_storage_endpoint "${STORAGE_ENDPOINT}")"
    log "Probing object storage bucket access"
    probe_bucket_rw "${STORAGE_BUCKET}" "${endpoint}" "${STORAGE_REGION}" || die "Object Storage probe failed with the current credentials"

    workflow_storage_value="$(jq -cn \
        --arg s3_endpoint "s3://${STORAGE_BUCKET}" \
        --arg override_url "${endpoint}" \
        --arg access_key_id "${STORAGE_ACCESS_KEY_ID}" \
        --arg access_key "${STORAGE_SECRET_ACCESS_KEY}" \
        --arg region "${STORAGE_REGION}" \
        '{credential: {endpoint: $s3_endpoint, override_url: $override_url, access_key_id: $access_key_id, access_key: $access_key, region: $region}}')"

    upsert_osmo_config_value_db "WORKFLOW" "workflow_log" "${workflow_storage_value}"
    upsert_osmo_config_value_db "WORKFLOW" "workflow_data" "${workflow_storage_value}"

    workflow_limits_file="$(make_temp_file "workflow-limits" ".json")"
    printf '%s\n' '{"max_num_tasks":200}' >"${workflow_limits_file}"
    patch_config_endpoint "api/configs/workflow" "${workflow_limits_file}" "Configure workflow limits"
    rm -f "${workflow_limits_file}"

    rollout_restart_if_present "osmo-worker"
    rollout_restart_if_present "osmo-service"
    rollout_restart_if_present "osmo-logger"
    rollout_restart_if_present "osmo-agent"
}

configure_dataset_bucket() {
    local endpoint
    local current_file
    local bucket_file
    local updated_file
    local dataset_json

    endpoint="$(normalize_storage_endpoint "${STORAGE_ENDPOINT}")"
    current_file="$(make_temp_file "dataset-current" ".json")"
    bucket_file="$(make_temp_file "dataset-bucket" ".json")"
    updated_file="$(make_temp_file "dataset-updated" ".json")"

    jq -n \
        --arg path "s3://${STORAGE_BUCKET}/osmo-datasets" \
        --arg region "${STORAGE_REGION}" \
        --arg endpoint "s3://${STORAGE_BUCKET}" \
        --arg override_url "${endpoint}" \
        --arg access_key_id "${STORAGE_ACCESS_KEY_ID}" \
        --arg access_key "${STORAGE_SECRET_ACCESS_KEY}" \
        '{
          dataset_path: $path,
          region: $region,
          description: "Nebius Object Storage bucket",
          mode: "read-write",
          default_credential: {
            endpoint: $endpoint,
            region: $region,
            override_url: $override_url,
            access_key_id: $access_key_id,
            access_key: $access_key
          }
        }' >"${bucket_file}" || die "Failed to render dataset bucket payload"

    dataset_json="$(osmo_curl GET "${OSMO_API_URL}/api/configs/dataset" 2>/dev/null || true)"
    if printf '%s' "${dataset_json}" | jq -r '.configs_dict // . | if type == "object" then . else empty end' >"${current_file}" 2>/dev/null && [[ -s "${current_file}" ]]; then
        jq --arg name "${DATASET_BUCKET_NAME}" \
           --slurpfile bucket "${bucket_file}" \
           '.buckets[$name] = $bucket[0] | .default_bucket = $name' \
           "${current_file}" >"${updated_file}" || die "Failed to merge dataset bucket config"
    else
        jq -n --arg name "${DATASET_BUCKET_NAME}" \
           --slurpfile bucket "${bucket_file}" \
           '{ buckets: { ($name): $bucket[0] }, default_bucket: $name }' >"${updated_file}" || die "Failed to build initial dataset bucket config"
    fi

    patch_config_endpoint "api/configs/dataset" "${updated_file}" "Register default dataset bucket"

    rm -f "${current_file}" "${bucket_file}" "${updated_file}"
}

configure_backend_scheduler() {
    local backend_object
    local updated_backend
    local verified_backend
    local scheduler_type
    local scheduler_name
    local scheduler_timeout

    log "Waiting for backend '${BACKEND_NAME}' to register with OSMO"
    backend_object="$(wait_for_backend_registration)" || die "Backend '${BACKEND_NAME}' was not registered within 10 minutes"
    updated_backend="$(printf '%s' "${backend_object}" | jq -c '. + {scheduler_settings: {"scheduler_type":"kai","scheduler_name":"kai-scheduler","scheduler_timeout":30}}')"
    upsert_osmo_config_value_db "BACKEND" "${BACKEND_NAME}" "${updated_backend}"

    verified_backend="$(wait_for_backend_registration)" || die "Could not re-read backend '${BACKEND_NAME}' after scheduler update"
    scheduler_type="$(printf '%s' "${verified_backend}" | jq -r '.scheduler_settings.scheduler_type // ""')"
    scheduler_name="$(printf '%s' "${verified_backend}" | jq -r '.scheduler_settings.scheduler_name // ""')"
    scheduler_timeout="$(printf '%s' "${verified_backend}" | jq -r '.scheduler_settings.scheduler_timeout // ""')"

    if [[ "${scheduler_type}" != "kai" || "${scheduler_name}" != "kai-scheduler" || "${scheduler_timeout}" != "30" ]]; then
        die "Backend scheduler verification failed for '${BACKEND_NAME}'"
    fi
}

configure_gpu_platform() {
    local resolved_gpu_template
    local response

    [[ -n "${GPU_PLATFORM_NAME}" ]] || die "GPU_PLATFORM_NAME must not be empty when CONFIGURE_GPU_PLATFORM=true"

    resolved_gpu_template="$(make_temp_file "gpu-pod-template" ".json")"
    sed \
      -e "s|{{NEBIUS_REGION}}|${NEBIUS_REGION}|g" \
      -e "s|{{STORAGE_ENDPOINT}}|${STORAGE_ENDPOINT}|g" \
      "${GPU_POD_TEMPLATE}" >"${resolved_gpu_template}" || die "Failed to render GPU pod template"
    inject_workflow_ingress_ca_into_template "${resolved_gpu_template}" "${resolved_gpu_template}.patched"
    mv "${resolved_gpu_template}.patched" "${resolved_gpu_template}" || die "Failed to finalize GPU pod template"
    put_json_file "${OSMO_API_URL}/api/configs/pod_template/gpu_tolerations" "${resolved_gpu_template}"
    rm -f "${resolved_gpu_template}"

    put_json_file "${OSMO_API_URL}/api/configs/pod_template/shm" "${SHM_POD_TEMPLATE}"
    put_json_file "${OSMO_API_URL}/api/configs/pool/default/platform/${GPU_PLATFORM_NAME}" "${GPU_PLATFORM_UPDATE_TEMPLATE}"

    response="$(osmo_curl PATCH "${OSMO_API_URL}/api/users/me" -d '{"default_pool":"default"}' -o /dev/null -w "%{http_code}" 2>/dev/null || true)"
    if [[ ! "${response}" =~ ^2 ]]; then
        warn "Could not set default pool for the current automation user"
    fi
}

configure_workflow_pod_templates() {
    local resolved_default_template

    resolved_default_template="$(make_temp_file "default-user-pod-template" ".json")"
    inject_workflow_ingress_ca_into_template "${DEFAULT_USER_POD_TEMPLATE}" "${resolved_default_template}"
    put_json_file "${OSMO_API_URL}/api/configs/pod_template/default_user" "${resolved_default_template}"
    rm -f "${resolved_default_template}"
}

run_post_install() {
    set_phase "Patching vault mounts"
    patch_vault_mounts
    set_phase "Ensuring ingress timeouts"
    ensure_service_ingress_timeouts
    set_phase "Ensuring UI TRPC rewrite"
    ensure_ui_trpc_rewrite
    set_phase "Ensuring envoy configmaps"
    ensure_envoy_configmaps
    set_phase "Ensuring UI login info cache"
    ensure_ui_login_info_cache

    for deploy in osmo-service osmo-router osmo-agent osmo-logger osmo-worker osmo-delayed-job-monitor; do
        CURRENT_PHASE="Waiting for rollout ${deploy}"
        wait_for_rollout "${deploy}"
    done

    if [[ "${DEPLOY_UI}" == "true" ]]; then
        CURRENT_PHASE="Waiting for rollout osmo-ui"
        wait_for_rollout "osmo-ui"
    fi

    set_phase "Refreshing internal service auth"
    refresh_service_auth_config || true
    set_phase "Configuring service base URL"
    configure_service_base_url
    log "OSMO post-install fixes complete"
}

run_app_configuration() {
    set_phase "Starting OSMO API session"
    start_osmo_api_session "${OSMO_NAMESPACE}"
    log "OSMO API is reachable at ${OSMO_API_URL}"

    set_phase "Configuring workflow pod templates"
    configure_workflow_pod_templates

    if [[ "${CONFIGURE_WORKFLOW_STORAGE}" == "true" ]]; then
        set_phase "Configuring workflow storage"
        configure_workflow_storage
    else
        log "Skipping workflow storage configuration"
    fi

    if [[ "${CONFIGURE_DATASET_BUCKET}" == "true" ]]; then
        set_phase "Configuring dataset bucket"
        configure_dataset_bucket
    else
        log "Skipping dataset bucket configuration"
    fi

    if [[ "${CONFIGURE_BACKEND_SCHEDULER}" == "true" ]]; then
        set_phase "Configuring backend scheduler"
        configure_backend_scheduler
    else
        log "Skipping backend scheduler configuration"
    fi

    if [[ "${CONFIGURE_GPU_PLATFORM}" == "true" ]]; then
        set_phase "Configuring GPU platform"
        configure_gpu_platform
    else
        log "Skipping GPU platform configuration"
    fi

    log "OSMO application configuration complete"
}

require_command kubectl
require_command jq

RUN_POST_INSTALL="$(normalize_bool "${RUN_POST_INSTALL:-true}")"
RUN_APP_CONFIGURATION="$(normalize_bool "${RUN_APP_CONFIGURATION:-false}")"

if [[ "${RUN_APP_CONFIGURATION}" == "true" ]]; then
    require_command curl
    require_command lsof
    if [[ "${TLS_ENABLED:-false}" == "true" && "${TLS_MODE:-}" == "self-signed" ]]; then
        require_command openssl
    fi
fi

: "${OSMO_NAMESPACE:?OSMO_NAMESPACE is required}"
: "${INGRESS_NAMESPACE:?INGRESS_NAMESPACE is required}"
: "${INGRESS_HOSTNAME:?INGRESS_HOSTNAME is required}"
: "${AUTH_DOMAIN:?AUTH_DOMAIN is required}"
: "${TLS_ENABLED:?TLS_ENABLED is required}"
: "${TLS_MODE:=}"
: "${TLS_SECRET_NAME:=}"
: "${ENABLE_AUTH:?ENABLE_AUTH is required}"
: "${DEPLOY_UI:?DEPLOY_UI is required}"
: "${SERVICE_BASE_URL:?SERVICE_BASE_URL is required}"
: "${WORKFLOWS_NAMESPACE:=}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

if [[ "${RUN_APP_CONFIGURATION}" == "true" ]]; then
    : "${BACKEND_NAME:?BACKEND_NAME is required}"
    : "${STORAGE_BUCKET:?STORAGE_BUCKET is required}"
    : "${STORAGE_ENDPOINT:?STORAGE_ENDPOINT is required}"
    : "${STORAGE_REGION:?STORAGE_REGION is required}"
    : "${STORAGE_ACCESS_KEY_ID:?STORAGE_ACCESS_KEY_ID is required}"
    : "${STORAGE_SECRET_ACCESS_KEY:?STORAGE_SECRET_ACCESS_KEY is required}"
    : "${CONFIGURE_WORKFLOW_STORAGE:?CONFIGURE_WORKFLOW_STORAGE is required}"
    : "${CONFIGURE_DATASET_BUCKET:?CONFIGURE_DATASET_BUCKET is required}"
    : "${DATASET_BUCKET_NAME:?DATASET_BUCKET_NAME is required}"
    : "${CONFIGURE_BACKEND_SCHEDULER:?CONFIGURE_BACKEND_SCHEDULER is required}"
    : "${CONFIGURE_GPU_PLATFORM:?CONFIGURE_GPU_PLATFORM is required}"
    : "${GPU_PLATFORM_NAME:=}"
    : "${NEBIUS_REGION:?NEBIUS_REGION is required}"
    : "${DEFAULT_USER_POD_TEMPLATE:?DEFAULT_USER_POD_TEMPLATE is required}"
    : "${GPU_POD_TEMPLATE:?GPU_POD_TEMPLATE is required}"
    : "${SHM_POD_TEMPLATE:?SHM_POD_TEMPLATE is required}"
    : "${GPU_PLATFORM_UPDATE_TEMPLATE:?GPU_PLATFORM_UPDATE_TEMPLATE is required}"

    CONFIGURE_WORKFLOW_STORAGE="$(normalize_bool "${CONFIGURE_WORKFLOW_STORAGE}")"
    CONFIGURE_DATASET_BUCKET="$(normalize_bool "${CONFIGURE_DATASET_BUCKET}")"
    CONFIGURE_BACKEND_SCHEDULER="$(normalize_bool "${CONFIGURE_BACKEND_SCHEDULER}")"
    CONFIGURE_GPU_PLATFORM="$(normalize_bool "${CONFIGURE_GPU_PLATFORM}")"
fi

if [[ "${RUN_POST_INSTALL}" == "true" ]]; then
    run_post_install
fi

if [[ "${RUN_APP_CONFIGURATION}" == "true" ]]; then
    run_app_configuration
fi
