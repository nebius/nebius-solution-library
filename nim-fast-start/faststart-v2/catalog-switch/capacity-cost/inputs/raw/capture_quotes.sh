#!/usr/bin/env bash
# Read-only capture of tenant-effective Nebius billing-calculator quotes and
# capacity resource-advice. Creates no cloud resources; every call is a pure
# estimate or list. Output: one JSON evidence file per call in this directory.
set -u
PROFILE=sandbox
PROJECT=project-e00z6b02t8ddk96c49
TENANT=tenant-e00f3wdfzwfjgbcyfv
OUTDIR="$(cd "$(dirname "$0")" && pwd)"

capture() {
  local name="$1"; shift
  local ts rc out
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  out="$("$@" 2>&1)"; rc=$?
  python3 - "$OUTDIR/$name.json" "$ts" "$rc" "$out" "$*" <<'PY'
import json, sys
path, ts, rc, out, cmd = sys.argv[1:6]
try:
    parsed = json.loads(out)
except Exception:
    parsed = None
json.dump({"captured_at_utc": ts, "command": cmd, "exit_code": int(rc),
           "response": parsed, "raw_text": None if parsed is not None else out},
          open(path, "w"), indent=2, sort_keys=True)
open(path, "a").write("\n")
PY
  echo "$name rc=$rc"
}

est="nebius --profile $PROFILE billing v1alpha1 calculator estimate --format json"
inst="--resource-spec-compute-instance-spec-parent-id $PROJECT"

# GPU instances: on-demand and preemptible(on-preemption=stop)
for p in "gpu-h100-sxm 1gpu-16vcpu-200gb" "gpu-h200-sxm 1gpu-16vcpu-200gb" \
         "gpu-b200-sxm 1gpu-20vcpu-224gb"; do
  set -- $p
  plat=$1; preset=$2
  capture "quote-${plat}-${preset}-ondemand" $est $inst \
    --resource-spec-compute-instance-spec-resources-platform "$plat" \
    --resource-spec-compute-instance-spec-resources-preset "$preset"
  capture "quote-${plat}-${preset}-preemptible" $est $inst \
    --resource-spec-compute-instance-spec-resources-platform "$plat" \
    --resource-spec-compute-instance-spec-resources-preset "$preset" \
    --resource-spec-compute-instance-spec-preemptible-on-preemption stop
done

# CPU controller/holder instance
capture "quote-cpu-d3-4vcpu-16gb-ondemand" $est $inst \
  --resource-spec-compute-instance-spec-resources-platform cpu-d3 \
  --resource-spec-compute-instance-spec-resources-preset 4vcpu-16gb

# Shared filesystem (SFS) tiers used by measured artifact/cache lanes
for gib in 1024 4096; do
  capture "quote-filesystem-network-ssd-${gib}gib" $est \
    --resource-spec-compute-filesystem-spec-parent-id $PROJECT \
    --resource-spec-compute-filesystem-spec-type network_ssd \
    --resource-spec-compute-filesystem-spec-size-gibibytes "$gib"
done

# Network SSD boot/scratch disk and non-replicated disk
capture "quote-disk-network-ssd-200gib" $est \
  --resource-spec-compute-disk-spec-parent-id $PROJECT \
  --resource-spec-compute-disk-spec-type network_ssd \
  --resource-spec-compute-disk-spec-size-gibibytes 200
capture "quote-disk-network-ssd-nonreplicated-930gib" $est \
  --resource-spec-compute-disk-spec-parent-id $PROJECT \
  --resource-spec-compute-disk-spec-type network_ssd_non_replicated \
  --resource-spec-compute-disk-spec-size-gibibytes 930

# Live capacity availability, quota-clipped, tenant-wide
capture "capacity-resource-advice" \
  nebius --profile $PROFILE capacity resource-advice list \
  --parent-id $TENANT --all --format json
