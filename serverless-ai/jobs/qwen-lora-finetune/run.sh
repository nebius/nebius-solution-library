#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

require_command nebius
load_environment "$ROOT_DIR"

SUBNET_ID="$(resolve_subnet_id)"
BUCKET_ID="$(nebius storage bucket get-by-name --name "$SERVERLESS_FINE_TUNE_BUCKET" --format jsonpath='{.metadata.id}')"
JOB_NAME="${SERVERLESS_FINE_TUNE_JOB_NAME}-$(random_suffix)"
AXOLOTL_COMMAND='RUN_ID=run-$(date +%Y%m%d-%H%M%S); axolotl train /workspace/data/config.yaml && mkdir -p /workspace/data/output/$RUN_ID && cp -r /workspace/output/. /workspace/data/output/$RUN_ID'

echo "Creating Serverless AI fine-tuning job: $JOB_NAME"
nebius ai job create \
  --name "$JOB_NAME" \
  --subnet-id "$SUBNET_ID" \
  --image "$SERVERLESS_FINE_TUNE_IMAGE" \
  --platform "$SERVERLESS_FINE_TUNE_PLATFORM" \
  --preset "$SERVERLESS_FINE_TUNE_PRESET" \
  --disk-size "$SERVERLESS_FINE_TUNE_DISK_SIZE" \
  --volume "$BUCKET_ID:/workspace/data" \
  --container-command bash \
  --args "-c \"$AXOLOTL_COMMAND\""

JOB_ID="$(nebius ai job get-by-name --name "$JOB_NAME" --format jsonpath='{.metadata.id}')"

cat <<EOF

Created fine-tuning job:
  name:   $JOB_NAME
  id:     $JOB_ID
  bucket: s3://$SERVERLESS_FINE_TUNE_BUCKET/output/

Watch status:
  nebius ai job get $JOB_ID

Watch logs:
  nebius ai job logs $JOB_ID

Delete the job record after validation:
  nebius ai job delete $JOB_ID
EOF
