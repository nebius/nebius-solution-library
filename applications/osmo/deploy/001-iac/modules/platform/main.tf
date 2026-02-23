# =============================================================================
# Platform Module - VPC, Storage, PostgreSQL, Container Registry
# =============================================================================

# -----------------------------------------------------------------------------
# VPC Network
# -----------------------------------------------------------------------------
resource "nebius_vpc_v1_network" "main" {
  parent_id = var.parent_id
  name      = "${var.name_prefix}-network"
}

resource "nebius_vpc_v1_subnet" "main" {
  parent_id  = var.parent_id
  name       = "${var.name_prefix}-subnet"
  network_id = nebius_vpc_v1_network.main.id

  # Use network's default pools - more reliable across regions
  ipv4_private_pools = {
    use_network_pools = true
  }
}

# -----------------------------------------------------------------------------
# Service Account for Storage
# -----------------------------------------------------------------------------
resource "nebius_iam_v1_service_account" "storage" {
  parent_id = var.parent_id
  name      = "${var.name_prefix}-storage-sa"
}

# Get the "editors" group from tenant (grants storage.editor permissions)
# Reference: nebius-solutions-library/anyscale/deploy/bucket_key.tf
# data "nebius_iam_v1_group" "editors" {
#   name      = "editors"
#   parent_id = var.tenant_id
# }

# Add the storage service account to the editors group
# This grants the service account permissions to write to storage buckets
# resource "nebius_iam_v1_group_membership" "storage_editor" {
#   parent_id = data.nebius_iam_v1_group.editors.id
#   member_id = nebius_iam_v1_service_account.storage.id
# }

resource "nebius_iam_v2_access_key" "storage" {
  parent_id   = var.parent_id
  name        = "${var.name_prefix}-storage-key"
  description = "Access key for OSMO storage bucket"

  # Store secret in MysteryBox instead of returning directly
  # Reference: nebius-solutions-library/modules/o11y/loki.tf
  secret_delivery_mode = "MYSTERY_BOX"

  account = {
    service_account = {
      id = nebius_iam_v1_service_account.storage.id
    }
  }

  # depends_on removed for arch-sandbox testing
}

# -----------------------------------------------------------------------------
# MysteryBox - Read storage secret (ephemeral, NOT stored in state)
# Reference: nebius-solutions-library/modules/o11y/mysterybox.tf
# Requires Terraform >= 1.10.0
# -----------------------------------------------------------------------------
# ephemeral "nebius_mysterybox_v1_secret_payload_entry" "storage_secret" {
#   secret_id = nebius_iam_v2_access_key.storage.status.secret_reference_id
#   key       = "secret"
# }

# -----------------------------------------------------------------------------
# Object Storage Bucket
# -----------------------------------------------------------------------------
resource "nebius_storage_v1_bucket" "main" {
  parent_id         = var.parent_id
  name              = var.storage_bucket_name
  versioning_policy = "ENABLED"
}

# -----------------------------------------------------------------------------
# Shared Filesystem (Filestore)
# -----------------------------------------------------------------------------
resource "nebius_compute_v1_filesystem" "shared" {
  count = var.enable_filestore ? 1 : 0

  parent_id        = var.parent_id
  name             = "${var.name_prefix}-filestore"
  type             = var.filestore_disk_type
  size_bytes       = var.filestore_size_gib * 1024 * 1024 * 1024
  block_size_bytes = var.filestore_block_size_kib * 1024

  lifecycle {
    ignore_changes = [labels]
  }
}

# -----------------------------------------------------------------------------
# PostgreSQL Password (from MysteryBox - REQUIRED)
# -----------------------------------------------------------------------------
# MysteryBox secret ID MUST be provided when using Managed PostgreSQL.
# This ensures passwords are NEVER stored in Terraform state.
#
# Setup: Run 'source ./secrets-init.sh' BEFORE 'terraform apply'
#
# Nebius PostgreSQL password requirements:
#   - Min. 8 characters
#   - At least one lowercase, uppercase, digit, special char EXCEPT %
# -----------------------------------------------------------------------------

# Validate that MysteryBox secret is provided when PostgreSQL is enabled
resource "terraform_data" "validate_postgresql_secret" {
  count = var.enable_managed_postgresql ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.postgresql_mysterybox_secret_id != null
      error_message = <<-EOT
        
        ══════════════════════════════════════════════════════════════════════
        ERROR: PostgreSQL MysteryBox secret ID is required!
        ══════════════════════════════════════════════════════════════════════
        
        You must run secrets-init.sh BEFORE terraform apply:
        
          cd ../000-prerequisites
          source ./secrets-init.sh
          cd ../001-iac
          terraform apply
        
        This creates the PostgreSQL password in MysteryBox and sets:
          TF_VAR_postgresql_mysterybox_secret_id
        
        Without this, Terraform cannot securely configure PostgreSQL.
        ══════════════════════════════════════════════════════════════════════
      EOT
    }
  }
}

# Read password from MysteryBox (ephemeral - NOT stored in state)
# ephemeral "nebius_mysterybox_v1_secret_payload_entry" "postgresql_password" {
#   count     = var.enable_managed_postgresql && var.postgresql_mysterybox_secret_id != null ? 1 : 0
#   secret_id = var.postgresql_mysterybox_secret_id
#   key       = "password"
# }

# # Local to get the password from MysteryBox
# locals {
#   postgresql_password = (
#     !var.enable_managed_postgresql
#     ? null  # PostgreSQL disabled
#     : var.postgresql_mysterybox_secret_id != null
#       ? ephemeral.nebius_mysterybox_v1_secret_payload_entry.postgresql_password[0].data.string_value
#       : null  # Will fail validation above
#   )
# }

# -----------------------------------------------------------------------------
# Managed PostgreSQL (MSP) - Nebius Managed Service for PostgreSQL
# Enabled by default for production-ready database service
# -----------------------------------------------------------------------------
resource "nebius_msp_postgresql_v1alpha1_cluster" "main" {
  count      = var.enable_managed_postgresql ? 1 : 0
  parent_id  = var.parent_id
  name       = "${var.name_prefix}-postgresql"
  network_id = nebius_vpc_v1_network.main.id

  config = {
    version       = var.postgresql_version
    public_access = var.postgresql_public_access

    template = {
      disk = {
        size_gibibytes = var.postgresql_disk_size_gib
        type           = var.postgresql_disk_type
      }
      resources = {
        platform = var.postgresql_platform
        preset   = var.postgresql_preset
      }
      hosts = {
        count = var.postgresql_host_count
      }
    }
  }

  bootstrap = {
    db_name   = var.postgresql_database_name
    user_name = var.postgresql_username
    # NOTE: user_password moved to sensitive block (write-only, not stored in state)
  }

  # Write-only field - password is NOT stored in Terraform state (more secure)
  # Requires Terraform >= 1.11.0
  sensitive = {
    bootstrap = {
      user_password = local.postgresql_password
    }
  }
}

# -----------------------------------------------------------------------------
# Container Registry
# Reference: https://docs.nebius.com/terraform-provider/reference/resources/registry_v1_registry
# Registry endpoint format: cr.<region>.nebius.cloud/<registry-name>
# -----------------------------------------------------------------------------
resource "nebius_registry_v1_registry" "main" {
  count = var.enable_container_registry ? 1 : 0

  parent_id = var.parent_id
  name      = var.container_registry_name != "" ? var.container_registry_name : "${var.name_prefix}-registry"
}

# --- PATCHED: Bypass MysteryBox read ---
locals {
  postgresql_password = var.postgresql_password_direct
}
