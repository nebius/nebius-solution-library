SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c

SOURCE_DIR ?= $(CURDIR)/.cache/dynamo-v1.4.0
IMAGE_PREFIX ?= archvteams-2407-k301ud
IMAGE_TAG ?= v1.4.0-public.1

.PHONY: prepare build-images package-chart verify-images deploy benchmark-qwen benchmark-sdxl cleanup-k8s cleanup-cloud

prepare:
	./scripts/prepare_upstream.sh "$(SOURCE_DIR)"

build-images: prepare
	OPERATOR_IMAGE="$(IMAGE_PREFIX)/kubernetes-operator:$(IMAGE_TAG)" \
	SNAPSHOT_AGENT_IMAGE="$(IMAGE_PREFIX)/snapshot-agent:$(IMAGE_TAG)" \
	QWEN_PLACEHOLDER_IMAGE="$(IMAGE_PREFIX)/qwen-vllm-placeholder:$(IMAGE_TAG)" \
	./scripts/build_images.sh "$(SOURCE_DIR)"

package-chart: prepare
	mkdir -p artifacts
	helm lint "$(SOURCE_DIR)/deploy/helm/charts/snapshot"
	helm package "$(SOURCE_DIR)/deploy/helm/charts/snapshot" --destination artifacts

verify-images:
	./scripts/verify_images.sh \
	  "$(IMAGE_PREFIX)/kubernetes-operator:$(IMAGE_TAG)" \
	  "$(IMAGE_PREFIX)/snapshot-agent:$(IMAGE_TAG)" \
	  "$(IMAGE_PREFIX)/qwen-vllm-placeholder:$(IMAGE_TAG)"

deploy:
	./scripts/deploy.sh "$(KUBECONFIG)" "$(SOURCE_DIR)"

benchmark-qwen:
	./scripts/benchmark_qwen.sh "$(KUBECONFIG)" "$(SNAPSHOTCTL)" 10

benchmark-sdxl:
	./scripts/benchmark_sdxl.sh "$(KUBECONFIG)" "$(SNAPSHOTCTL)" 10

cleanup-k8s:
	./scripts/cleanup_k8s.sh "$(KUBECONFIG)" "$(SOURCE_DIR)"

cleanup-cloud:
	./scripts/cleanup_cloud.sh "$(NEBIUS_PROFILE)"
