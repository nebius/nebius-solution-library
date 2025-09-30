variable "cluster_id" {
  description = "K8s cluster id."
  type        = string
}

variable "parent_id" {
  description = "Project id."
  type        = string
}

variable "dcgm_exporter_enabled" {
  description = "Enable or disable DCGM expoerter for nvidia-device-plugin"
  type        = bool
  default     = false
}