variable "cluster_id" {
  description = "K8s cluster id."
  type        = string
}

variable "parent_id" {
  description = "Project id."
  type        = string
}

variable "driver_version" {
  description = "GPU driver version."
  type        = string
  default     = "550.54.15"
}

variable "enable_dcgm_service_monitor" {
  description = "Whether to enable DCGM service monitor."
  type        = bool
  default     = false
}
