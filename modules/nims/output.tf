output "nims_lb_ip" {
  description = "LoadBalancer IP for all NIMs"
  value       = kubernetes_service_v1.nims_lb.status[0].load_balancer[0].ingress[0].ip
}

output "cosmos_lb_ip" {
  description = "LoadBalancer IP for Cosmos World Foundation Models"
  value       = kubernetes_service_v1.cosmos_lb.status[0].load_balancer[0].ingress[0].ip
}
