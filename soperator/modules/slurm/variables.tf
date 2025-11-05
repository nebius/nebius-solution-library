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

variable "operator_feature_gates" {
  description = "Feature gates for soperator. Example: 'NodeSetWorkers=true'"
  type        = string
  default     = ""
}

variable "iam_tenant_id" {
  description = "ID of the IAM tenant."
  type        = string
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

# endregion PartitionConfiguration

# region WorkerFeatures

variable "slurm_worker_features" {
  description = "List of features to be enabled on worker nodes."
  type = list(object({
    name          = string
    hostlist_expr = string
    nodeset_name  = optional(string)
  }))
  default = []
}

# endregion WorkerFeatures

# region HealthCheckConfig

variable "slurm_health_check_config" {
  description = "Health check configuration."
  type = object({
    health_check_interval = number
    health_check_program  = string
    health_check_node_state = list(object({
      state = string
    }))
  })
  nullable = true
  default  = null
}

# endregion HealthCheckConfig

# region Nodes

variable "node_count" {
  description = "Count of Slurm nodes."
  type = object({
    controller = number
    worker     = list(number)
    login      = number
  })
}

# endregion Nodes

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

  # Only enforce single worker nodeset when nodesets feature is disabled
  validation {
    condition     = var.slurm_nodesets_enabled || length(var.resources.worker) == 1
    error_message = "Only one worker nodeset is supported when slurm_nodesets_enabled is false."
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

# region Worker

variable "worker_sshd_config_map_ref_name" {
  description = "Name of configmap with SSHD config, which runs in slurmd container."
  type        = string
  default     = ""
}

# endregion Worker

# region Login

variable "login_allocation_id" {
  description = "ID of the VPC allocation used in case of `LoadBalancer` service type."
  type        = string
  nullable    = true
  default     = null
}

variable "login_public_ip" {
  description = "Public or private ip for login node load balancer"
  type        = bool
  default     = true
}

variable "tailscale_enabled" {
  description = "Whether to enable tailscale init container on login pod"
  type        = bool
  default     = false
}

variable "login_sshd_config_map_ref_name" {
  description = "Name of configmap with SSHD config, which runs in slurmd container."
  type        = string
  default     = ""
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
  default     = false
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

# region Disks
variable "controller_state_on_filestore" {
  description = "Whether to use filestore for controller node storage (when true) or PVC (when false)."
  type        = bool
  default     = false
}

variable "node_local_jail_submounts" {
  description = "Node-local disks to be mounted inside jail."
  type = list(object({
    name               = string
    mount_path         = string
    size_gibibytes     = number
    disk_type          = string
    filesystem_type    = string
    storage_class_name = string
  }))
  nullable = false
  default  = []
}

variable "node_local_image_storage" {
  description = "Node-local disk to store Docker/Enroot data."
  type = object({
    enabled = bool
    spec = optional(object({
      size_gibibytes     = number
      filesystem_type    = string
      storage_class_name = string
    }))
  })
  nullable = false
  default = {
    enabled = false
  }
}

# endregion Disks

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

variable "nfs_in_k8s" {
  type = object({
    enabled        = bool
    size_gibibytes = optional(number)
    storage_class  = optional(string, "compute-csi-network-ssd-io-m3-ext4")
  })
  default = {
    enabled = false
  }

  validation {
    condition     = var.nfs_in_k8s.enabled ? var.nfs_in_k8s.size_gibibytes != null : true
    error_message = "NFS size_gibibytes must be set."
  }

  validation {
    condition     = var.nfs_in_k8s.enabled ? var.nfs.enabled == false : true
    error_message = "Only one of nfs or nfs_in_k8s should be set."
  }

  validation {
    condition = (
      (
        var.nfs_in_k8s.enabled &&
        var.nfs_in_k8s.storage_class == "compute-csi-network-ssd-io-m3-ext4" &&
        var.nfs_in_k8s.size_gibibytes != null
      )
      ?
      (
        var.nfs_in_k8s.size_gibibytes % 93 == 0 &&
        var.nfs_in_k8s.size_gibibytes <= 262074
      )
      : true
    )
    error_message = "NFS size must be a multiple of 93 GiB and maximum value is 262074 GiB"
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

# region Telemetry

variable "telemetry_enabled" {
  description = "Whether to enable telemetry."
  type        = bool
  default     = true
}

variable "dcgm_job_mapping_enabled" {
  description = "Whether to enable HPC job mapping by installing a separate dcgm-exporter"
  type        = bool
  default     = true
}

variable "dcgm_job_map_dir" {
  description = "Directory where HPC job mapping files are located"
  type        = string
  default     = "/var/run/nebius/slurm"
}

# endregion Telemetry

# region Accounting

variable "accounting_enabled" {
  description = "Whether to enable accounting."
  type        = bool
  default     = true
}

variable "use_protected_secret" {
  description = "If true, protected user secret MariaDB will not be deleted after the MariaDB CR is deleted."
  type        = bool
  default     = true
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

# region Apparmor
variable "use_default_apparmor_profile" {
  description = "Whether to use default AppArmor profile."
  type        = bool
  default     = true
}

# endregion Apparmor

# region Maintenance
variable "maintenance" {
  description = "Whether to enable maintenance mode."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["downscaleAndDeletePopulateJail", "downscaleAndOverwritePopulateJail", "downscale", "none", "skipPopulateJail"], var.maintenance)
    error_message = "The maintenance variable must be one of: downscaleAndDeletePopulateJail, downscaleAndOverwritePopulateJail, downscale, none, skipPopulateJail."
  }
}

# endregion Maintenance

# region NodeConfigurator

variable "enable_node_configurator" {
  description = "Defined whether it's need to deploy node configurator"
  type        = bool
  default     = true
}

variable "node_configurator_log_level" {
  description = "Log level of node configurator"
  type        = string
  default     = "info"
}

# endregion NodeConfigurator

# region SoperatorChecks

variable "enable_soperator_checks" {
  description = "Defined whether it's need to deploy soperator checks"
  type        = bool
  default     = true
}

# endregion SoperatorChecks

# region Monitoring
variable "cluster_name" {
  description = "the cluster name to use for the monitoring"
  type        = string
}

variable "public_o11y_enabled" {
  description = "Whether to enable public observability endpoints."
  type        = bool
  default     = true
}

variable "soperator_notifier" {
  description = "Configuration of the Soperator Notifier (https://github.com/nebius/soperator/tree/main/helm/soperator-notifier)."
  type = object({
    enabled           = bool
    slack_webhook_url = optional(string)
  })
  default = {
    enabled = false
  }
  nullable = false
}

variable "create_pvcs" {
  description = "Whether to create PVCs. Uses emptyDir if false."
  type        = bool
  default     = true
}

variable "resources_vm_operator" {
  description = "Resources for VictoriaMetrics Operator."
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "512Mi"
    cpu    = "250m"
  }
}

variable "resources_vm_logs_server" {
  type = object({
    memory = string
    cpu    = string
    size   = string
  })
  default = {
    memory = "2Gi"
    cpu    = "1000m"
    size   = "40Gi"
  }
}

variable "resources_vm_single" {
  type = object({
    memory     = string
    cpu        = string
    size       = string
    gomaxprocs = number
  })
  default = {
    memory     = "24Gi"
    cpu        = "6000m"
    size       = "512Gi"
    gomaxprocs = 6
  }
}

variable "resources_vm_agent" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "10Gi"
    cpu    = "5000m"
  }
}

variable "resources_events_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "128Mi"
    cpu    = "100m"
  }
}


