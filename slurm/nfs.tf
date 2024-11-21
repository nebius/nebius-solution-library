module "nfs-module" {
  providers = {
    nebius = nebius
  }
  count          = var.shared_fs_type == "nfs" ? 1 : 0
  source         = "../modules/nfs-server"
  parent_id      = var.parent_id
  subnet_id      = var.subnet_id
  ssh_user_name  = "storage"
  ssh_public_key = local.ssh_public_key
  nfs_ip_range   = "192.168.0.0/16"
  nfs_size       = var.fs_size
  platform       = local.master_platform
  preset         = local.master_preset
}
