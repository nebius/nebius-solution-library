
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
  value     = module.o11y.grafana_password
}
output "kube_cluster_ca_certificate" {
  sensitive = true
  value     = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.auth.cluster_ca_certificate
}
