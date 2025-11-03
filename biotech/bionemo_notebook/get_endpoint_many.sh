#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------
# get_bionemo_endpoints.sh
# - Run Terraform to obtain bionemo release IDs (terraform output -json)
# - For each release ID:
#     * get entry id
#     * create access (best-effort)
#     * poll until the endpoint is available (or timeout)
# - Emit endpoints.json mapping release_id -> endpoint
# ---------------------------------------------------------------------

TF_DIR="${TF_DIR:-.}"
TF_OUTPUT_FILE="${TF_OUTPUT_FILE:-terraform-outputs.json}"
SLEEP_TIME="${SLEEP_TIME:-3}"         # wait after create-access before first poll
POLL_INTERVAL="${POLL_INTERVAL:-2}"   # seconds between polls
POLL_TIMEOUT="${POLL_TIMEOUT:-60}"    # max seconds to wait per release
OUTPUT_JSON="${OUTPUT_JSON:-endpoints.json}"

# Required binaries
for cmd in terraform jq yq npc; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    exit 2
  fi
done

# Run terraform output -json and write to file
if ! terraform -chdir="$TF_DIR" output -json > "$TF_OUTPUT_FILE"; then
  echo "Error: 'terraform output -json' failed." >&2
  exit 3
fi

if [[ ! -s "$TF_OUTPUT_FILE" ]]; then
  echo "Error: Terraform output file '$TF_OUTPUT_FILE' is empty." >&2
  exit 4
fi

# Extract number of release IDs
count=$(jq -r 'if has("bionemo_ids") and .bionemo_ids.value then (.bionemo_ids.value | length) else 0 end' "$TF_OUTPUT_FILE")

if [[ "$count" -le 0 ]]; then
  echo "Error: no bionemo_ids found in Terraform outputs." >&2
  exit 5
fi

echo "Found $count release ID(s)." >&2

# Prepare an ordered JSON object using jq.
# We'll build an array of {id,endpoint} objects then convert to object at the end.
tmp_array="[]"

for i in $(seq 0 $((count - 1))); do
  release_id=$(jq -r ".bionemo_ids.value[$i]" "$TF_OUTPUT_FILE")

  if [[ -z "$release_id" || "$release_id" == "null" ]]; then
    echo "Warning: empty release id at index $i, skipping" >&2
    continue
  fi

  echo "Processing release ($((i+1))/$count): $release_id" >&2

  # Get entry id
  entry_id=$(npc marketplace inner console release get-release-by-id --release-id "$release_id" 2>/dev/null | yq -r '.release.entries[0].id' || true)
  if [[ -z "$entry_id" || "$entry_id" == "null" ]]; then
    echo "Warning: could not determine entry id for release $release_id; skipping" >&2
    continue
  fi
  echo "  entry_id: $entry_id" >&2

  # Create access (best-effort: do not fail the whole run if it errors)
  if ! npc marketplace inner console release create-access --release-id "$release_id" --entry-id "$entry_id" >/dev/null 2>&1; then
    echo "  note: create-access returned non-zero; continuing to poll for endpoint anyway" >&2
  fi

  # initial wait before polling
  sleep "$SLEEP_TIME"

  # Poll for endpoint
  endpoint=""
  elapsed=0
  while true; do
    endpoint=$(npc marketplace inner console release get-release-by-id --release-id "$release_id" 2>/dev/null \
      | yq -r '.release.entries[0].access.endpoint' || true)

    if [[ -n "$endpoint" && "$endpoint" != "null" ]]; then
      echo "  endpoint found: $endpoint" >&2
      break
    fi

    if [[ "$elapsed" -ge "$POLL_TIMEOUT" ]]; then
      echo "  timeout waiting for endpoint for release $release_id (waited ${elapsed}s)." >&2
      break
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
  done

  # Append to temporary array for conversion to object later
  # If no endpoint was found, we will record null
  tmp_array=$(jq --arg id "$release_id" --arg endpoint "${endpoint:-}" \
    '. + [{id: $id, endpoint: ($endpoint // null)}]' <<<"$tmp_array")
done

# Convert array of {id,endpoint} to object {"id": "endpoint", ...}
# Keep releases with non-empty endpoint only, but also allow nulls if you prefer to keep them:
final_obj=$(jq 'reduce .[] as $item ({}; . + { ($item.id): ($item.endpoint) })' <<<"$tmp_array")

# Write pretty JSON
jq -S '.' <<<"$final_obj" > "$OUTPUT_JSON"

echo "Saved endpoints to: $OUTPUT_JSON" >&2
