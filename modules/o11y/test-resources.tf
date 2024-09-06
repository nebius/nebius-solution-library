locals {
  resources = {
    grafana                             = var.o11y.grafana.enabled ? { kind = "Deployment" } : null
    prometheus-server                   = var.o11y.prometheus.enabled ? { kind = "Deployment" } : null
    prometheus-prometheus-node-exporter = var.o11y.prometheus.enabled ? { kind = "DaemonSet" } : null
    promtail                            = var.o11y.loki.enabled ? { kind = "DaemonSet" } : null
  }
}

data "kubernetes_resource" "o11y" {
  depends_on = [
    helm_release.grafana,
    helm_release.loki,
    helm_release.prometheus,
  ]

  for_each = var.test_mode ? { for key, resource in local.resources : key => resource if resource != null } : {}

  api_version = "apps/v1"
  kind        = each.value.kind
  metadata {
    name      = each.key
    namespace = var.namespace
  }
}
