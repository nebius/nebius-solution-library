# region Cloud

variable "iam_token" {
  description = "IAM token used for communicating with Nebius services."
  type        = string
  nullable    = false
  sensitive   = true
}

variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
  nullable    = false

  validation {
    condition     = startswith(var.iam_project_id, "project-")
    error_message = "ID of the IAM project must start with `project-`."
  }
}
data "nebius_iam_v1_project" "this" {
  id = var.iam_project_id
}

variable "vpc_subnet_id" {
  description = "ID of VPC subnet."
  type        = string

  validation {
    condition     = startswith(var.vpc_subnet_id, "vpcsubnet-")
    error_message = "The ID of the VPC subnet must start with `vpcsubnet-`."
  }
}
data "nebius_vpc_v1_subnet" "this" {
  id = var.vpc_subnet_id
}

# endregion Cloud

# region Infrastructure

# region Storage

variable "filestore_controller_spool" {
  description = "Shared filesystem to be used on controller nodes."
  type = object({
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  })
  nullable = false

  validation {
    condition     = (var.filestore_controller_spool.existing != null && var.filestore_controller_spool.spec == null) || (var.filestore_controller_spool.existing == null && var.filestore_controller_spool.spec != null)
    error_message = "One of `existing` or `spec` must be provided."
  }
}

variable "filestore_jail" {
  description = "Shared filesystem to be used on controller, worker, and login nodes."
  type = object({
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  })
  nullable = false

  validation {
    condition     = (var.filestore_jail.existing != null && var.filestore_jail.spec == null) || (var.filestore_jail.existing == null && var.filestore_jail.spec != null)
    error_message = "One of `existing` or `spec` must be provided."
  }
}

variable "filestore_jail_submounts" {
  description = "Shared filesystems to be mounted inside jail."
  type = list(object({
    name       = string
    mount_path = string
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  }))
  default = []

  validation {
    condition = length([
      for sm in var.filestore_jail_submounts : true
      if(sm.existing != null && sm.spec == null) || (sm.existing == null && sm.spec != null)
    ]) == length(var.filestore_jail_submounts)
    error_message = "All submounts must have one of `existing` or `spec` provided."
  }
}

variable "filestore_accounting" {
  description = "Shared filesystem to be used for accounting DB"
  type = object({
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  })
  default  = null
  nullable = true

  validation {
    condition = var.filestore_accounting != null ? (
      (var.filestore_accounting.existing != null && var.filestore_accounting.spec == null) ||
      (var.filestore_accounting.existing == null && var.filestore_accounting.spec != null)
    ) : true
    error_message = "One of `existing` or `spec` must be provided."
  }
}

# endregion Storage

# region nfs-server

variable "nfs" {
  type = object({
    enabled        = bool
    size_gibibytes = number
    mount_path     = optional(string, "/mnt/nfs")
    resource = object({
      platform = string
      preset   = string
    })
  })
  default = {
    enabled        = false
    size_gibibytes = 93
    resource = {
      platform = "cpu-e2"
      preset   = "16vcpu-64gb"
    }
  }

  validation {
    condition     = var.nfs.enabled ? var.nfs.size_gibibytes % 93 == 0 && var.nfs.size_gibibytes <= 262074 : true
    error_message = "NFS size must be a multiple of 93 GiB and maximum value is 262074 GiB"
  }
}

# endregion nfs-server

# region k8s

variable "k8s_version" {
  description = "Version of the k8s to be used."
  type        = string
  default     = "1.30"

  validation {
    condition     = length(regexall("^[\\d]+\\.[\\d]+$", var.k8s_version)) == 1
    error_message = "The k8s cluster version now only supports version in format `<MAJOR>.<MINOR>`."
  }
}

variable "k8s_cluster_name" {
  description = "Name of the k8s cluster."
  type        = string
  nullable    = false

  validation {
    condition = (
      length(var.k8s_cluster_name) >= 1 &&
      length(var.k8s_cluster_name) <= 64 &&
      length(regexall("^[a-z][a-z\\d\\-]*[a-z\\d]+$", var.k8s_cluster_name)) == 1
    )
    error_message = <<EOF
      The k8s cluster name must:
      - be 1 to 64 characters long
      - start with a letter
      - end with a letter or digit
      - consist of letters, digits, or hyphens (-)
      - contain only lowercase letters
    EOF
  }
}

variable "k8s_cluster_node_ssh_access_users" {
  description = "SSH user credentials for accessing k8s nodes."
  type = list(object({
    name        = string
    public_keys = list(string)
  }))
  nullable = false
  default  = []
}

# endregion k8s

