#!/usr/bin/env bash
set -euo pipefail

readonly source_dir="${1:?usage: build_images.sh SOURCE_DIR}"
readonly operator_image="${OPERATOR_IMAGE:?set OPERATOR_IMAGE}"
readonly snapshot_agent_image="${SNAPSHOT_AGENT_IMAGE:?set SNAPSHOT_AGENT_IMAGE}"
readonly qwen_placeholder_image="${QWEN_PLACEHOLDER_IMAGE:?set QWEN_PLACEHOLDER_IMAGE}"
readonly criu_ref="${CRIU_REF:-91d552257809d0e5c7148190e9aa0372f13b76a0}"
readonly vllm_base="docker.io/vllm/vllm-openai@sha256:1161da8a5edbdff239ab1812784d7fe5d28775c675809a8420e8a0a05d0e56d1"

docker build \
  --platform linux/amd64 \
  --target public-operator \
  --build-context snapshot="${source_dir}/deploy/snapshot" \
  --tag "${operator_image}" \
  "${source_dir}/deploy/operator"

docker build \
  --platform linux/amd64 \
  --target public-agent \
  --build-context operator="${source_dir}/deploy/operator" \
  --build-arg "CRIU_REF=${criu_ref}" \
  --tag "${snapshot_agent_image}" \
  "${source_dir}/deploy/snapshot"

docker build \
  --platform linux/amd64 \
  --target placeholder \
  --build-context operator="${source_dir}/deploy/operator" \
  --build-arg "BASE_IMAGE=${vllm_base}" \
  --build-arg "CRIU_REF=${criu_ref}" \
  --tag "${qwen_placeholder_image}" \
  "${source_dir}/deploy/snapshot"
