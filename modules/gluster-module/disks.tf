locals {
  disk_device_names = [
    for disk in nebius_compute_v1_disk.glusterfs-storage-disk :
    "virtio-computedisk-${substr(disk.id, 12, 8)}"
  ]
}

resource "nebius_compute_v1_disk" "glusterfs-boot-disk" {
  parent_id           = var.parent_id
  count               = var.storage_nodes
  name                = "gluster-fs-boot-disk-${count.index}"
  block_size_bytes    = 4096
  size_bytes          = 64424509440
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu22.04-driverless" }
}

resource "nebius_compute_v1_disk" "glusterfs-storage-disk" {
  parent_id        = var.parent_id
  count            = var.disk_count_per_vm * var.storage_nodes
  name             = "gluster-fs-storage-disk-${count.index}"
  block_size_bytes = var.disk_block_size
  size_bytes       = var.disk_size # 100 GB
  type             = var.disk_type
}
