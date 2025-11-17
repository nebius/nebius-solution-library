locals {
  resources = {
    system     = module.resources.by_platform[var.slurm_nodeset_system.resource.platform][var.slurm_nodeset_system.resource.preset]
    controller = module.resources.by_platform[var.slurm_nodeset_controller.resource.platform][var.slurm_nodeset_controller.resource.preset]
    workers    = [for worker in var.slurm_nodeset_workers : module.resources.by_platform[worker.resource.platform][worker.resource.preset]]
    login      = module.resources.by_platform[var.slurm_nodeset_login.resource.platform][var.slurm_nodeset_login.resource.preset]
    accounting = var.slurm_nodeset_accounting != null ? module.resources.by_platform[var.slurm_nodeset_accounting.resource.platform][var.slurm_nodeset_accounting.resource.preset] : null
    nfs        = var.slurm_nodeset_nfs != null ? module.resources.by_platform[var.slurm_nodeset_nfs.resource.platform][var.slurm_nodeset_nfs.resource.preset] : null
  }

  slurm_cluster_name = "soperator"
  flux_namespace     = "flux-system"
  k8s_cluster_name   = format("soperator-%s", var.company_name)

  backups_enabled = (var.backups_enabled == "force_enable" ||
  (var.backups_enabled == "auto" && local.filestore_jail_calculated_size_gibibytes < 12 * 1024))

  # Legacy node_group_workers for old-style deployments (without nodesets)
  node_group_workers = flatten([for i, nodeset in var.slurm_nodeset_workers : [
    for subset in range(ceil(nodeset.size / 100.0)) : {
      size                    = min(100, nodeset.size - subset * 100)
      max_unavailable_percent = 50
      max_surge_percent       = null
      drain_timeout           = null
      resource                = nodeset.resource
      boot_disk               = nodeset.boot_disk
      gpu_cluster             = nodeset.gpu_cluster
      nodeset_index           = i
      subset_index            = subset
      preemptible             = nodeset.preemptible
    }
  ]])

  # V2 node_group_workers for new-style deployments (with nodesets)
  node_group_workers_v2 = flatten([for i, nodeset in var.slurm_nodeset_workers : [
    for subset in range(ceil(nodeset.size / 100.0)) : {
      name          = nodeset.name
      size          = min(100, nodeset.size - subset * 100)
      min_size      = 0
      max_size      = min(100, nodeset.size - subset * 100)
      autoscaling   = true
      resource      = nodeset.resource
      boot_disk     = nodeset.boot_disk
      gpu_cluster   = nodeset.gpu_cluster
      nodeset_index = i
      subset_index  = subset
      preemptible   = nodeset.preemptible
    }
  ]])
}

resource "terraform_data" "check_variables" {
  depends_on = [
    terraform_data.check_slurm_nodeset,
    terraform_data.check_slurm_nodeset_accounting,
    terraform_data.check_nfs,
  ]
}

module "filestore" {
  source = "../../modules/filestore"

  depends_on = [
    terraform_data.check_variables,
  ]

  iam_project_id = data.nebius_iam_v1_project.this.id

  k8s_cluster_name = local.k8s_cluster_name

  controller_spool = {
    spec = var.filestore_controller_spool.spec != null ? {
      disk_type            = "NETWORK_SSD"
      size_gibibytes       = var.filestore_controller_spool.spec.size_gibibytes
      block_size_kibibytes = var.filestore_controller_spool.spec.block_size_kibibytes
    } : null
    existing = var.filestore_controller_spool.existing != null ? {
      id = var.filestore_controller_spool.existing.id
    } : null
  }

  accounting = var.accounting_enabled ? {
    spec = var.filestore_accounting.spec != null ? {
      disk_type            = "NETWORK_SSD"
      size_gibibytes       = var.filestore_accounting.spec.size_gibibytes
      block_size_kibibytes = var.filestore_accounting.spec.block_size_kibibytes
    } : null
    existing = var.filestore_accounting.existing != null ? {
      id = var.filestore_accounting.existing.id
    } : null
  } : null

