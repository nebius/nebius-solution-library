# K8s cluster
variable "parent_id" {
  description = "Project ID."
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID."
  type        = string
}

variable "k8s_version" {
  description = "Kubernetes version to be used in the cluster."
  type        = string
  default     = "1.30"
}

variable "etcd_cluster_size" {
  description = "Size of etcd cluster. "
  type        = number
  default     = 3
}

# K8s filestore
variable "enable_filestore" {
  description = "Use Filestore."
  type        = bool
  default     = false
}

variable "filestore_disk_type" {
  description = "Filestore disk size in bytes."
  type        = string
  default     = "NETWORK_SSD"
}

variable "filestore_disk_size" {
  description = "Filestore disk size in bytes."
  type        = number
  default     = 1073741824
}

variable "filestore_block_size" {
  description = "Filestore block size in bytes."
  type        = number
  default     = 4096
}

# GlusterFS
variable "enable_glusterfs" {
  description = "Use GlusterFS."
  type        = bool
  default     = false
}

variable "glusterfs_storage_nodes" {
  type        = number
  default     = 3
  description = "Number of storage nodes."
}

variable "glusterfs_disk_count_per_vm" {
  type        = number
  default     = 2
  description = "Number disks for GlusterFS per VM"
}

variable "glusterfs_disk_type" {
  type        = string
  default     = "NETWORK_SSD"
  description = "Type of GlusterFS disk."
}

variable "glusterfs_disk_size" {
  type        = number
  default     = 107374182400 # 100 GB
  description = "Disk size bytes."
}

variable "glusterfs_disk_block_size" {
  type        = number
  default     = 4096
  description = "Disk block size."
}


# K8s access
variable "ssh_user_name" {
  description = "SSH username."
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key" {
  description = "SSH Public Key to access the cluster nodes"
  type        = object({
    key  = optional(string),
    path = optional(string, "~/.ssh/id_rsa.pub")
  })
  default = {}
  validation {
    condition     = var.ssh_public_key.key != null || fileexists(var.ssh_public_key.path)
    error_message = "SSH Public Key must be set by `key` or file `path` ${var.ssh_public_key.path}"
  }
}

# K8s CPU node group
variable "cpu_nodes_count" {
  description = "Number of nodes in the CPU-only node group."
  type        = number
  default     = 3
}

variable "cpu_nodes_platform" {
  description = "Platform for nodes in the CPU-only node group."
  type        = string
  default     = "cpu-e2"
}

variable "cpu_nodes_preset" {
  description = "CPU and RAM configuration for nodes in the CPU-only node group."
  type        = string
  default     = "16vcpu-64gb"
}

variable "cpu_disk_type" {
  description = "Disk type for nodes in the CPU-only node group."
  type        = string
  default     = "NETWORK_SSD"
}

variable "cpu_disk_size" {
  description = "Disk size (in GB) for nodes in the CPU-only node group."
  type        = string
  default     = "128"
}

# K8s GPU node group
variable "gpu_nodes_count" {
  description = "Number of nodes in the GPU node group."
  type        = number
  default     = 2
}

variable "gpu_nodes_platform" {
  description = "Platform for nodes in the GPU node group."
  type        = string
  default     = "gpu-h100-sxm"
}

variable "gpu_nodes_preset" {
  description = "Configuration for GPU amount, CPU, and RAM for nodes in the GPU node group."
  type        = string
  default     = "8gpu-128vcpu-1600gb"
}

variable "gpu_disk_type" {
  description = "Disk type for nodes in the GPU node group."
  type        = string
  default     = "NETWORK_SSD"
}

variable "gpu_disk_size" {
  description = "Disk size (in GB) for nodes in the GPU node group."
  type        = string
  default     = "1023"
}

variable "infiniband_fabric" {
  description = "Infiniband's fabric name."
  type        = string
  default     = "fabric-3"
}

variable "gpu_nodes_assign_public_ip" {
  description = "Assign public IP address to GPU nodes to make them directly accessible from the external internet."
  type        = bool
  default     = false
}

# Observability
variable "enable_grafana" {
  description = "Enable Grafana."
  type        = bool
  default     = true
}

variable "enable_loki" {
  description = "Enable Loki for logs aggregation."
  type        = bool
  default     = true
}

variable "enable_prometheus" {
  description = "Enable Prometheus for metrics collection."
  type        = bool
  default     = true
}

variable "enable_dcgm" {
  description = "Enable dcgm for GPU metrics collection."
  type        = bool
  default     = true
}

variable "loki_access_key_id" {
  type    = string
  default = null
}

variable "loki_secret_key" {
  type    = string
  default = null
}

# Helm
variable "iam_token" {
  description = "Token for Helm provider authentication. (source environment.sh)"
  type        = string
}

variable "test_mode" {
  description = "Switch between real usage and testing"
  type        = bool
  default     = false
}
