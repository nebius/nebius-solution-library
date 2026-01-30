variable "enable_mutator" {
  description = "Enable using OPA Gatekeeper as a mutating webhook"
  type        = bool
  default     = false
}

variable "mutated_namespaces" {
  description = "If using Gatekeeper to mutate, only do so for pods in these namespaces"
  type        = list(string)
  default     = ["default"]
}