  jail = {
    spec = var.filestore_jail.spec != null ? {
      disk_type            = "NETWORK_SSD"
      size_gibibytes       = var.filestore_jail.spec.size_gibibytes
      block_size_kibibytes = var.filestore_jail.spec.block_size_kibibytes
    } : null
    existing = var.filestore_jail.existing != null ? {
      id = var.filestore_jail.existing.id
    } : null
  }

  jail_submounts = [for submount in var.filestore_jail_submounts : {
    name = submount.name
    spec = submount.spec != null ? {
      disk_type            = "NETWORK_SSD"
      size_gibibytes       = submount.spec.size_gibibytes
      block_size_kibibytes = submount.spec.block_size_kibibytes
    } : null
    existing = submount.existing != null ? {
      id = submount.existing.id
    } : null
  }]

  providers = {
    nebius = nebius
    units  = units
  }
}

module "nfs-server" {
  count = var.nfs.enabled ? 1 : 0

  source = "../../../modules/nfs-server"

  parent_id = data.nebius_iam_v1_project.this.id
  subnet_id = data.nebius_vpc_v1_subnet.this.id

  platform      = var.nfs.resource.platform
  preset        = var.nfs.resource.preset
  instance_name = "${local.k8s_cluster_name}-nfs-server"

  nfs_disk_name_suffix = local.k8s_cluster_name
  nfs_ip_range         = data.nebius_vpc_v1_subnet.this.status.ipv4_private_cidrs[0]
  nfs_size             = provider::units::from_gib(var.nfs.size_gibibytes)
  nfs_path             = "/home"

  ssh_user_name   = "soperator"
  ssh_public_keys = var.slurm_login_ssh_root_public_keys

  public_ip = var.nfs.public_ip

  providers = {
    nebius = nebius
  }
}

module "cleanup" {
  source = "../../modules/cleanup"

  iam_project_id = var.iam_project_id
}

module "k8s" {
  depends_on = [
    module.filestore,
    module.nfs-server,
    module.cleanup,
    terraform_data.check_slurm_nodeset_accounting,
    terraform_data.check_slurm_nodeset,
  ]

  source = "../../modules/k8s"

  iam_project_id  = data.nebius_iam_v1_project.this.id
  vpc_subnet_id   = data.nebius_vpc_v1_subnet.this.id
  login_public_ip = var.slurm_login_public_ip

  k8s_version                  = var.k8s_version
  name                         = local.k8s_cluster_name
  company_name                 = var.company_name
  use_preinstalled_gpu_drivers = var.use_preinstalled_gpu_drivers

  etcd_cluster_size = var.etcd_cluster_size

  node_group_system      = var.slurm_nodeset_system
  node_group_controller  = var.slurm_nodeset_controller
  node_group_workers     = local.node_group_workers
  node_group_workers_v2  = local.node_group_workers_v2
  node_group_login       = var.slurm_nodeset_login
  slurm_nodesets_enabled = var.slurm_nodesets_enabled
  node_group_accounting = {
    enabled = var.accounting_enabled
    spec    = var.slurm_nodeset_accounting
  }
  node_group_nfs = {
    enabled = var.slurm_nodeset_nfs != null
    spec    = var.slurm_nodeset_nfs
  }

  filestores = {
    controller_spool = {
      id        = module.filestore.controller_spool.id
      mount_tag = module.filestore.controller_spool.mount_tag
    }
    jail = {
      id        = module.filestore.jail.id
      mount_tag = module.filestore.jail.mount_tag
    }
    jail_submounts = [for key, submount in module.filestore.jail_submounts : {
      id        = submount.id
      mount_tag = submount.mount_tag
    }]
    accounting = var.accounting_enabled ? {
      id        = module.filestore.accounting.id
      mount_tag = module.filestore.accounting.mount_tag
    } : null
  }

