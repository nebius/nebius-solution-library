resource "helm_release" "network_operator" {
  name       = "network-operator"
  repository = var.helm_repository
  chart      = "network-operator"
  namespace  = "network-operator"
  atomic     = true
  timeout    = 600

  create_namespace = true
  version          = var.helm_version

  set {
    name  = "operator.resources.limits.cpu"
    value = var.limit_cpu
  }

  set {
    name  = "operator.resources.limits.memory"
    value = var.limit_memory
  }
}
