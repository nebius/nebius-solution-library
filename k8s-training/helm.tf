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
  source     = "../modules/gpu-operator"
  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
}

module "o11y" {
  source    = "../modules/o11y"
  parent_id = var.parent_id
  o11y = {
    grafana = {
      enabled = var.enable_grafana
      pv_size = "25Gi"
    }
    loki = {
      enabled           = var.enable_loki
      aws_access_key_id = var.loki_access_key_id
      secret_key        = var.loki_secret_key
    }
    prometheus = {
      enabled       = var.enable_prometheus
      node_exporter = var.enable_prometheus
      pv_size       = "25Gi"
    },
    dcgm = {
      enabled = var.enable_dcgm,
      node_groups = {
        node_group_name = {
          gpus              = tonumber(split("gpu-", local.gpu_nodes_preset)[0])
          instance_group_id = nebius_mk8s_v1_node_group.gpu.id
        }
      }
      pv_root_path = var.enable_filestore ? "/mnt/filestore" : "/data"
    }
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
