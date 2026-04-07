locals {
  node_ssh_access = {
    enabled = length(var.node_ssh_access_users) > 0
  }

  node_cloud_init = {
    enabled = length(var.node_ssh_access_users) > 0 || length(var.nvidia_config_lines) > 0
    cloud_init_data = templatefile("${path.module}/templates/cloud_init.yaml.tftpl", {
      ssh_users                  = var.node_ssh_access_users
      nvidia_config_lines        = var.nvidia_config_lines
      local_nvme_enabled         = false
      local_nvme_mount_path      = "/mnt/local-nvme"
      local_nvme_filesystem_type = "ext4"
    })
    cloud_init_data_no_nvidia = templatefile("${path.module}/templates/cloud_init.yaml.tftpl", {
      ssh_users                  = var.node_ssh_access_users
      nvidia_config_lines        = []
      local_nvme_enabled         = false
      local_nvme_mount_path      = "/mnt/local-nvme"
      local_nvme_filesystem_type = "ext4"
    })
  }

  node_group_gpu_present = {
    worker = [
      for worker in var.node_group_workers :
      (module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpus > 0 ? true : false)
    ]
  }

  node_group_gpu_cluster_compatible = {
    worker = [for worker in var.node_group_workers :
      module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpu_cluster_compatible
    ]
  }

  node_group_workload_label = {
    worker = [for worker in local.node_group_gpu_present.worker :
      (worker ? module.labels.label_workload_gpu : module.labels.label_workload_cpu)
    ]
  }

  # V2 workers (for nodesets)
  node_group_gpu_present_v2 = {
    worker = [
      for worker in var.node_group_workers_v2 :
      (module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpus > 0 ? true : false)
    ]
  }

  node_group_gpu_cluster_compatible_v2 = {
    worker = [for worker in var.node_group_workers_v2 :
      module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpu_cluster_compatible
    ]
  }

  node_group_workload_label_v2 = {
    worker = [for worker in local.node_group_gpu_present_v2.worker :
      (worker ? module.labels.label_workload_gpu : module.labels.label_workload_cpu)
    ]
  }

  context_name = join(
    "-",
    [
      "nebius",
      replace(lower(var.company_name), " ", "-"),
      "slurm"
    ]
  )
}
