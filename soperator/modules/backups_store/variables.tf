variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "instance_name" {
  description = "Cluster instance name to distinguish between multiple clusters in tenant."
  type        = string
}

variable "cleanup_bucket_on_destroy" {
  description = "Whether to delete on destroy all backup data from bucket or not"
  type        = bool
}

