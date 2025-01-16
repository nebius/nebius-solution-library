#!/usr/bin/env bash

set -e

REGISTRY='cr.eu-north1.nebius.cloud/slurm-mlperf-training'
IMAGE_NAME='sd-3.0-mlcommons'
TAG="$(cat ./scripts/docker/VERSION)"

echo 'Build image'
docker build -f ./Dockerfile -t "${IMAGE_NAME}:${TAG}" --platform linux/amd64 -m 64G .

echo 'Tag image'
docker tag "${IMAGE_NAME}:${TAG}" "${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo 'Push image'
docker push "${REGISTRY}/${IMAGE_NAME}:${TAG}"
