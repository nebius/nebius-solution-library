output "regions" {
  description = "Supported regions."
  value       = [for k, v in local.regions : v]
}

output "platforms" {
  description = "Supported platforms."
  value       = [for k, v in local.platforms : v]
}

output "platform_regions" {
  description = "Map of supported regions grouped by platform."
  value       = local.platform_regions
}

output "by_platform" {
  description = "Map of available resource presets grouped by platform."
  value       = local.presets_by_platforms
}

output "k8s_ephemeral_storage_coefficient" {
  value = local.reserve.ephemeral_storage.coefficient
}

output "k8s_ephemeral_storage_reserve" {
  value = local.reserve.ephemeral_storage.count
}
