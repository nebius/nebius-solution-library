# =============================================================================
# Global Configuration
# =============================================================================

variable "tenant_id" {
  description = "Nebius tenant ID"
  type        = string
}

variable "parent_id" {
  description = "Nebius project ID"
  type        = string
}

variable "region" {
  description = "Nebius region for deployment"
  type        = string
  default     = "eu-north1"

  validation {
    condition     = contains(["eu-north1", "eu-north2", "eu-west1", "me-west1", "uk-south1", "us-central1"], var.region)
    error_message = "Region must be one of: eu-north1, eu-north2, eu-west1, me-west1, uk-south1, us-central1"
  }
}

variable "environment" {
  description = "Environment name (dev, stg, tst, pro)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "stg", "tst", "pro"], var.environment)
    error_message = "Environment must be one of: dev, stg, tst, pro"
  }
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "osmo"
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for VPC subnet (/20 recommended - /16 may exhaust pool)"
  type        = string
  default     = "10.0.0.0/20"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid CIDR block"
  }
}

# =============================================================================
# SSH Access
# =============================================================================

variable "ssh_user_name" {
  description = "SSH username for node access"
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key" {
  description = "SSH public key for node access"
  type = object({
    key  = optional(string)
    path = optional(string, "~/.ssh/id_rsa.pub")
  })
  default = {}
}

# =============================================================================
# Kubernetes Cluster Configuration
# =============================================================================

variable "k8s_version" {
  description = "Kubernetes version (null for latest)"
  type        = string
  default     = null
}

variable "etcd_cluster_size" {
  description = "Size of etcd cluster (1, 3, or 5)"
  type        = number
  default     = 3

  validation {
    condition     = contains([1, 3, 5], var.etcd_cluster_size)
    error_message = "etcd cluster size must be 1, 3, or 5"
  }
}

variable "enable_public_endpoint" {
  description = "Enable public endpoint for Kubernetes API"
  type        = bool
  default     = true
}

# =============================================================================
# CPU Node Group Configuration
# =============================================================================

variable "cpu_nodes_count" {
  description = "Number of CPU nodes"
  type        = number
  default     = 3

  validation {
    condition     = var.cpu_nodes_count >= 1 && var.cpu_nodes_count <= 100
    error_message = "CPU nodes count must be between 1 and 100"
  }
}

variable "cpu_nodes_platform" {
  description = "Platform for CPU nodes"
  type        = string
  default     = "cpu-d3"
}

variable "cpu_nodes_preset" {
  description = "Resource preset for CPU nodes"
  type        = string
  default     = "16vcpu-64gb"
}

variable "cpu_disk_type" {
  description = "Disk type for CPU nodes"
  type        = string
  default     = "NETWORK_SSD"
}

variable "cpu_disk_size_gib" {
  description = "Disk size in GiB for CPU nodes"
  type        = number
  default     = 128
}

variable "cpu_nodes_assign_public_ip" {
  description = "Assign public IPs to CPU nodes"
  type        = bool
  default     = false  # Private by default for security
}

# =============================================================================
# GPU Node Group Configuration
# =============================================================================

variable "gpu_nodes_count_per_group" {
  description = "Number of GPU nodes per group"
  type        = number
  default     = 1

  validation {
    condition     = var.gpu_nodes_count_per_group >= 0 && var.gpu_nodes_count_per_group <= 32
    error_message = "GPU nodes per group must be between 0 and 32"
  }
}

variable "gpu_node_groups" {
  description = "Number of GPU node groups"
  type        = number
  default     = 1
}

variable "gpu_nodes_platform" {
  description = "Platform for GPU nodes"
  type        = string
  default     = null
}

variable "gpu_nodes_preset" {
  description = "Resource preset for GPU nodes"
  type        = string
  default     = null
}

variable "gpu_disk_type" {
  description = "Disk type for GPU nodes"
  type        = string
  default     = "NETWORK_SSD"
}

variable "gpu_disk_size_gib" {
  description = "Disk size in GiB for GPU nodes"
  type        = number
  default     = 1023
}

variable "gpu_nodes_assign_public_ip" {
  description = "Assign public IPs to GPU nodes"
  type        = bool
  default     = false
}

variable "enable_gpu_cluster" {
  description = "Enable GPU cluster with InfiniBand"
  type        = bool
  default     = true
}

variable "infiniband_fabric" {
  description = "InfiniBand fabric name (null for region default)"
  type        = string
  default     = null
}

variable "enable_gpu_taints" {
  description = "Add NoSchedule taint to GPU nodes"
  type        = bool
  default     = true
}

variable "gpu_nodes_preemptible" {
  description = "Use preemptible GPU nodes (up to 70% cost savings)"
  type        = bool
  default     = false
}

variable "gpu_nodes_driverfull_image" {
  description = "Use Nebius driverfull images (pre-installed NVIDIA drivers). When true, GPU Operator driver installation is not needed."
  type        = bool
  default     = false
}

