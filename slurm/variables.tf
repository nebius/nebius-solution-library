variable "parent_id" {
  type = string
}
variable "subnet_id" {
  type = string
}

variable "region" {
  description = "Project region."
  type        = string
}

variable "ib_image_id" {
  type        = string
  description = "ID of Infiniband image"
  default     = "arljjqhufbo9rrjsonm2"
}

variable "cluster_workers_count" {
  type        = number
  description = "Amount of slurm workers"
}

variable "ssh_public_key" {
  description = "SSH Public Key to access the cluster nodes"
  type = object({
    key  = optional(string),
    path = optional(string, "~/.ssh/id_rsa.pub")
  })
  default = {}
  validation {
    condition     = var.ssh_public_key.key != null || fileexists(var.ssh_public_key.path)
    error_message = "SSH Public Key must be set by `key` or file `path` ${var.ssh_public_key.path}"
  }
}

variable "master_platform" {
  description = "Platform for Slurm Master."
  type        = string
  default     = null
}

variable "master_preset" {
  description = "Preset for Slurm Master."
  type        = string
  default     = null
}

variable "worker_platform" {
  description = "Platform for Slurm Worker."
  type        = string
  default     = null
}

variable "worker_preset" {
  description = "Preset for Slurm Worker."
  type        = string
  default     = null
}

variable "mysql_jobs_backend" {
  type        = bool
  description = "Use MySQL for jobs logging in slurm: 1 or 0"
  default     = false
}

variable "slurm_version" {
  type        = string
  description = "Slurm version"
  default     = "24.05.3"
}

variable "slurm_binaries" {
  type        = string
  description = "Slurm binaries URL"
  default     = "12.2.2-jammy-slurm"
}

variable "pmix_version" {
  type        = string
  description = "PMIX version"
  default     = "5.0.3"
}

variable "enroot_version" {
  type        = string
  description = "ENROOT version"
  default     = "3.4.1"
}

variable "shared_fs_type" {
  type        = string
  default     = null
  description = "Use shared managed FileStorage mounted on /mnt/slurm on every worker node"
  validation {
    condition     = var.shared_fs_type == null ? true : contains(["filesystem", "nfs"], var.shared_fs_type)
    error_message = "shared_fs_type must be one of: filesystem / nfs"
  }
}

variable "fs_size" {
  type        = number
  description = "Shared FileStorage or NFS size x93"
  default     = 93 * 1024 * 1024 * 1024
}

variable "worker_name_prefix" {
  type        = string
  description = "Slurm worker name prefix"
  default     = "slurm-worker"
}

variable "test_mode" {
  description = "Switch between real usage and testing"
  type        = bool
  default     = false
}
