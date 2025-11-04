module "kuberay" {
  source = "../modules/kuberay"
  count  = var.enable_kuberay ? 1 : 0

  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
    nebius_mk8s_v1_node_group.gpu,
    module.network-operator,
    module.gpu-operator,
  ]

  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
  #cpu worker setup
  cpu_platform     = local.cpu_nodes_platform
  cpu_worker_image = var.kuberay_cpu_worker_image
  min_cpu_replicas = var.kuberay_min_cpu_replicas
  max_cpu_replicas = var.kuberay_max_cpu_replicas
  cpu_resources    = var.kuberay_cpu_resources
  #gpu worker setup
  gpu_platform     = local.gpu_nodes_platform
  gpu_worker_image = var.kuberay_gpu_worker_image
  min_gpu_replicas = var.kuberay_min_gpu_replicas
  max_gpu_replicas = var.kuberay_max_gpu_replicas
  gpu_resources    = var.kuberay_gpu_resources

}