  node_ssh_access_users = var.k8s_cluster_node_ssh_access_users

  providers = {
    nebius = nebius
    units  = units
  }
}

module "k8s_storage_class" {
  depends_on = [
    module.k8s,
  ]

  source = "../../modules/k8s/storage_class"

  storage_class_requirements = concat(
    [{
      disk_type       = module.resources.disk_types.network_ssd
      filesystem_type = module.resources.filesystem_types.ext4
    }],
    [for sm in var.node_local_jail_submounts : {
      disk_type       = sm.disk_type
      filesystem_type = sm.filesystem_type
    }],
    !var.node_local_image_disk.enabled ? [] : [{
      disk_type       = var.node_local_image_disk.spec.disk_type
      filesystem_type = var.node_local_image_disk.spec.filesystem_type
    }]
  )

  providers = {
    kubernetes = kubernetes
  }
}

moved {
  from = module.k8s_storage_class[0]
  to   = module.k8s_storage_class
}

module "nvidia_operator_network" {
  count = module.k8s.gpu_involved && !var.use_preinstalled_gpu_drivers ? 1 : 0

  depends_on = [
    module.k8s
  ]

  source = "../../../modules/network-operator"

  cluster_id = module.k8s.cluster_id
  parent_id  = data.nebius_iam_v1_project.this.id

  providers = {
    nebius = nebius
  }
}

module "nvidia_operator_gpu" {
  count = module.k8s.gpu_involved && !var.use_preinstalled_gpu_drivers ? 1 : 0

  depends_on = [
    module.nvidia_operator_network
  ]

  source = "../../../modules/gpu-operator"

  cluster_id = module.k8s.cluster_id
  parent_id  = data.nebius_iam_v1_project.this.id

  enable_dcgm_exporter        = var.dcgm_job_mapping_enabled == false && var.telemetry_enabled
  enable_dcgm_service_monitor = var.dcgm_job_mapping_enabled == false && var.telemetry_enabled
  relabel_dcgm_exporter       = var.telemetry_enabled

  providers = {
    nebius = nebius
  }
}

module "o11y" {
  count = var.public_o11y_enabled ? 1 : 0

  depends_on = [
    module.k8s,
    module.fluxcd,
  ]

  source = "../../modules/o11y"

  iam_project_id      = var.iam_project_id
  o11y_iam_tenant_id  = var.o11y_iam_tenant_id
  o11y_profile        = var.o11y_profile
  k8s_cluster_context = module.k8s.cluster_context
  company_name        = var.company_name
}

module "slurm" {
  depends_on = [
    module.k8s,
    module.k8s_storage_class,
    module.o11y,
    module.fluxcd,
    module.backups,
  ]

  source = "../../modules/slurm"

  active_checks_scope = var.active_checks_scope

  region              = var.region
  iam_tenant_id       = var.iam_tenant_id
  iam_project_id      = var.iam_project_id
  cluster_name        = var.company_name
  name                = local.slurm_cluster_name
  k8s_cluster_context = module.k8s.cluster_context

  operator_version       = var.slurm_operator_version
  operator_stable        = var.slurm_operator_stable
  operator_feature_gates = var.slurm_operator_feature_gates

  maintenance                    = var.maintenance
  maintenance_ignore_node_groups = var.maintenance_ignore_node_groups

  use_preinstalled_gpu_drivers  = var.use_preinstalled_gpu_drivers
  use_cuda13rc                  = var.slurm_nodeset_workers[0].resource.platform == "gpu-b300-sxm" ? true : false
  controller_state_on_filestore = var.controller_state_on_filestore

  node_count = {
    controller = var.slurm_nodeset_controller.size
    worker     = [for workers in var.slurm_nodeset_workers : workers.size]
    login      = var.slurm_nodeset_login.size
  }

