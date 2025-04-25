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

variable "slurm_cluster_namespace" {
  description = "K8S cluster namespace of the Slurm cluster."
  type        = string
  nullable    = false
}

variable "slurm_cluster_ip" {
  description = "IP address to connect to the Slurm cluster with."
  type        = string
  nullable    = false
}

variable "num_of_login_nodes" {
  description = "Number of login nodes in the Slurm cluster."
  type        = number
  nullable    = false
}

variable "nebius_user_name" {
  description = "Name of the default created user for Nebius operations."
  type        = string
  default     = "nebius"
}
