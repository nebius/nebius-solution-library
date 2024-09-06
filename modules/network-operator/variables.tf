variable "helm_repository" {
  description = "Network Operator Helm chart source repository."
  type        = string
  default     = "oci://cr.nemax.nebius.cloud/yc-marketplace/nebius/elijahk-nvidia-network-operator/chart"
}

variable "helm_version" {
  description = "Version of Network Operator Helm chart."
  type        = string
  default     = "24.4.0"
}

variable "limit_cpu" {
  description = "CPU limit for the Network Operator"
  type        = string
  default     = "500m"
}

variable "limit_memory" {
  description = "Memory limit for the Network Operator"
  type        = string
  default     = "1280Mi"
}
