resource "nebius_mk8s_v1_node_group" "login" {
  depends_on = [
    nebius_mk8s_v1_cluster.this,
    terraform_data.check_resource_preset_sufficiency,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = module.labels.name_nodeset_login
  labels = merge(
    module.labels.label_nodeset_login,
    module.labels.label_workload_cpu,
    module.labels.label_jail,
  )

  fixed_node_count = var.node_group_login.size

  template = {
    metadata = {
      labels = merge(
        module.labels.label_nodeset_login,
        module.labels.label_workload_cpu,
        module.labels.label_jail,
      )
    }
    taints = [{
      key    = module.labels.key_slurm_nodeset_name,
      value  = module.labels.name_nodeset_login
      effect = "NO_SCHEDULE"
    }]

    resources = {
      platform = var.node_group_login.resource.platform
      preset   = var.node_group_login.resource.preset
    }

    boot_disk = {
      type             = var.node_group_login.boot_disk.type
      size_bytes       = provider::units::from_gib(var.node_group_login.boot_disk.size_gibibytes)
      block_size_bytes = provider::units::from_kib(var.node_group_login.boot_disk.block_size_kibibytes)
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

    network_interfaces = [
      {
        public_ip_address = local.node_ssh_access.enabled ? {} : null
        subnet_id         = var.vpc_subnet_id
      }
    ]

    cloud_init_user_data = local.node_ssh_access.enabled ? local.node_ssh_access.cloud_init_data : null
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}

resource "nebius_vpc_v1_allocation" "this" {
  parent_id = var.iam_project_id

  name = "${var.name}-static-ip"

  ipv4_public = {
    cidr      = "/32"
    subnet_id = var.vpc_subnet_id
  }
}
