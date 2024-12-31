resource "nebius_vpc_v1alpha1_allocation" "master" {
  parent_id = var.parent_id
  name      = "slurm-master"
  ipv4_private = {
    subnet_id = var.subnet_id
  }
}

resource "nebius_compute_v1_disk" "master" {
  parent_id           = var.parent_id
  name                = "slurm-boot-disk-master"
  block_size_bytes    = 4096
  size_bytes          = 107374182400
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-driverless" }
}

resource "nebius_compute_v1_instance" "master" {
  name      = "slurm-master"
  parent_id = var.parent_id
  resources = {
    platform = local.master_platform
    preset   = local.master_preset
  }
  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.master
  }

  filesystems = var.shared_fs_type == "filesystem" ? [{
    attach_mode = "READ_WRITE"
    device_name = "slurm-fs"
    mount_tag   = "slurm-fs"
    existing_filesystem = {
      id = nebius_compute_v1_filesystem.slurm-fs[0].id
  } }] : null

  cloud_init_user_data = templatefile(
    "${path.module}/files/cloud-config-master.yaml.tftpl", {
      ENROOT_VERSION        = var.enroot_version
      PMIX_VERSION          = var.pmix_version
      SLURM_VERSION         = var.slurm_version
      SLURM_BINARIES        = var.slurm_binaries
      shared_fs_type        = var.shared_fs_type
      nfs_export_path       = var.shared_fs_type == "nfs" ? module.nfs-module[0].nfs_export_path : 0
      nfs_ip                = var.shared_fs_type == "nfs" ? module.nfs-module[0].nfs_server_internal_ip : 0
      is_mysql              = var.mysql_jobs_backend
      ssh_user_name         = local.ssh_user_name
      ssh_public_key        = local.ssh_public_key
      cluster_workers_count = var.cluster_workers_count
      hostname              = "slurm-master"
      password              = "" #random_password.mysql.result
      master_public_key     = tls_private_key.master_key.public_key_openssh
      master_private_key    = tls_private_key.master_key.private_key_openssh
      slurm_workers_ip = {
        for worker_name, worker in nebius_vpc_v1alpha1_allocation.worker :
        worker_name => trimsuffix(worker.status.details.allocated_cidr, "/32")
      }
      worker_prefix = var.worker_name_prefix
      ansible_role  = base64gzip(filebase64(data.archive_file.ansible_role.output_path))
  })
  network_interfaces = [
    {
      name      = "eth0"
      subnet_id = var.subnet_id
      ip_address : {
        allocation_id = nebius_vpc_v1alpha1_allocation.master.id
      }
      public_ip_address : {}
    }
  ]
}
