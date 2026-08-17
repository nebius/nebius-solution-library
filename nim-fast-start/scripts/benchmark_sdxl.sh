#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 || $# > 3 )); then
  echo "usage: benchmark_sdxl.sh KUBECONFIG SNAPSHOTCTL [RESTORE_RUNS]" >&2
  exit 2
fi

readonly kubeconfig="$1"
readonly snapshotctl="$2"
readonly restore_runs="${3:-10}"
readonly namespace="archvteams-2407-k301ud"
readonly checkpoint_id="${SDXL_CHECKPOINT_ID:-sdxl-k301ud-aio-sleep-v1}"
readonly benchmark_variant="${BENCHMARK_VARIANT:-criu-aio-sleep}"
readonly create_checkpoint="${SDXL_CREATE_CHECKPOINT:-1}"
readonly snapshot_agent_daemonset="${SNAPSHOT_AGENT_DAEMONSET:-k301ud-snapshot-agent}"
readonly drop_page_cache_pod="${DROP_PAGE_CACHE_POD:-}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
root_dir="$(cd "${script_dir}/.." && pwd)"
readonly root_dir
readonly result_file="${root_dir}/results/sdxl-restore-${benchmark_variant}.csv"
readonly agent_log="${root_dir}/results/sdxl-agent-${benchmark_variant}.log"
readonly restore_manifest="${SDXL_RESTORE_MANIFEST:-${root_dir}/manifests/sdxl-restore-pod.yaml}"

export KUBECONFIG="${kubeconfig}"
benchmark_started_rfc3339="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
readonly benchmark_started_rfc3339

kubectl delete pod sdxl-restore -n "${namespace}" --ignore-not-found --wait=true
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
    --manifest "${root_dir}/manifests/sdxl-checkpoint-pod.yaml" \
    --container main \
    --disable-cuda-checkpoint-job-file \
    --namespace "${namespace}" \
    --checkpoint-id "${checkpoint_id}" \
    --timeout 45m | tee "${root_dir}/results/sdxl-checkpoint-${benchmark_variant}.log"
  checkpoint_finished_ns="$(date +%s%N)"
  python3 - "${checkpoint_started_ns}" "${checkpoint_finished_ns}" <<'PY'
import sys
print(f"checkpoint_wall_seconds={(int(sys.argv[2])-int(sys.argv[1]))/1e9:.3f}")
PY

  # Release the donor GPU and RWO cache volume before restore trials.
  kubectl delete jobs -n "${namespace}" \
    -l "nvidia.com/snapshot-checkpoint-id=${checkpoint_id}" \
    --cascade=foreground --ignore-not-found --wait=true
elif [[ "${create_checkpoint}" == "0" ]]; then
  echo "reusing_checkpoint_id=${checkpoint_id}"
else
  echo "SDXL_CREATE_CHECKPOINT must be 0 or 1, got: ${create_checkpoint}" >&2
  exit 2
fi

printf 'run,submitted_unix_ns,semantic_unix_ns,semantic_seconds,response\n' >"${result_file}"
for run in $(seq 1 "${restore_runs}"); do
  kubectl delete pod sdxl-restore -n "${namespace}" --ignore-not-found --wait=true
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

  response=''
  for attempt in $(seq 1 900); do
    response="$(kubectl exec -n "${namespace}" sdxl-restore -c main -- \
      /bin/bash -lc 'set -euo pipefail
curl --fail --silent --show-error \
  --header "Content-Type: application/json" \
  --data "{\"prompt\":\"A green mountain under a purple sky\",\"steps\":2,\"seed\":2407}" \
  http://127.0.0.1:8000/generate --output /tmp/k301ud-restore.png
python3 - <<"PY"
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageStat

path = Path("/tmp/k301ud-restore.png")
image = Image.open(path).convert("RGB")
assert image.size == (512, 512), image.size
extrema = ImageStat.Stat(image).extrema
assert any(high > low for low, high in extrema), extrema
payload = path.read_bytes()
print(json.dumps({
    "png_bytes": len(payload),
    "sha256": hashlib.sha256(payload).hexdigest(),
    "size": list(image.size),
    "nonconstant": True,
}, separators=(",", ":")))
PY' 2>/dev/null || true)"
    if [[ -n "${response}" ]] && RESPONSE="${response}" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["RESPONSE"])
assert payload["png_bytes"] > 1_000
assert payload["size"] == [512, 512]
assert payload["nonconstant"] is True
assert len(payload["sha256"]) == 64
PY
    then
      semantic_ns="$(date +%s%N)"
      seconds="$(python3 - "${submitted_ns}" "${semantic_ns}" <<'PY'
import sys
print(f"{(int(sys.argv[2])-int(sys.argv[1]))/1e9:.3f}")
PY
)"
      printf '%s,%s,%s,%s,%s\n' \
        "${run}" "${submitted_ns}" "${semantic_ns}" "${seconds}" \
        "$(printf '%s' "${response}" | base64 -w0)" >>"${result_file}"
      echo "run=${run} semantic_seconds=${seconds} ${response}"
      break
    fi
    if (( attempt == 900 )); then
      echo "restore run ${run} did not produce a validated image" >&2
      kubectl get pod sdxl-restore -n "${namespace}" -o yaml >&2 || true
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
