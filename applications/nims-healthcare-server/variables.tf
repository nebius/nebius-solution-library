variable "parent_id" {
  description = "Nebius project ID that owns the target Kubernetes cluster."
  type        = string
  default     = "project-e00z6b02t8ddk96c49"
}

variable "kube_config_path" {
  description = "Path to the kubeconfig containing the target context."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubernetes context for the target NIM server cluster."
  type        = string
  default     = "nebius-mk8s-forge-eu-e00tjerrz0axkghmbm"
}

variable "namespace" {
  description = "Namespace for NIM server workloads."
  type        = string
  default     = "nims-healthcare"
}

variable "ngc_key" {
  description = "NVIDIA NGC API key used for nvcr.io pulls and NIM runtime access."
  type        = string
  sensitive   = true
}

variable "nim_cache_host_path" {
  description = "Host path mounted into NIM pods for model cache data."
  type        = string
  default     = "/mnt/data/nim"
}

variable "enable_two_gpu_nims" {
  description = "Enable Evo2-40B and Qwen3 Next 80B. The target cluster needs nodes with at least two allocatable GPUs for these pods to schedule."
  type        = bool
  default     = true
}

variable "nim_resource_overrides" {
  description = "Per-NIM resource overrides passed through to the modules/nims resource map."
  type = map(object({
    cpu_request    = optional(string)
    cpu_limit      = optional(string)
    memory_request = optional(string)
    memory_limit   = optional(string)
    gpu            = optional(string)
    shm            = optional(string)
  }))
  default = {}
}
