locals {
  release-suffix = random_string.random.result
  ssh_public_key = var.ssh_public_key.key != null ? var.ssh_public_key.key : (
  fileexists(var.ssh_public_key.path) ? file(var.ssh_public_key.path) : null)

  regions_default = {
    eu-west1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h200-sxm"
      gpu_nodes_preset   = "8gpu-128vcpu-1600gb"
      infiniband_fabric  = "fabric-5"
    }
    eu-north1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h100-sxm"
      gpu_nodes_preset   = "8gpu-128vcpu-1600gb"
      infiniband_fabric  = "fabric-3"
    }
  }

  current_region_defaults = local.regions_default[var.region]

  cpu_nodes_preset   = coalesce(var.cpu_nodes_preset, local.current_region_defaults.cpu_nodes_preset)
  cpu_nodes_platform = coalesce(var.cpu_nodes_platform, local.current_region_defaults.cpu_nodes_platform)
  gpu_nodes_platform = coalesce(var.gpu_nodes_platform, local.current_region_defaults.gpu_nodes_platform)
  gpu_nodes_preset   = coalesce(var.gpu_nodes_preset, local.current_region_defaults.gpu_nodes_preset)
  infiniband_fabric  = coalesce(var.infiniband_fabric, local.current_region_defaults.infiniband_fabric)

  valid_mig_parted_configs = {
    "gpu-h100-sxm" = ["all-disabled", "all-enabled", "all-balanced", "all-1g.10gb", "all-1g.10gb.me", "all-1g.20gb", "all-2g.20gb", "all-3g.40gb", "all-4g.40gb", "all-7g.80gb"]
    "gpu-h200-sxm" = ["all-disabled", "all-enabled", "all-balanced", "all-1g.18gb", "all-1g.18gb.me", "all-1g.35gb", "all-2g.35gb", "all-3g.71gb", "all-4g.71gb", "all-7g.141gb"]
  }
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
