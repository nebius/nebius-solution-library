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

variable "backups_password" {
  description = "Password to encrypt backups."
  type        = string
  sensitive   = true
}
