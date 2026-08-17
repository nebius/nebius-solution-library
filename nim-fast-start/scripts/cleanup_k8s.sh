#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: cleanup_k8s.sh KUBECONFIG DYNAMO_SOURCE_DIR" >&2
  exit 2
fi

readonly kubeconfig="$1"
readonly source_dir="$2"
readonly namespace="archvteams-2407-k301ud"
readonly expected_cluster_id="mk8scluster-e00en4dkk80w2d09c0"
readonly crd_dir="${source_dir}/deploy/operator/config/crd/bases"

if ! compgen -G "${crd_dir}/*.yaml" >/dev/null; then
  echo "refusing cleanup: no Dynamo CRD manifests found under ${crd_dir}" >&2
  exit 1
fi

server="$(kubectl --kubeconfig "${kubeconfig}" config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
if [[ "${server}" != *"${expected_cluster_id}"* ]]; then
  echo "refusing cleanup: kubeconfig server does not contain ${expected_cluster_id}: ${server}" >&2
  exit 1
fi

namespace_part_of="$(kubectl --kubeconfig "${kubeconfig}" get namespace "${namespace}" \
  -o jsonpath='{.metadata.labels.app\.kubernetes\.io/part-of}' 2>/dev/null || true)"
if [[ -n "${namespace_part_of}" && "${namespace_part_of}" != "archvteams-2407-k301ud" ]]; then
  echo "refusing cleanup: unexpected namespace ownership label: ${namespace_part_of}" >&2
  exit 1
fi

# Remove only the task-owned directory from the user-authorized shared
# filesystem. The mount and literal path checks make a broader deletion fail
# closed. Existing sibling directories on the filesystem are never traversed.
if kubectl --kubeconfig "${kubeconfig}" get pod k301ud-sfs-mounter \
  --namespace "${namespace}" >/dev/null 2>&1; then
  kubectl --kubeconfig "${kubeconfig}" exec k301ud-sfs-mounter \
    --namespace "${namespace}" -- /bin/sh -c '
      set -eu
      grep -q " /host-mnt/k301ud-sfs virtiofs " /proc/mounts
      test -d /host-mnt/k301ud-sfs/k301ud
      rm -rf -- /host-mnt/k301ud-sfs/k301ud
      test ! -e /host-mnt/k301ud-sfs/k301ud
    '
  echo "removed task SFS directory /k301ud"
fi

# Delete namespace-scoped snapshot metadata while its controller is still
# present. Also remove any task contents left by an interrupted prior cleanup;
# PodSnapshotContent is cluster-scoped and does not disappear with a namespace.
if kubectl --kubeconfig "${kubeconfig}" get crd \
  podsnapshots.nvidia.com >/dev/null 2>&1; then
  mapfile -t snapshot_contents < <(
    kubectl --kubeconfig "${kubeconfig}" get \
      podsnapshotcontents.nvidia.com -o json 2>/dev/null \
      | jq -r --arg namespace "${namespace}" \
        '.items[] | select(.spec.snapshotRef.namespace == $namespace) | .metadata.name'
  )
  kubectl --kubeconfig "${kubeconfig}" delete podsnapshots.nvidia.com \
    --namespace "${namespace}" --all --ignore-not-found \
    --wait=true --timeout=5m
  if (( ${#snapshot_contents[@]} > 0 )); then
    kubectl --kubeconfig "${kubeconfig}" delete \
      podsnapshotcontents.nvidia.com "${snapshot_contents[@]}" \
      --ignore-not-found --wait=true --timeout=5m
  fi
fi

for release in k301ud-sfs k301ud-snapshot k301ud-operator; do
  if helm status "${release}" --namespace "${namespace}" \
    --kubeconfig "${kubeconfig}" >/dev/null 2>&1; then
    helm uninstall "${release}" --namespace "${namespace}" \
      --kubeconfig "${kubeconfig}" --wait --timeout 10m
  fi
done

kubectl --kubeconfig "${kubeconfig}" delete namespace "${namespace}" \
  --ignore-not-found --wait=true --timeout=15m
kubectl --kubeconfig "${kubeconfig}" delete pv \
  archvteams-2407-k301ud-checkpoints \
  archvteams-2407-k301ud-sfs-checkpoints --ignore-not-found
kubectl --kubeconfig "${kubeconfig}" delete storageclass \
  archvteams-2407-k301ud-memory \
  archvteams-2407-k301ud-sfs --ignore-not-found

# The cluster had no RuntimeClass before this task. Do not remove it if another
# namespace began using it while the benchmark was active.
runtime_users="$(kubectl --kubeconfig "${kubeconfig}" get pods --all-namespaces \
  -o json | jq '[.items[] | select(.spec.runtimeClassName == "nvidia")] | length')"
if [[ "${runtime_users}" == "0" ]]; then
  kubectl --kubeconfig "${kubeconfig}" delete runtimeclass nvidia --ignore-not-found
else
  echo "retaining RuntimeClass nvidia: ${runtime_users} live pod(s) use it" >&2
fi

# CRDs were absent before the task. Remove each only if no custom resources
# remain anywhere, so a newly arrived sibling workload can never be disrupted.
for crd_file in "${crd_dir}"/*.yaml; do
  crd_name="$(awk '$1 == "name:" {print $2; exit}' "${crd_file}")"
  [[ -n "${crd_name}" ]] || continue
  instance_count="$(kubectl --kubeconfig "${kubeconfig}" get "${crd_name}" \
    --all-namespaces -o json 2>/dev/null | jq '.items | length' || echo 0)"
  if [[ "${instance_count}" == "0" ]]; then
    kubectl --kubeconfig "${kubeconfig}" delete crd "${crd_name}" --ignore-not-found
  else
    echo "retaining CRD ${crd_name}: ${instance_count} custom resource(s) remain" >&2
  fi
done
