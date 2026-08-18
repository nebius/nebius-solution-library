#!/usr/bin/env bash
set -Eeuo pipefail

readonly allowed_server='https://pu.mk8scluster-e00en4dkk80w2d09c0.mk8s.eu-north1.nebius.cloud:443'
readonly allowed_node='computeinstance-e00hf93cfnsgaxygn3'
readonly namespace='nim-fast-start'
readonly script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

usage() {
  printf 'usage: %s --kubeconfig ABS_PATH --evidence-root ABS_DIR --batch-id DNS_LABEL\n' "$0" >&2
}

kubeconfig=''
evidence_root=''
batch_id=''
while (($#)); do
  case "$1" in
    --kubeconfig) kubeconfig=${2:-}; shift 2 ;;
    --evidence-root) evidence_root=${2:-}; shift 2 ;;
    --batch-id) batch_id=${2:-}; shift 2 ;;
    *) usage; exit 64 ;;
  esac
done
[[ $kubeconfig == /* && -f $kubeconfig ]] || { usage; exit 64; }
[[ $evidence_root == /* ]] || { usage; exit 64; }
[[ $batch_id =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#batch_id} -le 40 ]] || { usage; exit 64; }

install -d -m 0700 -- "$evidence_root"
readonly -a kubectl=(kubectl --kubeconfig "$kubeconfig" -n "$namespace")
actual_server=$(kubectl --kubeconfig "$kubeconfig" config view --minify -o jsonpath='{.clusters[0].cluster.server}')
[[ $actual_server == "$allowed_server" ]] || { printf 'cluster identity mismatch\n' >&2; exit 78; }

"${kubectl[@]}" get node "$allowed_node" -o json > "$evidence_root/node.json"
jq -e --arg node "$allowed_node" '
  .metadata.name==$node and
  any(.status.conditions[]; .type=="Ready" and .status=="True") and
  .metadata.labels["nebius.com/gpu-name"]=="H100" and
  .status.allocatable["nvidia.com/gpu"]=="1"
' "$evidence_root/node.json" >/dev/null
"${kubectl[@]}" get pvc msa-search-native-f7-cache -o json > "$evidence_root/cache-pvc.json"
jq -e '.status.phase=="Bound"' "$evidence_root/cache-pvc.json" >/dev/null

if ! "${kubectl[@]}" get pod msa-search-native-f7-cache-holder-hf93 >/dev/null 2>&1; then
  "${kubectl[@]}" create -f "$script_dir/conventional-cache-holder.yaml"
fi
"${kubectl[@]}" wait --for=condition=Ready pod/msa-search-native-f7-cache-holder-hf93 --timeout=300s
"${kubectl[@]}" get pod msa-search-native-f7-cache-holder-hf93 -o json > "$evidence_root/cache-holder.json"
"${kubectl[@]}" logs msa-search-native-f7-cache-holder-hf93 > "$evidence_root/cache-holder.log"
tail -1 "$evidence_root/cache-holder.log" | jq -e -c '
  select(.schema=="archvteams.nebius.ai/msa-search-conventional-cache-holder/v1" and
         .status=="PASS" and .storage_attached==true and
         .prewarm_outside_t0==true and .prewarm_bytes>0)
' > "$evidence_root/cache-holder-receipt.json"

inputs_name="${batch_id}-inputs"
"${kubectl[@]}" create configmap "$inputs_name" \
  --from-file=validate_msa_search.py="$script_dir/validate_msa_search.py" \
  --from-file=request-pdb70.json="$script_dir/fixtures/request-pdb70.json" \
  --from-file=verify_mmseqs_pipe.py="$script_dir/verify_mmseqs_pipe.py"

cleanup() {
  local run
  for run in 1 2 3; do
    "${kubectl[@]}" delete job "${batch_id}-r${run}" --ignore-not-found --wait=true --timeout=120s >/dev/null || true
  done
  "${kubectl[@]}" delete configmap "$inputs_name" --ignore-not-found --wait=true --timeout=60s >/dev/null || true
}
trap cleanup EXIT

for run in 1 2 3; do
  run_id="${batch_id}-r${run}"
  run_dir="$evidence_root/$run_id"
  install -d -m 0700 -- "$run_dir"

  kubectl --kubeconfig "$kubeconfig" get pods --all-namespaces \
    --field-selector "spec.nodeName=$allowed_node" -o json > "$run_dir/node-pods-preflight.json"
  jq -e '
    [ .items[]
      | select(.status.phase!="Succeeded" and .status.phase!="Failed")
      | .spec.containers[]
      | (.resources.requests["nvidia.com/gpu"] // "0" | tonumber)
    ] | add == 0
  ' "$run_dir/node-pods-preflight.json" >/dev/null || {
    printf 'GPU preflight is not zero before %s\n' "$run_id" >&2
    exit 78
  }

  sed \
    -e "s|@@JOB_NAME@@|${run_id}|g" \
    -e "s|@@RUN_ID@@|${run_id}|g" \
    -e "s|@@INPUTS_NAME@@|${inputs_name}|g" \
    "$script_dir/conventional-job.yaml.tmpl" > "$run_dir/job.yaml"
  date -u +%Y-%m-%dT%H:%M:%S.%NZ > "$run_dir/target-submit-at.txt"
  "${kubectl[@]}" create -f "$run_dir/job.yaml"
  pod=''
  for _ in $(seq 1 300); do
    pod=$("${kubectl[@]}" get pods -l "job-name=$run_id" -o json \
      | jq -er 'if (.items|length)==1 then .items[0].metadata.name else empty end' || true)
    [[ -n $pod ]] && break
    sleep 0.1
  done
  [[ -n $pod ]] || { printf 'conventional target Pod was not created\n' >&2; exit 1; }
  "${kubectl[@]}" wait --for=condition=Ready "pod/$pod" --timeout=120s
  "${kubectl[@]}" get pod "$pod" -o json > "$run_dir/pod-ready.json"
  "${kubectl[@]}" wait --for=condition=Complete "job/$run_id" --timeout=180s
  "${kubectl[@]}" get job "$run_id" -o json > "$run_dir/job.json"
  "${kubectl[@]}" get pods -l "job-name=$run_id" -o json > "$run_dir/pods.json"
  final_pod=$(jq -er 'select((.items|length)==1) | .items[0].metadata.name' "$run_dir/pods.json")
  [[ $final_pod == "$pod" ]] || { printf 'conventional target Pod identity changed\n' >&2; exit 1; }
  "${kubectl[@]}" get pod "$pod" -o json > "$run_dir/pod.json"
  "${kubectl[@]}" logs "$pod" > "$run_dir/pod.log"
  grep '^{' "$run_dir/pod.log" | jq -e -c \
    'select(.validator=="msa-search-pdb70-faststart-semantic-v1" and .status=="PASS" and .passed_case_count==2)' \
    > "$run_dir/semantic-summary.json"
  grep '^{' "$run_dir/pod.log" | jq -e -c \
    'select(.schema=="archvteams.nebius.ai/msa-search-mmseqs-pipe/v1" and .status=="PASS" and .shared_pipe_verified==true)' \
    > "$run_dir/mmseqs-pipe-receipt.json"

  python3 -B - "$run_dir/target-submit-at.txt" "$run_dir/semantic-summary.json" "$run_dir/pod-ready.json" > "$run_dir/result.json" <<'PY'
import datetime as dt
import json
import pathlib
import statistics
import sys

def stamp(value):
    return dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))

t0 = stamp(pathlib.Path(sys.argv[1]).read_text())
summary = json.loads(pathlib.Path(sys.argv[2]).read_text())
pod = json.loads(pathlib.Path(sys.argv[3]).read_text())
ready = stamp(summary["ready_at"])
finished = stamp(summary["finished_at"])
k8s_ready = None
for condition in pod.get("status", {}).get("conditions", []):
    if condition.get("type") == "Ready" and condition.get("status") == "True":
        k8s_ready = stamp(condition["lastTransitionTime"])
        break
result = {
    "schema": "archvteams.nebius.ai/msa-search-conventional-trial/v1",
    "status": "PASS",
    "run_id": summary["cases"][0]["input_id"].removesuffix("-semantic-a"),
    "storage_state": "cache PVC attached and fully prewarmed outside T0",
    "demand_at": t0.isoformat(),
    "http_ready_at": ready.isoformat(),
    "finished_at": finished.isoformat(),
    "demand_to_http_ready_seconds": round((ready - t0).total_seconds(), 6),
    "call1_seconds": summary["cases"][0]["elapsed_seconds"],
    "call2_seconds": summary["cases"][1]["elapsed_seconds"],
    "demand_to_call2_complete_seconds": round((finished - t0).total_seconds(), 6),
    "kubernetes_ready_at": k8s_ready.isoformat() if k8s_ready else None,
    "demand_to_kubernetes_ready_seconds": round((k8s_ready - t0).total_seconds(), 6) if k8s_ready else None,
    "semantic_pass_count": 2,
    "mmseqs_pipe_verified": True,
}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
PY
  jq -e '.status=="PASS" and .semantic_pass_count==2 and .mmseqs_pipe_verified==true' "$run_dir/result.json" >/dev/null
  "${kubectl[@]}" delete job "$run_id" --wait=true --timeout=120s
done

python3 -B - "$evidence_root" "$batch_id" > "$evidence_root/aggregate.json" <<'PY'
import json
import pathlib
import statistics
import sys

root = pathlib.Path(sys.argv[1])
batch = sys.argv[2]
trials = [json.loads((root / f"{batch}-r{index}" / "result.json").read_text()) for index in (1, 2, 3)]
holder = json.loads((root / "cache-holder-receipt.json").read_text())
if (
    holder.get("status") != "PASS"
    or holder.get("storage_attached") is not True
    or holder.get("prewarm_outside_t0") is not True
):
    raise SystemExit("cache holder receipt is not a storage-attached prewarm PASS")
fields = (
    "demand_to_http_ready_seconds",
    "call1_seconds",
    "call2_seconds",
    "demand_to_call2_complete_seconds",
    "demand_to_kubernetes_ready_seconds",
)
metrics = {}
for field in fields:
    values = [trial[field] for trial in trials if trial[field] is not None]
    metrics[field] = {
        "values": values,
        "median": statistics.median(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }
print(json.dumps({
    "schema": "archvteams.nebius.ai/msa-search-conventional-n3/v1",
    "status": "PASS",
    "trial_count": 3,
    "semantic_call_count": 6,
    "storage_state": "cache PVC attached and fully prewarmed before every T0",
    "storage": {
        "pvc": "msa-search-native-f7-cache",
        "attached_before_t0": True,
        "prewarm_outside_t0": True,
        "unique_regular_file_count": holder["regular_file_count"],
        "unique_prewarm_bytes": holder["prewarm_bytes"],
        "pdb70_index_bytes": holder["pdb70_index_bytes"],
        "content_stream_sha256": holder["content_stream_sha256"],
    },
    "metrics_seconds": metrics,
    "trials": trials,
}, sort_keys=True, separators=(",", ":")))
PY
jq -e '.status=="PASS" and .trial_count==3 and .semantic_call_count==6' "$evidence_root/aggregate.json" >/dev/null
cat "$evidence_root/aggregate.json"
