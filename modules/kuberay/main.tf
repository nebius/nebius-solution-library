resource "nebius_applications_v1alpha1_k8s_release" "this" {
  parent_id        = var.parent_id
  cluster_id       = var.cluster_id
  application_name = var.name
  namespace        = var.namespace
  product_slug     = "nebius/ray-cluster"
  values = templatefile("${path.module}/files/ray-values.yaml.tftpl", {
    cpu_platform     = var.cpu_platform
    cpu_worker_image = var.cpu_worker_image
    min_cpu_replicas = var.min_cpu_replicas
    max_cpu_replicas = var.max_cpu_replicas
    gpu_platform     = var.gpu_platform
    cpu_resources    = var.cpu_resources
    gpu_worker_image = var.gpu_worker_image
    min_gpu_replicas = var.min_gpu_replicas
    max_gpu_replicas = var.max_gpu_replicas
    gpu_resources    = var.gpu_resources
  })
}
