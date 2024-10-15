resource "nebius_compute_v1_disk" "nfs-boot-disk" {
  parent_id           = var.parent_id
  name                = "nfs-boot-disk"
  block_size_bytes    = 4096
  size_bytes          = 64424509440
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-driverless" }
}

resource "nebius_compute_v1_disk" "nfs-storage-disk" {
  parent_id        = var.parent_id
  name             = "nfs-storage-disk"
  block_size_bytes = var.disk_block_size
  size_bytes       = var.nfs_size
  type             = var.disk_type
}
