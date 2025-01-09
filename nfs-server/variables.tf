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

variable "ssh_public_keys" {
  description = "List of SSH Public Keys to access the NFS server"
  type        = list(string)
  default     = []
}

variable "ssh_user_name" {
  type        = string
  description = "Username for ssh"
  default     = "nfs"
}

variable "nfs_ip_range" {
  type        = string
  description = "Ip range from where NFS will be available"
}