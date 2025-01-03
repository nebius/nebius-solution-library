locals {
  resources = {
    system     = module.resources.this[var.slurm_nodeset_system.resource.platform][var.slurm_nodeset_system.resource.preset]
    controller = module.resources.this[var.slurm_nodeset_controller.resource.platform][var.slurm_nodeset_controller.resource.preset]
    workers    = [for worker in var.slurm_nodeset_workers : module.resources.this[worker.resource.platform][worker.resource.preset]]
    login      = module.resources.this[var.slurm_nodeset_login.resource.platform][var.slurm_nodeset_login.resource.preset]
    accounting = var.slurm_nodeset_accounting != null ? module.resources.this[var.slurm_nodeset_accounting.resource.platform][var.slurm_nodeset_accounting.resource.preset] : null
  }

  use_node_port = var.slurm_login_service_type == "NodePort"
}

module "filestore" {
  source = "../../modules/filestore"

  iam_project_id = data.nebius_iam_v1_project.this.id

  k8s_cluster_name = var.k8s_cluster_name

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
  count          = var.nfs.enabled ? 1 : 0
  source         = "../../../modules/nfs-server"
  parent_id      = data.nebius_iam_v1_project.this.id
  subnet_id      = data.nebius_vpc_v1_subnet.this.id
  ssh_user_name  = "soperator"
  ssh_public_key = var.slurm_login_ssh_root_public_keys[0]
  nfs_ip_range   = data.nebius_vpc_v1_subnet.this.ipv4_private_pools.pools[0].cidrs[0].cidr
  nfs_size       = var.nfs.size_gibibytes * 1024 * 1024 * 1024
  nfs_path       = "/mnt/nfs"
  platform       = var.nfs.resource.platform
  preset         = var.nfs.resource.preset

  providers = {
    nebius = nebius
  }
}

module "k8s" {
  depends_on = [
    module.filestore,
    terraform_data.check_slurm_nodeset_accounting,
    terraform_data.check_slurm_nodeset,
  ]

  source = "../../modules/k8s"

  iam_project_id = data.nebius_iam_v1_project.this.id
  vpc_subnet_id  = data.nebius_vpc_v1_subnet.this.id

  k8s_version        = var.k8s_version
  name               = var.k8s_cluster_name
  slurm_cluster_name = var.slurm_cluster_name
  company_name       = var.company_name

  node_group_system     = var.slurm_nodeset_system
  node_group_controller = var.slurm_nodeset_controller
  node_group_workers = flatten([for i, nodeset in var.slurm_nodeset_workers :
    [
      for subset in range(ceil(nodeset.size / nodeset.nodes_per_nodegroup)) :
      {
        size                    = nodeset.nodes_per_nodegroup
        max_unavailable_percent = nodeset.max_unavailable_percent
        resource                = nodeset.resource
        boot_disk               = nodeset.boot_disk
        gpu_cluster             = nodeset.gpu_cluster
        nodeset_index           = i
        subset_index            = subset
      }
    ]
  ])
  node_group_login = var.slurm_nodeset_login
  node_group_accounting = {
    enabled = var.accounting_enabled
    spec    = var.slurm_nodeset_accounting
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
  use_node_port         = local.use_node_port

  providers = {
    nebius = nebius
    units  = units
  }
}

module "nvidia_operator_network" {
  count = module.k8s.gpu_involved ? 1 : 0

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
  count = module.k8s.gpu_involved ? 1 : 0

  depends_on = [
    module.nvidia_operator_network
  ]

  source = "../../../modules/gpu-operator"

  cluster_id = module.k8s.cluster_id
  parent_id  = data.nebius_iam_v1_project.this.id

  enable_dcgm_service_monitor = var.telemetry_enabled

  providers = {
    nebius = nebius
  }
}

module "slurm" {
  depends_on = [
    module.k8s,
  ]

  source = "../../modules/slurm"

  name                = var.slurm_cluster_name
  operator_version    = var.slurm_operator_version
  k8s_cluster_context = module.k8s.cluster_context

