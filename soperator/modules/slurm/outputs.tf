output "monitoring" {
  description = "Monitoring metadata."
  value = var.telemetry_enabled ? {
    namespace = local.namespace
    } : {
    namespace = null
  }
}

output "debug_resources" {
  description = "resources"

  value = local.resources
}