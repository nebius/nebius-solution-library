# =============================================================================
# Platform Module Variables
# =============================================================================

variable "parent_id" {
  description = "Nebius project ID"
  type        = string
}

variable "tenant_id" {
  description = "Nebius tenant ID (required for IAM group membership)"
  type        = string
}

variable "region" {
  description = "Nebius region"
  type        = string
}

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

# -----------------------------------------------------------------------------
# Network Configuration
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for VPC subnet"
  type        = string
  default     = "10.0.0.0/16"
}

# -----------------------------------------------------------------------------
# Storage Configuration
# -----------------------------------------------------------------------------

variable "storage_bucket_name" {
  description = "Name for storage bucket"
  type        = string
}

# -----------------------------------------------------------------------------
# Filestore Configuration
# -----------------------------------------------------------------------------

variable "enable_filestore" {
  description = "Enable shared filesystem"
  type        = bool
  default     = true
}

variable "filestore_disk_type" {
  description = "Filestore disk type"
  type        = string
  default     = "NETWORK_SSD"
}

variable "filestore_size_gib" {
  description = "Filestore size in GiB"
  type        = number
  default     = 1024
}

variable "filestore_block_size_kib" {
  description = "Filestore block size in KiB"
  type        = number
  default     = 4
}

# -----------------------------------------------------------------------------
# PostgreSQL Configuration
# -----------------------------------------------------------------------------

variable "enable_managed_postgresql" {
  description = "Enable Nebius Managed PostgreSQL deployment"
  type        = bool
  default     = true
}

variable "postgresql_version" {
  description = "PostgreSQL version"
  type        = number
  default     = 16

  validation {
    condition     = contains([14, 15, 16], var.postgresql_version)
    error_message = "PostgreSQL version must be 14, 15, or 16."
  }
}

variable "postgresql_public_access" {
  description = "Enable public access to PostgreSQL (for testing only, not recommended for production)"
  type        = bool
  default     = false
}

variable "postgresql_platform" {
  description = "PostgreSQL platform (cpu-e2 for managed PostgreSQL in all regions)"
  type        = string
  default     = "cpu-e2"

  validation {
    condition     = contains(["cpu-d3", "cpu-e2"], var.postgresql_platform)
    error_message = "PostgreSQL platform must be cpu-e2 (recommended) or cpu-d3."
  }
}

variable "postgresql_preset" {
  description = "PostgreSQL resource preset (2vcpu-8gb is minimum)"
  type        = string
  default     = "2vcpu-8gb"
  
  validation {
    condition     = contains(["2vcpu-8gb", "4vcpu-16gb", "8vcpu-32gb"], var.postgresql_preset)
    error_message = "PostgreSQL preset must be 2vcpu-8gb, 4vcpu-16gb, or 8vcpu-32gb."
  }
}

variable "postgresql_disk_type" {
  description = "PostgreSQL disk type (network-ssd for managed PostgreSQL in all regions)"
  type        = string
  default     = "network-ssd"

  validation {
    condition     = contains(["nbs-csi-sc", "network-ssd"], var.postgresql_disk_type)
    error_message = "PostgreSQL disk type must be network-ssd (recommended) or nbs-csi-sc."
  }
}

variable "postgresql_disk_size_gib" {
  description = "PostgreSQL disk size in GiB"
  type        = number
  default     = 50
}

variable "postgresql_host_count" {
  description = "Number of PostgreSQL hosts"
  type        = number
  default     = 1
}

variable "postgresql_database_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "osmo"
}

variable "postgresql_username" {
  description = "PostgreSQL admin username"
  type        = string
  default     = "osmo_admin"
}

# -----------------------------------------------------------------------------
# MysteryBox Secret IDs (REQUIRED for Managed PostgreSQL)
# -----------------------------------------------------------------------------
# MysteryBox secret ID is REQUIRED when using Managed PostgreSQL.
# This ensures passwords are NEVER stored in Terraform state.
#
# REQUIRED setup (before terraform apply):
#   1. cd deploy/000-prerequisites
#   2. source ./secrets-init.sh
#   3. cd ../001-iac && terraform apply
#
# The script sets TF_VAR_postgresql_mysterybox_secret_id automatically.
# If you forget, Terraform will fail with a clear error message.
# -----------------------------------------------------------------------------

variable "postgresql_mysterybox_secret_id" {
  description = "MysteryBox secret ID for PostgreSQL password (REQUIRED when enable_managed_postgresql=true)"
  type        = string
  default     = null

  validation {
    condition     = var.postgresql_mysterybox_secret_id == null || can(regex("^mbsec-", var.postgresql_mysterybox_secret_id))
    error_message = "PostgreSQL MysteryBox secret ID must start with 'mbsec-'. Run: source ./secrets-init.sh"
  }
}

variable "mek_mysterybox_secret_id" {
  description = "MysteryBox secret ID for MEK (Master Encryption Key)"
  type        = string
  default     = null

  validation {
    condition     = var.mek_mysterybox_secret_id == null || can(regex("^mbsec-", var.mek_mysterybox_secret_id))
    error_message = "MEK MysteryBox secret ID must start with 'mbsec-'. Run: source ./secrets-init.sh"
  }
}

# -----------------------------------------------------------------------------
# Container Registry Configuration
# Reference: https://docs.nebius.com/terraform-provider/reference/resources/registry_v1_registry
# -----------------------------------------------------------------------------

variable "enable_container_registry" {
  description = "Enable Nebius Container Registry for storing container images"
  type        = bool
  default     = true
}

variable "container_registry_name" {
  description = "Custom name for container registry (defaults to <name_prefix>-registry)"
  type        = string
  default     = ""
}

variable "postgresql_password_direct" {
  description = "Direct PostgreSQL password (testing only)"
  type        = string
  sensitive   = true
  default     = null
}
