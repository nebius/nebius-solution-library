resource "random_password" "grafana" {
  count = var.o11y.prometheus.enabled ? 1 : 0

  length           = 16
  special          = true
  upper            = true
  lower            = true
  override_special = "@#$%"
}


resource "nebius_applications_v1alpha1_k8s_release" "prometheus" {
  count = var.o11y.prometheus.enabled ? 1 : 0

  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "grafana-and-prometheus"
  namespace        = var.namespace
  product_slug     = "nebius/grafana-and-prometheus"

  set = {
    "prometheus.alertmanager.enabled" : false,
    "prometheus.prometheus-pushgateway.enabled" : false,
    "prometheus.prometheus-node-exporter.enabled" : var.o11y.prometheus.node_exporter,
    "grafana.adminPassword" : random_password.grafana[0].result,
    "prometheus.server.scrape_interval" : "1m",
    "prometheus.server.retention" : "15d",
    "prometheus.server.persistentVolume.size" : var.o11y.prometheus.pv_size
  }
}

resource "time_static" "restarted_at" {}

resource "kubernetes_annotations" "restart_grafana" {
  api_version = "apps/v1"
  kind        = "Deployment"
  metadata {
    name      = "grafana-and-prometheus"
    namespace = var.namespace
  }
  template_annotations = {
    "kubectl.kubernetes.io/restartedAt" = time_static.restarted_at.rfc3339
  }

  depends_on = [
    nebius_applications_v1alpha1_k8s_release.prometheus
  ]
}
