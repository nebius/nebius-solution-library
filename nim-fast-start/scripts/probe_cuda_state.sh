#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 POD [CONTAINER]" >&2
  exit 2
fi

POD=$1
CONTAINER=${2:-}
NAMESPACE=${NAMESPACE:-nim-fast-start}
SNAPSHOT_RELEASE=${SNAPSHOT_RELEASE:-archvteams-2407-snapshot}

pod_json=$(kubectl -n "${NAMESPACE}" get pod "${POD}" -o json)
if [[ -z "${CONTAINER}" ]]; then
  CONTAINER=$(jq -r '.spec.containers[0].name' <<<"${pod_json}")
fi
container_id=$(jq -r --arg container "${CONTAINER}" '
  .status.containerStatuses[] | select(.name == $container) | .containerID
' <<<"${pod_json}")
container_id=${container_id#containerd://}
node=$(jq -r '.spec.nodeName' <<<"${pod_json}")

agent=$(kubectl -n "${NAMESPACE}" get pod \
  -l "app.kubernetes.io/instance=${SNAPSHOT_RELEASE},app.kubernetes.io/component=snapshot-agent" \
  --field-selector="spec.nodeName=${node},status.phase=Running" \
  -o jsonpath='{.items[0].metadata.name}')
if [[ -z "${agent}" ]]; then
  echo "No running snapshot agent found on ${node}" >&2
  exit 1
fi

# shellcheck disable=SC2016
states=$(kubectl -n "${NAMESPACE}" exec "${agent}" -c agent -- \
  sh -c '
    set -eu
    container_id=$1
    found=false
    for cgroup in /host/proc/[0-9]*/cgroup; do
      if ! grep -q "$container_id" "$cgroup" 2>/dev/null; then
        continue
      fi
      pid=${cgroup#/host/proc/}
      pid=${pid%/cgroup}
      restore_tid=$(/usr/local/bin/cuda-checkpoint-helper --get-restore-tid --pid "$pid" 2>/dev/null || true)
      if [ -z "$restore_tid" ]; then
        continue
      fi
      state=$(/usr/local/bin/cuda-checkpoint-helper --get-state --pid "$pid")
      printf "%s,%s,%s\n" "$pid" "$restore_tid" "$state"
      found=true
    done
    "$found"
  ' cuda-state "${container_id}")

if [[ -z "${states}" ]]; then
  echo "No CUDA process found in container ${container_id}" >&2
  exit 1
fi
if awk -F, '$3 != "running" {exit 1}' <<<"${states}"; then
  printf 'pod,container,container_id,node,agent,host_pid,restore_tid,state\n'
  while IFS=, read -r pid restore_tid state; do
    printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "${POD}" "${CONTAINER}" "${container_id}" "${node}" "${agent}" \
      "${pid}" "${restore_tid}" "${state}"
  done <<<"${states}"
else
  printf '%s\n' "${states}" >&2
  exit 1
fi
