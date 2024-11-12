#!/bin/bash

set -e

REGISTRY="cr.ai.nebius.cloud/crnbu823dealq64cp1s6"
REPOSITORY="nvidia-megatron"
TAG=$(cat ./VERSION)

echo "Build image"
docker build -f ./Dockerfile -t $REPOSITORY:$TAG --platform linux/amd64 -m 64G .

echo "Tag image"
docker tag $REPOSITORY:$TAG $REGISTRY/$REPOSITORY:$TAG

echo "Push image"
docker push $REGISTRY/$REPOSITORY:$TAG

