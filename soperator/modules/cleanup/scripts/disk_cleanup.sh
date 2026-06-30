#!/bin/bash
set -euo pipefail

parent_id="${PARENT_ID:?PARENT_ID is required}"
page_token=""
result_ids=()
allowed_cleanup_namespaces=("logs-system" "monitoring-system" "soperator" "nfs-system")

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


# Skip deletion if there are no disks to delete
if [ ${#result_ids[@]} -eq 0 ]; then
    exit 0
fi

retry_script="$(dirname "$0")/../../scripts/retry.sh"
max_delete_jobs="${MAX_DELETE_JOBS:-10}"
delete_pids=()
delete_status=0

if ! [[ "$max_delete_jobs" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_DELETE_JOBS must be a positive integer, got: $max_delete_jobs" >&2
  exit 1
fi

wait_for_delete_batch() {
  local pid
  for pid in "${delete_pids[@]}"; do
    if ! wait "$pid"; then
      delete_status=1
    fi
  done
  delete_pids=()
}

for id in "${result_ids[@]}"; do
  echo "Deleting leftover disk $id..."
  "$retry_script" -- nebius compute disk delete --id "$id" &
  delete_pids+=("$!")

  if [ "${#delete_pids[@]}" -ge "$max_delete_jobs" ]; then
    wait_for_delete_batch
  fi
done

wait_for_delete_batch
exit "$delete_status"
