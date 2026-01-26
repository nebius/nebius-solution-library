variable "project_id" {
  description = "The parent ID for the Nebius cluster"
  type        = string
}

variable "subnet_id" {
  description = "The subnet ID for the Nebius cluster"
  type        = string
}

variable "viewers_group_id" {
  description = "The ID of the viewers group for Nebius Container Registry access"
  type        = string
}

variable "cluster_name" {
  description = "Name of the Kubernetes cluster"
  type        = string
}

variable "saturn_domain" {
  description = "Saturn Cloud domain"
  type        = string
}

variable "saturn_bucket_name" {
  description = "Saturn Cloud S3 bucket name"
  type        = string
  default     = null
}

variable "saturn_admin_email" {
  description = "Saturn Cloud admin email"
  type        = string
}

variable "saturn_customer_name" {
  description = "Saturn Cloud customer name"
  type        = string
}

variable "saturn_base_url" {
  description = "Saturn Cloud base URL"
  type        = string
}

variable "saturn_ssh_domain" {
  description = "Saturn Cloud SSH domain"
  type        = string
}

variable "saturn_bootstrap_token" {
  description = "Saturn Cloud bootstrap token"
  type        = string
  sensitive   = true
}

variable "saturn_cloud_provider" {
  description = "Saturn Cloud provider name"
  type        = string
  default     = "nebius"
}

variable "saturn_region" {
  description = "Saturn Cloud region"
  type        = string
}

variable "saturn_availability_zone" {
  description = "Saturn Cloud availability zone"
  type        = string
}

variable "saturn_image_build_node_role" {
  description = "Saturn Cloud image build node role"
  type        = string
}

variable "iam_token" {
  description = "IAM token for Kubernetes/Helm provider authentication"
  type        = string
  sensitive   = true
}

variable "saturn_instance_config" {
  description = "Saturn Cloud instance configuration"
  type = object({
    default_cpu = string
    default_gpu = string
    sizes = list(object({
      name          = string
      cores         = number
      memory        = string
      gpu           = number
      gpu_type      = optional(string)
      hardware_type = optional(string)
      display_name  = string
      node_role     = string
      description   = optional(string)
      cloud         = optional(string)
    }))
  })
}
