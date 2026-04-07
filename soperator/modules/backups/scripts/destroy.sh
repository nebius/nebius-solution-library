#!/bin/bash
set -euo pipefail

# Set up kubectl context if the cluster ID is available (absent in old Terraform state).
if [ -n "${K8S_CLUSTER_ID:-}" ]; then
  nebius mk8s cluster get-credentials \
    --context-name "$K8S_CLUSTER_CONTEXT" \
    --external \
    --force \
    --id "$K8S_CLUSTER_ID"
fi

# Delete all IAM access keys for the service account.
for AKID in $(nebius iam v2 access-key list-by-account \
  --account-service-account-id "$SERVICE_ACCOUNT_ID" \
  --format json | jq -r '.items[].metadata.id'); do
  nebius iam v2 access-key delete --id "$AKID"
done

# Delete the k8s secret only if the context is available.
if kubectl config get-contexts "$K8S_CLUSTER_CONTEXT" &>/dev/null; then
  kubectl get \
    --context "$K8S_CLUSTER_CONTEXT" \
    -n "$NAMESPACE" \
    secret "$SECRET_NAME" \
    -oyaml \
    | kubectl delete --context "$K8S_CLUSTER_CONTEXT" -f -
else
  echo "kubectl context '$K8S_CLUSTER_CONTEXT' not found, skipping secret cleanup"
fi
