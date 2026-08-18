#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 RUN_ID [--cleanup]" >&2
  exit 64
fi

run_id=$1
cleanup=${2:-}
checkpoint_id=${B2_CHECKPOINT_ID:-boltz2-native-f7-v1}
artifact_manifest_sha256=${B2_ARTIFACT_MANIFEST_SHA256:-6539b9f50a71c9f5fb6a3fbacd44f5d5ea41003539b6563682a38600d1492456}
kubeconfig=/home/tux/.local/state/archvteams-2407/openfold2-snapshot/private/kubeconfig
namespace=nim-fast-start
node=computeinstance-e00t12crqg6tw0kz65
code_dir=/home/tux/worktrees/archvteams-2407-openfold2-faststart/nim-fast-start/faststart-v2/boltz2-native
root=/home/tux/.local/state/archvteams-2407/boltz2-native-f7-20260818T0310Z
run_dir="$root/runs/$run_id"
target="b2-target-$run_id"
worker="b2-restore-$run_id"
probe="b2-semantic-$run_id"
canary="b2-canary-$run_id"

if [[ ! $run_id =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ || ${#run_id} -gt 30 ]]; then
  echo "invalid run ID" >&2
  exit 64
fi
if [[ -e $run_dir ]]; then
  echo "run directory already exists: $run_dir" >&2
  exit 73
fi
if [[ $cleanup != "" && $cleanup != "--cleanup" ]]; then
  echo "second argument must be --cleanup" >&2
  exit 64
fi

server=$(kubectl --kubeconfig "$kubeconfig" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
if [[ $server != "https://pu.mk8scluster-e00en4dkk80w2d09c0.mk8s.eu-north1.nebius.cloud:443" ]]; then
  echo "kubeconfig is not bound to the allowed cluster" >&2
  exit 78
fi
for holder in of2-artifact-holder-t12 boltz2-cache-holder-r3-t12; do
  if [[ $(kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$holder" -o jsonpath='{.status.containerStatuses[0].ready}') != true ]]; then
    echo "required holder is not Ready: $holder" >&2
    exit 69
  fi
done
if kubectl --kubeconfig "$kubeconfig" -n "$namespace" get daemonset archvteams-2407-native-snapshot-agent >/dev/null 2>&1; then
  echo "native capture agent must be absent during restore" >&2
  exit 69
fi

install -d -m 700 "$root/runs"
mkdir -m 700 "$run_dir"
cp "$code_dir/restore-interface.live.json" "$run_dir/restore-interface.json"
sha256sum "$run_dir/restore-interface.json" > "$run_dir/restore-interface.sha256"

demand=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
jq -n \
  --arg run_id "$run_id" \
  --arg demand_at "$demand" \
  --arg node "$node" \
  --arg checkpoint_id "$checkpoint_id" \
  --arg artifact_manifest_sha256 "$artifact_manifest_sha256" \
  '{
    schema:"archvteams.nebius.ai/boltz2-faststart-run/v1",
    demand_at:$demand_at,
    run_id:$run_id,
    target_node:$node,
    checkpoint_id:$checkpoint_id,
    artifact_version:"1",
    artifact_manifest_sha256:$artifact_manifest_sha256,
    artifact_pvc:"mlspec-archvteams-2407-ckpt-m3",
    cache_pvc:"boltz2-nim-cache-native-f7-r3"
  }' > "$run_dir/run.json"

python3 "$code_dir/render.py" target \
  --contract "$run_dir/restore-interface.json" \
  --run-config "$run_dir/run.json" > "$run_dir/target.yaml"
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$run_dir/target-submit-at.txt"
kubectl --kubeconfig "$kubeconfig" create -f "$run_dir/target.yaml"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" wait \
  --for=jsonpath='{.status.containerStatuses[0].state.running}' \
  "pod/$target" --timeout=300s
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$target" -o json \
  > "$run_dir/target-before-binding.json"

python3 "$code_dir/bind_target.py" \
  --contract "$run_dir/restore-interface.json" \
  --run-config "$run_dir/run.json" \
  --pod-json "$run_dir/target-before-binding.json" \
  --collected-at "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" \
  --binding-output "$run_dir/binding.json" \
  --patch-output "$run_dir/target-pod-spec.patch.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" patch pod "$target" \
  --type=json --patch-file="$run_dir/target-pod-spec.patch.json" -o json \
  > "$run_dir/target-patch-response.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$target" -o json \
  > "$run_dir/target-bound.json"

# Submit the external CPU client before the one-shot restore worker. It polls
# the run-scoped ClusterIP and records exactly two distinct semantic calls.
python3 "$code_dir/render.py" probe \
  --contract "$run_dir/restore-interface.json" \
  --run-config "$run_dir/run.json" \
  --binding "$run_dir/binding.json" > "$run_dir/semantic-probe.yaml"
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$run_dir/probe-submit-at.txt"
kubectl --kubeconfig "$kubeconfig" create -f "$run_dir/semantic-probe.yaml"

python3 "$code_dir/render.py" restore \
  --contract "$run_dir/restore-interface.json" \
  --run-config "$run_dir/run.json" \
  --binding "$run_dir/binding.json" > "$run_dir/restore-worker.yaml"
date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$run_dir/worker-submit-at.txt"
kubectl --kubeconfig "$kubeconfig" create -f "$run_dir/restore-worker.yaml"

wait_for_job() {
  local name=$1
  local output=$2
  local attempt
  for ((attempt=0; attempt<900; attempt++)); do
    kubectl --kubeconfig "$kubeconfig" -n "$namespace" get job "$name" -o json > "$output"
    if jq -e '(.status.succeeded // 0) == 1' "$output" >/dev/null; then
      return 0
    fi
    if jq -e '(.status.failed // 0) > 0' "$output" >/dev/null; then
      return 1
    fi
    sleep 1
  done
  return 124
}

if ! wait_for_job "$worker" "$run_dir/worker-job.json"; then
  kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pods -l "job-name=$worker" -o json \
    > "$run_dir/worker-pods.failed.json"
  exit 1
fi
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pods -l "job-name=$worker" -o json \
  > "$run_dir/worker-pods.json"
worker_pod=$(jq -er 'select((.items|length)==1) | .items[0].metadata.name' "$run_dir/worker-pods.json")
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$worker_pod" -o json \
  > "$run_dir/worker-pod.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" logs "$worker_pod" > "$run_dir/worker.log"
tail -1 "$run_dir/worker.log" | jq -e -c 'select(.status=="succeeded")' \
  > "$run_dir/worker-receipt.json"

kubectl --kubeconfig "$kubeconfig" -n "$namespace" wait \
  --for=condition=Ready "pod/$target" --timeout=300s
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$target" -o json \
  > "$run_dir/target-ready.json"

if ! wait_for_job "$probe" "$run_dir/probe-job.json"; then
  kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pods -l "job-name=$probe" -o json \
    > "$run_dir/probe-pods.failed.json"
  exit 1
fi
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pods -l "job-name=$probe" -o json \
  > "$run_dir/probe-pods.json"
probe_pod=$(jq -er 'select((.items|length)==1) | .items[0].metadata.name' "$run_dir/probe-pods.json")
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$probe_pod" -o json \
  > "$run_dir/probe-pod.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" logs "$probe_pod" > "$run_dir/semantic-probe.log"
tail -1 "$run_dir/semantic-probe.log" | jq -e -c \
  'select(.status=="PASS" and .ok==true and .passed_case_count==2 and .failed_case_count==0)' \
  > "$run_dir/semantic-summary.json"

kubectl --kubeconfig "$kubeconfig" -n "$namespace" get pod "$target" -o json \
  > "$run_dir/target-final.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get service "$canary" -o json \
  > "$run_dir/canary-service.json"
kubectl --kubeconfig "$kubeconfig" -n "$namespace" get endpointslices.discovery.k8s.io \
  -l "kubernetes.io/service-name=$canary" -o json > "$run_dir/canary-endpointslices.json"

python3 - "$run_dir" <<'PY' > "$run_dir/trial-summary.json"
import json
import sys
from datetime import datetime
from pathlib import Path

directory = Path(sys.argv[1])
run = json.loads((directory / "run.json").read_text())
binding = json.loads((directory / "binding.json").read_text())
worker = json.loads((directory / "worker-receipt.json").read_text())
semantic = json.loads((directory / "semantic-summary.json").read_text())
parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
demand_to_two = (parse(semantic["finished_at"]) - parse(run["demand_at"])).total_seconds()
result = {
    "schema": "archvteams.nebius.ai/boltz2-native-trial-summary/v1",
    "run_id": run["run_id"],
    "status": "PASS",
    "checkpoint_id": run["checkpoint_id"],
    "artifact_manifest_sha256": run["artifact_manifest_sha256"],
    "pod_uid": binding["pod_uid"],
    "pod_spec_sha256": binding["pod_spec_sha256"],
    "worker_receipt": worker,
    "semantic": semantic,
    "demand_to_two_semantic_seconds": round(demand_to_two, 6),
}
print(json.dumps(result, sort_keys=True, indent=2))
PY

jq '{run_id,status,demand_to_two_semantic_seconds,restore_seconds:(.worker_receipt.duration_ms / 1000),semantic_seconds:.semantic.total_elapsed_seconds}' \
  "$run_dir/trial-summary.json"

if [[ $cleanup == "--cleanup" ]]; then
  kubectl --kubeconfig "$kubeconfig" delete -f "$run_dir/semantic-probe.yaml" --ignore-not-found --wait=true --timeout=120s
  kubectl --kubeconfig "$kubeconfig" delete -f "$run_dir/restore-worker.yaml" --ignore-not-found --wait=true --timeout=120s
  kubectl --kubeconfig "$kubeconfig" delete -f "$run_dir/target.yaml" --ignore-not-found --wait=true --timeout=180s
fi
