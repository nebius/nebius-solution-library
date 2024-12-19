resource "nebius_compute_v1_instance" "nfs_server" {
  parent_id = var.parent_id
  name      = var.instance_name

  network_interfaces = [
    {
      name              = "eth0"
      subnet_id         = var.subnet_id
      ip_address        = {}
      public_ip_address = {}
    }
  ]

  resources = {
    platform = var.platform
    preset   = var.preset
  }

  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.nfs-boot-disk
  }

  secondary_disks = [
    {
      attach_mode   = "READ_WRITE"
      existing_disk = nebius_compute_v1_disk.nfs-storage-disk
    }
  ]

  cloud_init_user_data = templatefile("${path.module}/files/nfs-cloud-init.tftpl", {
    ssh_user_name  = var.ssh_user_name,
    ssh_public_key = var.ssh_public_key,
    nfs_ip_range   = var.nfs_ip_range,
    nfs_path       = var.nfs_path,
    mtu_size       = var.mtu_size
  })
}
