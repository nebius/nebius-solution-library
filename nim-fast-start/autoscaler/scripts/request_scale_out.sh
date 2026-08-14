#!/usr/bin/env bash
set -euo pipefail

namespace="${NAMESPACE:-nim-fast-start}"
desired="${1:?usage: request_scale_out.sh DESIRED_ACTIVE_REPLICAS}"

[[ "$desired" =~ ^[0-9]+$ ]] || {
  echo "desired replicas must be a non-negative integer" >&2
  exit 2
}

kubectl patch configmap nim-prewarm-demand \
  --namespace "$namespace" \
  --type merge \
  --patch "{\"data\":{\"desired-active\":\"${desired}\"}}"
