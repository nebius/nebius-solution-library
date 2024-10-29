locals {
  node_ssh_access = {
    enabled = length(var.node_ssh_access_users) > 0
    cloud_init_data = templatefile("${path.module}/templates/cloud_init.yaml.tftpl", {
      ssh_users = var.node_ssh_access_users
    })
  }

  node_group_gpu_present = {
    system = (
      module.resources.this[var.node_group_system.resource.platform][var.node_group_system.resource.preset].gpus > 0
      ? true
      : false
    )
    controller = (
      module.resources.this[var.node_group_controller.resource.platform][var.node_group_controller.resource.preset].gpus > 0
      ? true
      : false
    )
    worker = [
      for worker in var.node_group_workers :
      (module.resources.this[worker.resource.platform][worker.resource.preset].gpus > 0 ? true : false)
    ]
    login = (
      module.resources.this[var.node_group_login.resource.platform][var.node_group_login.resource.preset].gpus > 0
      ? true
      : false
    )
    nlb = false
  }

  node_group_gpu_cluster_compatible = {
    system     = module.resources.this[var.node_group_system.resource.platform][var.node_group_system.resource.preset].gpu_cluster_compatible
    controller = module.resources.this[var.node_group_controller.resource.platform][var.node_group_controller.resource.preset].gpu_cluster_compatible
    worker = [for worker in var.node_group_workers :
      module.resources.this[worker.resource.platform][worker.resource.preset].gpu_cluster_compatible
    ]
    login = module.resources.this[var.node_group_login.resource.platform][var.node_group_login.resource.preset].gpu_cluster_compatible
    nlb   = false
  }

  node_group_workload_label = {
    system = (local.node_group_gpu_present.system
      ? module.labels.label_workload_gpu
      : module.labels.label_workload_cpu
    )
    controller = (local.node_group_gpu_present.controller
      ? module.labels.label_workload_gpu
      : module.labels.label_workload_cpu
    )
    worker = [for worker in local.node_group_gpu_present :
      (worker ? module.labels.label_workload_gpu : module.labels.label_workload_cpu)
    ]
    login = (local.node_group_gpu_present.login
      ? module.labels.label_workload_gpu
      : module.labels.label_workload_cpu
    )
    nlb = (local.node_group_gpu_present.nlb
      ? module.labels.label_workload_gpu
      : module.labels.label_workload_cpu
    )
  }
}
