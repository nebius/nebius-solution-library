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

variable "k8s_cluster_id" {
  description = "ID of the mk8s cluster."
  type        = string
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

variable "topology" {
  description = "Slurm topology configuration. topology/tree leaves the chart default unset; topology/block renders BlockAsNodeRank and requires block_size."
  type = object({
    plugin     = string
    block_size = optional(number)
  })
  default = {
    plugin = "topology/tree"
  }
  nullable = false

  validation {
    condition     = contains(["topology/tree", "topology/block"], var.topology.plugin)
    error_message = "topology.plugin must be one of 'topology/tree' or 'topology/block'."
  }

  validation {
    condition     = var.topology.plugin == "topology/block" ? try(var.topology.block_size > 0, false) : true
    error_message = "topology.block_size must be a positive number when topology.plugin is 'topology/block'."
  }
}

# endregion PartitionConfiguration

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

  validation {
    condition     = var.node_count.controller == 1
    error_message = "Only a single Slurm controller node is supported."
  }
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
    rest = optional(object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    }))
    exporter = optional(object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    }))
    mariadb = optional(object({
      cpu_cores                   = number
      memory_gibibytes            = number
      ephemeral_storage_gibibytes = number
    }))
    node_configurator = optional(object({
      requests = object({
        cpu_cores        = number
        memory_gibibytes = number
      })
      limits = object({
        memory_gibibytes = number
      })
    }))
    slurm_operator = optional(object({
      requests = object({
        cpu_cores        = number
        memory_gibibytes = number
      })
      limits = object({
        memory_gibibytes = number
      })
    }))
    slurm_checks = optional(object({
      requests = object({
        cpu_cores        = number
        memory_gibibytes = number
      })
      limits = object({
        memory_gibibytes = number
      })
    }))
    kruise_daemon = optional(object({
      cpu_cores        = number
      memory_gibibytes = number
    }))
    dcgm_exporter = optional(object({
      cpu_cores        = number
      memory_gibibytes = number
    }))
    nfs = optional(object({
      cpu_cores        = number
      memory_gibibytes = number
    }))
  })

  validation {
    condition     = length(var.resources.worker) > 0
    error_message = "At least one worker node must be provided."
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

variable "login_on_worker_nodes" {
  description = "Whether login pods and populate-jail should use the worker k8sNodeFilterName instead of dedicated CPU node filters. Used by GB300 installations that do not create dedicated CPU login nodes and need ARM populate-jail."
  type        = bool
  default     = false
}

variable "login_sshd_config_map_ref_name" {
  description = "Name of configmap with SSHD config, which runs in slurmd container."
  type        = string
  default     = ""
}

variable "sssd_conf_secret_ref_name" {
  description = "Name of Secret containing sssd.conf propagated to controller, login, and worker sssd containers."
  type        = string
  default     = ""
}

variable "sssd_ldap_ca_config_map_ref_name" {
  description = "Name of ConfigMap containing LDAP CA certificates propagated to controller, login, and worker sssd containers."
  type        = string
  default     = ""
}

variable "sssd_enabled" {
  description = "Whether to enable the SSSD sidecar on Slurm controller, login, and worker nodes."
  type        = bool
  default     = false
}

variable "login_ssh_root_public_keys" {
  description = "Authorized keys accepted for connecting to Slurm login nodes via SSH as 'root' user."
  type        = list(string)

  validation {
    condition     = length(var.login_ssh_root_public_keys) >= 1
    error_message = "At least one SSH public key must be provided."
  }

  validation {
    condition     = alltrue([for k in var.login_ssh_root_public_keys : length(k) > 0])
    error_message = "SSH public keys must not be empty strings."
  }
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

variable "enroot_direct_squashfs_enabled" {
  description = "Enable Pyxis/Enroot direct SquashFS startup through squashfuse. Node-local image-storage disk creation remains controlled by node_local_image_disk.enabled."
  type        = bool
  default     = true
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

variable "nfs_node_group_enabled" {
  description = "Whether the NFS node group is enabled."
  type        = bool
  default     = false
}

variable "nfs_in_k8s" {
  type = object({
    enabled         = bool
    version         = optional(string)
    use_stable_repo = optional(bool, true)
    size_gibibytes  = optional(number)
    storage_class   = optional(string, "compute-csi-network-ssd-io-m3-ext4")
    threads         = optional(number)
  })
  default = {
    enabled = false
  }

  validation {
    condition     = var.nfs_in_k8s.enabled ? var.nfs_in_k8s.version != null : true
    error_message = "NFS version must be set."
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

variable "kube_state_metrics_max_scrape_size" {
  description = "Maximum kube-state-metrics HTTP scrape size in bytes. Leave null to raise it automatically for large clusters."
  type        = number
  default     = null
  nullable    = true

  validation {
    condition     = var.kube_state_metrics_max_scrape_size == null || var.kube_state_metrics_max_scrape_size > 0
    error_message = "kube_state_metrics_max_scrape_size must be greater than 0 when set."
  }
}

variable "opentelemetry_batch" {
  description = "OpenTelemetry batch processor overrides for logs, jail logs, and events collectors. Leave null to use chart defaults."
  type = object({
    timeout             = optional(string)
    send_batch_size     = optional(number)
    send_batch_max_size = optional(number)
  })
  default  = null
  nullable = true

  validation {
    condition = (
      var.opentelemetry_batch == null ||
      var.opentelemetry_batch.timeout == null ||
      trimspace(var.opentelemetry_batch.timeout) != ""
    )
    error_message = "opentelemetry_batch.timeout must be non-empty when set."
  }

  validation {
    condition = (
      var.opentelemetry_batch == null ||
      var.opentelemetry_batch.send_batch_size == null ||
      var.opentelemetry_batch.send_batch_size > 0
    )
    error_message = "opentelemetry_batch.send_batch_size must be greater than 0 when set."
  }

  validation {
    condition = (
      var.opentelemetry_batch == null ||
      var.opentelemetry_batch.send_batch_max_size == null ||
      var.opentelemetry_batch.send_batch_max_size > 0
    )
    error_message = "opentelemetry_batch.send_batch_max_size must be greater than 0 when set."
  }

  validation {
    condition = (
      var.opentelemetry_batch == null ||
      var.opentelemetry_batch.send_batch_size == null ||
      var.opentelemetry_batch.send_batch_max_size == null ||
      var.opentelemetry_batch.send_batch_max_size >= var.opentelemetry_batch.send_batch_size
    )
    error_message = "opentelemetry_batch.send_batch_max_size must be greater than or equal to send_batch_size when both are set."
  }
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
  description = "Slurm accounting settings rendered into Soperator-generated slurm_base.conf.noedit, which is included by slurm.conf. See upstream Slurm slurm.conf documentation: https://slurm.schedmd.com/slurm.conf.html. Not all options are supported."
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

variable "maintenance_ignore_node_groups" {
  description = "List of node groups that Soperator should ignore for maintenance events. Supported values: controller, nfs, system, login, accounting."
  type        = list(string)
  default     = ["controller", "nfs"]

  validation {
    condition = alltrue([
      for group in var.maintenance_ignore_node_groups :
      contains(["system", "controller", "login", "accounting", "nfs"], group)
    ])
    error_message = "maintenance_ignore_node_groups must only contain: system, controller, login, accounting, nfs."
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

variable "nccl_inspector_profiling" {
  description = "Whether to enable NCCL Inspector profiling."
  type = object({
    enabled  = bool
    verbose  = optional(bool, false)
    dump_dir = optional(string, "/opt/soperator-outputs/nccl_profiles")
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
    size   = "256Gi"
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

variable "resources_nccl_profiles_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "200Mi"
    cpu    = "500m"
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
  default     = "25.10.2"
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

variable "backups_config" {
  description = "Configuration for backups."
  type = object({
    secret_name    = string
    password       = string
    schedule       = string
    prune_schedule = string
    retention      = map(any)
    storage = object({
      bucket    = string
      endpoint  = string
      bucket_id = string
    })
  })
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
  description = "Scope of active health-checks. Defines what checks should run after the cluster is provisioned."
  default     = "prod_quick"
  validation {
    condition     = contains(["dev", "testing", "prod_quick", "prod_acceptance", "essential"], var.active_checks_scope)
    error_message = "active_checks_scope should be one of: dev, testing, prod_quick, prod_acceptance, essential."
  }
}
# endregion ActiveChecks

# region Nodesets

variable "worker_nodesets" {
  type = list(object({
    name                           = string
    replicas                       = number
    max_unavailable                = string
    features                       = list(string)
    cpu_topology                   = map(number)
    gres_name                      = optional(string)
    gres_config                    = list(string)
    create_partition               = bool
    ephemeral_nodes                = optional(bool, false)
    initial_number_ephemeral_nodes = optional(number, 0)
    persistent_volume_claim_retention_policy = optional(object({
      when_deleted = string
      when_scaled  = string
    }))
    local_nvme = optional(object({
      enabled         = optional(bool, false)
      mount_path      = optional(string, "/mnt/local-nvme")
      filesystem_type = optional(string, "ext4")
    }), {})
    node_local_image_storage = object({
      enabled = bool
      spec = optional(object({
        size_gibibytes     = number
        filesystem_type    = string
        storage_class_name = string
      }))
    })
    node_local_jail_submounts = list(object({
      name               = string
      mount_path         = string
      size_gibibytes     = number
      disk_type          = string
      filesystem_type    = string
      storage_class_name = string
    }))
    topology = optional(object({
      fabric = string
    }))
  }))
  default = []

  validation {
    condition = alltrue([
      for worker in var.worker_nodesets :
      worker.persistent_volume_claim_retention_policy == null || (
        contains(["Retain", "Delete"], worker.persistent_volume_claim_retention_policy.when_deleted) &&
        contains(["Retain", "Delete"], worker.persistent_volume_claim_retention_policy.when_scaled)
      )
    ])
    error_message = "When worker persistent_volume_claim_retention_policy is set, when_deleted and when_scaled must be `Retain` or `Delete`."
  }
}

variable "slurm_nodesets_partitions" {
  description = <<-EOT
    Partition configuration for nodesets.
    Users must not remove the "hidden" partition.
    Users can modify the "main" partition, but should not remove it (there must be at least one default partition).
  EOT
  type = list(object({
    name         = string
    is_all       = optional(bool, false)
    nodeset_refs = optional(list(string), [])
    config       = string
  }))
  default = []

  validation {
    condition = (
      length(var.slurm_nodesets_partitions) == 0 ||
      anytrue([for p in var.slurm_nodesets_partitions : (p.name == "hidden")])
    )
    error_message = "slurm_nodesets_partitions must include a partition named \"hidden\"."
  }

  validation {
    condition = (
      length(var.slurm_nodesets_partitions) == 0 ||
      length([for p in var.slurm_nodesets_partitions : p if can(regex("Default=YES", p.config))]) == 1
    )
    error_message = "Exactly one partition in slurm_nodesets_partitions must have \"Default=YES\" in its config."
  }

  validation {
    condition = alltrue([
      for p in var.slurm_nodesets_partitions :
      (p.is_all || length(p.nodeset_refs) > 0)
    ])
    error_message = "Each partition must have either is_all = true or non-empty nodeset_refs."
  }

  validation {
    condition = alltrue([
      for p in var.slurm_nodesets_partitions :
      !(p.is_all && length(p.nodeset_refs) > 0)
    ])
    error_message = "A partition cannot have both is_all = true and non-empty nodeset_refs."
  }

  validation {
    condition = (
      length(distinct([for p in var.slurm_nodesets_partitions : p.name])) == length(var.slurm_nodesets_partitions)
    )
    error_message = "All partition names in slurm_nodesets_partitions must be unique."
  }
}

# endregion Nodesets

variable "cuda_version" {
  description = "CUDA version used for populate-jail image selection and active checks."
  type        = string
  default     = "13.0.2"
}
