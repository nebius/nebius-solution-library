#!/usr/bin/env bash

set -euo pipefail

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
}

load_environment() {
  local root_dir="$1"
  if [[ -f "$root_dir/.env.serverless-ai" ]]; then
    # shellcheck disable=SC1091
    source "$root_dir/.env.serverless-ai"
  else
    # shellcheck disable=SC1091
    source "$root_dir/environment.sh"
  fi
}

resolve_subnet_id() {
  if [[ -n "${SERVERLESS_SUBNET_ID:-}" ]]; then
    echo "$SERVERLESS_SUBNET_ID"
    return
  fi

  nebius vpc subnet get-by-name \
    --name "${SERVERLESS_SUBNET_NAME:-default-subnet}" \
    --format jsonpath='{.metadata.id}'
}

random_suffix() {
  date +%Y%m%d%H%M%S
}
