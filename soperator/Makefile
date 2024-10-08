SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

SLURM_VERSION					= 24.05.2
UBUNTU_VERSION					= jammy
VERSION							= $(shell cat VERSION)
IMAGE_TAG						= $(VERSION)
GREEN							= '\033[0;32m'
RESET							= '\033[0m'
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

TARBALL							= "slurm_operator_tf_$(shell echo "${IMAGE_TAG}" | tr '-' '_' | tr '.' '_').tar.gz"

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

	@# region installations/msp-slurm-test/main.tf
	@echo 'Syncing installations/msp-slurm-test/main.tf'
	@$(SED_COMMAND) -E 's/operator_version *= *"[0-9]+.[0-9]+.[0-9]+[^ ]*"/operator_version = "$(IMAGE_TAG)"/' installations/msp-slurm-test/main.tf >/dev/null 2>&1 || true
	@terraform fmt installations/msp-slurm-test/main.tf >/dev/null 2>&1 || true
	@# endregion installations/msp-slurm-test/main.tf

	@# region installations/msp-slurm-prod/main.tf
	@echo 'Syncing installations/msp-slurm-prod/main.tf'
	@$(SED_COMMAND) -E 's/operator_version *= *"[0-9]+.[0-9]+.[0-9]+[^ ]*"/operator_version = "$(IMAGE_TAG)"/' installations/msp-slurm-prod/main.tf >/dev/null 2>&1 || true
	@terraform fmt installations/msp-slurm-prod/main.tf >/dev/null 2>&1 || true
	@# endregion installations/msp-slurm-prod/main.tf

.PHONY: release-terraform
release-terraform: sync-version
	@echo "Packing new terraform tarball"
	VERSION=${IMAGE_TAG} ./release_terraform.sh -f
	@echo "Unpacking the terraform tarball"
	cd releases/unstable && VERSION=${IMAGE_TAG} TARBALL=${TARBALL} ./unpack_current_version.sh
ifeq ($(UNSTABLE), true)
	@echo "${GREEN}Unstable version ${IMAGE_TAG} is successfully released and unpacked to releases/unstable/${RESET}"
else
	mv "releases/unstable/${TARBALL}" "releases/stable/"
	@echo "${GREEN}Stable version ${IMAGE_TAG} is successfully released${RESET}"
endif

.PHONY: release-terraform-ci
release-terraform-ci:
	@echo "Packing terraform tarball with version - ${IMAGE_TAG}"
	VERSION=${IMAGE_TAG} ./release_terraform.sh -f
	mv "releases/unstable/${TARBALL}" "releases/"
