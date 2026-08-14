#!/usr/bin/env bash
# measure_startup.sh — NIM pod cold/warm startup timing baseline
#
# Usage:
#   ./measure_startup.sh <nim_name> <mode> <runs> <output_csv>
#
# nim_name: openfold2 | evo2-40b
# mode:     cold | warm
# runs:     number of measurement runs (default 5)
# output_csv: path to write results (default baselines/<nim_name>_<gpu_type>_<mode>.csv)
#
# Environment:
#   KUBECONFIG — path to cluster kubeconfig (required)
#   NAMESPACE  — kubernetes namespace (default: nim-fast-start)
#   GPU_TYPE   — label for CSV header (default: h100)

set -euo pipefail

NIM="${1:-openfold2}"
MODE="${2:-cold}"
RUNS="${3:-5}"
NAMESPACE="${NAMESPACE:-nim-fast-start}"
GPU_TYPE="${GPU_TYPE:-h100}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_CSV="${4:-$REPO_ROOT/baselines/${NIM}_${GPU_TYPE}_${MODE}.csv}"

# Set NIM-specific configuration
case "$NIM" in
  openfold2)
    DEPLOY_MANIFEST="openfold2-deployment.yaml"
    WARM_MANIFEST="openfold2-warm-deployment.yaml"
    SERVICE="openfold2-svc"
    HEALTH_PORT=8000
    SMOKE_PATH="/v1/health/ready"
    INFERENCE_PATH="/v1/protein-structure/predict"
    INFERENCE_BODY='{"sequence":"MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIHFVHSQELLSRYPDLDAKGRERAIAKDLGAVFLVGIGGKLSDGHRHDVRAPDYDDWSTPSELGHAGLNGDILVWNPVLEDAFELSSMGIRVDADTLKHQLALTGDENRTRDYSDVLPNEFFTEFKNVPNLPGYIVGFVLSGKPYGVSSGDKGPVQKTYQGYTPVYNTDSALHRALSDELEFSGSGYNLYNLYPNHAFAWMGSEAFNRAIFEYDYGRDGLSGSALGFKDEGKWLRSVSGTSGPKNAGNYAPAVNMQPQNIVNLNAGQTLPYGTPAGQIIGIPNQCGGVPALMGMPDNRNQGADAYQIAHQGYDIAGLIMGPSSQDGPFMPLHYATQAIVKNKQPIYAMRNLNGLNPAKIVPFLNQNTPNLDQIISGHTAYYQSLLNDLLLQMLNHQLHTAHTMVADAFMQQPQMQQQGQQAFMAQQMVQQQHIMQSAQQQPQLNAQTQNQQPQMQQQMVAQQQHIMQAAQQQPQLNAQTQNQQPQMQQPIMAQQQHIMQSVQQQPQLNAQTQNQQPQMQQQMVAQQQHIMQAAQQQPQLNAQTQNQQPQMQQQMVAQQQHIMQAAQQQPQLNAQTQNQQHQ"}'
    ;;
  evo2-40b)
    DEPLOY_MANIFEST="evo2-40b-deployment.yaml"
    WARM_MANIFEST="evo2-40b-warm-deployment.yaml"
    SERVICE="evo2-40b-svc"
    HEALTH_PORT=8000
    SMOKE_PATH="/v1/health/ready"
    INFERENCE_PATH="/v1/sequences/generate"
    INFERENCE_BODY='{"sequence":"ATCGATCGATCG","num_tokens":50,"top_k":1}'
    ;;
  *)
    echo "Unknown NIM: $NIM. Choose openfold2 or evo2-40b." >&2
    exit 1
    ;;
esac

MANIFEST_DIR="$REPO_ROOT/manifests"

if [[ "$MODE" == "cold" ]]; then
  APPLY_MANIFEST="$MANIFEST_DIR/$DEPLOY_MANIFEST"
else
  APPLY_MANIFEST="$MANIFEST_DIR/$WARM_MANIFEST"
fi

mkdir -p "$(dirname "$OUTPUT_CSV")"

# Write CSV header
echo "run,mode,gpu_type,nim,t_pod_create,t_initialized,t_containers_ready,t_pod_ready,t_health_ok,t_first_response,startup_total_s,weight_load_s,first_response_s,image_pull_s" \
  > "$OUTPUT_CSV"

