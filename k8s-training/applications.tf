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

  parent_id        = var.parent_id
  cluster_id       = nebius_mk8s_v1_cluster.k8s-cluster.id
  gpu_platform     = var.gpu_nodes_platform
  cpu_platform     = var.cpu_nodes_platform
  min_gpu_replicas = var.kuberay_min_gpu_replicas
  max_gpu_replicas = var.kuberay_max_gpu_replicas
}
