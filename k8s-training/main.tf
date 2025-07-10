
module "filestore" {
  count  = var.filestore_jail.existing == null ? 1 : 0
  source = "../modules/filestore"

  depends_on = []

  iam_project_id   = data.nebius_iam_v1_project.this.id
  k8s_cluster_name = local.k8s_cluster_name

  jail = {
    spec = var.filestore_jail.spec != null ? {
      disk_type            = "NETWORK_SSD"
      size_gibibytes       = var.filestore_jail.spec.size_gibibytes
      block_size_kibibytes = var.filestore_jail.spec.block_size_kibibytes
    } : null
    existing = var.filestore_jail.existing != null ? {
      id = var.filestore_jail.existing.id
    } : null
  }

  providers = {
    nebius = nebius
    dunits = dunits
  }
}

resource "nebius_mk8s_v1_cluster" "k8s-cluster" {
  parent_id = var.parent_id
  name      = local.k8s_cluster_name
  control_plane = {
    endpoints = {
      public_endpoint = {}
    }
    etcd_cluster_size = var.etcd_cluster_size
    subnet_id         = var.subnet_id
    version           = var.k8s_version
  }
}

data "nebius_iam_v1_group" "editors" {
  count     = var.enable_k8s_node_group_sa ? 1 : 0
  name      = "editors"
  parent_id = var.tenant_id
}

resource "nebius_iam_v1_service_account" "k8s_node_group_sa" {
  count     = var.enable_k8s_node_group_sa ? 1 : 0
  parent_id = var.parent_id
  name      = join("-", ["k8s_node_group_sa", local.release-suffix])
}

resource "nebius_iam_v1_group_membership" "k8s_node_group_sa-admin" {
  count     = var.enable_k8s_node_group_sa ? 1 : 0
  parent_id = data.nebius_iam_v1_group.editors[0].id
  member_id = nebius_iam_v1_service_account.k8s_node_group_sa[count.index].id
}

resource "nebius_mk8s_v1_node_group" "cpu-only" {
  fixed_node_count = var.cpu_nodes_count
  parent_id        = nebius_mk8s_v1_cluster.k8s-cluster.id
  name             = join("-", ["k8s-ng-cpu", local.release-suffix])
  labels = {
    "library-solution" : "k8s-training",
  }
  version = var.k8s_version
  template = {
    boot_disk = {
      size_gibibytes = var.cpu_disk_size
      type           = var.cpu_disk_type
    }

    service_account_id = var.enable_k8s_node_group_sa ? nebius_iam_v1_service_account.k8s_node_group_sa[0].id : null

    network_interfaces = [
      {
        public_ip_address = {}
        subnet_id         = var.subnet_id
      }
    ]
    resources = {
      platform = local.cpu_nodes_platform
      preset   = local.cpu_nodes_preset
    }
    filesystems = var.enable_filestore ? [
      {
        attach_mode         = "READ_WRITE"
        mount_tag           = "data"
        existing_filesystem = {
            id = local.filestore_jail_id
        }
      }
    ] : null
    underlay_required = false
    cloud_init_user_data = templatefile("../modules/cloud-init/k8s-cloud-init.tftpl", {
      enable_filestore = var.enable_filestore ? "true" : "false",
      ssh_user_name    = var.ssh_user_name,
      ssh_public_key   = local.ssh_public_key
    })
  }
}

resource "nebius_mk8s_v1_node_group" "gpu" {
  count            = var.gpu_node_groups
  fixed_node_count = var.gpu_nodes_count_per_group
  parent_id        = nebius_mk8s_v1_cluster.k8s-cluster.id
  name             = join("-", ["k8s-ng-gpu", local.release-suffix])
  labels = {
    "library-solution" : "k8s-training",
  }
  version = var.k8s_version
  template = {
    metadata = {
      labels = var.mig_parted_config != null ? {
        "nvidia.com/mig.config" = var.mig_parted_config
      } : {}
    }

    boot_disk = {
      size_gibibytes = var.gpu_disk_size
      type           = var.gpu_disk_type
    }

    service_account_id = var.enable_k8s_node_group_sa ? nebius_iam_v1_service_account.k8s_node_group_sa[0].id : null

    network_interfaces = [
      {
        subnet_id         = var.subnet_id
        public_ip_address = var.gpu_nodes_assign_public_ip ? {} : null
      }
    ]
    resources = {
      platform = local.gpu_nodes_platform
      preset   = local.gpu_nodes_preset
    }
    filesystems = var.enable_filestore ? [
      {
        attach_mode         = "READ_WRITE"
        mount_tag           = "data"
        existing_filesystem = {
            id = local.filestore_jail_id
        }
      }
    ] : null
    gpu_cluster  = nebius_compute_v1_gpu_cluster.fabric_2
    gpu_settings = var.gpu_nodes_driverfull_image ? { drivers_preset = "cuda12" } : null

    underlay_required = false
    cloud_init_user_data = templatefile("../modules/cloud-init/k8s-cloud-init.tftpl", {
      enable_filestore = var.enable_filestore ? "true" : "false",
      ssh_user_name    = var.ssh_user_name,
      ssh_public_key   = local.ssh_public_key
    })
  }
}
