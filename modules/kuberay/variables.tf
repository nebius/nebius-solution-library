variable "parent_id" {
  description = "Nebius project id"
  type        = string
}

variable "cluster_id" {
  description = "K8s cluster id"
  type        = string
}

variable "name" {
  description = "Application name"
  type        = string
  default     = "ray-cluster"
}

variable "namespace" {
  description = "Application namespace"
  type        = string
  default     = "ray-cluster"
}

variable "cpu_platform" {
  description = "Platform for nodes in the CPU-only node group."
  type        = string
}

variable "gpu_platform" {
  description = "Platform for nodes in the CPU-only node group."
  type        = string
}

variable "min_gpu_replicas" {
  description = "Minimum amount of kuberay gpu worker pods"
  type        = number
  default     = 0
}

variable "max_gpu_replicas" {
  description = "Minimum amount of kuberay gpu worker pods"
  type        = number
  default     = 1
}
