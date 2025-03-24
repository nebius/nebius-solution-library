variable "slurm_cluster_name" {
  description = "Name of the Slurm cluster."
  type        = string
  nullable    = false
}

variable "create_pvcs" {
  description = "Whether to create PVCs. Uses emptyDir if false."
  type        = bool
  default     = false
}

variable "resources_vm_operator" {
  description = "Resources for VictoriaMetrics Operator."
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "512Mi"
    cpu    = "250m"
  }
}

variable "resources_vm_logs_server" {
  type = object({
    memory = string
    cpu    = string
    size   = string
  })
  default = {
    memory = "2Gi"
    cpu    = "1000m"
    size   = "40Gi"
  }
}

variable "resources_vm_single" {
  type = object({
    memory     = string
    cpu        = string
    size       = string
    gomaxprocs = number
  })
  default = {
    memory     = "24Gi"
    cpu        = "6000m"
    size       = "80Gi"
    gomaxprocs = 6
  }
}

variable "resources_vm_agent" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "4Gi"
    cpu    = "2000m"
  }
}

variable "resources_events_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "128Mi"
    cpu    = "100m"
  }
}


variable "resources_logs_collector" {
  type = object({
    memory = string
    cpu    = string
  })
  default = {
    memory = "200Mi"
    cpu    = "200m"
  }
}

variable "grafana_admin_password" {
  description = "Password of `admin` user of Grafana."
  type        = string
}

variable "cluster_name" {
  description = "the cluster name to use for the monitoring"
  type        = string
}

variable "k8s_cluster_context" {
  description = "K8s context name for kubectl."
  type        = string
}

variable "public_o11y_enabled" {
  description = "Whether to enable public observability endpoints."
  type        = bool
  default     = true
}
