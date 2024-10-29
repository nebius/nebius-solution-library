output "name_nodeset_system" {
  description = "System nodeset name."
  value       = local.const.name.nodesets.system
}

output "name_nodeset_controller" {
  description = "Controller nodeset name."
  value       = local.const.name.nodesets.controller
}

output "name_nodeset_worker" {
  description = "Worker nodeset name."
  value       = local.const.name.nodesets.worker
}

output "name_nodeset_login" {
  description = "Login nodeset name."
  value       = local.const.name.nodesets.login
}

output "name_workload_cpu" {
  description = "CPU workload name."
  value       = local.const.name.workloads.cpu
}

output "name_workload_gpu" {
  description = "GPU workload name."
  value       = local.const.name.workloads.gpu
}

output "label_nebius_gpu" {
  description = "Nebius GPU label."
  value       = local.label.nebius_gpu
}

output "label_nodeset_system" {
  description = "System nodeset label."
  value       = local.label.nodeset.system
}

output "label_nodeset_controller" {
  description = "Controller nodeset label."
  value       = local.label.nodeset.controller
}

output "label_nodeset_worker" {
  description = "Worker nodeset label."
  value       = local.label.nodeset.worker
}

output "label_nodeset_login" {
  description = "Login nodeset label."
  value       = local.label.nodeset.login
}

output "label_workload_cpu" {
  description = "CPU workload label."
  value       = local.label.workload.cpu
}

output "label_workload_gpu" {
  description = "GPU workload label."
  value       = local.label.workload.gpu
}

# region TODO: remove

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

# endregion TODO: remove

output "key_nebius_gpu" {
  description = "Nebius GPU label key."
  value       = local.label_key.nebius_gpu
}

output "key_nvidia_gpu" {
  description = "Nvidia GPU label key."
  value       = local.label_key.nvidia_gpu
}

output "key_k8s_cluster_id" {
  description = "k8s cluster ID label key."
  value       = local.label_key.k8s_cluster_id
}

output "key_k8s_cluster_name" {
  description = "k8s cluster name label key."
  value       = local.label_key.k8s_cluster_name
}

output "key_slurm_nodeset_name" {
  description = "Slurm nodeset label key."
  value       = local.label_key.slurm_nodeset
}

output "key_slurm_workload_name" {
  description = "Slurm workload label key."
  value       = local.label_key.slurm_workload
}

# TODO: remove
output "key_slurm_node_group_name" {
  description = "Slurm node group label key."
  value       = local.label_key.slurm_group_name
}

output "key_slurm_cluster_name" {
  description = "Slurm cluster name label key."
  value       = local.label_key.slurm_cluster_name
}
