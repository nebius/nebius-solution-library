#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

require_command nebius
load_environment "$ROOT_DIR"

PROFILE="${1:-$SERVERLESS_FINE_TUNE_PROFILE}"

print_profiles() {
  cat <<'EOF'
Fine-tuning job profiles:
  l40s-a    gpu-l40s-a      1gpu-8vcpu-32gb       low-cost default
  l40s-d    gpu-l40s-d      4gpu-192vcpu-1152gb   largest documented L40S profile
  b200      gpu-b200-sxm    8gpu-160vcpu-1792gb   8x B200
  b200-a    gpu-b200-sxm-a  8gpu-160vcpu-1792gb   8x B200, ME West platform
  b300      gpu-b300-sxm    8gpu-192vcpu-2768gb   8x B300
  h100      gpu-h100-sxm    8gpu-128vcpu-1600gb   8x H100
  h200      gpu-h200-sxm    8gpu-128vcpu-1600gb   8x H200
  rtx6000   gpu-rtx6000     8gpu-192vcpu-1744gb   8x RTX PRO 6000

Custom:
  SERVERLESS_FINE_TUNE_PLATFORM=<platform> SERVERLESS_FINE_TUNE_PRESET=<preset> ./jobs/qwen-lora-finetune/run.sh custom

B100:
  Public Nebius docs do not currently list a B100 platform ID. If your project exposes one, use the custom profile.
EOF
}

case "$PROFILE" in
  list|--list|-l)
    print_profiles
    exit 0
    ;;
  l40s-a|ls40-a)
    PROFILE_PLATFORM="gpu-l40s-a"
    PROFILE_PRESET="1gpu-8vcpu-32gb"
    PROFILE_LABEL="l40s-a"
    ;;
  l40s-d|l40s|ls40|ls40-d)
    PROFILE_PLATFORM="gpu-l40s-d"
    PROFILE_PRESET="4gpu-192vcpu-1152gb"
    PROFILE_LABEL="l40s-d"
    ;;
  b200)
    PROFILE_PLATFORM="gpu-b200-sxm"
    PROFILE_PRESET="8gpu-160vcpu-1792gb"
    PROFILE_LABEL="b200"
    ;;
  b200-a)
    PROFILE_PLATFORM="gpu-b200-sxm-a"
    PROFILE_PRESET="8gpu-160vcpu-1792gb"
    PROFILE_LABEL="b200-a"
    ;;
  b300)
    PROFILE_PLATFORM="gpu-b300-sxm"
    PROFILE_PRESET="8gpu-192vcpu-2768gb"
    PROFILE_LABEL="b300"
    ;;
  h100)
    PROFILE_PLATFORM="gpu-h100-sxm"
    PROFILE_PRESET="8gpu-128vcpu-1600gb"
    PROFILE_LABEL="h100"
    ;;
  h200)
    PROFILE_PLATFORM="gpu-h200-sxm"
    PROFILE_PRESET="8gpu-128vcpu-1600gb"
    PROFILE_LABEL="h200"
    ;;
  rtx6000|rtx-pro-6000)
    PROFILE_PLATFORM="gpu-rtx6000"
    PROFILE_PRESET="8gpu-192vcpu-1744gb"
    PROFILE_LABEL="rtx6000"
    ;;
  b100)
    echo "B100 is not listed in the public Nebius platform docs. Use custom with SERVERLESS_FINE_TUNE_PLATFORM and SERVERLESS_FINE_TUNE_PRESET if your project exposes B100." >&2
    exit 2
    ;;
  custom)
    PROFILE_PLATFORM="${SERVERLESS_FINE_TUNE_PLATFORM:?Set SERVERLESS_FINE_TUNE_PLATFORM for custom profile}"
    PROFILE_PRESET="${SERVERLESS_FINE_TUNE_PRESET:?Set SERVERLESS_FINE_TUNE_PRESET for custom profile}"
    PROFILE_LABEL="custom"
    ;;
  *)
    echo "Unknown fine-tuning profile: $PROFILE" >&2
    echo >&2
    print_profiles >&2
    exit 2
    ;;
esac

FINE_TUNE_PLATFORM="${SERVERLESS_FINE_TUNE_PLATFORM:-$PROFILE_PLATFORM}"
FINE_TUNE_PRESET="${SERVERLESS_FINE_TUNE_PRESET:-$PROFILE_PRESET}"

SUBNET_ID="$(resolve_subnet_id)"
BUCKET_ID="$(nebius storage bucket get-by-name --name "$SERVERLESS_FINE_TUNE_BUCKET" --format jsonpath='{.metadata.id}')"
JOB_NAME="${SERVERLESS_FINE_TUNE_JOB_NAME}-${PROFILE_LABEL}-$(random_suffix)"
AXOLOTL_COMMAND='nvidia-smi -L || true; RUN_ID=run-$(date +%Y%m%d-%H%M%S); axolotl train /workspace/data/config.yaml && mkdir -p /workspace/data/output/$RUN_ID && cp -r /workspace/output/. /workspace/data/output/$RUN_ID'

echo "Creating Serverless AI fine-tuning job: $JOB_NAME"
echo "  profile:  $PROFILE_LABEL"
echo "  platform: $FINE_TUNE_PLATFORM"
echo "  preset:   $FINE_TUNE_PRESET"
nebius ai job create \
  --name "$JOB_NAME" \
  --subnet-id "$SUBNET_ID" \
  --image "$SERVERLESS_FINE_TUNE_IMAGE" \
  --platform "$FINE_TUNE_PLATFORM" \
  --preset "$FINE_TUNE_PRESET" \
  --disk-size "$SERVERLESS_FINE_TUNE_DISK_SIZE" \
  --volume "$BUCKET_ID:/workspace/data" \
  --container-command bash \
  --args "-c \"$AXOLOTL_COMMAND\""

JOB_ID="$(nebius ai job get-by-name --name "$JOB_NAME" --format jsonpath='{.metadata.id}')"

cat <<EOF

Created fine-tuning job:
  name:   $JOB_NAME
  id:     $JOB_ID
  profile:  $PROFILE_LABEL
  platform: $FINE_TUNE_PLATFORM
  preset:   $FINE_TUNE_PRESET
  bucket: s3://$SERVERLESS_FINE_TUNE_BUCKET/output/

Watch status:
  nebius ai job get $JOB_ID

Watch logs:
  nebius ai job logs $JOB_ID

Delete the job record after validation:
  nebius ai job delete $JOB_ID
EOF
