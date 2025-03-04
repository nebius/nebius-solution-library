locals {
  node_ssh_access = {
    enabled = length(var.node_ssh_access_users) > 0
    cloud_init_data = templatefile("${path.module}/templates/cloud_init.yaml.tftpl", {
      ssh_users = var.node_ssh_access_users
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

  context_name = join(
    "-",
    [
      "nebius",
      replace(lower(var.company_name), " ", "-"),
      "slurm"
    ]
  )
}
