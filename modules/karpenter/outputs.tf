output "service_account_id" {
  description = "Service account ID used by Karpenter-provisioned nodes"
  value       = nebius_iam_v1_service_account.karpenter-node-sa.id
}

output "cpu_nodeclass_name" {
  description = "Name of the CPU NebiusNodeClass"
  value       = "default"
}

output "gpu_nodeclass_name" {
  description = "Name of the GPU NebiusNodeClass"
  value       = "driverful-gpu"
}
