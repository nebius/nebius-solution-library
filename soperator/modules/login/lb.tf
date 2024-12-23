resource "terraform_data" "wait_for_slurm_login_service" {
  count = !var.node_port.used ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.loadBalancer.ingress}'",
        "--timeout", "5m",
        "--context", var.k8s_cluster_context,
        "-n", var.slurm_cluster_name,
        "service/${var.slurm_cluster_name}-login-svc"
      ]
    )
  }
}

data "kubernetes_service" "slurm_login" {
  count = !var.node_port.used ? 1 : 0

  depends_on = [
    terraform_data.wait_for_slurm_login_service
  ]

  metadata {
    namespace = var.slurm_cluster_name
    name      = "${var.slurm_cluster_name}-login-svc"
  }
}

resource "terraform_data" "lb_service_ip" {
  count = !var.node_port.used ? 1 : 0

  depends_on = [
    data.kubernetes_service.slurm_login
  ]

  triggers_replace = [
    one(one(data.kubernetes_service.slurm_login).metadata).resource_version
  ]

  input = one(one(one(one(data.kubernetes_service.slurm_login).status).load_balancer).ingress).ip
}
