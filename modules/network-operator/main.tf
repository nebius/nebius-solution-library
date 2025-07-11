resource "nebius_applications_v1alpha1_k8s_release" "this" {
  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "network-operator"
  namespace        = "network-operator"
  product_slug     = "nebius/nvidia-network-operator"

  set = {
    "operator.resources.limits.cpu" : var.limit_cpu,
    "operator.resources.limits.memory" : var.limit_memory,
    "operator.ofedDriver.livenessProbe.enabled" : false
  }
}
