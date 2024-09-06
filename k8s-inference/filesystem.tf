resource "nebius_compute_v1_filesystem" "shared-filesystem" {
  count            = var.enable_filestore ? 1 : 0
  parent_id        = var.parent_id
  name             = join("-", ["filesystem-tf", local.release-suffix])
  type             = var.filestore_disk_type
  size_bytes       = var.filestore_disk_size
  block_size_bytes = var.filestore_block_size
}