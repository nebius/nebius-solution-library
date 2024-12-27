variable "parent_id" {
  type        = string
  description = "Id of the folder where the resources going to be created."
  default     = null
}

variable "subnet_id" {
  type        = string
  description = "ID of the subnet."
  default     = null
}

variable "instance_count" {
  type = number
  description = "Number of instances"
  default = 1
}


variable "instance_name" {
  type = string
  description = "name of the instance"
  default = "instance"
}

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

variable "cpu_nodes_preset" {
  description = "CPU and RAM configuration for instances."
  type        = string
  default     = null
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
  default     = "tux"
}

variable "add_nfs_storage" {
  type = bool
  default = false
  description = "if true, a new nfs disk will be created and mounted at <nfs_path>"
 }

variable "nfs_path" {
  type = string
  default = "/mnt/nfs"
  description = "Folder where the network storage will be mounted on"
}

variable "nfs_size_gb" {
  type = number
  default = 50
  description = "size of the newly created nfs storage"
}

variable "public_ip" {
  type = bool
  default = true
  description = "attach a public ip to the vm if true"
}
