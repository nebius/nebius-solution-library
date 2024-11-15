SHELL = /usr/bin/env bash -o pipefail
.SHELLFLAGS = -ec

SOPERATOR_VERSION		= $(shell cat VERSION)
SUBVERSION				= $(shell cat SUBVERSION)
VERSION					= $(SOPERATOR_VERSION)-$(SUBVERSION)

ifeq ($(shell uname), Darwin)
    SED_COMMAND = sed -i ''
else
    SED_COMMAND = sed -i
endif

.PHONY: sync-version
sync-version: ## Sync Soperator version from file
	@echo 'Soperator version is - $(SOPERATOR_VERSION)'

	@# region installations/example/terraform.tfvars
	@echo 'Syncing installations/example/terraform.tfvars'
	@$(SED_COMMAND) -E 's/slurm_operator_version *= *"[0-9]+.[0-9]+.[0-9]+[^ ]*"/slurm_operator_version = "$(SOPERATOR_VERSION)"/' installations/example/terraform.tfvars
	@terraform fmt installations/example/terraform.tfvars
	@# endregion installations/example/terraform.tfvars

.PHONY: release
release: ## Create a zipped tarball with release TF recipe
	@echo "Packing terraform tarball with version - ${IMAGE_TAG}"
	VERSION=${VERSION} ./release_terraform.sh -f
