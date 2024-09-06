resource "helm_release" "promtail" {
  count            = var.o11y.loki.enabled ? 1 : 0
  repository       = "https://grafana.github.io/helm-charts"
  name             = "promtail"
  chart            = "promtail"
  namespace        = var.namespace
  create_namespace = true
  version          = "v6.7.4"
  atomic           = true
  values = [
    file("${path.module}/files/promtail.yaml")
  ]
}
