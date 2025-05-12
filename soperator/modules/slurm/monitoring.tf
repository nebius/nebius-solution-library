module "monitoring" {
  count = var.telemetry_enabled ? 1 : 0

  source = "../monitoring"

  slurm_cluster_name = var.name

  providers = {
    helm = helm
  }
}
