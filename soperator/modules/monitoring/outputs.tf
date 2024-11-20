output "metrics_collector_endpoint" {
  description = "Metrics collector endpoint."
  value = {
    http_host = local.metrics_collector.host
    port      = local.metrics_collector.port
  }
}
