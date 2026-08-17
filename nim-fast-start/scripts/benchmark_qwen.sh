#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 || $# > 3 )); then
  echo "usage: benchmark_qwen.sh KUBECONFIG SNAPSHOTCTL [RESTORE_RUNS]" >&2
  exit 2
fi

readonly kubeconfig="$1"
readonly snapshotctl="$2"
readonly restore_runs="${3:-10}"
readonly namespace="archvteams-2407-k301ud"
readonly checkpoint_id="${QWEN_CHECKPOINT_ID:-qwen3-8b-k301ud-aio-v1}"
readonly benchmark_variant="${BENCHMARK_VARIANT:-criu-aio}"
readonly create_checkpoint="${QWEN_CREATE_CHECKPOINT:-1}"
readonly snapshot_agent_daemonset="${SNAPSHOT_AGENT_DAEMONSET:-k301ud-snapshot-agent}"
readonly drop_page_cache_pod="${DROP_PAGE_CACHE_POD:-}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
root_dir="$(cd "${script_dir}/.." && pwd)"
readonly root_dir
readonly result_file="${root_dir}/results/qwen3-8b-restore-${benchmark_variant}.csv"
readonly agent_log="${root_dir}/results/qwen3-8b-agent-${benchmark_variant}.log"
readonly request='{"model":"qwen3-8b","messages":[{"role":"user","content":"Reply with exactly RESTORE_OK"}],"temperature":0,"max_tokens":8,"chat_template_kwargs":{"enable_thinking":false}}'
readonly restore_manifest="${QWEN_RESTORE_MANIFEST:-${root_dir}/manifests/qwen-restore-pod.yaml}"

export KUBECONFIG="${kubeconfig}"
benchmark_started_rfc3339="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
readonly benchmark_started_rfc3339

kubectl delete pod qwen3-8b-restore -n "${namespace}" --ignore-not-found --wait=true
kubectl delete pods -n "${namespace}" \
  -l "nvidia.com/snapshot-checkpoint-id=${checkpoint_id}" \
  --ignore-not-found --wait=true
kubectl delete jobs -n "${namespace}" \
  -l "nvidia.com/snapshot-checkpoint-id=${checkpoint_id}" \
  --cascade=foreground --ignore-not-found --wait=true
if [[ "${create_checkpoint}" == "1" ]]; then
  kubectl delete podsnapshot -n "${namespace}" --all --ignore-not-found --wait=true

  checkpoint_started_ns="$(date +%s%N)"
  "${snapshotctl}" checkpoint \
    --manifest "${root_dir}/manifests/qwen-checkpoint-pod.yaml" \
    --container main \
    --disable-cuda-checkpoint-job-file \
    --namespace "${namespace}" \
    --checkpoint-id "${checkpoint_id}" \
    --timeout 45m | tee "${root_dir}/results/qwen3-8b-checkpoint-${benchmark_variant}.log"
  checkpoint_finished_ns="$(date +%s%N)"
  python3 - "${checkpoint_started_ns}" "${checkpoint_finished_ns}" <<'PY'
import sys
print(f"checkpoint_wall_seconds={(int(sys.argv[2])-int(sys.argv[1]))/1e9:.3f}")
PY

  # The completed checkpoint artifact is independent of the source Job. Delete
  # the donor so its GPU allocation can be reused by restores.
  kubectl delete jobs -n "${namespace}" \
    -l "nvidia.com/snapshot-checkpoint-id=${checkpoint_id}" \
    --cascade=foreground --ignore-not-found --wait=true
elif [[ "${create_checkpoint}" == "0" ]]; then
  echo "reusing_checkpoint_id=${checkpoint_id}"
else
  echo "QWEN_CREATE_CHECKPOINT must be 0 or 1, got: ${create_checkpoint}" >&2
  exit 2
fi

printf 'run,submitted_unix_ns,wake_accepted_unix_ns,semantic_unix_ns,semantic_seconds,response\n' >"${result_file}"
for run in $(seq 1 "${restore_runs}"); do
  kubectl delete pod qwen3-8b-restore -n "${namespace}" --ignore-not-found --wait=true
  if [[ -n "${drop_page_cache_pod}" ]]; then
    kubectl exec -n "${namespace}" "${drop_page_cache_pod}" -- \
      sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
  fi
  submitted_ns="$(date +%s%N)"
  "${snapshotctl}" restore \
    --manifest "${restore_manifest}" \
    --containers main \
    --namespace "${namespace}" \
    --checkpoint-id "${checkpoint_id}"

  wake_accepted_ns=''
  for attempt in $(seq 1 900); do
    if kubectl exec -n "${namespace}" qwen3-8b-restore -c main -- \
      curl --fail --silent --show-error --request POST \
        http://127.0.0.1:8000/wake_up >/dev/null 2>&1; then
      wake_accepted_ns="$(date +%s%N)"
      break
    fi
    if (( attempt == 900 )); then
      echo "restore run ${run} did not accept vLLM wake_up" >&2
      exit 1
    fi
    sleep 0.2
  done

  response=''
  for attempt in $(seq 1 900); do
    response="$(kubectl exec -n "${namespace}" qwen3-8b-restore -c main -- \
      curl --fail --silent --show-error \
        --header 'Content-Type: application/json' \
        --data "${request}" \
        http://127.0.0.1:8000/v1/chat/completions 2>/dev/null || true)"
    if [[ -n "${response}" ]] && RESPONSE="${response}" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["RESPONSE"])
text = payload["choices"][0]["message"]["content"]
assert "RESTORE_OK" in text, text
PY
    then
      semantic_ns="$(date +%s%N)"
      seconds="$(python3 - "${submitted_ns}" "${semantic_ns}" <<'PY'
import sys
print(f"{(int(sys.argv[2])-int(sys.argv[1]))/1e9:.3f}")
PY
)"
      compact_response="$(RESPONSE="${response}" python3 - <<'PY'
import json
import os
print(json.dumps(json.loads(os.environ["RESPONSE"]), separators=(",", ":")))
PY
)"
      printf '%s,%s,%s,%s,%s,%s\n' \
        "${run}" "${submitted_ns}" "${wake_accepted_ns}" \
        "${semantic_ns}" "${seconds}" \
        "$(printf '%s' "${compact_response}" | base64 -w0)" >>"${result_file}"
      echo "run=${run} semantic_seconds=${seconds}"
      break
    fi
    if (( attempt == 900 )); then
      echo "restore run ${run} did not produce a semantic response" >&2
      kubectl get pod qwen3-8b-restore -n "${namespace}" -o yaml >&2 || true
      exit 1
    fi
    sleep 0.2
  done
done

python3 - "${result_file}" <<'PY'
import csv
import statistics
import sys

with open(sys.argv[1], newline="") as handle:
    values = [float(row["semantic_seconds"]) for row in csv.DictReader(handle)]
print(f"restore_runs={len(values)}")
print(f"restore_semantic_p50_seconds={statistics.median(values):.3f}")
p95 = (
    statistics.quantiles(values, n=20, method="inclusive")[18]
    if len(values) > 1
    else values[0]
)
print(f"restore_semantic_p95_seconds={p95:.3f}")
print(f"restore_semantic_min_seconds={min(values):.3f}")
print(f"restore_semantic_max_seconds={max(values):.3f}")
PY

kubectl logs "daemonset/${snapshot_agent_daemonset}" -n "${namespace}" \
  --since-time="${benchmark_started_rfc3339}" \
  | tee "${agent_log}" >/dev/null
python3 "${script_dir}/summarize_agent_timings.py" "${agent_log}" "${checkpoint_id}"
