module "glusterfs" {
  count             = var.enable_glusterfs ? 1 : 0
  source            = "../modules/gluster-module"
  parent_id         = var.parent_id
  subnet_id         = var.subnet_id
  storage_nodes     = var.glusterfs_storage_nodes
  disk_count_per_vm = var.glusterfs_disk_count_per_vm
  disk_size         = var.glusterfs_disk_size
  ssh_public_key    = local.ssh_public_key
  platform          = local.cpu_nodes_platform
  preset            = local.cpu_nodes_preset
}
