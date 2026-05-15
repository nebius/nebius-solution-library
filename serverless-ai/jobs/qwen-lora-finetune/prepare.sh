#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

require_command aws
require_command nebius
load_environment "$ROOT_DIR"

BUCKET_NAME="$SERVERLESS_FINE_TUNE_BUCKET"

if nebius storage bucket get-by-name --name "$BUCKET_NAME" >/dev/null 2>&1; then
  echo "Using existing bucket: $BUCKET_NAME"
else
  echo "Creating bucket: $BUCKET_NAME"
  nebius storage bucket create --name "$BUCKET_NAME"
fi

echo "Uploading Axolotl config to s3://$BUCKET_NAME/config.yaml"
aws s3 cp "$SCRIPT_DIR/config.yaml" "s3://$BUCKET_NAME/config.yaml"

cat <<EOF

Prepared fine-tuning inputs.

Next:
  ./jobs/qwen-lora-finetune/run.sh
EOF
