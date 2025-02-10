variable "k8s_cluster_context" {
  description = "Context name of the K8s cluster."
  type        = string
  nullable    = false
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
