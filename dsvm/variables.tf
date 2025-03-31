# Global parameters
variable "parent_id" {
  description = "Project ID."
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID."
  type        = string
}

variable "network_interface_name" {
  type        = string
  description = "Name of the VM network interface"
  default     = "eth0"
}

variable "region" {
  description = "Project region."
  type        = string
  default     = "eu-north1" # https://docs.nebius.com/overview/regions
}

# Platform
variable "platform" {
  description = "Platform for DSVM host."
  type        = string
  default     = "gpu-h100-sxm" # https://docs.nebius.com/compute/virtual-machines/types#gpu-configurations
}

variable "preset" {
  description = "Preset for DSVM host."
  type        = string
  default     = "1gpu-16vcpu-200gb" # https://docs.nebius.com/compute/virtual-machines/types#gpu-configurations
}

# SSH access
variable "ssh_user_name" {
  description = "SSH username."
  type        = string
  default     = "ubuntu"
}

variable "ssh_public_key" {
  description = "SSH Public Key to access the cluster nodes."
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

variable "test_mode" {
  description = "Switch between real usage and testing."
  type        = bool
  default     = false
}
