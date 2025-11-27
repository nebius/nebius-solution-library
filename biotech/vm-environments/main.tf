resource "nebius_compute_v1_gpu_cluster" "gpu-cluster" {
  count             = var.fabric != "" ? 1 : 0 # Create the resource only if fabric is set
  infiniband_fabric = var.fabric
  parent_id         = var.parent_id
  name              = join("-", [var.fabric, "cluster"])
}

resource "nebius_storage_v1_bucket" "bucket" {
  parent_id = var.parent_id
  count = local.effective_bucket_count
  name = "hackathon-team-${count.index + 1}"
  max_size_bytes = 1024 * 1024 * 1024 * 1024 * 5
  default_storage_class = "ENHANCED_THROUGHPUT"
}

resource "nebius_iam_v1_service_account" "bucket_sa" {
  parent_id = var.parent_id
  count = local.effective_bucket_count
  name = "hackathon-team-${count.index + 1}-sa"
}

resource "nebius_iam_v1_group" "bucket_group" {
  parent_id = var.parent_id
  count = local.effective_bucket_count
  name = "hackathon-team-${count.index + 1}-group"
}

resource "nebius_iam_v1_access_permit" "access_permit" {
  parent_id = nebius_iam_v1_group.bucket_group[count.index].id
  count = local.effective_bucket_count
  resource_id = nebius_storage_v1_bucket.bucket[count.index].id
  role = "editor"
}

resource "nebius_iam_v2_access_key" "access_key" {
  parent_id = var.parent_id
  count = local.effective_bucket_count
  account = {
    service_account = {
      id = nebius_iam_v1_service_account.bucket_sa[count.index].id
    }
  }
}

resource "nebius_iam_v1_group_membership" "group_membership" {
  parent_id = nebius_iam_v1_group.bucket_group[count.index].id
  count = local.effective_bucket_count
  member_id = nebius_iam_v1_service_account.bucket_sa[count.index].id
}

module "instance-module" {
  source                  = "../../modules/instance"
  parent_id               = var.parent_id
  subnet_id               = var.subnet_id
  count                   = var.instance_count
  gpu_cluster             = var.fabric != "" ? nebius_compute_v1_gpu_cluster.gpu-cluster[0].id : ""
  instance_name           = "hackathon-team-${count.index + 1}"
  users                   = var.users
  preset                  = var.preset
  platform                = var.platform
  boot_disk_size_gb       = var.boot_disk_size_gb
  shared_filesystem_id    = var.shared_filesystem_id
  shared_filesystem_mount = var.shared_filesystem_mount
  extra_path              = var.extra_path
  add_extra_storage       = var.add_extra_storage
  extra_storage_size_gb   = var.extra_storage_size_gb
  extra_storage_class     = var.extra_storage_class
  public_ip               = var.public_ip
  mount_bucket            = nebius_storage_v1_bucket.bucket[count.index].name
  s3_mount_path           = var.s3_mount_path
  aws_access_key_id       = nebius_iam_v2_access_key.access_key[count.index].status.aws_access_key_id
  aws_secret_access_key   = nebius_iam_v2_access_key.access_key[count.index].status.secret
  install_helical         = var.install_helical
  install_bionemo         = var.install_bionemo
}
