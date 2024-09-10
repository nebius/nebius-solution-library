variable "parent_id" {
  type        = string
  description = "Id of the folder where the resources going to be created."
}

variable "subnet_id" {
  type        = string
  description = "ID of the subnet."
}

# NUMBER OF VMs for cluster
variable "storage_nodes" {
  type        = number
  default     = 3
  description = "Number of storage nodes."
}

# DISK OPTIONS
variable "disk_count_per_vm" {
  type        = number
  default     = 2
  description = "Number disks for GlusterFS per VM"
}

variable "disk_type" {
  type        = string
  default     = "NETWORK_SSD"
  description = "Type of GlusterFS disk."
}

variable "disk_size" {
  type        = number
  default     = 107374182400 # 100 GB
  description = "Disk size bytes."
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
