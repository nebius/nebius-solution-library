locals {
  cluster_workers = toset([
    for worker_num in range(1, var.cluster_workers_count + 1) : "${var.worker_name_prefix}-${worker_num}"
  ])
}

resource "nebius_vpc_v1alpha1_allocation" "worker" {
  for_each  = local.cluster_workers
  parent_id = var.parent_id
  name      = each.key
  ipv4_private = {
    subnet_id = var.subnet_id
  }
}

resource "nebius_compute_v1_disk" "worker" {
  for_each  = local.cluster_workers
  parent_id = var.parent_id
  name      = "slurm-boot-disk-worker-${each.key}"

  block_size_bytes    = 4096
  size_bytes          = 549755813888
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-cuda12" }
}

resource "nebius_compute_v1_instance" "worker" {
  for_each  = local.cluster_workers
  name      = each.key
  parent_id = var.parent_id
  resources = {
    platform = local.worker_platform
    preset   = local.worker_preset
  }
  gpu_cluster = nebius_compute_v1_gpu_cluster.gpu-cluster-slurm

  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.worker[each.key]
  }

  filesystems = var.shared_fs_type == "filesystem" ? [
    {
      attach_mode = "READ_WRITE"
      device_name = "slurm-fs"
      mount_tag   = "slurm-fs"
      existing_filesystem = {
        id = nebius_compute_v1_filesystem.slurm-fs[0].id
      }
    }
  ] : null

  cloud_init_user_data = templatefile(
    "${path.module}/files/cloud-config-worker.yaml.tftpl", {
      ENROOT_VERSION        = "3.4.1"
      SLURM_VERSION         = var.slurm_version
      is_mysql              = var.mysql_jobs_backend
      ssh_public_key        = local.ssh_public_key
      shared_fs_type        = var.shared_fs_type
      nfs_export_path       = var.shared_fs_type == "nfs" ? module.nfs-module[0].nfs_export_path : 0
      nfs_ip                = var.shared_fs_type == "nfs" ? module.nfs-module[0].nfs_server_internal_ip : 0
      worker_prefix         = var.worker_name_prefix
      cluster_workers_count = var.cluster_workers_count
      hostname              = each.key
      password              = "" #random_password.mysql.result
      master_public_key     = tls_private_key.master_key.public_key_openssh
  })

  network_interfaces = [
    {
      name      = "eth0"
      subnet_id = var.subnet_id
      ip_address : {
        allocation_id = nebius_vpc_v1alpha1_allocation.worker[each.key].id
      }
    }
  ]
}
