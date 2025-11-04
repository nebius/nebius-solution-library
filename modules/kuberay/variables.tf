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
  description = "The CPU node platform"
  type        = string
}

variable "cpu_worker_image" {
  description = "Docker image to use for CPU Workers"
  type        = string
  default     = "rayproject/ray:2.46.0-py310"
  nullable    = false
}

variable "min_cpu_replicas" {
  description = "Minimum amount of kuberay CPU worker pods"
  type        = number
  default     = 0
  nullable    = false
}

variable "max_cpu_replicas" {
  description = "Minimum amount of kuberay CPU worker pods"
  type        = number
}

variable "cpu_resources" {
  description = "Amount of resources to assign to each CPU-only worker pod"
  type = object({
    cpus   = number
    memory = number
  })
  default = {
    cpus   = 2
    memory = 4 # in GiB
  }
  nullable = false
}

variable "gpu_platform" {
  description = "The GPU node platform"
  type        = string
}

variable "gpu_worker_image" {
  description = "Docker image to use for GPU workers"
  type        = string
  default     = "rayproject/ray:2.46.0-py310-gpu"
  nullable    = false
}

variable "min_gpu_replicas" {
  description = "Minimum amount of kuberay GPU worker pods"
  type        = number
  default     = 0
  nullable    = false
}

variable "max_gpu_replicas" {
  description = "Minimum amount of kuberay GPU worker pods"
  type        = number
  default     = 1
}

variable "gpu_resources" {
  description = "Amount of resources to assign to each GPU worker pod"
  type = object({
    cpus   = number
    memory = number
    gpus   = number
  })
  default = {
    cpus   = 15
    memory = 150 # in GiB
    gpus   = 1
  }
  nullable = false
}
