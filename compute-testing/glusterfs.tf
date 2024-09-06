module "glusterfs" {
  source            = "../modules/gluster-module"
  parent_id         = var.parent_id
  subnet_id         = var.subnet_id
  storage_nodes     = 3
  disk_count_per_vm = 3
  disk_size         = 26843545600
  ssh_public_key    = local.ssh_public_key
}
