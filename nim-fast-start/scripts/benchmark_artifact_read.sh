#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 || $# -gt 4 ]]; then
  echo "Usage: $0 CHECKPOINT_ID BACKEND [RUNS] [OUTPUT_CSV]" >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
CHECKPOINT_ID=$1
BACKEND=$2
RUNS=${3:-5}
OUTPUT=${4:-${ROOT_DIR}/feasibility/storage_read_timings.csv}
NAMESPACE=${NAMESPACE:-nim-fast-start}
SNAPSHOT_RELEASE=${SNAPSHOT_RELEASE:-archvteams-2407-snapshot}
ARTIFACT_PATH=${ARTIFACT_PATH:-/checkpoints/${CHECKPOINT_ID}/versions/1}

agent=$(kubectl -n "${NAMESPACE}" get pod \
  -l "app.kubernetes.io/instance=${SNAPSHOT_RELEASE},app.kubernetes.io/component=snapshot-agent" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}')
if [[ -z "${agent}" ]]; then
  echo "No running snapshot agent found for release ${SNAPSHOT_RELEASE}" >&2
  exit 1
fi

if [[ ! -f "${OUTPUT}" ]]; then
  mkdir -p "$(dirname "${OUTPUT}")"
  printf '%s\n' 'backend,run,checkpoint_id,bytes,read_s,mib_per_s,agent_pod,node' >"${OUTPUT}"
fi

node=$(kubectl -n "${NAMESPACE}" get pod "${agent}" -o jsonpath='{.spec.nodeName}')
for run in $(seq 1 "${RUNS}"); do
  # shellcheck disable=SC2016
  stats=$(kubectl -n "${NAMESPACE}" exec "${agent}" -c agent -- \
    sh -c '
      set -eu
      path=$1
      test -d "$path"
      bytes=$(du -sb "$path" | cut -f1)
      start=$(date +%s%N)
      tar -C "$path" -cf /dev/null .
      end=$(date +%s%N)
      awk -v bytes="$bytes" -v start="$start" -v end="$end" '\''BEGIN {
        seconds=(end-start)/1000000000
        printf "%s %.6f %.3f\n", bytes, seconds, bytes/1048576/seconds
      }'\''
    ' artifact-read "${ARTIFACT_PATH}")
  read -r bytes read_s mib_per_s <<<"${stats}"
  printf '%s\n' "${BACKEND},${run},${CHECKPOINT_ID},${bytes},${read_s},${mib_per_s},${agent},${node}" >>"${OUTPUT}"
  printf 'backend=%s run=%s read_s=%s mib_per_s=%s\n' \
    "${BACKEND}" "${run}" "${read_s}" "${mib_per_s}"
done
