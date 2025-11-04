variable "helm_repository" {
  description = "GPU Operator Helm chart source repository."
  type        = string
  default     = "https://helm.ngc.nvidia.com/nvidia"
}

variable "helm_version" {
  description = "Version of GPU Operator Helm chart."
  type        = string
  default     = "v25.10.0"
}

variable "driver_version" {
  description = "Enable Node Feature Discovery."
  type        = string
  default     = "580.95.05"
}

variable "nfd_enabled" {
  description = "Enable Node Feature Discovery."
  type        = bool
  default     = true
}
