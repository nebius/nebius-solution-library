#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
DYNAMO_REF=${DYNAMO_REF:-f7f37be174d252590c4b56e25ff4262dd82466fd}
DYNAMO_DIR=${DYNAMO_DIR:-${ROOT_DIR}/.cache/dynamo}
WORKLOAD_NAMESPACE=${WORKLOAD_NAMESPACE:-nim-fast-start}
SYSTEM_NAMESPACE=${SYSTEM_NAMESPACE:-nim-fast-start-system}
PULL_SECRET=${PULL_SECRET:-nvcrio-cred}
SNAPSHOT_PVC=${SNAPSHOT_PVC:-archvteams-2407-snapshot}
SNAPSHOT_SIZE=${SNAPSHOT_SIZE:-64Gi}
STORAGE_CLASS=${STORAGE_CLASS:-compute-csi-default-sc}
PLATFORM_RELEASE=${PLATFORM_RELEASE:-archvteams-2407-dynamo}
SNAPSHOT_RELEASE=${SNAPSHOT_RELEASE:-archvteams-2407-snapshot}
DYNAMO_IMAGE_TAG=${DYNAMO_IMAGE_TAG:-1.4.0}
EXPECTED_BRANCH=${EXPECTED_BRANCH:-agent/archvteams-2407-p2_t41skg}

if [[ -z "${KUBECONFIG:-}" ]]; then
  echo "KUBECONFIG must point to the task-owned cluster" >&2
  exit 1
fi

branch=$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)
if [[ "${branch}" != "${EXPECTED_BRANCH}" ]]; then
  echo "Refusing to deploy from ${branch}; expected ${EXPECTED_BRANCH}" >&2
  exit 1
fi

if [[ ! -x "${ROOT_DIR}/.tools/snapshotctl" ]]; then
  echo "Run ${SCRIPT_DIR}/prepare_snapshot_tools.sh first" >&2
  exit 1
fi

resolved_ref=$(git -C "${DYNAMO_DIR}" rev-parse HEAD 2>/dev/null || true)
if [[ "${resolved_ref}" != "${DYNAMO_REF}" ]]; then
  echo "Dynamo checkout mismatch: expected ${DYNAMO_REF}, got ${resolved_ref:-missing}" >&2
  exit 1
fi

kubectl cluster-info >/dev/null

existing_operator=$(helm list --all-namespaces -o json | jq -r \
  --arg release "${PLATFORM_RELEASE}" \
  '[.[] | select((.chart | startswith("dynamo-platform-")) and .name != $release)] | length')
if [[ "${existing_operator}" != "0" ]]; then
  echo "Another Dynamo platform release already exists; refusing a second cluster-wide operator" >&2
  exit 1
fi

kubectl create namespace "${SYSTEM_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl get secret "${PULL_SECRET}" -n "${WORKLOAD_NAMESPACE}" -o json \
  | jq --arg namespace "${SYSTEM_NAMESPACE}" '
      del(.metadata.creationTimestamp, .metadata.resourceVersion, .metadata.uid, .metadata.managedFields)
      | .metadata.namespace = $namespace
    ' \
  | kubectl apply -f - >/dev/null

helm upgrade --install "${PLATFORM_RELEASE}" "${DYNAMO_DIR}/deploy/helm/charts/platform" \
  --namespace "${SYSTEM_NAMESPACE}" \
  --set dynamo-operator.checkpoint.enabled=true \
  --set "dynamo-operator.imagePullSecrets[0].name=${PULL_SECRET}" \
  --set "dynamo-operator.controllerManager.manager.image.tag=${DYNAMO_IMAGE_TAG}" \
  --wait \
  --timeout 10m

helm upgrade --install "${SNAPSHOT_RELEASE}" "${DYNAMO_DIR}/deploy/helm/charts/snapshot" \
  --namespace "${WORKLOAD_NAMESPACE}" \
  --set storage.accessMode=agentMount \
  --set storage.pvc.create=true \
  --set "storage.pvc.name=${SNAPSHOT_PVC}" \
  --set "storage.pvc.size=${SNAPSHOT_SIZE}" \
  --set "storage.pvc.storageClass=${STORAGE_CLASS}" \
  --set storage.pvc.accessMode=ReadWriteOnce \
  --set "daemonset.image.tag=${DYNAMO_IMAGE_TAG}" \
  --set "daemonset.imagePullSecrets[0].name=${PULL_SECRET}" \
  --set daemonset.resources.requests.cpu=100m \
  --set daemonset.resources.requests.memory=256Mi \
  --set daemonset.resources.limits.cpu=4 \
  --set daemonset.resources.limits.memory=4Gi \
  --set-string 'daemonset.nodeSelector.nebius\.com/gpu=true' \
  --set 'daemonset.nodeSelector.nvidia\.com/gpu\.present=null' \
  --wait \
  --timeout 10m

kubectl label pvc "${SNAPSHOT_PVC}" -n "${WORKLOAD_NAMESPACE}" \
  workload=archvteams-2407 task=nim-fast-start phase=feasibility --overwrite

kubectl rollout status deployment -n "${SYSTEM_NAMESPACE}" \
  -l control-plane=controller-manager --timeout=5m
kubectl rollout status daemonset -n "${WORKLOAD_NAMESPACE}" \
  -l app.kubernetes.io/component=snapshot-agent --timeout=5m

printf 'Dynamo platform release: %s/%s\nSnapshot release: %s/%s\nSnapshot PVC: %s/%s\n' \
  "${SYSTEM_NAMESPACE}" "${PLATFORM_RELEASE}" \
  "${WORKLOAD_NAMESPACE}" "${SNAPSHOT_RELEASE}" \
  "${WORKLOAD_NAMESPACE}" "${SNAPSHOT_PVC}"
