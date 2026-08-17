#!/usr/bin/env bash
set -euo pipefail

if (( $# != 2 )); then
  echo "usage: build_snapshotctl.sh DYNAMO_SOURCE_DIR OUTPUT_PATH" >&2
  exit 2
fi

readonly source_dir="$1"
readonly output_path="$2"
output_dir="$(dirname "${output_path}")"
readonly output_dir
output_name="$(basename "${output_path}")"
readonly output_name
readonly go_image="docker.io/library/golang:1.26.3-bookworm@sha256:386d475a660466863d9f8c766fec64d7fdad3edac2c6a05020c09534d71edb4b"

mkdir -p "${output_dir}"
docker run --rm \
  --volume "${source_dir}:/src:ro" \
  --volume "${output_dir}:/out" \
  --workdir /src/deploy/snapshot \
  "${go_image}" \
  go build -buildvcs=false -trimpath -o "/out/${output_name}" ./cmd/snapshotctl

"${output_path}" --help >/dev/null
echo "built ${output_path}"
