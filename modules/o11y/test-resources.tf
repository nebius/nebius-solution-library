locals {
  resources = {
    # grafana                             = var.o11y.prometheus.enabled ? { kind = "Deployment" } : null
    # prometheus-server                   = var.o11y.prometheus.enabled ? { kind = "Deployment" } : null
    # prometheus-prometheus-node-exporter = var.o11y.prometheus.enabled ? { kind = "DaemonSet" } : null
    promtail = var.o11y.loki.enabled ? { kind = "DaemonSet" } : null
  }
}

data "kubernetes_resource" "o11y" {
  depends_on = [
    nebius_applications_v1alpha1_k8s_release.prometheus,
    nebius_applications_v1alpha1_k8s_release.loki,
  ]

  for_each = var.test_mode ? { for key, resource in local.resources : key => resource if resource != null } : {}

  api_version = "apps/v1"
  kind        = each.value.kind
  metadata {
    name      = each.key
    namespace = var.namespace
  }
}
