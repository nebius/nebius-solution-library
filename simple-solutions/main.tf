module "instance-module" {
  providers = {
    nebius = nebius
  }
  source         = "../modules/instance"
  parent_id      = var.parent_id
  subnet_id      = var.subnet_id
  count          = var.instance_count
  instance_name = "instance-${count.index}"
  users = var.users
  preset     = var.preset
  platform = var.platform
  boot_disk_size_gb = 500
  shared_filesystem_id = var.shared_filesystem_id
  shared_filesystem_mount = var.shared_filesystem_mount
  nfs_path = var.nfs_path
  add_nfs_storage = var.add_nfs_storage
  nfs_size_gb = var.nfs_size_gb
}