# endregion Infrastructure

# region Slurm

variable "slurm_cluster_name" {
  description = "Name of the Slurm cluster in k8s cluster."
  type        = string
  nullable    = false

  validation {
    condition = (
      length(var.slurm_cluster_name) >= 1 &&
      length(var.slurm_cluster_name) <= 64 &&
      length(regexall("^[a-z][a-z\\d\\-]*[a-z\\d]+$", var.slurm_cluster_name)) == 1
    )
    error_message = <<EOF
      The Slurm cluster name must:
      - be 1 to 64 characters long
      - start with a letter
      - end with a letter or digit
      - consist of letters, digits, or hyphens (-)
      - contain only lowercase letters
    EOF
  }
}

variable "slurm_operator_version" {
  description = "Version of soperator."
  type        = string
  nullable    = false
}

# region PartitionConfiguration

variable "slurm_partition_config_type" {
  description = "Type of the Slurm partition config. Could be either `default` or `custom`."
  default     = "default"
  type        = string

  validation {
    condition     = (contains(["default", "custom"], var.slurm_partition_config_type))
    error_message = "Invalid partition config type. It must be one of `default` or `custom`."
  }
}

variable "slurm_partition_raw_config" {
  description = "Partition config in case of `custom` slurm_partition_config_type. Each string must be started with `PartitionName`."
  default     = []
  type        = list(string)
}

# endregion PartitionConfiguration

# region Nodes

variable "slurm_nodeset_system" {
  description = "Configuration of System node set for system resources created by Soperator."
  type = object({
    size = number
    resource = object({
      platform = string
      preset   = string
    })
    boot_disk = object({
      type                 = string
      size_gibibytes       = number
      block_size_kibibytes = number
    })
  })
  nullable = false
  default = {
    size = 1
    resource = {
      platform = "cpu-e2"
      preset   = "16vcpu-64gb"
    }
    boot_disk = {
      type                 = "NETWORK_SSD"
      size_gibibytes       = 128
      block_size_kibibytes = 4
    }
  }
}

variable "slurm_nodeset_controller" {
  description = "Configuration of Slurm Controller node set."
  type = object({
    size = number
    resource = object({
      platform = string
      preset   = string
    })
    boot_disk = object({
      type                 = string
      size_gibibytes       = number
      block_size_kibibytes = number
    })
  })
  nullable = false
  default = {
    size = 1
    resource = {
      platform = "cpu-e2"
      preset   = "16vcpu-64gb"
    }
    boot_disk = {
      type                 = "NETWORK_SSD"
      size_gibibytes       = 128
      block_size_kibibytes = 4
    }
  }
}

variable "slurm_nodeset_workers" {
  description = "Configuration of Slurm Worker node sets."
  type = list(object({
    size                    = number
    nodes_per_nodegroup     = number
    max_unavailable_percent = number
    resource = object({
      platform = string
      preset   = string
    })
    boot_disk = object({
      type                 = string
      size_gibibytes       = number
      block_size_kibibytes = number
    })
    gpu_cluster = optional(object({
      infiniband_fabric = string
    }))
  }))
  nullable = false
  default = [{
    size                    = 1
    nodes_per_nodegroup     = 1
    max_unavailable_percent = 50
    resource = {
      platform = "cpu-e2"
      preset   = "16vcpu-64gb"
    }
    boot_disk = {
      type                 = "NETWORK_SSD"
      size_gibibytes       = 128
      block_size_kibibytes = 4
    }
  }]

  # TODO: change to `>0` when node sets supported in soperator
  validation {
    condition     = length(var.slurm_nodeset_workers) == 1
    error_message = "Only one worker node set must be provided for a while."
  }

  validation {
    condition = length([for worker in var.slurm_nodeset_workers :
      1 if worker.size % worker.nodes_per_nodegroup != 0
    ]) == 0
    error_message = "Worker count must be divisible by nodes_per_nodegroup."
  }
}

variable "slurm_nodeset_login" {
  description = "Configuration of Slurm Login node set."
  type = object({
    size = number
    resource = object({
      platform = string
      preset   = string
    })
    boot_disk = object({
      type                 = string
      size_gibibytes       = number
      block_size_kibibytes = number
    })
  })
  nullable = false
  default = {
    size = 1
    resource = {
      platform = "cpu-e2"
      preset   = "16vcpu-64gb"
    }
    boot_disk = {
      type                 = "NETWORK_SSD"
      size_gibibytes       = 128
      block_size_kibibytes = 4
    }
  }
}