variable "resources_logs_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "200Mi"
    cpu    = "200m"
  }
}

variable "resources_jail_logs_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "1Gi"
    cpu    = "1000m"
  }
}

# endregion Monitoring

# region SConfigController

variable "sconfigcontroller" {
  description = "Configuration for the sConfigController"
  type = object({
    node = object({
      k8s_node_filter_name = string
      size                 = number
    })
    container = object({
      image_pull_policy = string
      resources = object({
        cpu               = number
        memory            = number
        ephemeral_storage = number
      })
    })
  })
  default = {
    node = {
      k8s_node_filter_name = "system"
      size                 = 2
    }
    container = {
      image_pull_policy = "IfNotPresent"
      resources = {
        cpu               = 250
        memory            = 256
        ephemeral_storage = 500
      }
    }
  }
}

# endregion SConfigController

# region fluxcd
variable "github_org" {
  description = "The GitHub organization."
  type        = string
  default     = "nebius"
}

variable "github_repository" {
  description = "The GitHub repository."
  type        = string
  default     = "soperator"
}

variable "github_ref_type" {
  description = "The GitHub ref type (branch, tag, etc.)."
  type        = string
  default     = "branch"
}
variable "github_ref_value" {
  description = "The GitHub ref value (main, v1.22.0, etc.)."
  type        = string
  default     = "main"
}

