############################
# Nebius-injected (infrastructure context)
############################

variable "project_id" {
  description = "The Nebius project ID"
  type        = string
}

variable "subnet_id" {
  description = "The subnet ID where the cluster will be deployed"
  type        = string
}

variable "viewers_group_id" {
  description = "The ID of the viewers group for Nebius Container Registry access"
  type        = string
}

variable "iam_token" {
  description = "IAM token for Kubernetes/Helm provider authentication"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "Nebius region (used for saturn_region and saturn_availability_zone)"
  type        = string
}

############################
# User-provided (marketplace form)
############################

variable "cluster_name" {
  description = "Name of the Kubernetes cluster"
  type        = string
}

variable "saturn_domain" {
  description = "Saturn Cloud domain (base_url and ssh_domain are derived from this)"
  type        = string
}

variable "saturn_admin_email" {
  description = "Saturn Cloud admin email"
  type        = string
}

variable "saturn_customer_name" {
  description = "Saturn Cloud customer name"
  type        = string
}

variable "saturn_bootstrap_token" {
  description = "Saturn Cloud bootstrap token"
  type        = string
  sensitive   = true
}

variable "helm_chart_version" {
  description = "Version of the saturn-helm-operator chart"
  type        = string
  default     = null
}

variable "k8s_version" {
  description = "Kubernetes version for the cluster"
  type        = string
  default     = "1.30"
}

############################
# Node pool configuration
############################

variable "node_pools" {
  description = "List of node pools to create. Each pool becomes a node group and an instance config entry."
  type = list(object({
    platform          = string
    preset            = string
    min_nodes         = optional(number, 0)
    max_nodes         = optional(number, 10)
    boot_disk_gb      = optional(number, 93)
    infiniband_fabric = optional(string)
  }))

  default = [
    # CPU sizes
    { platform = "cpu-d3", preset = "4vcpu-16gb" },
    { platform = "cpu-d3", preset = "16vcpu-64gb" },
    { platform = "cpu-d3", preset = "64vcpu-256gb" },
    # GPU - H200 1-GPU
    { platform = "gpu-h200-sxm", preset = "1gpu-16vcpu-200gb" },
  ]
}
