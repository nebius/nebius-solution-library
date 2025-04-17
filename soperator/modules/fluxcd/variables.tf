variable "k8s_cluster_context" {
  description = "The context of the Kubernetes cluster."
  type        = string
}

variable "flux_version" {
  description = "The version of Flux to install."
  type        = string
  default     = "v2.5.1"
}

variable "github_org" {
  description = "The GitHub organization."
  type        = string
  default     = "nebius"
}

variable "github_repository" {
  description = "The GitHub repository."
  type        = string
  default     = "soperator"
}
