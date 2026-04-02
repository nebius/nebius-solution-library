locals {
  # Derived URLs from saturn_domain
  saturn_base_url   = "https://app.${var.saturn_domain}"
  saturn_ssh_domain = "ssh.${var.saturn_domain}"

  # Hardcoded constants
  saturn_cloud_provider        = "nebius"
  saturn_image_build_node_role = "cpu-d3-4vcpu-16gb"

  # Build a node group key for each pool (used as for_each keys and node_role names)
  node_pool_keys = {
    for i, pool in var.node_pools : "${pool.platform}-${pool.preset}${pool.infiniband_fabric != null ? "-${pool.infiniband_fabric}" : ""}" => pool
  }

  # Derive unique infiniband fabrics from node pools that have fabric set
  # Keyed by "${platform}-${fabric}" to ensure one gpu_cluster per platform+fabric combo
  infiniband_fabrics = {
    for key, pool in local.node_pool_keys : "${pool.platform}-${pool.infiniband_fabric}" => pool
    if pool.infiniband_fabric != null
  }

  # Identify first CPU and first GPU pools for defaults
  cpu_pools = [for pool in var.node_pools : pool if !startswith(pool.platform, "gpu-")]
  gpu_pools = [for pool in var.node_pools : pool if startswith(pool.platform, "gpu-")]

  default_cpu_name = length(local.cpu_pools) > 0 ? "nebius-${local.cpu_pools[0].platform}-${local.cpu_pools[0].preset}" : null
  default_gpu_name = length(local.gpu_pools) > 0 ? (
    local.gpu_pools[0].infiniband_fabric != null
    ? "nebius-${local.gpu_pools[0].platform}-${local.gpu_pools[0].preset}-${local.gpu_pools[0].infiniband_fabric}"
    : "nebius-${local.gpu_pools[0].platform}-${local.gpu_pools[0].preset}"
  ) : null

  # Build saturn_instance_config dynamically from node_pools + validation map
  instance_config = {
    default_cpu = local.default_cpu_name
    default_gpu = local.default_gpu_name
    sizes = [
      for key, pool in local.node_pool_keys : {
        name          = "nebius-${key}"
        cores         = local.valid_presets["${pool.platform}/${pool.preset}"].cores
        memory        = local.valid_presets["${pool.platform}/${pool.preset}"].memory
        gpu           = local.valid_presets["${pool.platform}/${pool.preset}"].gpus
        gpu_type      = local.valid_presets["${pool.platform}/${pool.preset}"].gpu_type
        hardware_type = local.valid_presets["${pool.platform}/${pool.preset}"].hardware_type
        display_name  = key
        node_role     = key
      }
    ]
  }

  # Clean instance config by removing null values from each size object
  cleaned_instance_config = {
    default_cpu = local.instance_config.default_cpu
    default_gpu = local.instance_config.default_gpu
    sizes = [
      for size in local.instance_config.sizes : {
        for k, v in size : k => v if v != null
      }
    ]
  }
}
