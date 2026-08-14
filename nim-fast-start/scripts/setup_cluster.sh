#!/usr/bin/env bash
# setup_cluster.sh — provision MK8s cluster and node groups for NIM baselines
#
# Usage:
#   ./setup_cluster.sh [--kubeconfig <path>]
#
# Requires: nebius CLI (profile sandbox), kubectl
# Cluster: archvteams-2407-baselines in project-e00z6b02t8ddk96c49
# Node groups:
#   - h100-1gpu  : 1×H100 SXM (for OpenFold2)
#   - h200-8gpu  : 1×H200 SXM 8-GPU (for Evo2-40B, uses 2 GPUs)
# Leaves environments running for Phase 2.

set -euo pipefail

PROFILE="${NEBIUS_PROFILE:-sandbox}"
PROJECT_ID="project-e00z6b02t8ddk96c49"
CLUSTER_ID="mk8scluster-e00en4dkk80w2d09c0"
CLUSTER_NAME="archvteams-2407-baselines"
SUBNET_ID="vpcsubnet-e00p701fa30cj5f7wq"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/archvteams-2407-baselines.yaml}"
NGC_SECRET_ID="mbsec-e00n1kv926bm41jrff"
NAMESPACE="nim-fast-start"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 1. Wait for cluster RUNNING ────────────────────────────────────────────
echo "[1/5] Waiting for cluster $CLUSTER_NAME to be RUNNING..."
for _ in $(seq 1 60); do
  STATE=$(nebius mk8s cluster get --id "$CLUSTER_ID" --profile "$PROFILE" \
          --format json 2>/dev/null | python3 -c \
          "import json,sys; print(json.load(sys.stdin).get('status',{}).get('state',''))" \
          2>/dev/null || echo "")
  echo "  state=$STATE"
  [[ "$STATE" == "RUNNING" ]] && break
  sleep 30
done
[[ "$STATE" != "RUNNING" ]] && { echo "ERROR: cluster not RUNNING after 30 min"; exit 1; }

# ── 2. Get kubeconfig ──────────────────────────────────────────────────────
echo "[2/5] Fetching kubeconfig..."
nebius mk8s cluster get-credentials \
  --id "$CLUSTER_ID" \
  --profile "$PROFILE" \
  --external \
  --kubeconfig "$KUBECONFIG_PATH" 2>/dev/null || \
nebius mk8s cluster get-credentials \
  --id "$CLUSTER_ID" \
  --profile "$PROFILE" \
  --kubeconfig "$KUBECONFIG_PATH"

export KUBECONFIG="$KUBECONFIG_PATH"
echo "  KUBECONFIG=$KUBECONFIG_PATH"

# ── 3. Create node groups ──────────────────────────────────────────────────
echo "[3/5] Creating node groups..."

create_ng_if_missing() {
  local ng_name="$1"; shift
  EXISTING=$(nebius mk8s node-group list --parent-id "$CLUSTER_ID" --profile "$PROFILE" \
    --format json 2>/dev/null | python3 -c \
    "import json,sys; ngs=json.load(sys.stdin).get('items',[]); print(next((n['metadata']['id'] for n in ngs if n['metadata']['name']=='$ng_name'),''))" \
    2>/dev/null || echo "")
  if [[ -n "$EXISTING" ]]; then
    echo "  Node group $ng_name already exists ($EXISTING)"
    return
  fi
  echo "  Creating node group $ng_name..."
  nebius mk8s node-group create --parent-id "$CLUSTER_ID" --profile "$PROFILE" \
    --name "$ng_name" "$@" --async
}

# H100 1-GPU for OpenFold2
create_ng_if_missing h100-1gpu \
  --fixed-node-count 1 \
  --template-resources-platform gpu-h100-sxm \
  --template-resources-preset 1gpu-16vcpu-200gb \
  --template-gpu-settings-drivers-preset cuda13.0 \
  --template-network-interfaces-subnet-id "$SUBNET_ID"

# H100 8-GPU for Evo2-40B (pod requests 2 GPUs)
create_ng_if_missing h100-8gpu \
  --fixed-node-count 1 \
  --template-resources-platform gpu-h100-sxm \
  --template-resources-preset 8gpu-128vcpu-1600gb \
  --template-gpu-settings-drivers-preset cuda13.0 \
  --template-network-interfaces-subnet-id "$SUBNET_ID"

# ── 4. Wait for nodes to join ──────────────────────────────────────────────
echo "[4/5] Waiting for GPU nodes to join..."
for _ in $(seq 1 60); do
  GPU_NODES=$(kubectl get nodes --kubeconfig "$KUBECONFIG_PATH" \
    -l 'nvidia.com/gpu.present=true' --no-headers 2>/dev/null | wc -l || echo 0)
  echo "  GPU nodes ready: $GPU_NODES"
  [[ "$GPU_NODES" -ge 2 ]] && break
  sleep 30
done

# ── 5. Deploy namespace and secrets ───────────────────────────────────────
echo "[5/5] Configuring namespace and secrets..."
kubectl apply -f "$REPO_ROOT/manifests/namespace.yaml" --kubeconfig "$KUBECONFIG_PATH"

NGC_API_KEY=$(nebius mysterybox payload get \
  --secret-id "$NGC_SECRET_ID" \
  --profile "$PROFILE" \
  --format json 2>/dev/null | python3 -c \
  "import json,sys; print(json.load(sys.stdin)['data'][0]['string_value'])")

kubectl create secret docker-registry nvcrio-cred \
  --docker-server=nvcr.io \
  --docker-username='$oauthtoken' \
  --docker-password="$NGC_API_KEY" \
  -n "$NAMESPACE" --kubeconfig "$KUBECONFIG_PATH" \
  --dry-run=client -o yaml | kubectl apply -f - --kubeconfig "$KUBECONFIG_PATH"

kubectl create secret generic ngc-api-key \
  --from-literal=NGC_API_KEY="$NGC_API_KEY" \
  -n "$NAMESPACE" --kubeconfig "$KUBECONFIG_PATH" \
  --dry-run=client -o yaml | kubectl apply -f - --kubeconfig "$KUBECONFIG_PATH"

echo ""
echo "Setup complete. KUBECONFIG=$KUBECONFIG_PATH"
echo "Next: run measure_startup.sh to collect baselines"
