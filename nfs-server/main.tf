module "nfs-module" {
  providers = {
    nebius = nebius
  }
  source            = "../modules/nfs-server"
  parent_id         = var.parent_id
  subnet_id         = var.subnet_id
  ssh_user_name     = var.ssh_user_name
  ssh_public_keys   = var.ssh_public_keys
  nfs_ip_range      = var.nfs_ip_range
  nfs_size          = var.nfs_size
  platform          = local.cpu_nodes_platform
  preset            = local.cpu_nodes_preset
  disk_type         = var.disk_type
  number_raid_disks = var.number_raid_disks
  public_ip         = var.public_ip
}
