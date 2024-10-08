output "name_node_group_cpu" {
  description = "CPU node group name."
  value       = local.const.name.node_group.cpu
}

output "name_node_group_gpu" {
  description = "GPU node group name."
  value       = local.const.name.node_group.gpu
}

output "name_node_group_nlb" {
  description = "NLB node group name."
  value       = local.const.name.node_group.nlb
}

output "label_group_name_cpu" {
  description = "CPU node group label."
  value       = local.label.group_name.cpu
}

output "label_group_name_gpu" {
  description = "GPU node group label."
  value       = local.label.group_name.gpu
}

output "label_group_name_nlb" {
  description = "NLB node group label."
  value       = local.label.group_name.nlb
}

output "key_k8s_cluster_id" {
  description = "k8s cluster ID label key."
  value       = local.label_key.k8s_cluster_id
}

output "key_k8s_cluster_name" {
  description = "k8s cluster name label key."
  value       = local.label_key.k8s_cluster_name
}

output "key_slurm_node_group_name" {
  description = "Slurm node group label key."
  value       = local.label_key.slurm_group_name
}

output "key_slurm_cluster_name" {
  description = "Slurm cluster name label key."
  value       = local.label_key.slurm_cluster_name
}
