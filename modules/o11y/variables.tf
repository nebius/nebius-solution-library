# Kubernetes Master parameters
variable "parent_id" {
  description = "The ID of the folder that the Kubernetes cluster belongs to."
  type        = string
}

variable "namespace" {
  type    = string
  default = "o11y"
}

variable "o11y" {
  type = object({
    grafana = optional(object({
      enabled = optional(bool, true)
      pv_size = optional(string, "25Gi")
    })),
    loki = optional(object({
      enabled           = optional(bool, true)
      aws_access_key_id = string
      secret_key        = string
    })),
    prometheus = optional(object({
      enabled       = optional(bool, true)
      node_exporter = optional(bool, true)
      pv_size       = optional(string, "25Gi")
    }), {})
    dcgm = optional(object({
      enabled = optional(bool, true)
      node_groups = optional(map(object({
        gpus              = number
        instance_group_id = string
      })), {})
    }), {})
    pv_root_path = optional(string, "/mnt/filestore")
  })
  description = "Configuration of observability stack."
  default     = {}
}

variable "test_mode" {
  description = "Switch between real usage and testing"
  type        = bool
  default     = false
}
