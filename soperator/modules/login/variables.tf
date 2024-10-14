variable "nlb_used" {
  description = "Whether NLB node group is used."
  type        = bool
  nullable    = false
}

variable "slurm_cluster_name" {
  description = "Name of the Slurm cluster in k8s cluster."
  type        = string
  nullable    = false
}
