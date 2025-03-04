resource "nebius_compute_v1_disk" "nfs-boot-disk" {
  parent_id           = var.parent_id
  name                = var.nfs_disk_name_suffix == "" ? "nfs-boot-disk" : format("nfs-boot-disk-%s", var.nfs_disk_name_suffix)
  block_size_bytes    = 4096
  size_bytes          = 64424509440
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-driverless" }
}

resource "nebius_compute_v1_disk" "nfs-storage-disk" {
  parent_id        = var.parent_id
  name             = var.nfs_disk_name_suffix == "" ? "nfs-storage-disk" : format("nfs-storage-disk-%s", var.nfs_disk_name_suffix)
  block_size_bytes = var.disk_block_size
  size_bytes       = var.nfs_size
  type             = var.disk_type
}
