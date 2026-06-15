output "cluster_id" {
  description = "ID of the dedicated healthcare NIM Kubernetes cluster."
  value       = module.cluster.kube_cluster.id
}

output "cluster_name" {
  description = "Name of the dedicated healthcare NIM Kubernetes cluster."
  value       = module.cluster.kube_cluster.name
}

output "cluster_public_endpoint" {
  description = "Public Kubernetes API endpoint for the dedicated healthcare NIM cluster."
  value       = module.cluster.kube_cluster.endpoints.public_endpoint
}

output "namespace" {
  description = "Kubernetes namespace for the NIM server."
  value       = var.namespace
}

output "nims_lb_ip" {
  description = "LoadBalancer IP for healthcare/life-science NIMs."
  value       = module.nims.nims_lb_ip
}
