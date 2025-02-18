resource "nebius_storage_v1_bucket" "backups_bucket" {
  parent_id = var.iam_project_id
  name = "${var.instance_name}-backups"
}

output "name" {
  value = nebius_storage_v1_bucket.backups_bucket.name
}

output "endpoint" {
  value = "https://${nebius_storage_v1_bucket.backups_bucket.status.domain_name}:443"
}

output "bucket_id" {
  value = nebius_storage_v1_bucket.backups_bucket.id
}
