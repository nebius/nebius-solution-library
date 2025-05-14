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
    slurm_exporter         = "exporter"
    kube_state_metrics     = "kube-state-metrics"
    pod_resources          = "pod-resources"
    workers_overview       = "workers-overview"
    workers_detailed_stats = "workers-detailed-stats"
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
