locals {
  namespace = {
    monitoring = "monitoring-system"
  }

  repository = {
    raw = {
      repository = "https://bedag.github.io/helm-charts/"
      chart      = "raw"
      version    = "2.0.0"
    }
  }

}
resource "helm_release" "dashboard" {
  for_each = tomap({
    gpu_metrics        = "gpu-metrics"
    slurm_exporter     = "exporter"
    kube_state_metrics = "kube-state-metrics"
    node_exporter      = "node-exporter"
    pod_resources      = "pod-resources"
  })

  name       = "${var.slurm_cluster_name}-grafana-dashboard-${each.value}"
  repository = local.repository.raw.repository
  chart      = local.repository.raw.chart
  version    = local.repository.raw.version

  namespace = local.namespace.monitoring

  values = [templatefile("${path.module}/templates/dashboards/${each.key}.yaml.tftpl", {
    namespace = local.namespace.monitoring
    name      = "${var.slurm_cluster_name}-${each.value}"
    filename  = "${each.value}.json"
  })]

  wait = true
}
