locals {
  worker_gpu_fabric_checks = {
    for idx, worker in var.node_group_workers_v2 :
    idx => {
      name                      = worker.name
      preset                    = worker.resource.preset
      platform                  = worker.resource.platform
      is_gpu                    = module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpus > 0
      is_gpu_cluster_compatible = module.resources.by_platform[worker.resource.platform][worker.resource.preset].gpu_cluster_compatible
      has_gpu_cluster           = worker.gpu_cluster != null
      fabric                    = worker.gpu_cluster != null ? trimspace(worker.gpu_cluster.infiniband_fabric) : ""
    }
  }
}

resource "terraform_data" "check_worker_gpu_fabric" {
  for_each = local.worker_gpu_fabric_checks

  lifecycle {
    precondition {
      condition = (
        each.value.is_gpu_cluster_compatible
        ? (each.value.has_gpu_cluster && length(each.value.fabric) > 0)
        : !each.value.has_gpu_cluster
      )
      error_message = (
        each.value.is_gpu_cluster_compatible
        ? "Worker '${each.value.name}' uses GPU preset '${each.value.preset}' with InfiniBand support and requires gpu_cluster.infiniband_fabric to be set to a non-empty value."
        : each.value.is_gpu
        ? "Worker '${each.value.name}' uses GPU preset '${each.value.preset}' without gpu_cluster support, so gpu_cluster must be unset."
        : "Worker '${each.value.name}' uses CPU preset '${each.value.preset}', so gpu_cluster must be unset."
      )
    }
  }
}
