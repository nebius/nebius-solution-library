#!/usr/bin/env bash
# Read-only capture of tenant-effective Nebius billing-calculator quotes and
# capacity resource-advice. Creates no cloud resources; every call is a pure
# estimate or list. Output: one JSON evidence file per call in this directory.
#
# Region/project parameterization: each SKU names the project (and therefore
# region) it is quoted in, because a platform must exist in the parent
# project's region. Overrides bind together: overriding PROJECT_EU/PROJECT_US
# requires the matching REGION_EU/REGION_US, and every emitted evidence file
# carries an explicit "parameters" block (profile/project/region/tenant) so
# downstream snapshot generation labels quotes from the evidence itself, never
# from assumptions. Committed captures of 2026-08-19T15:07-15:08Z predate the
# parameters block; their binding is the parent-id in the recorded command,
# which build_snapshots.py parses and maps through its attested
# PROJECT_REGION table (both paths are tested).
#
# Defaults (used for the committed evidence):
#   PROFILE=sandbox
#   PROJECT_EU=project-e00z6b02t8ddk96c49  REGION_EU=eu-north1
#   PROJECT_US=project-u00tds8vpr00jaxa76s22d  REGION_US=us-central1
#   TENANT=tenant-e00f3wdfzwfjgbcyfv
set -u
PROFILE="${PROFILE:-sandbox}"
PROJECT_EU="${PROJECT_EU:-project-e00z6b02t8ddk96c49}"
REGION_EU="${REGION_EU:-eu-north1}"
PROJECT_US="${PROJECT_US:-project-u00tds8vpr00jaxa76s22d}"
REGION_US="${REGION_US:-us-central1}"
TENANT="${TENANT:-tenant-e00f3wdfzwfjgbcyfv}"
OUTDIR="$(cd "$(dirname "$0")" && pwd)"

capture() {
  local name="$1" project="$2" region="$3"; shift 3
  local ts rc out
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  out="$("$@" 2>&1)"; rc=$?
  python3 - "$OUTDIR/$name.json" "$ts" "$rc" "$out" "$*" \
      "$PROFILE" "$project" "$region" "$TENANT" <<'PY'
import json, sys
path, ts, rc, out, cmd, profile, project, region, tenant = sys.argv[1:10]
try:
    parsed = json.loads(out)
except Exception:
    parsed = None
json.dump({"captured_at_utc": ts, "command": cmd, "exit_code": int(rc),
           "parameters": {"profile": profile, "project": project,
                          "region": region, "tenant": tenant},
           "response": parsed, "raw_text": None if parsed is not None else out},
          open(path, "w"), indent=2, sort_keys=True)
open(path, "a").write("\n")
PY
  echo "$name rc=$rc"
}

est="nebius --profile $PROFILE billing v1alpha1 calculator estimate --format json"

# GPU instances: "<platform> <preset> <project> <region>", quoted on-demand
# and preemptible(on-preemption=stop) in the project whose region offers them.
for p in "gpu-h100-sxm 1gpu-16vcpu-200gb $PROJECT_EU $REGION_EU" \
         "gpu-h200-sxm 1gpu-16vcpu-200gb $PROJECT_EU $REGION_EU" \
         "gpu-b200-sxm 1gpu-20vcpu-224gb $PROJECT_US $REGION_US"; do
  set -- $p
  plat=$1; preset=$2; project=$3; region=$4
  capture "quote-${plat}-${preset}-ondemand" "$project" "$region" $est \
    --resource-spec-compute-instance-spec-parent-id "$project" \
    --resource-spec-compute-instance-spec-resources-platform "$plat" \
    --resource-spec-compute-instance-spec-resources-preset "$preset"
  capture "quote-${plat}-${preset}-preemptible" "$project" "$region" $est \
    --resource-spec-compute-instance-spec-parent-id "$project" \
    --resource-spec-compute-instance-spec-resources-platform "$plat" \
    --resource-spec-compute-instance-spec-resources-preset "$preset" \
    --resource-spec-compute-instance-spec-preemptible-on-preemption stop
done

# CPU controller/holder instance (EU project/region pair)
capture "quote-cpu-d3-4vcpu-16gb-ondemand" "$PROJECT_EU" "$REGION_EU" $est \
  --resource-spec-compute-instance-spec-parent-id "$PROJECT_EU" \
  --resource-spec-compute-instance-spec-resources-platform cpu-d3 \
  --resource-spec-compute-instance-spec-resources-preset 4vcpu-16gb

# Shared filesystem (SFS) tiers used by measured artifact/cache lanes
for gib in 1024 4096; do
  capture "quote-filesystem-network-ssd-${gib}gib" "$PROJECT_EU" "$REGION_EU" \
    $est \
    --resource-spec-compute-filesystem-spec-parent-id "$PROJECT_EU" \
    --resource-spec-compute-filesystem-spec-type network_ssd \
    --resource-spec-compute-filesystem-spec-size-gibibytes "$gib"
done

# Network SSD boot/scratch disk and non-replicated disk
capture "quote-disk-network-ssd-200gib" "$PROJECT_EU" "$REGION_EU" $est \
  --resource-spec-compute-disk-spec-parent-id "$PROJECT_EU" \
  --resource-spec-compute-disk-spec-type network_ssd \
  --resource-spec-compute-disk-spec-size-gibibytes 200
capture "quote-disk-network-ssd-nonreplicated-930gib" "$PROJECT_EU" \
  "$REGION_EU" $est \
  --resource-spec-compute-disk-spec-parent-id "$PROJECT_EU" \
  --resource-spec-compute-disk-spec-type network_ssd_non_replicated \
  --resource-spec-compute-disk-spec-size-gibibytes 930

# Live capacity availability, quota-clipped, tenant-wide
capture "capacity-resource-advice" "-" "tenant-wide" \
  nebius --profile "$PROFILE" capacity resource-advice list \
  --parent-id "$TENANT" --all --format json
