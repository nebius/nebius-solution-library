variable "enable_mutator" {
  description = "Enable using OPA Gatekeeper as a mutating webhook"
  type        = bool
  default     = false
}

variable "mutated_namespaces" {
  description = "If using Gatekeeper to mutate, only do so for pods in these namespaces (Recommended default: [\"default\"])"
  type        = list(string)
}

variable "kube_sched_ver" {
  description = "This is the version of kube-scheduler it must be <= API version"
  type        = string
}
