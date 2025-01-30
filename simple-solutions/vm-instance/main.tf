module "instance-module" {
  providers = {
    nebius = nebius
  }
  source         = "../../modules/instance"
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
  extra_path = var.extra_path
  add_extra_storage = var.add_extra_storage
  extra_storage_size_gb = var.extra_storage_size_gb
  public_ip = var.public_ip
  mount_bucket = var.mount_bucket
  s3_mount_path = var.s3_mount_path
  aws_access_key_id = var.aws_access_key_id
  aws_secret_access_key = var.aws_secret_access_key
}
