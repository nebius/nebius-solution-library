output "openfold3_lb_ip" {
  value = kubernetes_service.openfold3_lb.status[0].load_balancer[0].ingress[0].ip
}
