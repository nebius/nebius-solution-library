output "monitoring" {
  description = "Monitoring metadata."
  value = var.telemetry_enabled ? {
    namespace                  = one(module.monitoring).namespace
    metrics_collector_endpoint = one(module.monitoring).metrics_collector_endpoint
    } : {
    namespace                  = null
    metrics_collector_endpoint = null
  }
}
