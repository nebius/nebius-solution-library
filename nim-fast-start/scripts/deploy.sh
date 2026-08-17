#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: deploy.sh KUBECONFIG DYNAMO_SOURCE_DIR" >&2
  exit 2
fi

readonly kubeconfig="$1"
readonly source_dir="$2"
readonly namespace="archvteams-2407-k301ud"
readonly expected_cluster_id="mk8scluster-e00en4dkk80w2d09c0"
readonly task_selector="ml-specialist.nebius.ai/task=k301ud"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
root_dir="$(cd "${script_dir}/.." && pwd)"
readonly root_dir

server="$(kubectl --kubeconfig "${kubeconfig}" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
if [[ "${server}" != *"${expected_cluster_id}"* ]]; then
  echo "refusing deployment: kubeconfig server does not contain ${expected_cluster_id}: ${server}" >&2
  exit 1
fi

node_count="$(kubectl --kubeconfig "${kubeconfig}" get nodes -l "${task_selector}" -o json | jq '.items | length')"
if [[ "${node_count}" != "1" ]]; then
  echo "refusing deployment: expected exactly one task node, found ${node_count}" >&2
  exit 1
fi

kubectl --kubeconfig "${kubeconfig}" apply -f "${root_dir}/manifests/namespace.yaml"
kubectl --kubeconfig "${kubeconfig}" apply -f "${root_dir}/manifests/runtime-class.yaml"
kubectl --kubeconfig "${kubeconfig}" apply -f "${root_dir}/manifests/storage.yaml"

for crd in "${source_dir}"/deploy/operator/config/crd/bases/*.yaml; do
  applied_crd="$(kubectl --kubeconfig "${kubeconfig}" apply \
    --server-side \
    --field-manager=archvteams-2407-k301ud \
    -f "${crd}" -o name)"
  kubectl --kubeconfig "${kubeconfig}" label "${applied_crd}" \
    app.kubernetes.io/part-of=archvteams-2407-k301ud \
    ml-specialist.nebius.ai/task=k301ud --overwrite
done

helm upgrade --install k301ud-operator \
  "${source_dir}/deploy/helm/charts/platform/components/operator" \
  --kubeconfig "${kubeconfig}" \
  --namespace "${namespace}" \
  --values "${root_dir}/manifests/operator-values.yaml" \
  --wait \
  --timeout 10m

helm upgrade --install k301ud-snapshot \
  "${source_dir}/deploy/helm/charts/snapshot" \
  --kubeconfig "${kubeconfig}" \
  --namespace "${namespace}" \
  --values "${root_dir}/manifests/snapshot-values.yaml" \
  --wait \
  --timeout 15m

kubectl --kubeconfig "${kubeconfig}" wait \
  --namespace "${namespace}" \
  --for=condition=Available deployment/k301ud-operator-dynamo-operator-controller-manager \
  --timeout=10m
kubectl --kubeconfig "${kubeconfig}" rollout status \
  --namespace "${namespace}" daemonset/k301ud-snapshot-agent \
  --timeout=10m

kubectl --kubeconfig "${kubeconfig}" apply --dry-run=server \
  -f "${root_dir}/manifests/qwen-checkpoint-pod.yaml" >/dev/null
kubectl --kubeconfig "${kubeconfig}" apply --dry-run=server \
  -f "${root_dir}/manifests/qwen-restore-pod.yaml" >/dev/null
kubectl --kubeconfig "${kubeconfig}" apply --dry-run=server \
  -f "${root_dir}/manifests/sdxl-checkpoint-pod.yaml" >/dev/null
kubectl --kubeconfig "${kubeconfig}" apply --dry-run=server \
  -f "${root_dir}/manifests/sdxl-restore-pod.yaml" >/dev/null

kubectl --kubeconfig "${kubeconfig}" get pods,pvc -n "${namespace}" -o wide
