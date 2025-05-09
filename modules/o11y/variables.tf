# Kubernetes Master parameters
variable "parent_id" {
  description = "The ID of the folder that the Kubernetes cluster belongs to."
  type        = string
}

variable "cluster_id" {
  description = "K8s cluster id."
  type        = string
}

variable "namespace" {
  type    = string
  default = "o11y"
}

variable "cpu_nodes_count" {
  type = number
}

variable "gpu_nodes_count" {
  type = number
}

variable "o11y" {
  type = object({
    grafana = optional(object({
      enabled = optional(bool, true)
      pv_size = optional(string, "25Gi")
    })),
    loki = optional(object({
      enabled            = optional(bool, true)
      region             = string
      replication_factor = optional(number)
      aws_access_key_id  = string
      secret_key         = string
    })),
    prometheus = optional(object({
      enabled       = optional(bool, true)
      node_exporter = optional(bool, true)
      pv_size       = optional(string, "25Gi")
    }), {})
  })
  description = "Configuration of observability stack."
  default     = {}

  validation {
    condition     = var.o11y.loki.enabled ? (var.o11y.loki.aws_access_key_id != "" && var.o11y.loki.secret_key != "") : true
    error_message = "aws_access_key_id and secret_key must be set if Loki enabled ${jsonencode(var.o11y.loki)}"
  }
}

variable "test_mode" {
  description = "Switch between real usage and testing"
  type        = bool
  default     = false
}
