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
ENDPOINT_NAME="${SERVERLESS_ENDPOINT_NAME}-$(random_suffix)"

echo "Creating authenticated Serverless AI endpoint: $ENDPOINT_NAME"
nebius ai endpoint create \
  --name "$ENDPOINT_NAME" \
  --image nginx:alpine \
  --platform "$SERVERLESS_ENDPOINT_PLATFORM" \
  --preset "$SERVERLESS_ENDPOINT_PRESET" \
  --public \
  --container-port 80 \
  --auth token \
  --token "$AUTH_TOKEN" \
  --subnet-id "$SUBNET_ID"

ENDPOINT_ID="$(nebius ai endpoint get-by-name --name "$ENDPOINT_NAME" --format jsonpath='{.metadata.id}')"

cat <<EOF

Created endpoint:
  name: $ENDPOINT_NAME
  id:   $ENDPOINT_ID

Wait until the endpoint is Running:
  nebius ai endpoint get $ENDPOINT_ID
EOF

echo
echo "Resolving public endpoint address..."
ENDPOINT_IP="$(nebius ai endpoint get "$ENDPOINT_ID" --format jsonpath='{.status.public_endpoints[0]}')"

cat <<EOF

Endpoint IP:
  $ENDPOINT_IP

Testing authenticated request:
EOF

curl -fsS "http://$ENDPOINT_IP" -H "Authorization: Bearer $AUTH_TOKEN" >/dev/null
echo "Authenticated request succeeded."

echo "Testing unauthenticated request; expected HTTP 401 or 403."
HTTP_STATUS="$(curl -sS -o /dev/null -w "%{http_code}" "http://$ENDPOINT_IP" || true)"
echo "Unauthenticated HTTP status: $HTTP_STATUS"

cat <<EOF

View logs:
  nebius ai endpoint logs $ENDPOINT_ID

Delete the endpoint after validation:
  nebius ai endpoint delete $ENDPOINT_ID
EOF
