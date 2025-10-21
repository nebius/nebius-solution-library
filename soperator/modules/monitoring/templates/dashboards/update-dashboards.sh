#!/bin/bash
# Updates soperator Grafana dashboards in a Kubernetes cluster by replacing ConfigMaps
# Usage: ./update-dashboards.sh <k8s-context-name>
# This script will switch to the specified context and update all dashboard ConfigMaps
# in the monitoring-system namespace with the JSON files from this directory

set -e

if [ $# -ne 1 ]; then
    echo "Error: Please provide a Kubernetes context name"
    echo "Usage: $0 <k8s-context-name>"
    exit 1
fi

CONTEXT="$1"
NAMESPACE="monitoring-system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Updating soperator Grafana dashboards..."
echo "Dashboard directory: ${SCRIPT_DIR}"

kubectl config use-context "${CONTEXT}"

DASHBOARDS=($(ls "${SCRIPT_DIR}"/*.json 2>/dev/null | xargs -n1 basename))

if [ ${#DASHBOARDS[@]} -eq 0 ]; then
    echo "Error: No JSON dashboard files found in ${SCRIPT_DIR}"
    exit 1
fi

echo "Found ${#DASHBOARDS[@]} dashboard files: ${DASHBOARDS[*]}"
echo

updated_count=0
skipped_count=0

for file in "${DASHBOARDS[@]}"; do
    configmap_name="soperator-${file%.json}"
    configmap_name="${configmap_name//_/-}"

    local_hash=$(md5sum "${SCRIPT_DIR}/${file}" | cut -d' ' -f1)

    current_configmap_hash=""
    if kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" >/dev/null 2>&1; then
        current_configmap_hash=$(kubectl get configmap "${configmap_name}" -n "${NAMESPACE}" -o jsonpath="{.data['${file%.json}\.json']}" 2>/dev/null | md5sum | cut -d' ' -f1)
    fi

    if [ "$local_hash" = "$current_configmap_hash" ] && [ -n "$current_configmap_hash" ]; then
        echo "✓ ${configmap_name} - no changes, skipping"
        ((skipped_count++))
        continue
    fi

    echo "↻ ${configmap_name} - updating..."

    kubectl delete configmap "${configmap_name}" -n "${NAMESPACE}" 2>/dev/null || true

    kubectl create configmap "${configmap_name}" -n "${NAMESPACE}" \
        --from-file="${file%.json}.json=${SCRIPT_DIR}/${file}"

    kubectl label configmap "${configmap_name}" -n "${NAMESPACE}" grafana_dashboard=1

    ((updated_count++))
done

echo
if [ $updated_count -eq 0 ]; then
    echo "✅ All dashboards are up to date!"
else
    echo "✅ Updated $updated_count dashboard(s), skipped $skipped_count unchanged"
    echo "⏳ Waiting for Grafana to reload dashboards automatically..."
    for i in {30..1}; do
        printf "\r⏳ Wait for %2d seconds..." "$i"
        sleep 1
    done
    printf "\r✅ Done waiting! Dashboards should be reloaded.\n"
fi
