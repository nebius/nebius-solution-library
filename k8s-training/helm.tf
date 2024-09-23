module "network-operator" {
  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
    nebius_mk8s_v1_node_group.gpu,
  ]
  source = "../modules/network-operator"
}

module "gpu-operator" {
  depends_on = [
    module.network-operator
  ]
  source      = "../modules/gpu-operator"
  nfd_enabled = false
}

## FIXME o11y is not working yet, because buckets and S3 keys are not yet implemented in the public tf provider
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
          gpus              = tonumber(split("gpu-", var.gpu_nodes_preset)[0])
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

module "kuberay" {
  source = "../modules/kuberay"
  count  = var.enable_kuberay ? 1 : 0

  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
    nebius_mk8s_v1_node_group.gpu,
    module.network-operator,
    module.gpu-operator,
    module.csi-mounted-fs-path,
  ]

  gpu_platform     = var.gpu_nodes_platform
  cpu_platform     = var.cpu_nodes_platform
  min_gpu_replicas = var.kuberay_min_gpu_replicas
  max_gpu_replicas = var.kuberay_max_gpu_replicas
}


module "csi-mounted-fs-path" {
  source = "../modules/csi-mounted-fs-path"
  count  = var.enable_filestore ? 1 : 0

}
