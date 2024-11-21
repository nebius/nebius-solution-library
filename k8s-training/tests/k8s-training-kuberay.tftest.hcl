run "k8s_training_kuberay_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_cluster.k8s-cluster
    ]
  }
  variables {
    region            = "eu-north1"
    etcd_cluster_size = 1
  }
}

run "k8s_node_groups_training_kuberay_apply" {
  command = apply
  plan_options {
    target = [
      nebius_mk8s_v1_node_group.cpu-only,
      nebius_mk8s_v1_node_group.gpu
    ]
  }
  variables {
    region            = "eu-north1"
    etcd_cluster_size = 1
  }
}

run "full_training_kuberay_apply" {
  command = apply

  variables {
    region            = "eu-north1"
    etcd_cluster_size = 1
    enable_loki       = false # TODO: Disabling Loki since not possible to delete non-empty storage bucket
    enable_kuberay    = true
  }
}
