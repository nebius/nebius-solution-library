run "k8s_inference_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_cluster.k8s-cluster
    ]
  }
}

run "k8s_node_groups_inference_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_node_group.cpu-only,
      nebius_mk8s_v1_node_group.gpu
    ]
  }
}

run "full_inference_apply" {
  command = apply
}

run "test_mode_k8s_inference_apply" {
  command = apply

  variables {
    test_mode = true
  }

  assert {
    condition     = alltrue([for status in module.o11y.helm_release_status : status == "deployed" if status != null])
    error_message = "Fail to deploy helm o11y releases ${jsonencode(module.o11y.helm_release_status)}"
  }

  assert {
    condition     = alltrue([for pod_alive in module.o11y.k8s_apps_status : pod_alive == 1])
    error_message = "Not all pods in running status ${jsonencode(module.o11y.k8s_apps_status)}"
  }
}
