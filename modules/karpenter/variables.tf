variable "parent_id" {
  description = "Project ID where resources will be created"
  type        = string
}

variable "tenant_id" {
  description = "Tenant ID (parent of the project)"
  type        = string
}

variable "cluster_id" {
  description = "ID of the existing MK8s cluster"
  type        = string
}

variable "cluster_name" {
  description = "Name of the cluster (used for naming resources)"
  type        = string
}

variable "subnet_id" {
  description = "VPC subnet ID for Karpenter-provisioned nodes"
  type        = string
}

variable "k8s_version" {
  description = "Kubernetes version for node image family selection"
  type        = string
  default     = "1.31"
}

variable "karpenter_version" {
  description = "Karpenter Helm chart and controller version"
  type        = string
  default     = "0.1.4"
}

variable "create_default_nodepools" {
  description = "Whether to create default CPU and GPU NodePools"
  type        = bool
  default     = true
}

variable "gpu_nodeclass_image_family" {
  description = "Image family for GPU nodes (with CUDA drivers)"
  type        = string
  default     = null
}

variable "cpu_nodeclass_image_family" {
  description = "Image family for CPU nodes"
  type        = string
  default     = null
}