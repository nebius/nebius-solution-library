resource "nebius_applications_v1alpha1_k8s_release" "this" {
  parent_id        = var.parent_id
  cluster_id       = var.cluster_id
  application_name = var.name
  namespace        = var.namespace
  product_slug     = "nebius/ray-cluster"
  values = templatefile("${path.module}/files/ray-values.yaml.tftpl", {
    cpu_platform     = var.cpu_platform
    gpu_platform     = var.gpu_platform
    max_gpu_replicas = var.max_gpu_replicas
    min_gpu_replicas = var.min_gpu_replicas
  })
}
