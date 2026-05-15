#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib.sh"

require_command curl
require_command nebius
require_command openssl
load_environment "$ROOT_DIR"

SUBNET_ID="$(resolve_subnet_id)"
AUTH_TOKEN="${AUTH_TOKEN:-$(openssl rand -hex 32)}"
ENDPOINT_NAME="${SERVERLESS_VLLM_ENDPOINT_NAME}-$(random_suffix)"

echo "Creating OpenAI-compatible vLLM endpoint: $ENDPOINT_NAME"
nebius ai endpoint create \
  --name "$ENDPOINT_NAME" \
  --image "$SERVERLESS_VLLM_IMAGE" \
  --container-command "python3 -m vllm.entrypoints.openai.api_server" \
  --args "--model $SERVERLESS_VLLM_MODEL_ID --host 0.0.0.0 --port 8000" \
  --platform "$SERVERLESS_VLLM_PLATFORM" \
  --preset "$SERVERLESS_VLLM_PRESET" \
  --public \
  --container-port 8000 \
  --auth token \
  --token "$AUTH_TOKEN" \
  --shm-size "$SERVERLESS_VLLM_SHM_SIZE" \
  --subnet-id "$SUBNET_ID"

ENDPOINT_ID="$(nebius ai endpoint get-by-name --name "$ENDPOINT_NAME" --format jsonpath='{.metadata.id}')"

cat <<EOF

Created endpoint:
  name: $ENDPOINT_NAME
  id:   $ENDPOINT_ID

Endpoint startup can take several minutes. Wait until status is Running:
  nebius ai endpoint get $ENDPOINT_ID
EOF

echo
echo "Resolving public endpoint address..."
ENDPOINT_IP="$(nebius ai endpoint get "$ENDPOINT_ID" --format jsonpath='{.status.public_endpoints[0]}')"
ENDPOINT_ENV="$SCRIPT_DIR/.endpoint.env"

cat > "$ENDPOINT_ENV" <<EOF
ENDPOINT_NAME="$ENDPOINT_NAME"
ENDPOINT_ID="$ENDPOINT_ID"
ENDPOINT_IP="$ENDPOINT_IP"
ENDPOINT_URL="http://$ENDPOINT_IP"
AUTH_TOKEN="$AUTH_TOKEN"
MODEL_ID="$SERVERLESS_VLLM_MODEL_ID"
EOF

cat <<EOF

Endpoint IP:
  $ENDPOINT_IP

Connection details written to:
  $ENDPOINT_ENV

List models:
  curl "http://$ENDPOINT_IP/v1/models" -H "Authorization: Bearer $AUTH_TOKEN"

After the endpoint status is Running, run the support-ticket triage example:
  ./endpoints/vllm-openai/run-triage.sh

View logs:
  nebius ai endpoint logs $ENDPOINT_ID

Delete the endpoint after validation:
  nebius ai endpoint delete $ENDPOINT_ID
EOF
