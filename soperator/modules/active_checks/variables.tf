variable "k8s_cluster_context" {
  description = "Context name of the K8s cluster."
  type        = string
  nullable    = false
}

variable "slurm_cluster_name" {
  description = "Name of the Slurm cluster in k8s cluster."
  type        = string
  nullable    = false
}

variable "slurm_cluster_namespace" {
  description = "K8S cluster namespace of the Slurm cluster."
  type        = string
  nullable    = false
}

variable "num_of_login_nodes" {
  description = "Number of login nodes in the Slurm cluster."
  type        = number
  nullable    = false
}

variable "checks" {
  description = "Defines what checks should be enabled."
  type = object({
    create_soperatorchecks_user = bool

    create_nebius_user = bool
    nebius_username = string

    ssh_check_enabled = bool
    install_package_check_enabled = bool
    upgrade_cuda_enabled = bool
    cuda_version = string
  })
  default = {
    create_nebius_user = true
    nebius_username = "nebius"
    create_soperatorchecks_user = true
    soperatorchecks_username = "soperatorchecks"

    ssh_check_enabled = true
    install_package_check_enabled = true
    upgrade_cuda_enabled = true
    cuda_version = "12.4.1-1"
  }

  validation {
    condition = !var.checks.create_soperatorchecks_user || var.checks.create_nebius_user
    error_message = "Create nebius user check could not be performed without soperatorchecks user creation."
  }

  validation {
    condition = !var.checks.create_soperatorchecks_user || var.checks.ssh_check_enabled
    error_message = "SSH check could not be performed without soperatorchecks user creation."
  }

  validation {
    condition = !var.checks.create_soperatorchecks_user || var.checks.install_package_check_enabled
    error_message = "Install package check could not be performed without soperatorchecks user creation."
  }

    validation {
    condition = !var.checks.create_soperatorchecks_user || var.checks.upgrade_cuda_enabled
    error_message = "Upgrade CUDA check could not be performed without soperatorchecks user creation."
  }
}
