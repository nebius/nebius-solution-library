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
    cluster_health         = "cluster-health"
    jobs_overview          = "jobs-overview"
    workers_overview       = "workers-overview"
    workers_detailed_stats = "workers-detailed-stats"
    nfs_server             = "nfs-server"
  })

  name       = "${var.slurm_cluster_name}-grafana-dashboard-${each.value}"
  repository = local.repository.raw.repository
  chart      = local.repository.raw.chart
  version    = local.repository.raw.version

  namespace = local.namespace.monitoring

  values = [yamlencode({
    resources = [{
      apiVersion = "v1"
      kind       = "ConfigMap"
      metadata = {
        namespace = local.namespace.monitoring
        name      = "${var.slurm_cluster_name}-${each.value}"
        labels = {
          grafana_dashboard = "1"
        }
      }
      data = {
        # sensitive() to exclude the big JSON from change output in plan/apply
        "${each.value}.json" = sensitive(file("${path.module}/templates/dashboards/${each.key}.json"))
      }
    }]
  })]

  wait = true
}
