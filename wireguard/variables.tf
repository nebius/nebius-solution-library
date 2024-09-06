# K8s cluster
variable "parent_id" {
  description = "Project ID."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID."
  type        = string
  default     = ""
}

# SSH access
variable "ssh_user_name" {
  description = "SSH username."
  type        = string
  default     = ""
}

variable "public_ssh_key" {
  description = "SSH public key."
  type        = string
  default     = ""
}


# Access By IP
variable "public_ip_allocation_id" {
  description = "Id of a manually created public_ip_allocation."
  type        = string
  default     = null
}