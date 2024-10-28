variable "parent_id" {
  type        = string
  description = "Id of the folder where the resources going to be created."
}

variable "subnet_id" {
  type        = string
  description = "ID of the subnet."
}

variable "disk_type" {
  type        = string
  default     = "NETWORK_SSD_IO_M3" # "NETWORK_SSD"
  description = "Type of NFS data disk."
}

variable "disk_block_size" {
  type        = number
  default     = 4096
  description = "Disk block size."
}

# STORAGE VM RESOURCES
variable "platform" {
  description = "VM platform."
  type        = string
  default     = "cpu-e2"
}

variable "preset" {
  description = "VM resources preset."
  type        = string
  default     = "16vcpu-64gb"
}

# SSH KEY
variable "ssh_public_key" {
  description = "SSH public key for the 'root' user."
  type        = string
}

variable "instance_name" {
  type        = string
  description = "Instance name for the nfs server."
  default     = "nfs-share"
}

variable "ssh_user_name" {
  type        = string
  description = "Username for ssh"
  default     = "nfs"
}

variable "nfs_path" {
  type        = string
  description = "Path to nfs_device"
  default     = "/nfs"
}

variable "nfs_ip_range" {
  type        = string
  description = "Ip range from where NFS will be available"
}

variable "mtu_size" {
  type        = string
  description = "MTU size to make network fater"
  default     = "8910"
}

variable "nfs_size" {
  type        = string
  description = "Size of the NFS in GB, should be divisbile by 93"
}