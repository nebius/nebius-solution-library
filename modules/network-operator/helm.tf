resource "nebius_applications_v1alpha1_k8s_release" "network-operator" {
  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "network-operator"
  namespace        = "network-operator"
  product_slug     = var.product_slug

  #  set = {
  #    "operator.resources.limits.cpu" : var.limit_cpu,
  #    "operator.resources.limits.memory" : var.limit_memory
  #  }
  values = <<EOT
  operator:
    resources:
      limits:
        cpu: ${var.limit_cpu}
        memory: ${var.limit_memory}
  EOT
}
