# Global parameters
variable "parent_id" {
  description = "Project ID."
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID."
  type        = string
}

variable "region" {
  description = "Project region."
  type        = string
}


# Platform
variable "platform" {
  description = "Platform for WireGuard host."
  type        = string
  default     = "cpu-e2"
}

variable "preset" {
  description = "Preset for WireGuard host."
  type        = string
  default     = "4vcpu-16gb"
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

# Access By IP
variable "public_ip_allocation_id" {
  description = "Id of a manually created public_ip_allocation."
  type        = string
  default     = null
}

variable "test_mode" {
  description = "Switch between real usage and testing."
  type        = bool
  default     = false
}
