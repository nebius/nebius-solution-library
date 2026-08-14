#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
SNAPSHOTCTL=${SNAPSHOTCTL:-${ROOT_DIR}/.tools/snapshotctl}
MANIFEST=${MANIFEST:-${ROOT_DIR}/feasibility/manifests/openfold2-checkpoint-pod.yaml}
NAMESPACE=${NAMESPACE:-nim-fast-start}
CHECKPOINT_ID=${CHECKPOINT_ID:-openfold2-h100-v1}
TIMEOUT=${TIMEOUT:-30m}
KEEP_SOURCE=${KEEP_SOURCE:-false}
SOURCE_EVIDENCE=${SOURCE_EVIDENCE:-${ROOT_DIR}/feasibility/results/checkpoint_source.json}
SNAPSHOT_RELEASE=${SNAPSHOT_RELEASE:-archvteams-2407-snapshot}

if [[ ! -x "${SNAPSHOTCTL}" ]]; then
  echo "snapshotctl is missing; run prepare_snapshot_tools.sh" >&2
  exit 1
fi

if kubectl -n "${NAMESPACE}" get pods -l app=openfold2 -o json \
  | jq -e '.items[] | select(.status.phase == "Running")' >/dev/null; then
  echo "A conventional OpenFold2 pod is still running; scale it down before creating the checkpoint" >&2
  exit 1
fi

kubectl -n "${NAMESPACE}" delete job openfold2-checkpoint-source-checkpoint --ignore-not-found --wait=true
kubectl -n "${NAMESPACE}" delete podsnapshot openfold2-checkpoint-source-checkpoint --ignore-not-found --wait=true

started_at=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
start_ns=$(date +%s%N)
result=$(
  "${SNAPSHOTCTL}" checkpoint \
    --manifest "${MANIFEST}" \
    --container openfold2 \
    --namespace "${NAMESPACE}" \
    --checkpoint-id "${CHECKPOINT_ID}" \
    --timeout "${TIMEOUT}"
)
end_ns=$(date +%s%N)
duration=$(awk -v start="${start_ns}" -v end="${end_ns}" 'BEGIN {printf "%.3f", (end-start)/1000000000}')

checkpoint_job=$(awk -F= '$1 == "checkpoint_job" {print $2}' <<<"${result}")
source_pod=$(kubectl -n "${NAMESPACE}" get pods -l "job-name=${checkpoint_job}" -o json \
  | jq -r '.items[0].metadata.name')
mkdir -p "$(dirname "${SOURCE_EVIDENCE}")"
kubectl -n "${NAMESPACE}" get pod "${source_pod}" -o json \
  | jq '{
      pod: .metadata.name,
      pod_uid: .metadata.uid,
      node: .spec.nodeName,
      image_id: .status.containerStatuses[] | select(.name == "openfold2") | .imageID,
      container_id: .status.containerStatuses[] | select(.name == "openfold2") | .containerID
    }' >"${SOURCE_EVIDENCE}"
gpu_uuid=$(kubectl -n "${NAMESPACE}" exec "${source_pod}" -c openfold2 -- \
  nvidia-smi --query-gpu=uuid --format=csv,noheader | head -1 | tr -d '[:space:]')
agent=$(kubectl -n "${NAMESPACE}" get pod \
  -l "app.kubernetes.io/instance=${SNAPSHOT_RELEASE},app.kubernetes.io/component=snapshot-agent" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')
artifact_path="/checkpoints/${CHECKPOINT_ID}/versions/1"
artifact_bytes=$(kubectl -n "${NAMESPACE}" exec "${agent}" -c agent -- \
  du -sb "${artifact_path}" | cut -f1)
kubectl -n "${NAMESPACE}" logs "${agent}" -c agent --since-time="${started_at}" \
  >"$(dirname "${SOURCE_EVIDENCE}")/checkpoint_agent.log"
jq \
  --arg gpu_uuid "${gpu_uuid}" \
  --arg checkpoint_id "${CHECKPOINT_ID}" \
  --arg checkpoint_started_at "${started_at}" \
  --arg checkpoint_total_s "${duration}" \
  --arg artifact_path "${artifact_path}" \
  --argjson artifact_bytes "${artifact_bytes}" \
  '. + {
    gpu_uuid: $gpu_uuid,
    checkpoint_id: $checkpoint_id,
    checkpoint_started_at: $checkpoint_started_at,
    checkpoint_total_s: ($checkpoint_total_s | tonumber),
    artifact_path: $artifact_path,
    artifact_bytes: $artifact_bytes
  }' \
  "${SOURCE_EVIDENCE}" >"${SOURCE_EVIDENCE}.tmp"
mv "${SOURCE_EVIDENCE}.tmp" "${SOURCE_EVIDENCE}"

if [[ "${KEEP_SOURCE}" != "true" ]]; then
  kubectl -n "${NAMESPACE}" delete job "${checkpoint_job}" --wait=true >/dev/null
fi

printf '%s\n' "${result}"
printf 'checkpoint_started_at=%s\ncheckpoint_total_s=%s\nartifact_bytes=%s\nsource_evidence=%s\nsource_deleted=%s\n' \
  "${started_at}" "${duration}" "${artifact_bytes}" "${SOURCE_EVIDENCE}" \
  "$([[ "${KEEP_SOURCE}" == "true" ]] && echo false || echo true)"
