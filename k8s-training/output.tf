
output "kube_cluster" {
  description = "Kubernetes cluster info."
  value = {
    id        = try(nebius_mk8s_v1_cluster.k8s-cluster.id, null)
    name      = try(nebius_mk8s_v1_cluster.k8s-cluster.name, null)
    endpoints = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.endpoints
  }
}

output "grafana_password" {
  sensitive = true
  value     = module.o11y.nebius_grafana_password
}

output "grafana_service_account" {
  description = "Grafana service account information."
  sensitive   = true
  value       = module.o11y.grafana_service_account
}
output "kube_cluster_ca_certificate" {
  sensitive = true
  value     = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.auth.cluster_ca_certificate
}

output "shared-filesystem" {
  description = "Shared-filesystem."
  value       = local.shared-filesystem
}

output "filesystem_csi" {
  description = "Nebius Shared Filesystem CSI installation details."
  value = local.filesystem_csi_enabled ? {
    release_name                = nonsensitive(one(helm_release.filesystem_csi).name)
    namespace                   = nonsensitive(one(helm_release.filesystem_csi).namespace)
    status                      = nonsensitive(one(helm_release.filesystem_csi).status)
    storage_class_name          = local.filesystem_csi_storage_class_name
    default_storage_class_patch = var.filesystem_csi.make_default_storage_class
  } : null
}
