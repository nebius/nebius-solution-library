resource "nebius_compute_v1_filesystem" "slurm-fs" {
  count            = var.shared_fs_type == "filesystem" ? 1 : 0
  parent_id        = var.parent_id
  name             = "slurm-fs"
  type             = "NETWORK_SSD"
  block_size_bytes = 4096
  size_bytes       = var.fs_size
}
