# Kubernetes Master parameters
variable "tenant_id" {
  description = "Tenant ID."
  type        = string
}

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
    })),
    prometheus = optional(object({
      enabled       = optional(bool, true)
      node_exporter = optional(bool, true)
      pv_size       = optional(string, "25Gi")
    }), {})
  })
  description = "Configuration of observability stack."
  default     = {}
}

variable "test_mode" {
  description = "Switch between real usage and testing"
  type        = bool
  default     = false
}
