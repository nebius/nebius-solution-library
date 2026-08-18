#!/usr/bin/env bash

# Capture a Cristian-style controller/target-node clock bracket without adding
# a privileged host component.  The target container is already bound to the
# requested node; the aggregate independently proves that worker and semantic
# probe Pods ran on that same node.

capture_target_clock_sample() {
  local kubectl_array_name=$1 sampled_pod_name=$2 sampled_pod_uid=$3 target_node=$4
  local sampled_container=$5 phase=$6 output=$7
  local -n clock_kubectl=$kubectl_array_name
  local controller_before node_observed controller_after partial
  partial="${output}.partial"

  controller_before=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ) || return 1
  if [[ -n $sampled_container ]]; then
    node_observed=$(
      "${clock_kubectl[@]}" exec "pod/$sampled_pod_name" -c "$sampled_container" -- \
        /bin/date -u +%Y-%m-%dT%H:%M:%S.%NZ
    ) || return 1
  else
    node_observed=$(
      "${clock_kubectl[@]}" exec "pod/$sampled_pod_name" -- \
        /bin/date -u +%Y-%m-%dT%H:%M:%S.%NZ
    ) || return 1
  fi
  controller_after=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ) || return 1
  jq -n \
    --arg schema "archvteams.nebius.ai/node-clock-sample/v1" \
    --arg phase "$phase" \
    --arg sampled_pod_name "$sampled_pod_name" \
    --arg sampled_pod_uid "$sampled_pod_uid" \
    --arg target_node "$target_node" \
    --arg sampled_container "$sampled_container" \
    --arg controller_before "$controller_before" \
    --arg node_observed "$node_observed" \
    --arg controller_after "$controller_after" \
    '{schema:$schema,phase:$phase,sampled_pod_name:$sampled_pod_name,
      sampled_pod_uid:$sampled_pod_uid,target_node:$target_node,
      sampled_container:$sampled_container,
      controller_before:$controller_before,node_observed:$node_observed,
      controller_after:$controller_after}' > "$partial" || return 1
  mv -- "$partial" "$output"
}