  resources = {
    system = {
      cpu_cores        = local.resources.system.cpu_cores
      memory_gibibytes = local.resources.system.memory_gibibytes
      ephemeral_storage_gibibytes = floor(
        var.slurm_nodeset_system.boot_disk.size_gibibytes * module.resources.k8s_ephemeral_storage_coefficient
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    controller = {
      cpu_cores        = local.resources.controller.cpu_cores
      memory_gibibytes = floor(local.resources.controller.memory_gibibytes)
      ephemeral_storage_gibibytes = floor(
        var.slurm_nodeset_controller.boot_disk.size_gibibytes * module.resources.k8s_ephemeral_storage_coefficient
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    worker = [for i, worker in var.slurm_nodeset_workers :
      {
        cpu_cores        = local.resources.workers[i].cpu_cores
        memory_gibibytes = floor(local.resources.workers[i].memory_gibibytes)
        ephemeral_storage_gibibytes = floor(
          worker.boot_disk.size_gibibytes * module.resources.k8s_ephemeral_storage_coefficient
          -module.resources.k8s_ephemeral_storage_reserve.gibibytes
        )
        gpus = local.resources.workers[i].gpus
      }
    ]
    login = {
      cpu_cores        = local.resources.login.cpu_cores
      memory_gibibytes = floor(local.resources.login.memory_gibibytes)
      ephemeral_storage_gibibytes = floor(
        var.slurm_nodeset_login.boot_disk.size_gibibytes * module.resources.k8s_ephemeral_storage_coefficient
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    accounting = var.accounting_enabled ? {
      cpu_cores        = local.resources.accounting.cpu_cores
      memory_gibibytes = floor(local.resources.accounting.memory_gibibytes)
      ephemeral_storage_gibibytes = floor(
        var.slurm_nodeset_accounting.boot_disk.size_gibibytes * module.resources.k8s_ephemeral_storage_coefficient
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    } : null
    nfs = var.slurm_nodeset_nfs != null ? {
      cpu_cores        = local.resources.nfs.cpu_cores
      memory_gibibytes = floor(local.resources.nfs.memory_gibibytes)
    } : null
  }

  filestores = {
    controller_spool = {
      size_gibibytes = module.filestore.controller_spool.size_gibibytes
      device         = module.filestore.controller_spool.mount_tag
    }
    jail = {
      size_gibibytes = module.filestore.jail.size_gibibytes
      device         = module.filestore.jail.mount_tag
    }
    jail_submounts = [for submount in var.filestore_jail_submounts : {
      name           = submount.name
      size_gibibytes = module.filestore.jail_submounts[submount.name].size_gibibytes
      device         = module.filestore.jail_submounts[submount.name].mount_tag
      mount_path     = submount.mount_path
    }]
    accounting = var.accounting_enabled ? {
      size_gibibytes = module.filestore.accounting.size_gibibytes
      device         = module.filestore.accounting.mount_tag
    } : null
  }
  node_local_jail_submounts = [for sm in var.node_local_jail_submounts : {
    name               = sm.name
    mount_path         = sm.mount_path
    size_gibibytes     = sm.size_gibibytes
    disk_type          = sm.disk_type
    filesystem_type    = sm.filesystem_type
    storage_class_name = module.k8s_storage_class.storage_classes[sm.disk_type][sm.filesystem_type]
  }]
  node_local_image_storage = {
    enabled = var.node_local_image_disk.enabled
    spec = var.node_local_image_disk.enabled ? {
      size_gibibytes     = var.node_local_image_disk.spec.size_gibibytes
      filesystem_type    = var.node_local_image_disk.spec.filesystem_type
      storage_class_name = module.k8s_storage_class.storage_classes[var.node_local_image_disk.spec.disk_type][var.node_local_image_disk.spec.filesystem_type]
    } : null
  }

  nfs = {
    enabled    = var.nfs.enabled
    path       = var.nfs.enabled ? module.nfs-server[0].nfs_export_path : null
    host       = var.nfs.enabled ? module.nfs-server[0].nfs_server_internal_ip : null
    mount_path = var.nfs.enabled ? var.nfs.mount_path : null
  }

  nfs_in_k8s             = var.nfs_in_k8s
  nfs_node_group_enabled = var.slurm_nodeset_nfs != null

  exporter_enabled    = var.slurm_exporter_enabled
  rest_enabled        = var.slurm_rest_enabled
  accounting_enabled  = var.accounting_enabled
  backups_enabled     = local.backups_enabled
  telemetry_enabled   = var.telemetry_enabled
  public_o11y_enabled = var.public_o11y_enabled
  soperator_notifier  = var.soperator_notifier

  slurmdbd_config         = var.slurmdbd_config
  slurm_accounting_config = var.slurm_accounting_config

  use_default_apparmor_profile    = var.use_default_apparmor_profile
  worker_sshd_config_map_ref_name = var.slurm_worker_sshd_config_map_ref_name
  shared_memory_size_gibibytes    = var.slurm_shared_memory_size_gibibytes
  slurm_partition_config_type     = var.slurm_partition_config_type
  slurm_partition_raw_config      = var.slurm_partition_raw_config
  slurm_worker_features           = var.slurm_worker_features
  slurm_health_check_config       = var.slurm_health_check_config

  slurm_nodesets_enabled    = var.slurm_nodesets_enabled
  slurm_nodesets_partitions = var.slurm_nodesets_partitions
  node_group_workers_v2     = local.node_group_workers_v2

  login_allocation_id            = module.k8s.static_ip_allocation_id
  login_public_ip                = var.slurm_login_public_ip
  tailscale_enabled              = var.tailscale_enabled
  login_sshd_config_map_ref_name = var.slurm_login_sshd_config_map_ref_name
  login_ssh_root_public_keys     = var.slurm_login_ssh_root_public_keys

  github_org              = var.github_org
  github_repository       = var.github_repository
  github_ref_type         = var.slurm_operator_stable ? "tag" : "branch"
  github_ref_value        = var.slurm_operator_stable ? var.slurm_operator_version : "main"
  flux_namespace          = local.flux_namespace
  flux_interval           = var.flux_interval
  flux_kustomization_path = var.slurm_operator_stable ? "fluxcd/environment/nebius-cloud/prod" : "fluxcd/environment/nebius-cloud/dev"

  providers = {
    helm = helm
  }
}

module "login_script" {
  depends_on = [
    module.slurm
  ]

  source = "../../modules/login"

  slurm_cluster_name = local.slurm_cluster_name

  k8s_cluster_context = module.k8s.cluster_context

  providers = {
    kubernetes = kubernetes
  }
}

module "backups_store" {
  count = local.backups_enabled ? 1 : 0

  source = "../../modules/backups_store"

  iam_project_id = var.iam_project_id
  instance_name  = local.k8s_cluster_name

  cleanup_bucket_on_destroy = var.cleanup_bucket_on_destroy

  depends_on = [
    module.k8s,
    module.fluxcd,
  ]
}

module "backups" {
  count = local.backups_enabled ? 1 : 0

  source = "../../modules/backups"

  k8s_cluster_context = module.k8s.cluster_context

  iam_project_id      = var.iam_project_id
  iam_tenant_id       = var.iam_tenant_id
  instance_name       = local.k8s_cluster_name
  flux_namespace      = local.flux_namespace
  soperator_namespace = local.slurm_cluster_name
  bucket_name         = module.backups_store[count.index].name
  bucket_endpoint     = module.backups_store[count.index].endpoint

  backups_password  = var.backups_password
  backups_schedule  = var.backups_schedule
  prune_schedule    = var.backups_prune_schedule
  backups_retention = var.backups_retention

  providers = {
    nebius = nebius
    helm   = helm
  }

  depends_on = [
    module.k8s,
  ]
}

module "fluxcd" {
  depends_on = [
    module.k8s,
  ]
  source              = "../../modules/fluxcd"
  k8s_cluster_context = module.k8s.cluster_context
}
