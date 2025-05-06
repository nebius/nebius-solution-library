output "nebius_application_status" {
  value = {
    loki       = var.o11y.loki.enabled ? nebius_applications_v1alpha1_k8s_release.loki[0].status : null
    prometheus = var.o11y.prometheus.enabled ? nebius_applications_v1alpha1_k8s_release.prometheus[0].status : null
  }
}

output "k8s_apps_status" {
  value = { for key, app in data.kubernetes_resource.o11y :
    key => app.kind == "Deployment" ?
    app.object.status.availableReplicas / app.object.status.replicas :
    app.object.status.numberAvailable / app.object.status.desiredNumberScheduled
  }
}

output "grafana_password" {
  sensitive = true
  value     = random_password.grafana[0].result
}