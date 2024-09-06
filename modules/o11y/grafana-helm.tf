resource "helm_release" "grafana" {
  depends_on       = [helm_release.utility-storage]
  count            = var.o11y.grafana.enabled ? 1 : 0
  repository       = "https://grafana.github.io/helm-charts"
  name             = "grafana"
  chart            = "grafana"
  namespace        = var.namespace
  create_namespace = true
  version          = "v8.0.2"
  atomic           = true

  values = [
    templatefile(
      "${path.module}/files/grafana-values.yaml.tftpl", {
        alert_rules = templatefile("${path.module}/files/grafana-alert-rules.yaml.tftpl", {
          dcgm_node_groups = var.o11y.dcgm.node_groups
        })
        loki                     = var.o11y.loki.enabled
        prometheus               = var.o11y.prometheus.enabled
        prometheus_node_exporter = var.o11y.prometheus.node_exporter
        dcgm_enabled             = var.o11y.dcgm.enabled
      }
    )
  ]
}
