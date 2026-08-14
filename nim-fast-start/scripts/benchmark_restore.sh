#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: $0 CHECKPOINT_ID [RUNS] [OUTPUT_CSV]" >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
CHECKPOINT_ID=$1
RUNS=${2:-5}
OUTPUT=${3:-${ROOT_DIR}/feasibility/restore_timings.csv}
SNAPSHOTCTL=${SNAPSHOTCTL:-${ROOT_DIR}/.tools/snapshotctl}
MANIFEST=${MANIFEST:-${ROOT_DIR}/feasibility/manifests/openfold2-restore-pod.yaml}
NAMESPACE=${NAMESPACE:-nim-fast-start}
POD_NAME=${POD_NAME:-openfold2-restore}
TIMEOUT=${TIMEOUT:-180s}
SMOKE_SEQUENCE=${SMOKE_SEQUENCE:-MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLS}

if [[ ! -x "${SNAPSHOTCTL}" ]]; then
  echo "snapshotctl is missing; run prepare_snapshot_tools.sh" >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT}")"
printf '%s\n' 'run,checkpoint_id,t0,ready_at,restore_total_s,smoke_http_status,smoke_total_s,response_sha256,pod_uid,pod_ip,container_id,node,gpu_uuid' >"${OUTPUT}"

for run in $(seq 1 "${RUNS}"); do
  kubectl -n "${NAMESPACE}" delete pod "${POD_NAME}" --ignore-not-found --wait=true >/dev/null

  t0=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
  start_ns=$(date +%s%N)
  "${SNAPSHOTCTL}" restore \
    --manifest "${MANIFEST}" \
    --containers openfold2 \
    --namespace "${NAMESPACE}" \
    --checkpoint-id "${CHECKPOINT_ID}" >/dev/null

  if ! kubectl -n "${NAMESPACE}" wait --for=condition=Ready "pod/${POD_NAME}" --timeout="${TIMEOUT}" >/dev/null; then
    kubectl -n "${NAMESPACE}" describe pod "${POD_NAME}" >&2 || true
    exit 1
  fi

  ready_ns=$(date +%s%N)
  ready_at=$(kubectl -n "${NAMESPACE}" get pod "${POD_NAME}" -o json \
    | jq -r '.status.conditions[] | select(.type == "Ready" and .status == "True") | .lastTransitionTime')
  restore_total=$(awk -v start="${start_ns}" -v end="${ready_ns}" 'BEGIN {printf "%.3f", (end-start)/1000000000}')

  smoke_start_ns=$(date +%s%N)
  # shellcheck disable=SC2016
  smoke_result=$(kubectl -n "${NAMESPACE}" exec "${POD_NAME}" -c openfold2 -- \
    sh -lc 'response=$(mktemp); code=$(curl -sS -o "$response" -w "%{http_code}" --max-time 300 -X POST http://127.0.0.1:8000/v1/protein-structure/predict -H "Content-Type: application/json" --data "$1"); sha=$(sha256sum "$response" | cut -d" " -f1); rm -f "$response"; printf "%s %s\n" "$code" "$sha"' \
    smoke "{\"sequence\":\"${SMOKE_SEQUENCE}\"}")
  smoke_end_ns=$(date +%s%N)
  smoke_status=${smoke_result%% *}
  response_sha=${smoke_result##* }
  smoke_total=$(awk -v start="${smoke_start_ns}" -v end="${smoke_end_ns}" 'BEGIN {printf "%.3f", (end-start)/1000000000}')

  if [[ "${smoke_status}" != "200" ]]; then
    echo "Restore run ${run} inference returned HTTP ${smoke_status}" >&2
    exit 1
  fi

  pod_json=$(kubectl -n "${NAMESPACE}" get pod "${POD_NAME}" -o json)
  pod_uid=$(jq -r '.metadata.uid' <<<"${pod_json}")
  pod_ip=$(jq -r '.status.podIP' <<<"${pod_json}")
  container_id=$(jq -r '.status.containerStatuses[] | select(.name == "openfold2") | .containerID' <<<"${pod_json}")
  node=$(jq -r '.spec.nodeName' <<<"${pod_json}")
  gpu_uuid=$(kubectl -n "${NAMESPACE}" exec "${POD_NAME}" -c openfold2 -- \
    nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1 | tr -d '[:space:]')

  printf '%s\n' "${run},${CHECKPOINT_ID},${t0},${ready_at},${restore_total},${smoke_status},${smoke_total},${response_sha},${pod_uid},${pod_ip},${container_id},${node},${gpu_uuid}" >>"${OUTPUT}"
  printf 'run=%s restore_total_s=%s smoke_total_s=%s pod_uid=%s gpu_uuid=%s\n' \
    "${run}" "${restore_total}" "${smoke_total}" "${pod_uid}" "${gpu_uuid}"
done

python3 "${SCRIPT_DIR}/summarize_timings.py" "${OUTPUT}" restore_total_s smoke_total_s
