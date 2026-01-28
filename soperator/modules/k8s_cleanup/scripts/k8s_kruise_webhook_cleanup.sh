#!/bin/bash
set -euo pipefail

context="${K8S_CLUSTER_CONTEXT:?context is required}"
webhook="${K8S_WEBHOOK_NAME:?webhook name is required}"

if ! kubectl version --context "$context" >/dev/null 2>&1; then
  echo "Cluster unreachable for context $context; skipping kruise webhook cleanup."
  exit 0
fi

if ! kubectl get mutatingwebhookconfiguration "$webhook" --context "$context" >/dev/null 2>&1; then
  echo "MutatingWebhookConfiguration $webhook not found; nothing to delete."
  exit 0
fi

echo "Deleting MutatingWebhookConfiguration $webhook..."
kubectl delete mutatingwebhookconfiguration "$webhook" --context "$context" --wait=true --timeout=2m
