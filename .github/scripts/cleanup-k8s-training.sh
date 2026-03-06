#!/usr/bin/env bash
set -euo pipefail

# Added by: Aaron Fagan
# JIRA: ARCHVTEAMS-1583
#
# Purpose:
# Centralized cleanup for k8s-training CI resources in the shared test project.
# This script removes stale MK8s clusters and node-group service accounts using
# name-prefix filters that match both legacy static names and new suffixed CI
# names.
#
# Why:
# k8s-training tests run in a constrained shared environment. If runs fail,
# hang, or are manually canceled, leftover resources can cause name collisions
# and block subsequent PR checks.
#
# Where it is used:
# - Preflight cleanup in terraform.yml (best effort before test start)
# - Post-run cleanup in terraform.yml (strict cleanup after test)
# - Fallback canceled-run cleanup in terraform-cancelled-cleanup.yml
#
# Behavior:
# - Retries delete operations for transient failures
# - Waits for eventual-consistency deletion to complete
# - Exits non-zero if prefixed resources remain after timeout

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <parent_id> [cluster_prefix] [sa_prefix] [grafana_key_prefix] [loki_key_prefix]"
  exit 1
fi

PARENT_ID="$1"
CLUSTER_PREFIX="${2:-k8s-training}"
SA_PREFIX="${3:-${CLUSTER_PREFIX}-k8s-node-group-sa}"
GRAFANA_KEY_PREFIX="${4:-${CLUSTER_PREFIX}-grafana-access-key}"
LOKI_KEY_PREFIX="${5:-${CLUSTER_PREFIX}-loki-s3-access-key}"
MAX_RETRIES=3
RETRY_DELAY_SECONDS=10
WAIT_TIMEOUT_SECONDS=300
WAIT_POLL_SECONDS=10

log() {
  echo "[cleanup] $*"
}

retry_cmd() {
  local attempt=1
  while true; do
    if "$@"; then
      return 0
    fi
    if (( attempt >= MAX_RETRIES )); then
      return 1
    fi
    log "Retry ${attempt}/${MAX_RETRIES} failed for: $*"
    sleep "${RETRY_DELAY_SECONDS}"
    attempt=$((attempt + 1))
  done
}

list_cluster_ids() {
  nebius --format json mk8s v1 cluster list --parent-id "${PARENT_ID}" \
    | jq -r --arg prefix "${CLUSTER_PREFIX}" '(.items // [])[] | select(.metadata.name | startswith($prefix)) | .metadata.id'
}

list_service_account_ids() {
  nebius --format json iam v1 service-account list --parent-id "${PARENT_ID}" \
    | jq -r --arg prefix "${SA_PREFIX}" '(.items // [])[] | select(.metadata.name | startswith($prefix)) | .metadata.id'
}

list_access_key_ids() {
  local matching_sa_ids
  local matching_sa_ids_json

  mapfile -t matching_sa_ids < <(list_service_account_ids)
  if [[ ${#matching_sa_ids[@]} -eq 0 ]]; then
    matching_sa_ids_json='[]'
  else
    matching_sa_ids_json="$(printf '%s\n' "${matching_sa_ids[@]}" | jq -R . | jq -s -c .)"
  fi

  nebius --format json iam v2 access-key list --parent-id "${PARENT_ID}" \
    | jq -r \
      --arg grafana_prefix "${GRAFANA_KEY_PREFIX}" \
      --arg loki_prefix "${LOKI_KEY_PREFIX}" \
      --argjson matching_sa_ids "${matching_sa_ids_json}" \
      '(.items // [])[]
      | select(
          ((.metadata.name // "") | startswith($grafana_prefix))
          or ((.metadata.name // "") | startswith($loki_prefix))
          or ((.account.service_account.id // "") as $sa_id | ($matching_sa_ids | index($sa_id)) != null)
        )
      | .metadata.id'
}

delete_clusters() {
  mapfile -t ids < <(list_cluster_ids)
  if [[ ${#ids[@]} -eq 0 ]]; then
    log "No MK8s clusters found for prefix ${CLUSTER_PREFIX}"
    return 0
  fi

  for id in "${ids[@]}"; do
    [[ -z "${id}" ]] && continue
    log "Deleting MK8s cluster ${id}"
    retry_cmd nebius mk8s v1 cluster delete --id "${id}"
  done
}

delete_service_accounts() {
  mapfile -t ids < <(list_service_account_ids)
  if [[ ${#ids[@]} -eq 0 ]]; then
    log "No service accounts found for prefix ${SA_PREFIX}"
    return 0
  fi

  for id in "${ids[@]}"; do
    [[ -z "${id}" ]] && continue
    log "Deleting service account ${id}"
    retry_cmd nebius iam v1 service-account delete --id "${id}"
  done
}

delete_access_keys() {
  mapfile -t ids < <(list_access_key_ids)
  if [[ ${#ids[@]} -eq 0 ]]; then
    log "No IAM access keys found for prefixes ${GRAFANA_KEY_PREFIX} / ${LOKI_KEY_PREFIX}"
    return 0
  fi

  for id in "${ids[@]}"; do
    [[ -z "${id}" ]] && continue
    log "Deleting IAM access key ${id}"
    retry_cmd nebius iam v2 access-key delete --id "${id}"
  done
}

wait_until_empty() {
  local name="$1"
  local list_fn="$2"
  local waited=0
  local ids=""

  while true; do
    ids="$(${list_fn})"
    if [[ -z "${ids}" ]]; then
      log "${name} cleanup complete"
      return 0
    fi

    if (( waited >= WAIT_TIMEOUT_SECONDS )); then
      log "Timed out waiting for ${name} cleanup. Remaining IDs:"
      echo "${ids}"
      return 1
    fi

    log "Waiting for ${name} cleanup to finish. Remaining IDs: ${ids//$'\n'/ }"
    sleep "${WAIT_POLL_SECONDS}"
    waited=$((waited + WAIT_POLL_SECONDS))
  done
}

log "Starting k8s-training cleanup with cluster prefix ${CLUSTER_PREFIX}, SA prefix ${SA_PREFIX}, key prefixes ${GRAFANA_KEY_PREFIX} / ${LOKI_KEY_PREFIX}"
delete_clusters
delete_access_keys
delete_service_accounts
wait_until_empty "cluster" list_cluster_ids
wait_until_empty "access key" list_access_key_ids
wait_until_empty "service account" list_service_account_ids
log "k8s-training cleanup finished"
