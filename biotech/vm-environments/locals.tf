locals {
  effective_bucket_count = var.custom_buckets ? var.instance_count : 0
}