  iam_project_id = var.iam_project_id

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
        module.resources.k8s_ephemeral_storage_coefficient * var.slurm_nodeset_system.boot_disk.size_gibibytes
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    controller = {
      cpu_cores        = local.resources.controller.cpu_cores
      memory_gibibytes = local.resources.controller.memory_gibibytes
      ephemeral_storage_gibibytes = floor(
        module.resources.k8s_ephemeral_storage_coefficient * var.slurm_nodeset_controller.boot_disk.size_gibibytes
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    worker = [for i, worker in var.slurm_nodeset_workers :
      {
        cpu_cores        = local.resources.workers[i].cpu_cores
        memory_gibibytes = local.resources.workers[i].memory_gibibytes
        ephemeral_storage_gibibytes = (
          module.k8s.gpu_involved
          ? floor(
            module.resources.k8s_ephemeral_storage_coefficient * worker.boot_disk.size_gibibytes
            -2 * module.resources.k8s_ephemeral_storage_reserve.gibibytes
          )
          : floor(
            module.resources.k8s_ephemeral_storage_coefficient * worker.boot_disk.size_gibibytes
            -module.resources.k8s_ephemeral_storage_reserve.gibibytes
          )
        )
        gpus = local.resources.workers[i].gpus
      }
    ]
    login = {
      cpu_cores        = local.resources.login.cpu_cores
      memory_gibibytes = local.resources.login.memory_gibibytes
      ephemeral_storage_gibibytes = floor(
        module.resources.k8s_ephemeral_storage_coefficient * var.slurm_nodeset_login.boot_disk.size_gibibytes
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    }
    accounting = var.accounting_enabled ? {
      cpu_cores        = local.resources.accounting.cpu_cores
      memory_gibibytes = local.resources.accounting.memory_gibibytes
      ephemeral_storage_gibibytes = floor(
        module.resources.k8s_ephemeral_storage_coefficient * var.slurm_nodeset_accounting.boot_disk.size_gibibytes
        -module.resources.k8s_ephemeral_storage_reserve.gibibytes
      )
    } : null
  }

  login_service_type              = var.slurm_login_service_type
  login_node_port                 = var.slurm_login_node_port
  login_allocation_id             = module.k8s.allocation_id
  login_sshd_config_map_ref_name  = var.slurm_login_sshd_config_map_ref_name
  login_ssh_root_public_keys      = var.slurm_login_ssh_root_public_keys

  worker_sshd_config_map_ref_name  = var.slurm_worker_sshd_config_map_ref_name

  exporter_enabled        = var.slurm_exporter_enabled
  rest_enabled            = var.slurm_rest_enabled
  accounting_enabled      = var.accounting_enabled
  slurmdbd_config         = var.slurmdbd_config
  slurm_accounting_config = var.slurm_accounting_config

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

  nfs = {
    enabled    = var.nfs.enabled
    path       = var.nfs.enabled ? module.nfs-server[0].nfs_export_path : null
    host       = var.nfs.enabled ? module.nfs-server[0].nfs_server_internal_ip : null
    mount_path = var.nfs.enabled ? var.nfs.mount_path : null
  }

  shared_memory_size_gibibytes = var.slurm_shared_memory_size_gibibytes

  nccl_topology_type           = "auto"
  nccl_benchmark_enable        = var.nccl_benchmark_enable
  nccl_benchmark_schedule      = var.nccl_benchmark_schedule
  nccl_benchmark_min_threshold = var.nccl_benchmark_min_threshold
  nccl_use_infiniband          = var.nccl_use_infiniband

  telemetry_enabled                = var.telemetry_enabled
  telemetry_grafana_admin_password = var.telemetry_grafana_admin_password

  providers = {
    helm = helm
  }
}

module "login_script" {
  depends_on = [
    module.slurm
  ]

  source = "../../modules/login"

  node_port = {
    used = local.use_node_port
    port = var.slurm_login_node_port
  }
  slurm_cluster_name = var.slurm_cluster_name

  k8s_cluster_context = module.k8s.cluster_context

  providers = {
    kubernetes = kubernetes
  }
}
