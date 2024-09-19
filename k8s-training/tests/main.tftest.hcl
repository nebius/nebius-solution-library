run "k8s_training_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_cluster.k8s-cluster
    ]
  }
  variables {
    etcd_cluster_size = 1
  }
}

run "k8s_node_groups_training_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_node_group.cpu-only,
      nebius_mk8s_v1_node_group.gpu
    ]
  }
  variables {
    etcd_cluster_size = 1
  }
}

run "full_training_apply" {
  command = apply

  variables {
    enable_loki       = false # TODO: Disabling Loki since not possible to delete non-empty storage bucket
    etcd_cluster_size = 1
  }
}

run "test_mode_k8s_training_apply" {
  command = apply

  variables {
    enable_loki       = false # TODO: Disabling Loki since not possible to delete non-empty storage bucket
    test_mode         = true
    etcd_cluster_size = 1
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
