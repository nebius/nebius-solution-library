#!/usr/bin/env bash
# run_all_baselines.sh — run all 4 baseline suites and write SUMMARY.md
#
# Usage:
#   KUBECONFIG=<path> GPU_TYPE=h100 ./run_all_baselines.sh
#
# Runs 5 cold + 5 warm measurements for OpenFold2 and Evo2-40B.
# Writes CSV files to baselines/ and a SUMMARY.md with p50/p95.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NAMESPACE="${NAMESPACE:-nim-fast-start}"
GPU_TYPE="${GPU_TYPE:-h100}"
RUNS="${RUNS:-5}"

cd "$SCRIPT_DIR"

echo "=== Phase 1: OpenFold2 cold-start ==="
NAMESPACE="$NAMESPACE" GPU_TYPE="$GPU_TYPE" \
  ./measure_startup.sh openfold2 cold "$RUNS" \
  "$REPO_ROOT/baselines/openfold2_${GPU_TYPE}_cold.csv"

echo ""
echo "=== Phase 2: OpenFold2 warm-cache ==="
NAMESPACE="$NAMESPACE" GPU_TYPE="$GPU_TYPE" \
  ./measure_startup.sh openfold2 warm "$RUNS" \
  "$REPO_ROOT/baselines/openfold2_${GPU_TYPE}_warm.csv"

echo ""
echo "=== Phase 3: Evo2-40B cold-start ==="
NAMESPACE="$NAMESPACE" GPU_TYPE="$GPU_TYPE" \
  ./measure_startup.sh evo2-40b cold "$RUNS" \
  "$REPO_ROOT/baselines/evo2_40b_${GPU_TYPE}_cold.csv"

echo ""
echo "=== Phase 4: Evo2-40B warm-cache ==="
NAMESPACE="$NAMESPACE" GPU_TYPE="$GPU_TYPE" \
  ./measure_startup.sh evo2-40b warm "$RUNS" \
  "$REPO_ROOT/baselines/evo2_40b_${GPU_TYPE}_warm.csv"

echo ""
echo "=== Generating SUMMARY.md ==="
python3 - "$REPO_ROOT" "$GPU_TYPE" <<'EOF'
import csv, os, statistics, sys

repo_root = sys.argv[1]
gpu_type = sys.argv[2]
baselines_dir = os.path.join(repo_root, "baselines")

files = {
    ("openfold2", "cold"): f"openfold2_{gpu_type}_cold.csv",
    ("openfold2", "warm"): f"openfold2_{gpu_type}_warm.csv",
    ("evo2-40b",  "cold"): f"evo2_40b_{gpu_type}_cold.csv",
    ("evo2-40b",  "warm"): f"evo2_40b_{gpu_type}_warm.csv",
}

METRICS = ["startup_total_s", "weight_load_s", "image_pull_s", "first_response_s"]
METRIC_LABELS = {
    "startup_total_s": "T0→Ready (s)",
    "weight_load_s": "Weight load (s)",
    "image_pull_s": "Image pull (s)",
    "first_response_s": "T0→1st response (s)",
}

def pct(vals, p):
    vs = sorted(float(v) for v in vals if v and v != "0")
    if not vs:
        return "n/a"
    idx = min(int(len(vs) * p / 100), len(vs) - 1)
    return f"{vs[idx]:.1f}"

results = {}
for (nim, mode), fname in files.items():
    path = os.path.join(baselines_dir, fname)
    if not os.path.exists(path):
        continue
    with open(path) as f:
        rows = list(csv.DictReader(f))
    results[(nim, mode)] = rows

summary_path = os.path.join(baselines_dir, "SUMMARY.md")
with open(summary_path, "w") as out:
    out.write("# NIM Cold-Start Baseline Summary\n\n")
    out.write(f"GPU type: **{gpu_type.upper()}**  \n")
    out.write(f"Runs per suite: {len(next(iter(results.values()), []))}  \n\n")

    for nim in ["openfold2", "evo2-40b"]:
        out.write(f"## {nim}\n\n")
        out.write(f"| Metric | Cold p50 | Cold p95 | Warm p50 | Warm p95 |\n")
        out.write(f"|--------|----------|----------|----------|----------|\n")
        for metric in METRICS:
            label = METRIC_LABELS.get(metric, metric)
            cp50 = pct([r[metric] for r in results.get((nim, "cold"), [])], 50)
            cp95 = pct([r[metric] for r in results.get((nim, "cold"), [])], 95)
            wp50 = pct([r[metric] for r in results.get((nim, "warm"), [])], 50)
            wp95 = pct([r[metric] for r in results.get((nim, "warm"), [])], 95)
            out.write(f"| {label} | {cp50} | {cp95} | {wp50} | {wp95} |\n")
        out.write("\n")

    out.write("## Notes\n\n")
    out.write("- **Cold**: emptyDir cache (no pre-cached model weights) — pure network download\n")
    out.write("- **Warm**: PVC cache (model weights pre-downloaded on first cold run)\n")
    out.write("- **T0**: time `kubectl apply` was issued\n")
    out.write("- **T0→Ready**: T0 to pod `Ready` condition\n")
    out.write("- **Weight load**: `ContainersReady` to `Ready` (GPU model load time)\n")
    out.write("- **Image pull**: time between `Pulling` and `Pulled` events\n")
    out.write("- **T0→1st response**: T0 to first successful HTTP inference response\n")

print(f"SUMMARY written to {summary_path}")
EOF

echo ""
echo "All baselines complete. See baselines/SUMMARY.md"
