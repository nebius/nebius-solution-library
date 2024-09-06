output "helm_release_status" {
  value = {
    grafana    = var.o11y.grafana.enabled ? helm_release.grafana[0].status : null
    loki       = var.o11y.loki.enabled ? helm_release.loki[0].status : null
    promtail   = var.o11y.loki.enabled ? helm_release.promtail[0].status : null
    prometheus = var.o11y.prometheus.enabled ? helm_release.prometheus[0].status : null
  }
}

output "k8s_apps_status" {
  value = { for key, app in data.kubernetes_resource.o11y :
    key => app.kind == "Deployment" ?
    app.object.status.availableReplicas / app.object.status.replicas :
    app.object.status.numberAvailable / app.object.status.desiredNumberScheduled
  }
}
