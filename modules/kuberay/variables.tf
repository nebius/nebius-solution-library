variable "folder_id" {
  description = "The ID of the folder that the Bastion should be deployed to."
  type        = string
  default     = null
  }

variable "cpu_platform" {
  description = "Platform for nodes in the CPU-only node group."
  type        = string
  default     = null
}

variable "gpu_platform" {
  description = "Platform for nodes in the CPU-only node group."
  type        = string
  default     = null
}

variable "kuberay_name" {
    description = "kuberay operator name"
    type = string
    default = "ray-cluster"
  }

variable "kuberay_repository_path" {
    description = "kuberay repository chart path"
    type = string
    default = "oci://cr.nemax.nebius.cloud/yc-marketplace/nebius/ray-cluster/chart/"
  }

variable "kuberay_chart_name" {
    description = "kuberay chart name"
    type = string
    default = "ray-cluster"
  }

variable "kuberay_namespace" {
    description = "kuberay namespace name"
    type = string
    default = "ray-cluster"
  }

variable "kuberay_create_namespace" {
    description = "kuberay boolean variable for create a new namespace from scratch or not"
    type = bool
    default = true
  }

  variable "kube_host" {
  description = "The Kubernetes API server endpoint"
  type        = string
}

variable "cluster_ca_certificate" {
  description = "The Kubernetes cluster CA certificate"
  type        = string
}

variable "kube_token" {
  description = "The Kubernetes authentication token"
  type        = string
}

variable "gpu_workers" {
  description = "Ray GPU worker nodes"
  type        = number
}