resource "nebius_compute_v1_disk" "bastion-boot-disk" {
  parent_id           = var.parent_id
  name                = "bastion-boot-disk"
  block_size_bytes    = 4096
  size_bytes          = 60 * 1024 * 1024 * 1024 # 60 GiB
  type                = "NETWORK_SSD"
  source_image_family = { image_family = "ubuntu24.04-driverless" }
}

