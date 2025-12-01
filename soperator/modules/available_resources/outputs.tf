output "regions" {
  description = "Supported regions."
  value       = [for k, v in local.regions : v]
}

output "platforms" {
  description = "Supported platforms."
  value       = [for k, v in local.platforms : v]
}

output "presets" {
  description = "Supported presets."
  value       = [for k, v in local.presets : v]
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

output "disk_types" {
  description = "Supported disk types."
  value       = local.disk_types
}

output "filesystem_types" {
  description = "Supported filesystem types."
  value       = local.filesystem_types
}

output "driver_preset_by_platform" {
  description = "Supported driver preset by platform."
  value       = local.platform_driver_presets
}

output "cpu_topology_by_platform" {
  description = "CPU topologies preset by platform."
  value       = local.cpu_topologies_by_platforms
}
