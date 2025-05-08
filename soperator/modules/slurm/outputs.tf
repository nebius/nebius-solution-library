output "monitoring" {
  description = "Monitoring metadata."
  value = var.telemetry_enabled ? {
    namespace = local.namespace
    } : {
    namespace = null
  }
}
