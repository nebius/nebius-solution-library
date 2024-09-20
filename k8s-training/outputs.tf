output "kube_cluster_id" {
  description = "Kubernetes cluster ID."
  value       = try(nebius_mk8s_v1_cluster.k8s-cluster.id, null)
}

output "kube_cluster_name" {
  description = "Kubernetes cluster name."
  value       = try(nebius_mk8s_v1_cluster.k8s-cluster.name, null)
}
