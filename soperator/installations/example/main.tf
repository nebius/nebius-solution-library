locals {
  create_nlb = var.slurm_login_service_type == "NodePort"
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

module "k8s" {
  depends_on = [
    module.filestore
  ]

  source = "../../modules/k8s"

  iam_project_id = data.nebius_iam_v1_project.this.id
  vpc_subnet_id  = data.nebius_vpc_v1_subnet.this.id

  k8s_version        = var.k8s_version
  name               = var.k8s_cluster_name
  slurm_cluster_name = var.slurm_cluster_name

  node_group_cpu = {
    size      = var.slurm_node_count.controller
    resource  = var.k8s_cluster_node_group_cpu.resource
    boot_disk = var.k8s_cluster_node_group_cpu.boot_disk
  }
  node_group_gpu = {
    size        = var.slurm_node_count.worker
    resource    = var.k8s_cluster_node_group_gpu.resource
    boot_disk   = var.k8s_cluster_node_group_gpu.boot_disk
    gpu_cluster = var.k8s_cluster_node_group_gpu.gpu_cluster
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

  create_nlb = local.create_nlb

  node_ssh_access_users = var.k8s_cluster_node_ssh_access_users

  providers = {
    nebius = nebius
    units  = units
  }
}

module "nvidia_operators" {
  depends_on = [
    module.k8s
  ]

  source = "../../modules/nvidia_operators"

  providers = {
    helm = helm
  }
}

module "slurm" {
  depends_on = [
    module.k8s
  ]

  source = "../../modules/slurm"

  name             = var.slurm_cluster_name
  operator_version = var.slurm_operator_version

  node_count = var.slurm_node_count

  worker_resources = tomap({
    "8gpu-128vcpu-1600gb" = {
      cpu_cores                   = 128 - 48
      memory_gibibytes            = 1600 - 400
      ephemeral_storage_gibibytes = ceil(var.k8s_cluster_node_group_gpu.boot_disk.size_gibibytes / 2)
      gpus                        = 8
    }
    "1gpu-20vcpu-200gb" = {
      cpu_cores                   = 20 - 4
      memory_gibibytes            = 200 - 50
      ephemeral_storage_gibibytes = ceil(var.k8s_cluster_node_group_gpu.boot_disk.size_gibibytes / 2)
      gpus                        = 1
    }
  })[var.k8s_cluster_node_group_gpu.resource.preset]

  login_service_type         = var.slurm_login_service_type
  login_node_port            = var.slurm_login_node_port
  login_allocation_id        = module.k8s.allocation_id
  login_ssh_root_public_keys = var.slurm_login_ssh_root_public_keys

  exporter_enabled        = var.slurm_exporter_enabled
  accounting_enabled      = var.accounting_enabled
  slurmdbd_config         = var.slurmdbd_config
  slurm_accounting_config = var.slurm_accounting_config

  # TODO: MSP-2817 - use computed values of filestore sizes
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

  shared_memory_size_gibibytes = var.slurm_shared_memory_size_gibibytes

  nccl_topology_type           = var.k8s_cluster_node_group_gpu.resource.platform == "gpu-h100-sxm" ? "H100 GPU cluster" : "auto"
  nccl_benchmark_enable        = var.nccl_benchmark_enable
  nccl_benchmark_schedule      = var.nccl_benchmark_schedule
  nccl_benchmark_min_threshold = var.nccl_benchmark_min_threshold

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

  nlb_used           = local.create_nlb
  slurm_cluster_name = var.slurm_cluster_name

  providers = {
    kubernetes = kubernetes
  }
}
