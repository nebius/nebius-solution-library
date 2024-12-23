variable "name" {
  description = "Name of the Slurm cluster in k8s cluster."
  type        = string
}

variable "operator_version" {
  description = "Version of the Soperator."
  type        = string
}

variable "operator_stable" {
  description = "Whether to use stable version of the Soperator."
  type        = bool
  default     = true
}

variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "k8s_cluster_context" {
  description = "Context name of the K8s cluster."
  type        = string
  nullable    = false
}

# region PartitionConfiguration

variable "slurm_partition_config_type" {
  description = "Type of the Slurm partition config. Could be either `default` or `custom`."
  default     = "default"
  type        = string
}

variable "slurm_partition_raw_config" {
  description = "Partition config in case of `custom` slurm_partition_config_type. Each string must be started with `PartitionName`."
  type        = list(string)
  default     = []
}

# region Nodes

variable "node_count" {
  description = "Count of Slurm nodes."
  type = object({
    controller = number
    worker     = list(number)
    login      = number
  })
}

# region Resources

variable "resources" {
  description = "Resources of Slurm nodes."
  type = object({
    system = object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    })
    controller = object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    })
    worker = list(object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
      gpus                        = number
    }))
    login = object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    })
    accounting = optional(object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    }))
  })

  validation {
    condition     = length(var.resources.worker) > 0
    error_message = "At least one worker node must be provided."
  }

  # TODO: remove when node sets are supported
  validation {
    condition     = length(var.resources.worker) == 1
    error_message = "Only one worker node is supported."
  }
}

resource "terraform_data" "check_worker_nodesets" {
  lifecycle {
    precondition {
      condition     = length(var.node_count.worker) == length(var.resources.worker)
      error_message = "Worker node set resources must accord to the worker node count."
    }
  }
}

# endregion Resources

# region Login

variable "login_service_type" {
  description = "Type of the k8s service to connect to login nodes."
  type        = string
}

variable "login_node_port" {
  description = "Port of the host to be opened in case of use of `NodePort` service type."
  type        = number
}

variable "login_allocation_id" {
  description = "ID of the VPC allocation used in case of `LoadBalancer` service type."
  type        = string
  nullable    = true
  default     = null
}

variable "login_ssh_root_public_keys" {
  description = "Authorized keys accepted for connecting to Slurm login nodes via SSH as 'root' user."
  type        = list(string)
}

# endregion Login

# region Exporter

variable "exporter_enabled" {
  description = "Whether to enable Slurm metrics exporter."
  type        = bool
  default     = true
}

# endregion Exporter

# region REST API

variable "rest_enabled" {
  description = "Whether to enable Slurm REST API."
  type        = bool
  default     = true
}

# endregion REST API

# endregion Nodes

# region Filestore

variable "filestores" {
  description = "Filestores to be used in Slurm cluster."
  type = object({
    controller_spool = object({
      size_gibibytes = number
      device         = string
    })
    jail = object({
      size_gibibytes = number
      device         = string
    })
    jail_submounts = list(object({
      name           = string
      size_gibibytes = number
      device         = string
      mount_path     = string
    }))
    accounting = optional(object({
      size_gibibytes = number
      device         = string
    }))
  })
}

# endregion Filestore

# region nfs-server

variable "nfs" {
  type = object({
    enabled    = bool
    mount_path = optional(string, "/mnt/nfs")
    path       = optional(string)
    host       = optional(string)
  })
  default = {
    enabled = false
  }

  validation {
    condition     = var.nfs.enabled ? var.nfs.path != null && var.nfs.host != null : true
    error_message = "NFS path and host must be set."
  }
}

# endregion nfs-server

# region Config

variable "shared_memory_size_gibibytes" {
  description = "Shared memory size for Slurm controller and worker nodes in GiB."
  type        = number
  default     = 64
}

# endregion Config

# region NCCL

variable "nccl_topology_type" {
  description = "NCCL topology type."
  type        = string
  default     = "auto"
}

# Benchmark

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

# endregion NCCL

# region Telemetry

variable "telemetry_enabled" {
  description = "Whether to enable telemetry."
  type        = bool
  default     = true
}

variable "telemetry_grafana_admin_password" {
  description = "Password of `admin` user of Grafana."
  type        = string
}

# endregion Telemetry

# region Accounting

variable "mariadb_operator_namespace" {
  description = "Namespace for MariaDB operator."
  type        = string
  default     = "mariadb-operator-system"
}

variable "accounting_enabled" {
  description = "Whether to enable accounting."
  type        = bool
  default     = false
}

variable "use_protected_secret" {
  description = "If true, protected user secret MariaDB will not be deleted after the MariaDB CR is deleted."
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
