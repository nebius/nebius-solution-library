locals {
  ssh_public_key = var.ssh_public_key.key != null ? var.ssh_public_key.key : (
  fileexists(var.ssh_public_key.path) ? file(var.ssh_public_key.path) : null)


  regions_default = {
    eu-west1 = {
      master_platform = "cpu-d3"
      master_preset   = "16vcpu-64gb"
      worker_platform = "gpu-h200-sxm"
      worker_preset   = "1gpu-16vcpu-200gb"
    }
    eu-north1 = {
      master_platform = "cpu-e2"
      master_preset   = "16vcpu-64gb"
      worker_platform = "gpu-h100-sxm"
      worker_preset   = "1gpu-16vcpu-200gb"
    }
  }

  current_region_defaults = local.regions_default[var.region]

  master_platform = coalesce(var.master_platform, local.current_region_defaults.master_platform)
  master_preset   = coalesce(var.master_preset, local.current_region_defaults.master_preset)
  worker_platform = coalesce(var.worker_platform, local.current_region_defaults.worker_platform)
  worker_preset   = coalesce(var.worker_preset, local.current_region_defaults.worker_preset)
}