variable "flux_interval" {
  description = "The interval for Flux to check for changes."
  type        = string
  default     = "1m"
}

variable "flux_kustomization_path" {
  description = "The name of the Flux customization."
  type        = string
  default     = "fluxcd/environment/nebius-cloud"
}

variable "cert_manager_version" {
  description = "The version of the cert-manager."
  type        = string
  default     = ""
}

variable "k8up_version" {
  description = "The version of the k8up."
  type        = string
  default     = ""
}

variable "mariadb_operator_version" {
  description = "The version of the mariadb operator."
  type        = string
  default     = ""
}

variable "opentelemetry_collector_version" {
  description = "The version of the opentelemetry operator."
  type        = string
  default     = ""
}

variable "prometheus_crds_version" {
  description = "The version of the prometheus crds."
  type        = string
  default     = ""
}
variable "security_profiles_operator_version" {
  description = "The version of the security profiles operator."
  type        = string
  default     = ""
}

variable "vmstack_version" {
  description = "The version of the vmstack."
  type        = string
  default     = ""
}

variable "vmstack_crds_version" {
  description = "The version of the vmstack."
  type        = string
  default     = ""
}

variable "vmlogs_version" {
  description = "The version of the vmlogs."
  type        = string
  default     = ""
}

variable "flux_namespace" {
  description = "Kubernetes namespace to look for jail in."
  type        = string
}
# endregion fluxcd

variable "backups_enabled" {
  description = "Whether to enable backups."
  type        = bool
  default     = false
}


variable "region" {
  description = "Region where the Slurm cluster is deployed."
  type        = string
  default     = "eu-north1"
}

variable "use_preinstalled_gpu_drivers" {
  description = "Whether to use preinstalled GPU drivers."
  type        = bool
  default     = false
}

# region ActiveChecks
variable "active_checks_scope" {
  type        = string
  description = "Scope of active checks. Defines what active checks should be checked during cluster bootstrap."
  default     = "prod"
  validation {
    condition     = contains(["dev", "testing", "prod"], var.active_checks_scope)
    error_message = "active_checks_scope should be one of: dev, testing, prod."
  }
}
# endregion ActiveChecks

# region Nodesets

variable "slurm_nodesets_enabled" {
  description = "Enable nodesets feature for Slurm cluster. When enabled, creates separate nodesets for each worker configuration."
  type        = bool
  default     = false
}

variable "node_group_workers_v2" {
  description = "Worker node groups specification for nodesets (v2)."
  type = list(object({
    name        = string
    size        = number
    min_size    = number
    max_size    = number
    autoscaling = bool
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
    preemptible   = optional(object({}))
    nodeset_index = number
    subset_index  = number
  }))
  default = []
}

variable "slurm_nodesets_partitions" {
  description = "Partition configuration for nodesets. Used only when slurm_nodesets_enabled is true."
  type = list(object({
    name         = string
    is_all       = optional(bool, false)
    nodeset_refs = optional(list(string), [])
    config       = string
  }))
  default = []
}

# endregion Nodesets
