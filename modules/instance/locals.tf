locals {
  ssh_public_key = var.ssh_public_key.key != null ? var.ssh_public_key.key : (
  fileexists(var.ssh_public_key.path) ? file(var.ssh_public_key.path) : null)

  ssh_public_key_2 = var.ssh_public_key_2.key != null ? var.ssh_public_key_2.key : (
  fileexists(var.ssh_public_key_2.path) ? file(var.ssh_public_key_2.path) : null)

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

  # cpu_nodes_preset   = coalesce(var.cpu_nodes_preset, local.current_region_defaults.cpu_nodes_preset)
  # cpu_nodes_platform = coalesce(var.cpu_nodes_platform, local.current_region_defaults.cpu_nodes_platform)
  # gpu_nodes_platform = coalesce(var.gpu_nodes_platform, local.current_region_defaults.gpu_nodes_platform)
  # gpu_nodes_preset   = coalesce(var.gpu_nodes_preset, local.current_region_defaults.gpu_nodes_preset)

  nfs_path       = var.nfs_path
  nfs_disk_id    = var.add_nfs_storage ? substr(nebius_compute_v1_disk.nfs-storage-disk[0].id, 0, 20) : ""


  cloud_init_log = jsonencode({
    ssh_user_name  = var.ssh_user_name
    ssh_public_key = local.ssh_public_key
    nfs_path       = local.nfs_path
    nfs_disk_id    = local.nfs_disk_id
    state         = terraform.workspace
  })
  # current_region_defaults = local.regions_default[var.region]
  #
  # cpu_nodes_preset   = coalesce(var.cpu_nodes_preset, local.current_region_defaults.cpu_nodes_preset)
  # cpu_nodes_platform = coalesce(var.cpu_nodes_platform, local.current_region_defaults.cpu_nodes_platform)
}
