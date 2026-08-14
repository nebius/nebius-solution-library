#!/usr/bin/env bash
# snapshot-lifecycle.sh — validate, version, invalidate, and GC snapshots
#
# Usage:
#   snapshot-lifecycle.sh <command> [OPTIONS]
#
# Commands:
#   validate DIR          Check snapshot health and compatibility
#   invalidate DIR        Mark a snapshot as invalid (prevents future restores)
#   gc BASE_DIR [--keep N]  Garbage collect old snapshots (keep latest N per NIM)
#   list BASE_DIR         List all snapshots with metadata
#
# Environment:
#   SNAPSHOT_BASE         Base directory (default: /snapshots)

set -euo pipefail

SNAPSHOT_BASE="${SNAPSHOT_BASE:-/snapshots}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
die() { log "ERROR: $*"; exit 1; }

# ── validate ──────────────────────────────────────────────────────────────────
cmd_validate() {
  local dir="$1"
  local exit_code=0

  [[ -d "$dir" ]] || die "Directory not found: $dir"

  echo "=== Validating snapshot: $dir ==="

  # Required files
  for f in metadata.json .ready; do
    if [[ -f "$dir/$f" ]]; then
      echo "  ✓ $f present"
    else
      echo "  ✗ $f MISSING"
      exit_code=1
    fi
  done

  # Check snapshot is not invalidated
  if [[ -f "$dir/.invalid" ]]; then
    echo "  ✗ Snapshot is marked INVALID: $(cat "$dir/.invalid")"
    exit_code=1
  fi

  # Parse metadata
  if [[ -f "$dir/metadata.json" ]]; then
    local nim version gpu driver tool created
    nim=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('nim_name','?'))" 2>/dev/null)
    version=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('version','?'))" 2>/dev/null)
    gpu=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('gpu_product','?'))" 2>/dev/null)
    driver=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('driver_version','?'))" 2>/dev/null)
    tool=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('checkpoint_tool','?'))" 2>/dev/null)
    created=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('created_at','?'))" 2>/dev/null)

    echo "  NIM:     $nim"
    echo "  Version: $version"
    echo "  GPU:     $gpu"
    echo "  Driver:  $driver"
    echo "  Tool:    $tool"
    echo "  Created: $created"

    # Check checkpoint images exist
    if [[ "$tool" == "criu" ]]; then
      if [[ -d "$dir/criu-images" ]] && [[ -n "$(ls "$dir/criu-images/" 2>/dev/null)" ]]; then
        echo "  ✓ CRIU images present ($(du -sh "$dir/criu-images" | cut -f1))"
      else
        echo "  ✗ CRIU images MISSING"
        exit_code=1
      fi
    elif [[ "$tool" == "cuda-checkpoint" ]]; then
      if [[ -d "$dir/cuda-images" ]]; then
        echo "  ✓ cuda-checkpoint images present"
      else
        echo "  ✗ cuda-checkpoint images MISSING"
        exit_code=1
      fi
    fi

    # Check Triton cache
    if [[ -f "$dir/triton-cache.tar.gz" ]]; then
      echo "  ✓ Triton cache present ($(du -sh "$dir/triton-cache.tar.gz" | cut -f1))"
    else
      echo "  ⚠ No Triton cache (restore will recompile kernels)"
    fi
  fi

  # Check node GPU compatibility if we can reach k8s
  if command -v kubectl >/dev/null 2>&1; then
    local snap_node snap_gpu
    snap_node=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('node',''))" 2>/dev/null)
    snap_gpu=$(python3 -c "import json; d=json.load(open('$dir/metadata.json')); print(d.get('gpu_product',''))" 2>/dev/null)
    if [[ -n "$snap_node" ]] && kubectl get node "$snap_node" >/dev/null 2>&1; then
      local node_gpu
      node_gpu=$(kubectl get node "$snap_node" \
        -o jsonpath='{.metadata.labels.nebius\.com/gpu-name}' 2>/dev/null)
      if [[ "$node_gpu" == "$snap_gpu" ]]; then
        echo "  ✓ Node $snap_node GPU matches ($node_gpu)"
      else
        echo "  ✗ GPU MISMATCH: snapshot=$snap_gpu, node=$node_gpu"
        exit_code=1
      fi
    fi
  fi

  if [[ $exit_code -eq 0 ]]; then
    echo "  VALID"
  else
    echo "  INVALID"
  fi
  return $exit_code
}

# ── invalidate ────────────────────────────────────────────────────────────────
cmd_invalidate() {
  local dir="$1"
  local reason="${2:-manual invalidation}"
  [[ -d "$dir" ]] || die "Directory not found: $dir"
  echo "$reason at $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$dir/.invalid"
  rm -f "$dir/.ready"
  log "Snapshot invalidated: $dir"
}

