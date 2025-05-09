module "network-operator" {
  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
    nebius_mk8s_v1_node_group.gpu,
  ]
  source     = "../modules/network-operator"
  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
}

module "gpu-operator" {
  depends_on = [
    module.network-operator
  ]
  source       = "../modules/gpu-operator"
  parent_id    = var.parent_id
  cluster_id   = nebius_mk8s_v1_cluster.k8s-cluster.id
  mig_strategy = var.mig_strategy
}

module "o11y" {
  source          = "../modules/o11y"
  parent_id       = var.parent_id
  cluster_id      = nebius_mk8s_v1_cluster.k8s-cluster.id
  cpu_nodes_count = var.cpu_nodes_count
  gpu_nodes_count = var.gpu_nodes_count

  o11y = {
    loki = {
      enabled            = var.enable_loki
      aws_access_key_id  = var.loki_access_key_id
      secret_key         = var.loki_secret_key
      replication_factor = var.loki_custom_replication_factor
      region             = var.region
    }
    prometheus = {
      enabled = var.enable_prometheus
      pv_size = "25Gi"
    },
  }
  test_mode = var.test_mode
}

module "nccl-test" {
  depends_on = [
    module.gpu-operator,
  ]

  count           = var.test_mode ? 1 : 0
  source          = "../modules/nccl-test"
  number_of_hosts = nebius_mk8s_v1_node_group.gpu.fixed_node_count
}