echo "[measure_startup] NIM=$NIM MODE=$MODE RUNS=$RUNS GPU=$GPU_TYPE"
echo "[measure_startup] Output: $OUTPUT_CSV"

for RUN in $(seq 1 "$RUNS"); do
  echo ""
  echo "=== Run $RUN/$RUNS ==="

  # Delete existing pod to force restart
  kubectl delete deployment "$NIM" -n "$NAMESPACE" --ignore-not-found --wait=true 2>/dev/null || true

  # Record T0 = time apply is issued
  T0=$(date +%s%N)
  T0_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

  kubectl apply -f "$APPLY_MANIFEST" -n "$NAMESPACE" > /dev/null

  # Wait for pod to appear
  echo -n "  Waiting for pod..."
  POD=""
  for _ in $(seq 1 60); do
    POD=$(kubectl get pods -n "$NAMESPACE" -l "app=$NIM" \
          --field-selector=status.phase!=Succeeded \
          -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    [[ -n "$POD" ]] && break
    sleep 2
  done
  [[ -z "$POD" ]] && { echo "ERROR: pod never appeared" >&2; continue; }
  echo " $POD"

  # T_POD_CREATE from pod's creationTimestamp
  T_POD_CREATE_ISO=$(kubectl get pod "$POD" -n "$NAMESPACE" \
    -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null)
  T_POD_CREATE=$(date -d "$T_POD_CREATE_ISO" +%s%N 2>/dev/null || echo "$T0")

  # Poll pod conditions
  T_INITIALIZED=0
  T_CONTAINERS_READY=0
  T_POD_READY=0
  IMAGE_PULL_START=0
  IMAGE_PULL_END=0

  echo -n "  Waiting for Ready..."
  TIMEOUT=1800  # 30 min maximum
  ELAPSED=0
  while [[ $ELAPSED -lt $TIMEOUT ]]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))

    CONDITIONS=$(kubectl get pod "$POD" -n "$NAMESPACE" \
      -o jsonpath='{.status.conditions}' 2>/dev/null || echo "[]")

    # Extract condition timestamps
    T_INIT_ISO=$(echo "$CONDITIONS" | python3 -c "
import json,sys
conds = json.load(sys.stdin) if sys.stdin else []
for c in conds:
    if c.get('type') == 'Initialized' and c.get('status') == 'True':
        print(c.get('lastTransitionTime',''))
        break
" 2>/dev/null || true)

    T_CR_ISO=$(echo "$CONDITIONS" | python3 -c "
import json,sys
conds = json.load(sys.stdin) if sys.stdin else []
for c in conds:
    if c.get('type') == 'ContainersReady' and c.get('status') == 'True':
        print(c.get('lastTransitionTime',''))
        break
" 2>/dev/null || true)

    T_RDY_ISO=$(echo "$CONDITIONS" | python3 -c "
import json,sys
conds = json.load(sys.stdin) if sys.stdin else []
for c in conds:
    if c.get('type') == 'Ready' and c.get('status') == 'True':
        print(c.get('lastTransitionTime',''))
        break
" 2>/dev/null || true)

    [[ -n "$T_INIT_ISO" ]] && T_INITIALIZED=$(date -d "$T_INIT_ISO" +%s%N 2>/dev/null || echo 0)
    [[ -n "$T_CR_ISO" ]]   && T_CONTAINERS_READY=$(date -d "$T_CR_ISO" +%s%N 2>/dev/null || echo 0)
    [[ -n "$T_RDY_ISO" ]]  && T_POD_READY=$(date -d "$T_RDY_ISO" +%s%N 2>/dev/null || echo 0)

    [[ "$T_POD_READY" -gt 0 ]] && break

    POD_PHASE=$(kubectl get pod "$POD" -n "$NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null)
    [[ "$POD_PHASE" == "Failed" ]] && { echo "  Pod failed"; break; }
  done

  if [[ "$T_POD_READY" -eq 0 ]]; then
    echo " TIMEOUT waiting for Ready after ${ELAPSED}s"
    kubectl describe pod "$POD" -n "$NAMESPACE" | tail -20 >&2
    continue
  fi
  echo " Ready"

  # T_HEALTH_OK: poll health endpoint via port-forward
  echo -n "  Checking health endpoint..."
  kubectl port-forward "svc/$SERVICE" 18000:8000 -n "$NAMESPACE" &
  PF_PID=$!
  sleep 3

  T_HEALTH_OK=0
  for _ in $(seq 1 30); do
    if curl -sf "http://localhost:18000${SMOKE_PATH}" > /dev/null 2>&1; then
      T_HEALTH_OK=$(date +%s%N)
      break
    fi
    sleep 5
  done
  echo " $([ "$T_HEALTH_OK" -gt 0 ] && echo OK || echo FAILED)"

  # T_FIRST_RESPONSE: send inference request
  echo -n "  Sending inference request..."
  T_FIRST_RESPONSE=0
  if [[ "$T_HEALTH_OK" -gt 0 ]]; then
    HTTP_STATUS=$(curl -sf -w "%{http_code}" -o /tmp/nim_response.json \
      -X POST "http://localhost:18000${INFERENCE_PATH}" \
      -H "Content-Type: application/json" \
      -d "$INFERENCE_BODY" \
      --max-time 300 2>/dev/null || echo "000")
    T_FIRST_RESPONSE=$(date +%s%N)
    echo " HTTP $HTTP_STATUS"
  fi

  kill $PF_PID 2>/dev/null || true

  # Extract image pull timing from events
  IMAGE_PULL_S=0
  EVENTS=$(kubectl get events -n "$NAMESPACE" \
    --field-selector "involvedObject.name=$POD" \
    --sort-by='.lastTimestamp' -o json 2>/dev/null || echo '{"items":[]}')

  IMAGE_PULL_S=$(echo "$EVENTS" | python3 -c "
import json, sys, re
from datetime import datetime, timezone

events = json.load(sys.stdin).get('items', [])
pull_start = None
pull_end = None
for e in events:
    reason = e.get('reason', '')
    msg = e.get('message', '')
    ts = e.get('lastTimestamp') or e.get('eventTime')
    if not ts:
        continue
    ts_dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    if reason == 'Pulling':
        pull_start = ts_dt
    elif reason == 'Pulled':
        pull_end = ts_dt
if pull_start and pull_end:
    print(f'{(pull_end - pull_start).total_seconds():.1f}')
else:
    print('0')
" 2>/dev/null || echo "0")

  # Calculate durations in seconds
  ns_to_s() { echo "scale=1; ($1 - $2) / 1000000000" | bc 2>/dev/null || echo "0"; }

  STARTUP_TOTAL_S=$(ns_to_s "$T_POD_READY" "$T0")
  WEIGHT_LOAD_S=$(ns_to_s "$T_POD_READY" "$T_CONTAINERS_READY")
  FIRST_RESP_S=$([ "$T_FIRST_RESPONSE" -gt 0 ] && ns_to_s "$T_FIRST_RESPONSE" "$T0" || echo "0")

  echo "  startup_total=${STARTUP_TOTAL_S}s weight_load=${WEIGHT_LOAD_S}s first_response=${FIRST_RESP_S}s image_pull=${IMAGE_PULL_S}s"

  # Append CSV row
  echo "$RUN,$MODE,$GPU_TYPE,$NIM,$T_POD_CREATE_ISO,$T_INIT_ISO,$T_CR_ISO,$T_RDY_ISO,${T_HEALTH_OK},${T_FIRST_RESPONSE},${STARTUP_TOTAL_S},${WEIGHT_LOAD_S},${FIRST_RESP_S},${IMAGE_PULL_S}" \
    >> "$OUTPUT_CSV"
done

echo ""
echo "=== Results written to $OUTPUT_CSV ==="
echo ""
python3 - <<'EOF'
import csv, sys, statistics, os

output_csv = sys.argv[1] if len(sys.argv) > 1 else ""
if not output_csv or not os.path.exists(output_csv):
    print("(no CSV to summarize)")
    sys.exit(0)

with open(output_csv) as f:
    rows = list(csv.DictReader(f))

def stats(vals):
    vs = [float(v) for v in vals if v and v != '0']
    if not vs:
        return "n/a", "n/a"
    return f"{statistics.median(vs):.1f}", f"{sorted(vs)[int(len(vs)*0.95)]:.1f}"

fields = ['startup_total_s', 'weight_load_s', 'first_response_s', 'image_pull_s']
print(f"{'metric':<20} {'p50':>8} {'p95':>8}")
print("-" * 40)
for f in fields:
    vals = [r[f] for r in rows if f in r]
    p50, p95 = stats(vals)
    print(f"{f:<20} {p50:>8} {p95:>8}")
EOF
