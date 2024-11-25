locals {
  release-suffix = random_string.random.result
  ssh_public_key = var.ssh_public_key.key != null ? var.ssh_public_key.key : (
  fileexists(var.ssh_public_key.path) ? file(var.ssh_public_key.path) : null)

  regions_default = {
    eu-west1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h200-sxm"
      gpu_nodes_preset   = "1gpu-16vcpu-200gb"
    }
    eu-north1 = {
      cpu_nodes_platform = "cpu-e2"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h100-sxm"
      gpu_nodes_preset   = "1gpu-16vcpu-200gb"
    }
  }

  current_region_defaults = local.regions_default[var.region]

  cpu_nodes_preset   = coalesce(var.cpu_nodes_preset, local.current_region_defaults.cpu_nodes_preset)
  cpu_nodes_platform = coalesce(var.cpu_nodes_platform, local.current_region_defaults.cpu_nodes_platform)
  gpu_nodes_platform = coalesce(var.gpu_nodes_platform, local.current_region_defaults.gpu_nodes_platform)
  gpu_nodes_preset   = coalesce(var.gpu_nodes_preset, local.current_region_defaults.gpu_nodes_preset)
}

resource "random_string" "random" {
  keepers = {
    ami_id = "${var.parent_id}"
  }
  length  = 6
  upper   = true
  lower   = true
  numeric = true
  special = false
}
