resource "nebius_compute_v1_disk" "nfs-boot-disk" {
  parent_id           = var.parent_id
  name                = "nfs-boot-disk"
  block_size_bytes    = 4096
  size_bytes          = 1024 * 1024 * 1024 * 50
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-cuda12" }
}

resource "nebius_compute_v1_disk" "nfs-storage-disk" {
  count            = var.add_nfs_storage ? 1 : 0
  parent_id        = var.parent_id
  name             = "nfs-storage-disk"
  block_size_bytes = 4096
  size_bytes       = 1024 * 1024 * 1024 * var.nfs_size_gb
  type             = "NETWORK_SSD"

}


resource "nebius_compute_v1_instance" "instance" {
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

  secondary_disks = var.add_nfs_storage ? [
    {
      attach_mode   = "READ_WRITE"
      existing_disk = {
        id = nebius_compute_v1_disk.nfs-storage-disk[0].id
      }
    }
  ] : []

  cloud_init_user_data = templatefile("../modules/cloud-init/simple-setup-init.tftpl", {
    ssh_user_name  = var.ssh_user_name,
    ssh_public_key = local.ssh_public_key,
    nfs_path       = local.nfs_path,
    nfs_disk_id    = local.nfs_disk_id

  })
}

resource "local_file" "cloud_init_variables_log" {
  content  = local.cloud_init_log
  filename = "${path.module}/cloud-init-variables.log"
}