variable "slurm_nodeset_accounting" {
  description = "Configuration of Slurm Accounting node set."
  type = object({
    resource = object({
      platform = string
      preset   = string
    })
    boot_disk = object({
      type                 = string
      size_gibibytes       = number
      block_size_kibibytes = number
    })
  })
  nullable = true
  default  = null
}

resource "terraform_data" "check_slurm_nodeset_accounting" {
  lifecycle {
    precondition {
      condition = (var.accounting_enabled
        ? var.slurm_nodeset_accounting != null
        : true
      )
      error_message = "Accounting node set must be provided when accounting is enabled."
    }
  }
}

resource "terraform_data" "check_slurm_nodeset" {
  for_each = merge({
    "system"     = var.slurm_nodeset_system
    "controller" = var.slurm_nodeset_controller
    "login"      = var.slurm_nodeset_login
    }, { for i, worker in var.slurm_nodeset_workers :
    "worker_${i}" => worker
  })

  lifecycle {
    precondition {
      condition     = each.value.size > 0
      error_message = "Size must be greater than zero in node set ${each.key}."
    }

    precondition {
      condition     = contains(keys(module.resources.this), each.value.resource.platform)
      error_message = "Unsupported platform ${each.value.resource.platform} in node set ${each.key}."
    }

    precondition {
      condition     = contains(keys(module.resources.this[each.value.resource.platform]), each.value.resource.preset)
      error_message = "Unsupported preset ${each.value.resource.preset} in node set ${each.key}."
    }

    # TODO: precondition for total node group count
  }
}

# region Login

variable "slurm_login_service_type" {
  description = "Type of the k8s service to connect to login nodes."
  type        = string
  nullable    = false

  validation {
    condition     = (contains(["LoadBalancer", "NodePort"], var.slurm_login_service_type))
    error_message = "Invalid service type. It must be one of `LoadBalancer` or `NodePort`."
  }
}

variable "slurm_login_node_port" {
  description = "Port of the host to be opened in case of use of `NodePort` service type."
  type        = number
  default     = 30022

  validation {
    condition     = var.slurm_login_node_port >= 30000 && var.slurm_login_node_port < 32768
    error_message = "Invalid node port. It must be in range [30000,32768)."
  }
}

variable "slurm_login_ssh_root_public_keys" {
  description = "Authorized keys accepted for connecting to Slurm login nodes via SSH as 'root' user."
  type        = list(string)
  nullable    = false
}

# endregion Login

# region Exporter

variable "slurm_exporter_enabled" {
  description = "Whether to enable Slurm metrics exporter."
  type        = bool
  default     = true
}

# endregion Exporter

# region REST API

variable "slurm_rest_enabled" {
  description = "Whether to enable Slurm REST API."
  type        = bool
  default     = true
}

# endregion REST API

# endregion Nodes

# region Config

variable "slurm_shared_memory_size_gibibytes" {
  description = "Shared memory size for Slurm controller and worker nodes in GiB."
  type        = number
  default     = 64
}

# endregion Config

# region NCCL benchmark

variable "nccl_benchmark_enable" {
  description = "Whether to enable NCCL benchmark CronJob to benchmark GPU performance. It won't take effect in case of 1-GPU hosts."
  type        = bool
  default     = true
}

variable "nccl_benchmark_schedule" {
  description = "NCCL benchmark's CronJob schedule."
  type        = string
  default     = "0 */3 * * *"
}

variable "nccl_benchmark_min_threshold" {
  description = "Minimal threshold of NCCL benchmark for GPU performance to be considered as acceptable."
  type        = number
  default     = 45
}

variable "nccl_use_infiniband" {
  description = "Use infiniband defines using NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1 NCCL_ALGO=Ring env variables for test."
  type        = bool
  default     = true
}

# endregion NCCL benchmark

# region Telemetry

variable "telemetry_enabled" {
  description = "Whether to enable telemetry."
  type        = bool
  default     = true
}

variable "telemetry_grafana_admin_password" {
  description = "Password of `admin` user of Grafana."
  type        = string
  nullable    = false
  sensitive   = true
}

# endregion Telemetry

# region Accounting

variable "accounting_enabled" {
  description = "Whether to enable accounting."
  type        = bool
  default     = false
}

variable "slurmdbd_config" {
  description = "Slurmdbd.conf configuration. See https://slurm.schedmd.com/slurmdbd.conf.html.Not all options are supported."
  type        = map(any)
  default     = {}
}

variable "slurm_accounting_config" {
  description = "Slurm.conf accounting configuration. See https://slurm.schedmd.com/slurm.conf.html. Not all options are supported."
  type        = map(any)
  default     = {}
}

# endregion Accounting

# endregion Slurm
