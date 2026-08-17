#!/usr/bin/env bash
set -euo pipefail

if (( $# != 3 )); then
  echo "usage: verify_images.sh OPERATOR_IMAGE SNAPSHOT_AGENT_IMAGE PLACEHOLDER_IMAGE" >&2
  exit 2
fi

readonly operator_image="$1"
readonly snapshot_agent_image="$2"
readonly placeholder_image="$3"

for image_ref in "$@"; do
  docker image inspect "${image_ref}" \
    --format 'image={{index .RepoTags 0}} id={{.Id}} arch={{.Architecture}} os={{.Os}} size={{.Size}}'
done

docker run --rm "${operator_image}" --help >/dev/null
docker run --rm --entrypoint /bin/sh "${snapshot_agent_image}" -c \
  'criu --version && test -x /usr/local/sbin/cuda-checkpoint && test -x /usr/local/bin/snapshot-agent'
docker run --rm --entrypoint /bin/sh "${placeholder_image}" -c \
  'criu --version && test -x /usr/local/sbin/cuda-checkpoint && test -x /usr/local/bin/nsrestore && python3 -c "import vllm"'

echo "offline image verification passed; cuda-checkpoint execution requires an NVIDIA GPU runtime"
