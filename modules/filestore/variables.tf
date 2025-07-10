variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "k8s_cluster_name" {
  description = "Name of the k8s cluster."
  type        = string
}

variable "jail" {
  description = "Filestore for jail."
  type = object({
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      disk_type            = string
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  })
  nullable = false

  validation {
    condition = (
      var.jail.existing != null && var.jail.spec == null
    ) || (var.jail.existing == null && var.jail.spec != null)
    error_message = "One of `existing` or `spec` must be provided."
  }
}