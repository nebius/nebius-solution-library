variable "iam_tenant_id" {
  description = "ID of the IAM tenant."
  type        = string
}

variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "instance_name" {
  description = "Cluster instance name to distinguish between multiple clusters in tenant."
  type        = string
}

variable "k8s_cluster_context" {
  description = "K8s context name for kubectl."
  type        = string
}

variable "soperator_namespace" {
  description = "Kubernetes namespace to look for jail in."
  type        = string
}

variable "flux_namespace" {
  description = "Kubernetes namespace for flux installations."
  type        = string
}

variable "k8up_operator_namespace" {
  description = "Kubernetes namespace to install k8up operator to."
  type        = string
  default     = "k8up-system"
}

variable "backups_password" {
  description = "Password to encrypt backups."
  type        = string
  sensitive   = true
}

variable "backups_schedule" {
  description = "Cron schedule for backup jobs."
  type        = string
}

variable "prune_schedule" {
  description = "Cron schedule for prune jobs."
  type        = string
}

variable "backups_retention" {
  description = "Backup retention as in k8up Prune."
  type        = map(any)
}

variable "bucket_name" {
  description = "S3 bucket name to store backups in (created in backups_store module)."
  type        = string
}

variable "bucket_endpoint" {
  description = "S3 bucket endpoint."
  type        = string
}

variable "monitoring" {
  description = "Monitoring configuration."
  type = object({
    enabled   = bool
    namespace = string
  })
  default = {
    enabled   = false
    namespace = ""
  }
}