# =============================================================================
# Filestore Configuration
# =============================================================================

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

# =============================================================================
# Object Storage Configuration
# =============================================================================

variable "storage_bucket_name" {
  description = "Name for the storage bucket (must be globally unique)"
  type        = string
  default     = ""
}

# =============================================================================
# PostgreSQL Configuration
# Region-specific defaults (auto-selected when set to null):
#   eu-north1: platform=cpu-e2, disk=network-ssd
#   All other regions: platform=cpu-d3, disk=network-ssd
# Safe preset across all regions: 2vcpu-8gb or 4vcpu-16gb
# =============================================================================

variable "enable_managed_postgresql" {
  description = "Enable Nebius Managed PostgreSQL deployment"
  type        = bool
  default     = true
}

variable "postgresql_version" {
  description = "PostgreSQL version (14, 15, or 16)"
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
  description = "PostgreSQL platform (null for region default: cpu-e2 in eu-north1, cpu-d3 elsewhere)"
  type        = string
  default     = null
}

variable "postgresql_preset" {
  description = "PostgreSQL resource preset (2vcpu-8gb is minimum)"
  type        = string
  default     = "2vcpu-8gb"
}

variable "postgresql_disk_type" {
  description = "PostgreSQL disk type (null for region default: network-ssd in eu-north1, nbs-csi-sc elsewhere)"
  type        = string
  default     = null
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

  validation {
    condition     = var.postgresql_host_count >= 1 && var.postgresql_host_count <= 3
    error_message = "PostgreSQL host count must be between 1 and 3"
  }
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

# =============================================================================
# Container Registry Configuration
# Reference: https://docs.nebius.com/terraform-provider/reference/resources/registry_v1_registry
# =============================================================================

variable "enable_container_registry" {
  description = "Enable Nebius Container Registry for storing container images"
  type        = bool
  default     = true
}

variable "container_registry_name" {
  description = "Custom name for the container registry (defaults to <project_name>-<environment>-registry)"
  type        = string
  default     = ""
}

# =============================================================================
# MysteryBox Secrets Configuration (REQUIRED for Managed PostgreSQL)
# =============================================================================
# These variables MUST be set when using Managed PostgreSQL.
# Secrets are stored in MysteryBox, keeping them OUT of Terraform state.
#
# REQUIRED Setup (before terraform apply):
#   1. cd deploy/000-prerequisites
#   2. source ./secrets-init.sh
#   3. This sets TF_VAR_postgresql_mysterybox_secret_id automatically
#
# If you see validation errors, you forgot to run secrets-init.sh!
# =============================================================================

variable "postgresql_mysterybox_secret_id" {
  description = "MysteryBox secret ID for PostgreSQL password (REQUIRED - set by secrets-init.sh)"
  type        = string
  default     = null

  validation {
    condition     = var.postgresql_mysterybox_secret_id == null || can(regex("^mbsec-", var.postgresql_mysterybox_secret_id))
    error_message = "PostgreSQL MysteryBox secret ID must start with 'mbsec-' (e.g., mbsec-e00xxx). Run: source ./secrets-init.sh"
  }
}

variable "mek_mysterybox_secret_id" {
  description = "MysteryBox secret ID for OSMO MEK (Master Encryption Key)"
  type        = string
  default     = null

  validation {
    condition     = var.mek_mysterybox_secret_id == null || can(regex("^mbsec-", var.mek_mysterybox_secret_id))
    error_message = "MEK MysteryBox secret ID must start with 'mbsec-' (e.g., mbsec-e00xxx). Run: source ./secrets-init.sh"
  }
}

# =============================================================================
# WireGuard VPN Configuration
# =============================================================================

variable "enable_wireguard" {
  description = "Enable WireGuard VPN for private access"
  type        = bool
  default     = false
}

variable "wireguard_platform" {
  description = "Platform for WireGuard instance (cpu-d3 available in all regions, cpu-e2 only in eu-north1)"
  type        = string
  default     = "cpu-d3"
}

variable "wireguard_preset" {
  description = "Resource preset for WireGuard instance"
  type        = string
  default     = "2vcpu-8gb"
}

variable "wireguard_disk_size_gib" {
  description = "Disk size for WireGuard instance"
  type        = number
  default     = 64
}

variable "wireguard_port" {
  description = "WireGuard UDP port"
  type        = number
  default     = 51820
}

variable "wireguard_network" {
  description = "WireGuard VPN network CIDR"
  type        = string
  default     = "10.8.0.0/24"
}

variable "wireguard_ui_port" {
  description = "WireGuard Web UI port"
  type        = number
  default     = 5000
}

variable "postgresql_password_direct" {
  description = "Direct PostgreSQL password (testing only)"
  type        = string
  sensitive   = true
  default     = null
}
