variable "cluster_id" {
  description = "K8s cluster id."
  type        = string
}

variable "parent_id" {
  description = "Project id."
  type        = string
}

variable "product_slug" {
  description = "Marketplace product slug."
  type        = string
  default     = "nebius/nvidia-gpu-operator"
}

variable "driver_version" {
  description = "Enable Node Feature Discovery."
  type        = string
  default     = "550.54.15"
}
