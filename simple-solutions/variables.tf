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

variable "users" {
  description = "List of users with their SSH keys"
  type = list(object({
    user_name           = string
    ssh_public_key = optional(string) # Inline SSH key
    ssh_key_path   = optional(string, "~/.ssh/id_rsa.pub") # Path to SSH key file
  }))
  default = []
  validation {
    condition = alltrue([
      for user in var.users : user.ssh_public_key != null || fileexists(user.ssh_key_path)
    ])
    error_message = "Each user must have at least one SSH key defined as 'ssh_public_key' or 'ssh_key_path'."
  }
}

variable "shared_filesystem_id" {
  description = "Id of an existing shared file system"
  type = string
  default = ""
}

variable "shared_filesystem_mount" {
  description = "mounting point of the shared file system"
  type = string
  default = "/mnt/share"
}

variable "region" {
  type = string
  description = "region"
  default = "eu-north1"
}

variable "add_extra_storage" {
  type = bool
  default = false
  description = "if true, a new disk will be created and mounted <extra_path>"
 }

variable "extra_path" {
  type = string
  default = "/mnt/storage"
  description = "Folder where the network storage will be mounted on"
}

variable "extra_storage_size_gb" {
  type = number
  default = 50
  description = "size of the newly created extra storage"
}

variable "public_ip" {
  type = bool
  default = true
  description = "attach a public ip to the vm if true"
}
