resource "nebius_mk8s_v1_node_group" "nlb" {
  count = var.create_nlb ? 1 : 0

  depends_on = [
    nebius_mk8s_v1_cluster.this,
  ]

  parent_id = nebius_mk8s_v1_cluster.this.id

  name = module.labels.name_node_group_nlb
  labels = merge(
    module.labels.label_group_name_nlb
  )

  version          = var.k8s_version
  fixed_node_count = 1

  template = {
    metadata = {
      labels = module.labels.label_group_name_nlb
    }

    resources = {
      platform = "cpu-e2"
      preset   = "2vcpu-8gb"
    }

    boot_disk = {
      type       = "NETWORK_SSD"
      size_bytes = provider::units::from_gib(64)
    }

    network_interfaces = [{
      public_ip_address = {}
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

resource "nebius_vpc_v1_allocation" "this" {
  count = var.create_nlb ? 0 : 1

  depends_on = [
    nebius_mk8s_v1_cluster.this,
  ]

  parent_id = var.iam_project_id

  name = "${var.name}-${var.slurm_cluster_name}"
  labels = tomap({
    (module.labels.key_k8s_cluster_id)     = (nebius_mk8s_v1_cluster.this.id)
    (module.labels.key_k8s_cluster_name)   = (nebius_mk8s_v1_cluster.this.name)
    (module.labels.key_slurm_cluster_name) = (var.slurm_cluster_name)
  })

  ipv4_public = {
    subnet_id = var.vpc_subnet_id
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}

locals {
  # TODO: return IP for NLB as well
  login_ip = var.create_nlb ? "" : regexall("[\\d\\.]+", one(nebius_vpc_v1_allocation.this).status.details.allocated_cidr)[0]
}
