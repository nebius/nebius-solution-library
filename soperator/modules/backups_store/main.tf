resource "nebius_storage_v1_bucket" "backups_bucket" {
  parent_id = var.iam_project_id
  name      = "${var.instance_name}-backups"
}

resource "terraform_data" "cleanup_bucket" {
  count = var.cleanup_bucket_on_destroy ? 1 : 0

  triggers_replace = {
    bucket_name = nebius_storage_v1_bucket.backups_bucket.name
  }

  depends_on = [
    nebius_storage_v1_bucket.backups_bucket
  ]

  provisioner "local-exec" {
    when        = destroy
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command     = <<EOT
which aws
if [ $? != 0 ]; then
  echo "AWS cli not found, skipping"
  exit 0
fi

aws s3 rm s3://${self.triggers_replace.bucket_name}/ --recursive
EOT
  }
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
