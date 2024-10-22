locals {
  gpu = {
    cluster = {
      create = module.resources.this[var.node_group_gpu.resource.platform][var.node_group_gpu.resource.preset].gpu_cluster_compatible
      name = join("-", [
        trimsuffix(
          substr(
            var.name,
            0,
            64 - (length(var.node_group_gpu.gpu_cluster.infiniband_fabric) + 1)
          ),
          "-"
        ),
        var.node_group_gpu.gpu_cluster.infiniband_fabric
      ])
    }
  }
}

resource "nebius_compute_v1_gpu_cluster" "this" {
  count = local.gpu.cluster.create ? 1 : 0

  parent_id = var.iam_project_id

  name = local.gpu.cluster.name

  infiniband_fabric = var.node_group_gpu.gpu_cluster.infiniband_fabric

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}

resource "nebius_mk8s_v1_node_group" "gpu" {
  depends_on = [
    nebius_mk8s_v1_cluster.this,
    nebius_compute_v1_gpu_cluster.this,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = module.labels.name_node_group_gpu
  labels = merge(
    module.labels.label_group_name_gpu
  )

  version          = var.k8s_version
  fixed_node_count = var.node_group_gpu.size

  template = {
    metadata = {
      labels = module.labels.label_group_name_gpu
    }
    taints = module.resources.this[var.node_group_gpu.resource.platform][var.node_group_gpu.resource.preset].gpus > 0 ? [{
      key    = "nvidia.com/gpu",
      value  = module.resources.this[var.node_group_gpu.resource.platform][var.node_group_gpu.resource.preset].gpus
      effect = "NO_SCHEDULE"
    }] : null

    resources = {
      platform = var.node_group_gpu.resource.platform
      preset   = var.node_group_gpu.resource.preset
    }
    gpu_cluster = local.gpu.cluster.create ? one(nebius_compute_v1_gpu_cluster.this) : null

    boot_disk = {
      type       = var.node_group_gpu.boot_disk.type
      size_bytes = provider::units::from_gib(var.node_group_gpu.boot_disk.size_gibibytes)
    }

    filesystems = concat([{
      attach_mode = "READ_WRITE"
      mount_tag   = var.filestores.jail.mount_tag
      existing_filesystem = {
        id = var.filestores.jail.id
      }
      }], [for submount in var.filestores.jail_submounts : {
      attach_mode = "READ_WRITE"
      mount_tag   = submount.mount_tag
      existing_filesystem = {
        id = submount.id
      }
    }])

    network_interfaces = [{
      public_ip_address = local.node_ssh_access.enabled ? {} : null
      subnet_id         = var.vpc_subnet_id
    }]

    cloud_init_user_data = local.node_ssh_access.enabled ? local.node_ssh_access.cloud_init_data : null
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]

    precondition {
      condition = (var.node_group_gpu.resource.platform == "cpu-e2"
        ? !contains(["2vcpu-8gb", "4vcpu-16gb"], var.node_group_gpu.resource.preset)
        : true
      )
      error_message = "Worker resource preset '${var.node_group_gpu.resource.preset}' is insufficient."
    }
  }
}
