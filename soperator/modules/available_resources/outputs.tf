output "this" {
  description = "Map of available node resources grouped by platform -> preset."
  value       = local.resources
}

output "k8s_ephemeral_storage_reserve" {
  value = data.units_data_size.k8s_ephemeral_storage_reserve
}
