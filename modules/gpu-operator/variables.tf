variable "helm_repository" {
  description = "GPU Operator Helm chart source repository."
  type        = string
  default     = "oci://cr.nemax.nebius.cloud/yc-marketplace/nebius/nvidia-gpu-operator/chart/"
}

variable "helm_version" {
  description = "Version of GPU Operator Helm chart."
  type        = string
  default     = "v24.3.0"
}

variable "driver_version" {
  description = "Enable Node Feature Discovery."
  type        = string
  default     = "550.54.15"
}

variable "nfd_enabled" {
  description = "Enable Node Feature Discovery."
  type        = bool
  default     = true
}