# ── gc ────────────────────────────────────────────────────────────────────────
cmd_gc() {
  local base_dir="${1:-$SNAPSHOT_BASE}"
  local keep=3

  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep) keep="$2"; shift 2 ;;
      *) die "Unknown gc option: $1" ;;
    esac
  done

  [[ -d "$base_dir" ]] || die "Base directory not found: $base_dir"

  log "GC: scanning $base_dir (keep latest $keep per NIM)"
  local total_freed=0

  # Iterate over NIM directories
  for nim_dir in "$base_dir"/*/; do
    [[ -d "$nim_dir" ]] || continue
    local nim_name
    nim_name=$(basename "$nim_dir")
    local count
    count=$(ls -1 "$nim_dir" 2>/dev/null | wc -l)

    if [[ $count -le $keep ]]; then
      log "  $nim_name: $count snapshots (keeping all)"
      continue
    fi

    # Get all versions sorted by creation time (oldest first)
    local to_delete
    to_delete=$(ls -1t "$nim_dir" | tail -n "+$((keep + 1))")

    for ver in $to_delete; do
      local snap_path="$nim_dir/$ver"
      if [[ -f "$snap_path/.invalid" ]]; then
        log "  Deleting invalid snapshot: $nim_name/$ver"
      else
        log "  GC: removing old snapshot $nim_name/$ver"
      fi
      local sz
      sz=$(du -sh "$snap_path" 2>/dev/null | cut -f1)
      rm -rf "$snap_path"
      log "    Freed $sz"
    done
  done

  log "GC complete"
}

# ── list ──────────────────────────────────────────────────────────────────────
cmd_list() {
  local base_dir="${1:-$SNAPSHOT_BASE}"
  printf "%-20s %-20s %-12s %-20s %s\n" "NIM" "VERSION" "STATUS" "GPU" "CREATED"
  printf "%-20s %-20s %-12s %-20s %s\n" "---" "-------" "------" "---" "-------"

  for metadata in "$base_dir"/*/*/metadata.json; do
    [[ -f "$metadata" ]] || continue
    local snap_dir
    snap_dir=$(dirname "$metadata")
    local nim version gpu created status
    nim=$(python3 -c "import json; d=json.load(open('$metadata')); print(d.get('nim_name','?'))" 2>/dev/null)
    version=$(python3 -c "import json; d=json.load(open('$metadata')); print(d.get('version','?'))" 2>/dev/null)
    gpu=$(python3 -c "import json; d=json.load(open('$metadata')); print(d.get('gpu_product','?'))" 2>/dev/null)
    created=$(python3 -c "import json; d=json.load(open('$metadata')); print(d.get('created_at','?'))" 2>/dev/null)

    if [[ -f "$snap_dir/.invalid" ]]; then
      status="INVALID"
    elif [[ -f "$snap_dir/.ready" ]]; then
      status="ready"
    else
      status="incomplete"
    fi
    printf "%-20s %-20s %-12s %-20s %s\n" "$nim" "$version" "$status" "$gpu" "$created"
  done
}

# ── on-image-update: invalidate snapshots for old image ───────────────────────
cmd_on_image_update() {
  local nim_name="$1"
  local new_image_id="$2"
  local base_dir="${3:-$SNAPSHOT_BASE}"

  log "Invalidating snapshots for $nim_name with old image..."
  local count=0
  for metadata in "$base_dir/$nim_name"/*/metadata.json; do
    [[ -f "$metadata" ]] || continue
    local snap_dir img
    snap_dir=$(dirname "$metadata")
    img=$(python3 -c "import json; d=json.load(open('$metadata')); print(d.get('image_id',''))" 2>/dev/null)
    if [[ "$img" != "$new_image_id" ]]; then
      cmd_invalidate "$snap_dir" "image updated: old=$img new=$new_image_id"
      count=$((count + 1))
    fi
  done
  log "Invalidated $count old snapshot(s) for $nim_name"
}

# ── dispatch ──────────────────────────────────────────────────────────────────
CMD="${1:-list}"
shift || true

case "$CMD" in
  validate)        cmd_validate "${1:?snapshot dir required}" ;;
  invalidate)      cmd_invalidate "${1:?snapshot dir required}" "${2:-}" ;;
  gc)              cmd_gc "$@" ;;
  list)            cmd_list "$@" ;;
  on-image-update) cmd_on_image_update "${1:?}" "${2:?}" "${3:-}" ;;
  *) die "Unknown command: $CMD (use validate|invalidate|gc|list|on-image-update)" ;;
esac
