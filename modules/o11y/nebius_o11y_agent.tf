resource "nebius_applications_v1alpha1_k8s_release" "nebius-observability-agent" {
  count      = var.o11y.nebius_o11y_agent.enabled ? 1 : 0
  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "nebius-observability-agent"
  namespace        = "o11y"
  product_slug     = "nebius/nebius-observability-agent"

  set = {
    "config.metrics.collectK8sClusterMetrics" : var.o11y.nebius_o11y_agent.collectK8sClusterMetrics,
  }
}
