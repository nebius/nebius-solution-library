module "monitoring" {
  count = var.telemetry_enabled ? 1 : 0
  depends_on = [
    helm_release.flux2_sync,
    terraform_data.wait_for_monitoring_namespace,
  ]

  source = "../monitoring"

  slurm_cluster_name = var.name

  providers = {
    helm = helm
  }
  cluster_name        = var.cluster_name
  k8s_cluster_context = var.k8s_cluster_context
  public_o11y_enabled = var.public_o11y_enabled
}
