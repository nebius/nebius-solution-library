module "monitoring" {
  count = var.telemetry_enabled ? 1 : 0

  source = "../monitoring"

  slurm_cluster_name = var.name

  grafana_admin_password = var.telemetry_grafana_admin_password

  providers = {
    helm = helm
  }
  cluster_name = var.cluster_name
  k8s_cluster_context = var.k8s_cluster_context
  public_o11y_enabled = var.public_o11y_enabled
}
