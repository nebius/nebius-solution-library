resource "helm_release" "prometheus" {
  count            = var.o11y.prometheus.enabled ? 1 : 0
  repository       = "https://prometheus-community.github.io/helm-charts"
  name             = "prometheus"
  chart            = "prometheus"
  namespace        = var.namespace
  create_namespace = true
  version          = "v19.7.2"
  atomic           = true
  values = [
    templatefile("${path.module}/files/prometheus-values.yaml.tftpl", {
      prometheus_node_exporter = var.o11y.prometheus.node_exporter
      }
    )
  ]
}
