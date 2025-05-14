#!/bin/bash

parent_id=$PARENT_ID
page_size=100
page_token=""
result_ids=()
allowed_cleanup_namespaces=("logs-system" "monitoring-system" "soperator")

is_allowed_namespace() {
  local ns="$1"
  for allowed in "${allowed_cleanup_namespaces[@]}"; do
    if [[ "$ns" == "$allowed" ]]; then
      return 0
    fi
  done
  return 1
}

while true; do
  output=$(nebius compute disk list --parent-id "$parent_id" --page-token "$page_token")

  item_count=$(echo "$output" | yq '.items | length')
  for ((i = 0; i < item_count; i++)); do
    id=$(echo "$output" | yq -r ".items[$i] | .metadata.id")
    name=$(echo "$output" | yq -r ".items[$i] | .metadata.name")
    attachment=$(echo "$output" | yq -r ".items[$i] | .status.read_write_attachment // \"\"")
    namespace=$(echo "$output" | yq -r ".items[$i] | .metadata.labels.\"kubernetes.io/created-for/pvc/namespace\" // \"\"")

    # We only cleanup disks, that doesn't have attachments, have namespace well-known label
    # and their name starts with `pvc-`
    if [[ -z "$attachment" && -n "$namespace" && "$name" == pvc-* ]]; then
      if is_allowed_namespace "$namespace"; then
        result_ids+=("$id")
      fi
    fi
  done

  page_token=$(echo "$output" | yq -r '.next_page_token // ""')
  if [ -z "$page_token" ]; then
    break
  fi
done


for id in "${result_ids[@]}"; do
  echo "Deleting leftover disk $id..."
  nebius compute disk delete --id "$id"
done
