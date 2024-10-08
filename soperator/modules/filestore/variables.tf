variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "k8s_cluster_name" {
  description = "Name of the k8s cluster."
  type        = string
}

#---

variable "controller_spool" {
  description = "Filestore for Slurm controller's spool."
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
      var.controller_spool.existing != null && var.controller_spool.spec == null
    ) || (var.controller_spool.existing == null && var.controller_spool.spec != null)
    error_message = "One of `existing` or `spec` must be provided."
  }
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

variable "jail_submounts" {
  description = "Filestores for jail submounts."
  type = list(object({
    name = string
    existing = optional(object({
      id = string
    }))
    spec = optional(object({
      disk_type            = string
      size_gibibytes       = number
      block_size_kibibytes = number
    }))
  }))
  default = []

  validation {
    condition = length([
      for sm in var.jail_submounts : true
      if(sm.existing != null && sm.spec == null) || (sm.existing == null && sm.spec != null)
    ]) == length(var.jail_submounts)
    error_message = "All submounts must have one of `existing` or `spec` provided."
  }
}

variable "accounting" {
  description = "Filestore for Slurm accounting database."
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
  nullable = true
  default  = null

  validation {
    condition = var.accounting != null ? (
      (var.accounting.existing != null && var.accounting.spec == null) ||
      (var.accounting.existing == null && var.accounting.spec != null)
    ) : true
    error_message = "One of `existing` or `spec` must be provided."
  }
}
