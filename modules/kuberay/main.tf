resource "helm_release" "kuberay-operator" {
  name             = var.kuberay_name
  repository       = var.kuberay_repository_path
  chart            = var.kuberay_chart_name
  namespace        = var.kuberay_namespace
  create_namespace = true
  version          = "1.1.0"
  atomic           = true
  values = [
    templatefile("${path.module}/helm/ray-values.yaml.tftpl", {
      cpu_platform     = var.cpu_platform
      gpu_platform     = var.gpu_platform
      max_gpu_replicas = var.max_gpu_replicas
      min_gpu_replicas = var.min_gpu_replicas
    })
  ]
}
