resource "nebius_compute_v1_disk" "nfs-boot-disk" {
  parent_id           = var.parent_id
  name                = var.nfs_disk_name_suffix == "" ? "nfs-boot-disk" : format("nfs-boot-disk-%s", var.nfs_disk_name_suffix)
  block_size_bytes    = 4096
  size_bytes          = 60 * 1024 * 1024 * 1024 # 60 GiB
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-driverless" }
}

resource "nebius_compute_v1_disk" "nfs-storage-disk" {
  count = var.number_raid_disks

  parent_id = var.parent_id
  name      = format("nfs-storage-disk-%s-%02d", var.nfs_disk_name_suffix, count.index + 1)

  block_size_bytes = var.disk_block_size
  size_bytes       = var.nfs_size
  type             = var.disk_type
}
