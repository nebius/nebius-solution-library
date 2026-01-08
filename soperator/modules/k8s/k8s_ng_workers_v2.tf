locals {
  # GPU clusters for v2 worker nodes (when nodesets are enabled)
  gpu_clusters_v2 = var.slurm_nodesets_enabled ? {
    for gpu_placement in distinct([for worker in var.node_group_workers_v2 :
      {
        fabric = worker.gpu_cluster.infiniband_fabric
      }
      if worker.gpu_cluster != null
    ]) :
    gpu_placement.fabric => {
      fabric = gpu_placement.fabric
    }
  } : {}
  gpu_clusters_by_nodegroup = var.slurm_nodesets_enabled ? {
    for ng in distinct([for worker in var.node_group_workers_v2 :
      {
        name   = worker.name
        fabric = worker.gpu_cluster.infiniband_fabric
      }
      if worker.gpu_cluster != null
    ]) :
    ng.name => ng.fabric
  } : {}
}

resource "nebius_compute_v1_gpu_cluster" "this_v2" {
  for_each = local.gpu_clusters_v2

  parent_id = var.iam_project_id

  name = "${var.name}-${each.value.fabric}"

  infiniband_fabric = each.value.fabric

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}

resource "nebius_mk8s_v1_node_group" "worker_v2" {
  count = var.slurm_nodesets_enabled ? length(var.node_group_workers_v2) : 0

  depends_on = [
    nebius_mk8s_v1_cluster.this,
    nebius_compute_v1_gpu_cluster.this,
    terraform_data.check_resource_preset_sufficiency,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = join("-", [
    var.node_group_workers_v2[count.index].name,
    var.node_group_workers_v2[count.index].subset_index,
  ])
  labels = merge(
    tomap({
      (module.labels.key_slurm_nodeset_name) = var.node_group_workers_v2[count.index].name
    }),
    local.node_group_workload_label_v2.worker[count.index],
    module.labels.label_jail,
  )

  autoscaling = var.node_group_workers_v2[count.index].autoscaling ? {
    min_node_count = var.node_group_workers_v2[count.index].min_size
    max_node_count = var.node_group_workers_v2[count.index].max_size
  } : null

  fixed_node_count = var.node_group_workers_v2[count.index].autoscaling ? null : var.node_group_workers_v2[count.index].size

  auto_repair = {
    conditions = [
      {
        type     = "NebiusBootDiskIOError"
        status   = "TRUE"
        disabled = true
      },
      {
        type     = "NodeReady"
        status   = "UNKNOWN"
        disabled = true
      },
      {
        type    = "HardwareIssuesSuspected"
        status  = "TRUE"
        timeout = "1s"
      },
    ]
  }

  template = {
    metadata = {
      labels = merge(
        module.labels.label_jail,
        module.labels.label_nodeset_worker,
        tomap({
          (module.labels.key_slurm_nodeset_name_name) = var.node_group_workers_v2[count.index].name
        }),
        local.node_group_workload_label_v2.worker[count.index],
        (local.node_group_gpu_present_v2.worker[count.index] ? module.labels.label_nebius_gpu : {}),
        module.labels.label_exclude_from_external_lb,
      )
    }
    taints = local.node_group_gpu_present_v2.worker[count.index] ? [{
      key    = module.labels.key_nvidia_gpu,
      value  = module.resources.by_platform[var.node_group_workers_v2[count.index].resource.platform][var.node_group_workers_v2[count.index].resource.preset].gpus
      effect = "NO_SCHEDULE"
    }] : null

    resources = {
      platform = var.node_group_workers_v2[count.index].resource.platform
      preset   = var.node_group_workers_v2[count.index].resource.preset
    }
    gpu_cluster = (local.node_group_gpu_cluster_compatible_v2.worker[count.index]
      ? (var.node_group_workers_v2[count.index].gpu_cluster != null
        ? nebius_compute_v1_gpu_cluster.this_v2[local.gpu_clusters_by_nodegroup[var.node_group_workers_v2[count.index].name]]
        : null
      )
      : null
    )

    preemptible = var.node_group_workers_v2[count.index].preemptible

    gpu_settings = (var.use_preinstalled_gpu_drivers && local.node_group_gpu_present_v2.worker[count.index]) ? {
      drivers_preset = module.resources.driver_preset_by_platform[var.node_group_workers_v2[count.index].resource.platform]
    } : null

    boot_disk = {
      type             = var.node_group_workers_v2[count.index].boot_disk.type
      size_bytes       = provider::units::from_gib(var.node_group_workers_v2[count.index].boot_disk.size_gibibytes)
      block_size_bytes = provider::units::from_kib(var.node_group_workers_v2[count.index].boot_disk.block_size_kibibytes)
    }

    filesystems = concat(
      [
        {
          attach_mode = "READ_WRITE"
          mount_tag   = var.filestores.jail.mount_tag
          existing_filesystem = {
            id = var.filestores.jail.id
          }
        }
      ],
      [
        for submount in var.filestores.jail_submounts :
        {
          attach_mode = "READ_WRITE"
          mount_tag   = submount.mount_tag
          existing_filesystem = {
            id = submount.id
          }
        }
      ]
    )

    network_interfaces = [{
      public_ip_address = local.node_ssh_access.enabled ? {} : null
      subnet_id         = var.vpc_subnet_id
    }]

    os = "ubuntu24.04"

    cloud_init_user_data = local.node_group_gpu_present_v2.worker[count.index] ? (
      local.node_cloud_init.enabled ? local.node_cloud_init.cloud_init_data : null
      ) : (
      local.node_ssh_access.enabled ? local.node_cloud_init.cloud_init_data_no_nvidia : null
    )
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]

    precondition {
      condition = (var.node_group_workers_v2[count.index].resource.platform == "cpu-e2"
        ? !contains(["2vcpu-8gb", "4vcpu-16gb"], var.node_group_workers_v2[count.index].resource.preset)
        : true
      )
      error_message = "Worker[${count.index}] resource preset '${var.node_group_workers_v2[count.index].resource.preset}' is insufficient."
    }
  }
}
