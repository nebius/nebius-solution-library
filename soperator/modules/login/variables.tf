variable "node_port" {
  description = "NodePort service configuration."
  type = object({
    used = bool
    port = number
  })
}

variable "slurm_cluster_name" {
  description = "Name of the Slurm cluster in k8s cluster."
  type        = string
  nullable    = false
}

variable "script_name" {
  description = "Name of the script file."
  type        = string
  default     = "login"
}
