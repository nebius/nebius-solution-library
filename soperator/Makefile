SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

VERSION							= $(shell cat VERSION)
IMAGE_TAG						= $(VERSION)
DOCKER_REGISTRY_NAME			= soperator

ifeq ($(shell uname), Darwin)
    SHA_CMD = shasum -a 256
    SED_COMMAND = sed -i ''
    USER_MAIL					= $(shell git config user.email)
else
    SHA_CMD = sha256sum
    SED_COMMAND = sed -i
    USER_MAIL					= $(shell git log -1 --pretty=format:'%ae')
endif
ifeq ($(UNSTABLE), true)
    SHORT_SHA 					= $(shell echo -n "$(USER_MAIL)-$(VERSION)" | $(SHA_CMD) | cut -c1-8)
	IMAGE_TAG					= $(VERSION)-$(SHORT_SHA)
	DOCKER_REGISTRY_NAME		= soperator-unstable
endif

.PHONY: get-image-version
get-image-version:
	@echo '$(IMAGE_TAG)'

.PHONY: sync-version
sync-version: ## Sync versions from file
	@echo 'Version is - $(VERSION)'
	@echo 'Image version is - $(IMAGE_TAG)'

	@# region modules/slurm/locals.tf
	@$(SED_COMMAND) "s|\(oci://cr.eu-north1.nebius.cloud/\)[^\"]*|\1$(DOCKER_REGISTRY_NAME)|" modules/slurm/locals.tf
	@# endregion modules/slurm/locals.tf

	@# region installations/example/terraform.tfvars
	@echo 'Syncing installations/example/terraform.tfvars'
	@$(SED_COMMAND) -E 's/slurm_operator_version *= *"[0-9]+.[0-9]+.[0-9]+[^ ]*"/slurm_operator_version = "$(IMAGE_TAG)"/' installations/example/terraform.tfvars
	@terraform fmt installations/example/terraform.tfvars
	@# endregion installations/example/terraform.tfvars

.PHONY: release
release:
	@echo "Packing terraform tarball with version - ${IMAGE_TAG}"
	VERSION=${IMAGE_TAG} ./release_terraform.sh -f
