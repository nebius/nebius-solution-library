resource "helm_release" "certificate_manager" {
  name       = "cert-manager"
  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = "v1.16.2"

  create_namespace = true
  namespace        = "cert-manager"

  set {
    name  = "installCRDs"
    value = true
  }
  set {
    name  = "prometheus.enabled"
    value = false
  }

  wait = true
}
