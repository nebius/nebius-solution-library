variable "parent_id" {
  type        = string
  description = "Id of the folder where the resources going to be created."
}

variable "subnet_id" {
  type        = string
  description = "ID of the subnet."
}

variable "region" {
  type        = string
  description = "Project region."
}

variable "cpu_nodes_platform" {
  description = "Platform for instances."
  type        = string
  default     = null
}

variable "cpu_nodes_preset" {
  description = "CPU and RAM configuration for instances."
  type        = string
  default     = null
}

variable "nfs_size" {
  type        = number
  default     = 93 * 1024 * 1024 * 1024 # size should be a multiple of 99857989632
  description = "Size of the NFS in GB, should be divisbile by 93"
}

variable "ssh_public_key" {
  description = "SSH Public Key to access the cluster nodes"
  type = object({
    key  = optional(string),
    path = optional(string, "~/.ssh/id_rsa.pub")
  })
  default = {}
  validation {
    condition     = var.ssh_public_key.key != null || fileexists(var.ssh_public_key.path)
    error_message = "SSH Public Key must be set by `key` or file `path` ${var.ssh_public_key.path}"
  }
}

variable "ssh_user_name" {
  type        = string
  description = "Username for ssh"
  default     = "nfs"
}

variable "nfs_ip_range" {
  type        = string
  description = "Ip range from where NFS will be available"
  default     = "192.168.0.0/16"
}