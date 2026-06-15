variable "tenant_id" {
  description = "Nebius tenant ID that owns the target project."
  type        = string
  default     = "tenant-e00f3wdfzwfjgbcyfv"
}

variable "parent_id" {
  description = "Nebius project ID where the new cluster and NIM workloads are created."
  type        = string
  default     = "project-e00z6b02t8ddk96c49"
}

variable "region" {
  description = "Nebius region for the new cluster."
  type        = string
  default     = "eu-north1"
}

variable "subnet_id" {
  description = "Subnet ID for the new cluster."
  type        = string
  default     = "vpcsubnet-e00p701fa30cj5f7wq"
}

variable "cluster_name" {
  description = "Name for the new healthcare NIM Kubernetes cluster."
  type        = string
  default     = "nims-healthcare"
}

variable "k8s_version" {
  description = "Kubernetes version for the new cluster. Leave null to use the Nebius backend default."
  type        = string
  default     = null
}

variable "etcd_cluster_size" {
  description = "Control plane etcd cluster size for the new cluster."
  type        = number
  default     = 3
}

variable "namespace" {
  description = "Namespace for NIM server workloads."
  type        = string
  default     = "nims-healthcare"
}

variable "iam_token" {
  description = "Nebius IAM token used by Terraform Kubernetes, Helm, and kubectl providers for the newly-created cluster."
  type        = string
  sensitive   = true
}

variable "ngc_key" {
  description = "NVIDIA NGC API key used for nvcr.io pulls and NIM runtime access."
  type        = string
  sensitive   = true
}

variable "ngc_key_revision" {
  description = "Revision counter for write-only Kubernetes NGC secrets. Increment when rotating ngc_key."
  type        = number
  default     = 1
}

variable "ssh_user_name" {
  description = "SSH username for cluster nodes."
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key" {
  description = "SSH public key for cluster node access."
  type = object({
    key  = optional(string)
    path = optional(string, "~/.ssh/codex_forge_ed25519.pub")
  })
  default = {}
}

variable "cpu_nodes_fixed_count" {
  description = "Number of CPU nodes in the new cluster. Default is zero because tenant non-GPU vCPU quota is exhausted; system workloads run on GPU workers."
  type        = number
  default     = 0
}

variable "gpu_nodes_fixed_count_per_group" {
  description = "Number of 8-GPU nodes in the new cluster. Two nodes provide 16 GPUs for all default healthcare NIM replicas."
  type        = number
  default     = 2
}

variable "gpu_node_groups" {
  description = "Number of GPU node groups in the new cluster."
  type        = number
  default     = 1
}

variable "cpu_nodes_platform" {
  description = "CPU node platform."
  type        = string
  default     = "cpu-d3"
}

variable "cpu_nodes_preset" {
  description = "CPU node preset."
  type        = string
  default     = "16vcpu-64gb"
}

variable "gpu_nodes_platform" {
  description = "GPU node platform."
  type        = string
  default     = "gpu-h200-sxm"
}

variable "gpu_nodes_preset" {
  description = "GPU node preset."
  type        = string
  default     = "8gpu-128vcpu-1600gb"
}

variable "gpu_disk_size" {
  description = "Boot disk size in GiB for GPU nodes."
  type        = string
  default     = "1023"
}

variable "filestore_disk_size_gibibytes" {
  description = "Shared filesystem size for the NIM model cache."
  type        = number
  default     = 5120
}

variable "filestore_mount_path" {
  description = "Shared filesystem mount path on cluster nodes."
  type        = string
  default     = "/mnt/data"
}

variable "filestore_forbid_deletion" {
  description = "Protect the Terraform-created shared filesystem from deletion."
  type        = bool
  default     = false
}

variable "filesystem_csi" {
  description = "Nebius Shared Filesystem CSI settings for the new cluster."
  type = object({
    chart_version                       = optional(string, "0.1.5")
    namespace                           = optional(string, "kube-system")
    make_default_storage_class          = optional(bool, true)
    previous_default_storage_class_name = optional(string, "compute-csi-default-sc")
  })
  default = {}
}

variable "enable_two_gpu_nims" {
  description = "Enable Evo2-40B and Qwen3 Next 80B. Keep enabled with the default two 8-GPU nodes."
  type        = bool
  default     = true
}

variable "nim_resource_overrides" {
  description = "Per-NIM resource overrides passed through to the modules/nims resource map."
  type = map(object({
    cpu_request    = optional(string)
    cpu_limit      = optional(string)
    memory_request = optional(string)
    memory_limit   = optional(string)
    gpu            = optional(string)
    shm            = optional(string)
  }))
  default = {}
}
