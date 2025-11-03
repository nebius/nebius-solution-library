variable "cluster_id" {
  type = string
}
variable "parent_id" {
  type = string
}
variable "jupyter_password" {
  type      = string
  sensitive = true
  description = "Password for DummyAuthenticator"
}

variable "num_bionemo_instances" {
  type        = number
  description = "Number of BioNeMo JupyterHub installations to create"
  default     = 1
}
