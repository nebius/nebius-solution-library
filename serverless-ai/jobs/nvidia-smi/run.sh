#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

require_command nebius
load_environment "$ROOT_DIR"

SUBNET_ID="$(resolve_subnet_id)"
JOB_NAME="${SERVERLESS_JOB_NAME}-$(random_suffix)"

echo "Creating Serverless AI job: $JOB_NAME"
nebius ai job create \
  --name "$JOB_NAME" \
  --image "$SERVERLESS_JOB_IMAGE" \
  --container-command bash \
  --args "-c nvidia-smi" \
  --platform "$SERVERLESS_JOB_PLATFORM" \
  --preset "$SERVERLESS_JOB_PRESET" \
  --timeout "$SERVERLESS_JOB_TIMEOUT" \
  --subnet-id "$SUBNET_ID"

JOB_ID="$(nebius ai job get-by-name --name "$JOB_NAME" --format jsonpath='{.metadata.id}')"

cat <<EOF

Created job:
  name: $JOB_NAME
  id:   $JOB_ID

Inspect status:
  nebius ai job get $JOB_ID

View logs:
  nebius ai job logs $JOB_ID

Delete the job record after validation:
  nebius ai job delete $JOB_ID
EOF
