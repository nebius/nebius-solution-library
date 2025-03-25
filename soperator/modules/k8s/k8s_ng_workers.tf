locals {
  gpu_clusters = { for cluster in distinct([for worker in var.node_group_workers :
    {
      nodeset = worker.nodeset_index
      fabric  = worker.gpu_cluster.infiniband_fabric
    }
    if worker.gpu_cluster != null
    ]) :
    cluster.nodeset => cluster.fabric
  }
}

resource "nebius_compute_v1_gpu_cluster" "this" {
  for_each = local.gpu_clusters

  parent_id = var.iam_project_id

  name = "${var.name}-${each.key}"

  infiniband_fabric = each.value

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}

resource "nebius_mk8s_v1_node_group" "worker" {
  count = length(var.node_group_workers)

  depends_on = [
    nebius_mk8s_v1_cluster.this,
    nebius_compute_v1_gpu_cluster.this,
    terraform_data.check_resource_preset_sufficiency,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = join("-", [
    module.labels.name_nodeset_worker,
    var.node_group_workers[count.index].nodeset_index,
    var.node_group_workers[count.index].subset_index,
  ])
  labels = merge(
    tomap({
      (module.labels.key_slurm_nodeset_name) = join("-", [
        module.labels.name_nodeset_worker,
        var.node_group_workers[count.index].nodeset_index,
      ])
    }),
    local.node_group_workload_label.worker[count.index],
    module.labels.label_jail,
  )

  fixed_node_count = var.node_group_workers[count.index].size
  strategy = {
    max_unavailable = {
      percent = var.node_group_workers[count.index].max_unavailable_percent
    }
  }

  template = {
    metadata = {
      labels = merge(
        module.labels.label_jail,
        tomap({
          (module.labels.key_slurm_nodeset_name) = join("-", [
            module.labels.name_nodeset_worker,
            var.node_group_workers[count.index].nodeset_index,
          ])
        }),
        local.node_group_workload_label.worker[count.index],
        (local.node_group_gpu_present.worker[count.index] ? module.labels.label_nebius_gpu : {}),
      )
    }
    taints = local.node_group_gpu_present.worker[count.index] ? [{
      key    = module.labels.key_nvidia_gpu,
      value  = module.resources.by_platform[var.node_group_workers[count.index].resource.platform][var.node_group_workers[count.index].resource.preset].gpus
      effect = "NO_SCHEDULE"
    }] : null

    resources = {
      platform = var.node_group_workers[count.index].resource.platform
      preset   = var.node_group_workers[count.index].resource.preset
    }
    gpu_cluster = (local.node_group_gpu_cluster_compatible.worker[count.index]
      ? (var.node_group_workers[count.index].gpu_cluster != null
        ? nebius_compute_v1_gpu_cluster.this[var.node_group_workers[count.index].nodeset_index]
        : null
      )
      : null
    )

    boot_disk = {
      type             = var.node_group_workers[count.index].boot_disk.type
      size_bytes       = provider::units::from_gib(var.node_group_workers[count.index].boot_disk.size_gibibytes)
      block_size_bytes = provider::units::from_kib(var.node_group_workers[count.index].boot_disk.block_size_kibibytes)
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

    cloud_init_user_data = local.node_ssh_access.enabled ? local.node_ssh_access.cloud_init_data : null
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]

    precondition {
      condition = (var.node_group_workers[count.index].resource.platform == "cpu-e2"
        ? !contains(["2vcpu-8gb", "4vcpu-16gb"], var.node_group_workers[count.index].resource.preset)
        : true
      )
      error_message = "Worker[${count.index}] resource preset '${var.node_group_workers[count.index].resource.preset}' is insufficient."
    }
  }
}
