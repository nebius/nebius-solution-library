resource "helm_release" "utility-storage" {
  count            = var.o11y.grafana.enabled || var.o11y.prometheus.enabled ? 1 : 0
  name             = "utility-storage"
  chart            = "${path.module}/files/utility-storage-0.1.0.tgz"
  namespace        = var.namespace
  create_namespace = true
  atomic           = true


  set {
    name  = "root_host_path"
    value = var.o11y.pv_root_path
  }

  set {
    name  = "grafana_pv_size"
    value = var.o11y.grafana.pv_size
  }

  set {
    name  = "prometheus_pv_size"
    value = var.o11y.prometheus.pv_size
  }
}
