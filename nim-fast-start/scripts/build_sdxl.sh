#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "usage: build_sdxl.sh IMAGE_REF" >&2
  exit 2
fi

readonly image_ref="$1"
readonly local_base="${SDXL_BASE_IMAGE:-archvteams-2407-k301ud/qwen-vllm-placeholder:v1.4.0-public-criu-aio.1}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
root_dir="$(cd "${script_dir}/.." && pwd)"
readonly root_dir

docker build \
  --platform linux/amd64 \
  --build-arg "BASE_IMAGE=${local_base}" \
  --tag "${image_ref}" \
  "${root_dir}/sdxl"

docker run --rm --entrypoint /usr/bin/python3 "${image_ref}" -c \
  'import diffusers, torch; assert diffusers.__version__ == "0.39.0"; print(torch.__version__, torch.version.cuda, diffusers.__version__)'
