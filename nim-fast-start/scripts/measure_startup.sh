#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: measure_startup.sh --manifest FILE --selector LABELS --output FILE [options]

Options:
  --namespace NAME   Kubernetes namespace (default: nim-fast-start)
  --runs COUNT       Number of runs (default: 5)
  --timeout SECONDS  Ready timeout per run (default: 1800)
EOF
}

namespace="nim-fast-start"
runs=5
timeout=1800
manifest=""
selector=""
output=""

while (($#)); do
  case "$1" in
    --manifest) manifest="$2"; shift 2 ;;
    --selector) selector="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    --namespace) namespace="$2"; shift 2 ;;
    --runs) runs="$2"; shift 2 ;;
    --timeout) timeout="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -f "$manifest" && -n "$selector" && -n "$output" ]] || {
  usage >&2
  exit 2
}
[[ "$runs" =~ ^[1-9][0-9]*$ && "$timeout" =~ ^[1-9][0-9]*$ ]] || {
  echo "runs and timeout must be positive integers" >&2
  exit 2
}

mkdir -p "$(dirname "$output")"
echo 'run,pod,pod_uid,node,created_at,ready_at,elapsed_s,result' > "$output"

cleanup() {
  kubectl delete --filename "$manifest" --namespace "$namespace" \
    --ignore-not-found --wait=true >/dev/null 2>&1 || true
}
trap cleanup EXIT

for run in $(seq 1 "$runs"); do
  cleanup
  started=$(date +%s)
  kubectl apply --filename "$manifest" --namespace "$namespace" >/dev/null

  pod=""
  for _ in $(seq 1 60); do
    pod=$(kubectl get pods --namespace "$namespace" --selector "$selector" \
      --sort-by=.metadata.creationTimestamp \
      --output jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true)
    [[ -n "$pod" ]] && break
    sleep 2
  done

  if [[ -z "$pod" ]]; then
    echo "$run,,,,,,0,pod-not-created" >> "$output"
    continue
  fi

  if kubectl wait pod "$pod" --namespace "$namespace" \
    --for condition=Ready --timeout "${timeout}s" >/dev/null 2>&1; then
    result=ready
  else
    result=timeout
  fi

  finished=$(date +%s)
  row=$(kubectl get pod "$pod" --namespace "$namespace" --output json | jq -r \
    --arg run "$run" --arg elapsed "$((finished - started))" --arg result "$result" \
    '[
      $run,
      .metadata.name,
      .metadata.uid,
      .spec.nodeName,
      .metadata.creationTimestamp,
      ([.status.conditions[]? | select(.type == "Ready" and .status == "True") | .lastTransitionTime][0] // ""),
      $elapsed,
      $result
    ] | @csv')
  echo "$row" >> "$output"
done

echo "wrote $output"
