locals {
  release-suffix = random_string.random.result
  ssh_public_key = var.ssh_public_key.key != null ? var.ssh_public_key.key : (
  fileexists(var.ssh_public_key.path) ? file(var.ssh_public_key.path) : null)

  filestore = {
    mount_tag  = "data"
    mount_path = var.filestore_mount_path
  }

  filesystem_csi_chart_name          = "csi-mounted-fs-path"
  filesystem_csi_storage_class_name  = "csi-mounted-fs-path-sc"
  filesystem_csi_enabled             = local.shared-filesystem != null
  filesystem_csi_data_dir            = "${trimsuffix(local.filestore.mount_path, "/")}/csi-mounted-fs-path-data/"
  filesystem_csi_previous_default_sc = var.filesystem_csi.previous_default_storage_class_name

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
    eu-north2 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h200-sxm"
      gpu_nodes_preset   = "8gpu-128vcpu-1600gb"
      infiniband_fabric  = "eu-north2-a"
    }
    us-central1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-h200-sxm"
      gpu_nodes_preset   = "8gpu-128vcpu-1600gb"
      infiniband_fabric  = "us-central1-a"
    }
    me-west1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-b200-sxm-a"
      gpu_nodes_preset   = "8gpu-160vcpu-1792gb"
      infiniband_fabric  = "ramon"
    }
    uk-south1 = {
      cpu_nodes_platform = "cpu-d3"
      cpu_nodes_preset   = "16vcpu-64gb"
      gpu_nodes_platform = "gpu-b300-sxm"
      gpu_nodes_preset   = "8gpu-192vcpu-2768gb"
      infiniband_fabric  = "uk-south1-a"
    }
  }

  current_region_defaults = local.regions_default[var.region]

  cpu_nodes_preset   = coalesce(var.cpu_nodes_preset, local.current_region_defaults.cpu_nodes_preset)
  cpu_nodes_platform = coalesce(var.cpu_nodes_platform, local.current_region_defaults.cpu_nodes_platform)
  gpu_nodes_platform = coalesce(var.gpu_nodes_platform, local.current_region_defaults.gpu_nodes_platform)
  gpu_nodes_preset   = coalesce(var.gpu_nodes_preset, local.current_region_defaults.gpu_nodes_preset)
  infiniband_fabric  = coalesce(var.infiniband_fabric, local.current_region_defaults.infiniband_fabric)
  device_preset      = "cuda13.0"
  gpu_operator_cdi_enabled = (
    !var.gpu_nodes_driverfull_image &&
    var.mig_strategy != null &&
    var.mig_strategy != "none"
  ) ? true : null

  # Known-good kubelet NUMA/topology configs validated during GPU node testing.
  gpu_kubelet_numa_presets = {
    "h200-standard" = {
      cpu_manager_policy      = "static"
      topology_manager_policy = "restricted"
      memory_manager_policy   = "Static"
      kube_reserved_memory    = "1229Mi"
      reserved_memory = [
        {
          numa_node = 0
          memory    = "1329Mi"
        }
      ]
    }
    "b200-standard" = {
      cpu_manager_policy      = "static"
      topology_manager_policy = "restricted"
      memory_manager_policy   = "Static"
      kube_reserved_memory    = "1229Mi"
      reserved_memory = [
        {
          numa_node = 0
          memory    = "1329Mi"
        }
      ]
    }
    "b300-standard" = {
      cpu_manager_policy      = "static"
      topology_manager_policy = "restricted"
      memory_manager_policy   = "Static"
      kube_reserved_memory    = "1229Mi"
      reserved_memory = [
        {
          numa_node = 0
          memory    = "1329Mi"
        }
      ]
    }
  }

  gpu_kubelet_numa_platform_presets = {
    "gpu-h200-sxm"   = "h200-standard"
    "gpu-b200-sxm"   = "b200-standard"
    "gpu-b200-sxm-a" = "b200-standard"
    "gpu-b300-sxm"   = "b300-standard"
  }

  resolved_gpu_kubelet_numa_preset = var.gpu_kubelet_numa_preset != null ? var.gpu_kubelet_numa_preset : (
    var.enable_gpu_kubelet_numa ? lookup(
      local.gpu_kubelet_numa_platform_presets,
      local.gpu_nodes_platform,
      null
    ) : null
  )

  effective_gpu_kubelet_numa_config = var.gpu_kubelet_numa_config != null ? var.gpu_kubelet_numa_config : (
    local.resolved_gpu_kubelet_numa_preset == null ? null : local.gpu_kubelet_numa_presets[local.resolved_gpu_kubelet_numa_preset]
  )

  gpu_kubelet_numa_config_yaml = local.effective_gpu_kubelet_numa_config == null ? "" : yamlencode(
    merge(
      {
        cpuManagerPolicy      = local.effective_gpu_kubelet_numa_config.cpu_manager_policy
        topologyManagerPolicy = local.effective_gpu_kubelet_numa_config.topology_manager_policy
        memoryManagerPolicy   = local.effective_gpu_kubelet_numa_config.memory_manager_policy
        reservedMemory = [
          for item in local.effective_gpu_kubelet_numa_config.reserved_memory : {
            numaNode = item.numa_node
            limits = {
              memory = item.memory
            }
          }
        ]
      },
      local.effective_gpu_kubelet_numa_config.kube_reserved_memory == null ? {} : {
        kubeReserved = {
          memory = local.effective_gpu_kubelet_numa_config.kube_reserved_memory
        }
      }
    )
  )

  #List of official MIG configs https://docs.nvidia.com/datacenter/tesla/mig-user-guide/supported-mig-profiles.html
  valid_mig_parted_configs = {
    "gpu-h100-sxm"   = ["all-disabled", "all-enabled", "all-balanced", "all-1g.10gb", "all-1g.10gb.me", "all-1g.20gb", "all-2g.20gb", "all-3g.40gb", "all-4g.40gb", "all-7g.80gb"]
    "gpu-h200-sxm"   = ["all-disabled", "all-enabled", "all-balanced", "all-1g.18gb", "all-1g.18gb.me", "all-1g.35gb", "all-2g.35gb", "all-3g.71gb", "all-4g.71gb", "all-7g.141gb"]
    "gpu-b200-sxm"   = ["all-disabled", "all-enabled", "all-balanced", "all-1g.23gb", "all-1g.23gb.me", "all-1g.45gb", "all-2g.45gb", "all-3g.90gb", "all-4g.90gb", "all-7g.180gb"]
    "gpu-b200-sxm-a" = ["all-disabled", "all-enabled", "all-balanced", "all-1g.23gb", "all-1g.23gb.me", "all-1g.45gb", "all-2g.45gb", "all-3g.90gb", "all-4g.90gb", "all-7g.180gb"]
    "gpu-b300-sxm"   = ["all-disabled", "all-enabled", "all-balanced", "all-1g.23gb", "all-1g.23gb.me", "all-1g.45gb", "all-2g.45gb", "all-3g.90gb", "all-4g.90gb", "all-7g.180gb"]
    "gpu-rtx6000"    = ["all-disabled", "all-enabled", "all-balanced", "all-1g.24gb", "all-1g.24gb.me", "all-1g.48gb", "all-2g.48gb", "all-4g.96gb"]
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
