module "nfs-module" {
  providers = {
    nebius = nebius
  }
  source         = "../modules/nfs-server"
  parent_id      = var.parent_id
  subnet_id      = var.subnet_id
  ssh_user_name  = var.ssh_user_name
  ssh_public_key = var.ssh_public_key.key
  nfs_ip_range   = var.nfs_ip_range
  nfs_size       = var.nfs_size
}
