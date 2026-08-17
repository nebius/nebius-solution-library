#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "usage: cleanup_cloud.sh NEBIUS_PROFILE" >&2
  exit 2
fi

readonly profile="$1"
readonly expected_cluster_id="mk8scluster-e00en4dkk80w2d09c0"

delete_node_group() {
  local node_group_id="$1"
  local expected_name="$2"
  local record
  local parent_id
  local actual_name

  if ! record="$(nebius mk8s node-group get --id "${node_group_id}" \
    --profile "${profile}" --format json 2>&1)"; then
    if [[ "${record}" == *"NotFound"* || "${record}" == *"not found"* ]]; then
      echo "node group already absent: ${node_group_id}"
      return
    fi
    echo "failed to inspect node group ${node_group_id}: ${record}" >&2
    exit 1
  fi
  parent_id="$(jq -r '.metadata.parent_id' <<<"${record}")"
  actual_name="$(jq -r '.metadata.name' <<<"${record}")"
  if [[ "${parent_id}" != "${expected_cluster_id}" || "${actual_name}" != "${expected_name}" ]]; then
    echo "refusing delete: unexpected node-group identity: ${node_group_id} ${parent_id} ${actual_name}" >&2
    exit 1
  fi
  nebius mk8s node-group delete --id "${node_group_id}" --profile "${profile}"
}

delete_node_group \
  mk8snodegroup-e00xcmxy1gnkabgsdf \
  archvteams-2407-k301ud-h100-preempt
delete_node_group \
  mk8snodegroup-e00q3skyvtc8fxb9nd \
  archvteams-2407-k301ud-sfs-h100-preempt
