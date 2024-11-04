resource "nebius_mk8s_v1_node_group" "login" {
  depends_on = [
    nebius_mk8s_v1_cluster.this,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = "slurm-${module.labels.name_nodeset_login}"
  labels = merge(
    module.labels.label_nodeset_login,
    module.labels.label_workload_cpu,
  )

  version          = var.k8s_version
  fixed_node_count = var.node_group_login.size

  template = {
    metadata = {
      labels = merge(
        module.labels.label_nodeset_login,
        module.labels.label_workload_cpu,
      )
    }
    taints = [{
      key    = module.labels.key_slurm_nodeset_name,
      value  = module.labels.name_nodeset_login
      effect = "PREFER_NO_SCHEDULE"
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
        public_ip_address = (local.node_ssh_access.enabled || var.use_node_port) ? {} : null
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

# TODO: Use allocation for static IPs when it's ready
#
# resource "nebius_vpc_v1_allocation" "this" {
#   count = var.create_nlb ? 0 : 1
#
#   depends_on = [
#     nebius_mk8s_v1_cluster.this,
#   ]
#
#   parent_id = var.iam_project_id
#
#   name = "${var.name}-${var.slurm_cluster_name}"
#   labels = tomap({
#     (module.labels.key_k8s_cluster_id)     = (nebius_mk8s_v1_cluster.this.id)
#     (module.labels.key_k8s_cluster_name)   = (nebius_mk8s_v1_cluster.this.name)
#     (module.labels.key_slurm_cluster_name) = (var.slurm_cluster_name)
#   })
#
#   ipv4_public = {
#     cidr = "/32"
#     subnet_id = var.vpc_subnet_id
#   }
#
#   lifecycle {
#     ignore_changes = [
#       labels,
#       ipv4_public.subnet_id,
#     ]
#   }
# }

locals {
  # allocation_id = nebius_vpc_v1_allocation.this.id
  allocation_id = null
}
