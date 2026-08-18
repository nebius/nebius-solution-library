#!/usr/bin/env bash
set -euo pipefail

umask 077

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly script_dir
readonly trial_runner="${script_dir}/run_provisioned_trial.sh"

run_prefix=""
evidence_root=""
node=""
kubeconfig=""
artifact_holder=""
checkpoint_id=""
target_glibc_version=""
image_io_mode=""
artifact_manifest_sha256=""
cleanup=0

usage() {
  cat >&2 <<'USAGE'
usage: run_n3.sh \
  --run-prefix DNS_LABEL \
  --evidence-root ABSOLUTE_DIRECTORY \
  --node ALLOWED_H100_HOSTNAME \
  --kubeconfig ABSOLUTE_FILE \
  --artifact-holder READY_POD \
  --checkpoint-id EXACT_CHECKPOINT_ID \
  --target-glibc-version MAJOR.MINOR \
  --image-io-mode direct|buffered \
  --artifact-manifest-sha256 CAPTURED_64_HEX_SHA256 [--cleanup]
USAGE
}

die_usage() {
  printf '%s\n' "$1" >&2
  usage
  exit 64
}

set_once() {
  local option_name=$1 current_value=$2 new_value=$3
  [[ -z $current_value ]] || die_usage "${option_name} may be supplied only once"
  [[ -n $new_value ]] || die_usage "${option_name} requires a nonempty value"
}

while (($# > 0)); do
  case "$1" in
    --run-prefix)
      (($# >= 2)) || die_usage "--run-prefix requires a value"
      set_once "$1" "$run_prefix" "$2"; run_prefix=$2; shift 2 ;;
    --evidence-root)
      (($# >= 2)) || die_usage "--evidence-root requires a value"
      set_once "$1" "$evidence_root" "$2"; evidence_root=$2; shift 2 ;;
    --node)
      (($# >= 2)) || die_usage "--node requires a value"
      set_once "$1" "$node" "$2"; node=$2; shift 2 ;;
    --kubeconfig)
      (($# >= 2)) || die_usage "--kubeconfig requires a value"
      set_once "$1" "$kubeconfig" "$2"; kubeconfig=$2; shift 2 ;;
    --artifact-holder)
      (($# >= 2)) || die_usage "--artifact-holder requires a value"
      set_once "$1" "$artifact_holder" "$2"; artifact_holder=$2; shift 2 ;;
    --checkpoint-id)
      (($# >= 2)) || die_usage "--checkpoint-id requires a value"
      set_once "$1" "$checkpoint_id" "$2"; checkpoint_id=$2; shift 2 ;;
    --target-glibc-version)
      (($# >= 2)) || die_usage "--target-glibc-version requires a value"
      set_once "$1" "$target_glibc_version" "$2"; target_glibc_version=$2; shift 2 ;;
    --image-io-mode)
      (($# >= 2)) || die_usage "--image-io-mode requires a value"
      set_once "$1" "$image_io_mode" "$2"; image_io_mode=$2; shift 2 ;;
    --artifact-manifest-sha256)
      (($# >= 2)) || die_usage "--artifact-manifest-sha256 requires a value"
      set_once "$1" "$artifact_manifest_sha256" "$2"; artifact_manifest_sha256=$2; shift 2 ;;
    --cleanup)
      ((cleanup == 0)) || die_usage "--cleanup may be supplied only once"
      cleanup=1; shift ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      die_usage "unknown argument: $1" ;;
  esac
done

for required_name in run_prefix evidence_root node kubeconfig artifact_holder \
  checkpoint_id target_glibc_version image_io_mode artifact_manifest_sha256; do
  [[ -n ${!required_name} ]] || die_usage "--${required_name//_/-} is required"
done
if [[ ! $run_prefix =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ || ${#run_prefix} -gt 25 ]]; then
  die_usage "--run-prefix must be a DNS label of at most 25 characters"
fi
[[ -x $trial_runner ]] || { printf 'trial runner is not executable\n' >&2; exit 69; }
[[ -d $evidence_root/runs && ! -L $evidence_root/runs ]] || \
  die_usage "--evidence-root/runs must be an existing non-symlink directory"

summary_path="${evidence_root}/n3-${run_prefix}-${image_io_mode}.json"
partial_path="${summary_path}.partial"
if [[ -e $summary_path || -L $summary_path || -e $partial_path || -L $partial_path ]]; then
  printf 'n=3 summary path already exists\n' >&2
  exit 73
fi

common_args=(
  --evidence-root "$evidence_root"
  --node "$node"
  --kubeconfig "$kubeconfig"
  --artifact-holder "$artifact_holder"
  --checkpoint-id "$checkpoint_id"
  --target-glibc-version "$target_glibc_version"
  --image-io-mode "$image_io_mode"
  --artifact-manifest-sha256 "$artifact_manifest_sha256"
)
if ((cleanup == 1)); then
  common_args+=(--cleanup)
fi

run_ids=()
for repetition in 1 2 3; do
  run_id="${run_prefix}-r${repetition}"
  run_ids+=("$run_id")
  "$trial_runner" --run-id "$run_id" "${common_args[@]}"
done

python3 - "$evidence_root" "$checkpoint_id" "$image_io_mode" \
  "${run_ids[@]}" <<'PY' > "$partial_path"
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
checkpoint_id = sys.argv[2]
image_io_mode = sys.argv[3]
run_ids = sys.argv[4:]
if len(run_ids) != 3 or len(set(run_ids)) != 3:
    raise SystemExit("n=3 runner did not produce exactly three unique run IDs")
runs = []
for run_id in run_ids:
    path = root / "runs" / run_id / "canary-evidence.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("status") != "PASS"
        or value.get("request_count") != 2
        or value.get("semantic_pass_count") != 2
    ):
        raise SystemExit(f"trial is not a strict two-call PASS: {run_id}")
    artifact = value.get("artifact", {})
    if artifact.get("checkpoint_id") != checkpoint_id or artifact.get("image_io_mode") != image_io_mode:
        raise SystemExit(f"trial artifact identity mismatch: {run_id}")
    runs.append(value)

demand = [float(run["timings_seconds"]["demand_to_two_semantic_responses"]) for run in runs]
restore = [float(run["timings_seconds"]["worker_restore"]) for run in runs]
result = {
    "schema": "archvteams.nebius.ai/openfold3-native-n3/v1",
    "status": "PASS",
    "checkpoint_id": checkpoint_id,
    "image_io_mode": image_io_mode,
    "trial_count": 3,
    "request_count": 6,
    "semantic_pass_count": 6,
    "run_ids": run_ids,
    "demand_to_two_semantic_seconds": demand,
    "worker_restore_seconds": restore,
    "statistics_seconds": {
        "demand_to_two_semantic_min": min(demand),
        "demand_to_two_semantic_median": statistics.median(demand),
        "demand_to_two_semantic_max": max(demand),
        "demand_to_two_semantic_mean": statistics.mean(demand),
        "worker_restore_median": statistics.median(restore),
    },
}
print(json.dumps(result, sort_keys=True, indent=2))
PY
chmod 0600 "$partial_path"
mv -- "$partial_path" "$summary_path"
jq '{status,checkpoint_id,image_io_mode,trial_count,request_count,statistics_seconds}' \
  "$summary_path"
