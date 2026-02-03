#!/bin/bash
set -euo pipefail

context="${K8S_CLUSTER_CONTEXT:?context is required}"
namespace="${SOPERATOR_NAMESPACE:?namespace is required}"
service="${LOGIN_SERVICE_NAME:?service name is required}"

system_namespace="${namespace}-system"

if ! kubectl get namespace "$namespace" --context "$context" >/dev/null 2>&1; then
  echo "Namespace $namespace not found or cluster unreachable; skipping login service cleanup."
  exit 0
fi

if ! kubectl get namespace "$system_namespace" --context "$context" >/dev/null 2>&1; then
  echo "Namespace $namespace not found or cluster unreachable; skipping login service cleanup."
  exit 0
fi

echo "Attempting to stop soperator controller to prevent service recreation..."
if kubectl get deployment soperator-controller-manager -n "$system_namespace" --context "$context" >/dev/null 2>&1; then
  kubectl scale deployment soperator-controller-manager -n "$system_namespace" --context "$context" --replicas=0
fi

if ! kubectl get service "$service" -n "$namespace" --context "$context" >/dev/null 2>&1; then
  echo "Service $namespace/$service not found; nothing to delete."
  exit 0
fi

echo "Deleting service $namespace/$service..."
kubectl delete service "$service" -n "$namespace" --context "$context" --wait=true --timeout=5m
