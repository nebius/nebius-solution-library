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

variable "manage_helm" {
  description = "Whether Terraform manages the Saturn Helm release. Set to false to manage Helm externally."
  type        = bool
  default     = true
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
# Shared filesystem (filestore)
############################

variable "enable_filestore" {
  description = "Enable Nebius shared filesystem (filestore) for ReadWriteMany storage."
  type        = bool
  default     = true
}

variable "existing_filestore" {
  description = "ID of an existing filestore to use. If empty, a new one is created when enable_filestore=true."
  type        = string
  default     = ""
}

variable "filestore_disk_type" {
  description = "Filestore disk type."
  type        = string
  default     = "NETWORK_SSD"
}

variable "filestore_disk_size_gibibytes" {
  description = "Filestore disk size in GiB."
  type        = number
  default     = 100
}

variable "filestore_block_size_kibibytes" {
  description = "Filestore block size in KiB."
  type        = number
  default     = 4
}

variable "filestore_mount_path" {
  description = "Mount path for the shared filesystem on Kubernetes nodes."
  type        = string
  default     = "/mnt/data"
}

variable "filesystem_csi" {
  description = "Configuration for the Nebius Shared Filesystem CSI driver."
  type = object({
    chart_version = optional(string, "0.1.5")
    namespace     = optional(string, "kube-system")
  })
  default = {}
}

variable "ssh_public_key" {
  description = "SSH public key for node access (needed for cloud-init when filestore is enabled)."
  type = object({
    key  = optional(string)
    path = optional(string, "~/.ssh/id_rsa.pub")
  })
  default = {}
}

############################
# Node pool configuration
############################

variable "extra_instance_sizes" {
  description = "Additional instance sizes to show in Saturn UI that don't correspond to real node pools (e.g. coming-soon entries)."
  type = list(object({
    name            = string
    display_name    = string
    cores           = number
    memory          = string
    gpu             = number
    gpu_type        = optional(string)
    hardware_type   = optional(string)
    disabled        = optional(bool, false)
    disabled_reason = optional(string)
  }))
  default = []
}

variable "node_pools" {
  description = "List of node pools to create. Each pool becomes a node group and an instance config entry."
  type = list(object({
    platform          = string
    preset            = string
    min_nodes         = optional(number, 0)
    max_nodes         = optional(number, 10)
    boot_disk_gb      = optional(number, 372)
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
