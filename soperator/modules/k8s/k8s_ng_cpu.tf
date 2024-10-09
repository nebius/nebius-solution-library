resource "nebius_mk8s_v1_node_group" "cpu" {
  depends_on = [
    nebius_mk8s_v1_cluster.this,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = module.labels.name_node_group_cpu
  labels = merge(
    module.labels.label_group_name_cpu
  )

  version          = var.k8s_version
  fixed_node_count = var.node_group_cpu.size

  template = {
    metadata = {
      labels = module.labels.label_group_name_cpu
    }

    resources = {
      platform = var.node_group_cpu.resource.platform
      preset   = var.node_group_cpu.resource.preset
    }

    boot_disk = {
      type       = var.node_group_cpu.boot_disk.type
      size_bytes = provider::units::from_gib(var.node_group_cpu.boot_disk.size_gibibytes)
    }

    filesystems = concat([{
      attach_mode = "READ_WRITE"
      mount_tag   = var.filestores.jail.mount_tag
      existing_filesystem = {
        id = var.filestores.jail.id
      }
      }, {
      attach_mode = "READ_WRITE"
      mount_tag   = var.filestores.controller_spool.mount_tag
      existing_filesystem = {
        id = var.filestores.controller_spool.id
      }
      }], [for submount in var.filestores.jail_submounts : {
      attach_mode = "READ_WRITE"
      mount_tag   = submount.mount_tag
      existing_filesystem = {
        id = submount.id
      }
      }], var.filestores.accounting != null ? [
      {
        attach_mode = "READ_WRITE"
        mount_tag   = var.filestores.accounting.mount_tag
        existing_filesystem = {
          id = var.filestores.accounting.id
        }
      }
    ] : [])

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
  }
}
