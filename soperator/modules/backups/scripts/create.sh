#!/bin/bash
set -euo pipefail

kubectl create namespace "$NAMESPACE" --context "$K8S_CLUSTER_CONTEXT" || true

AKID=$(nebius iam v2 access-key create --parent-id "$IAM_PROJECT_ID" \
  --account-service-account-id "$SERVICE_ACCOUNT_ID" \
  --format json | jq -r '.metadata.id')

kubectl apply --server-side --context "$K8S_CLUSTER_CONTEXT" -f - <<EOF
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: $SECRET_NAME
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/managed-by: soperator-terraform
  annotations:
    slurm.nebius.ai/service-account: $SERVICE_ACCOUNT_ID
data:
  aws-access-key-id: $(nebius iam v2 access-key get --id "$AKID" --format json | jq -r '.status.aws_access_key_id' | tr -d '\n' | base64)
  aws-access-secret-key: $(nebius iam v2 access-key get --id "$AKID" --format json | jq -r '.status.secret' | tr -d '\n' | base64)
  backup-password: $(echo -n "$BACKUPS_PASSWORD" | base64)
EOF
