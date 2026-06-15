output "namespace" {
  description = "Kubernetes namespace for the NIM server."
  value       = var.namespace
}

output "nims_lb_ip" {
  description = "LoadBalancer IP for healthcare/life-science NIMs."
  value       = module.nims.nims_lb_ip
}
