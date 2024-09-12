run "create_cluster" {
  command = apply

  variables {
    enable_loki       = false # TODO: Disabling Loki since not possible to delete non-empty storage bucket
    test_mode         = true
    infiniband_fabric = "fabric-4"
    gpu_nodes_count   = 2
  }

  assert {
    condition     = alltrue([for status in module.o11y.helm_release_status : status == "deployed" if status != null])
    error_message = "Fail to deploy helm o11y releases ${jsonencode(module.o11y.helm_release_status)}"
  }

  assert {
    condition     = alltrue([for pod_alive in module.o11y.k8s_apps_status : pod_alive == 1])
    error_message = "Not all pods in running status ${jsonencode(module.o11y.k8s_apps_status)}"
  }

  assert {
    condition     = module.nccl-test[0].helm_release_status == "deployed"
    error_message = "Fail to deploy helm nccl-test release ${module.nccl-test[0].helm_release_status}"
  }
}
