resource "terraform_data" "wait_for_slurm_login_service" {
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
  depends_on = [
    terraform_data.wait_for_slurm_login_service
  ]

  metadata {
    namespace = var.slurm_cluster_name
    name      = "${var.slurm_cluster_name}-login-svc"
  }
}

resource "terraform_data" "lb_service_ip" {
  depends_on = [
    data.kubernetes_service.slurm_login
  ]

  triggers_replace = [
    one(data.kubernetes_service.slurm_login.metadata).resource_version
  ]

  input = one(one(one(data.kubernetes_service.slurm_login.status).load_balancer).ingress).ip
}


resource "local_file" "this" {
  depends_on = [
    terraform_data.lb_service_ip,
  ]

  filename        = "${path.root}/${var.script_name}.sh"
  file_permission = "0774"
  content = templatefile("${path.module}/templates/login.sh.tftpl", {
    address = terraform_data.lb_service_ip.output
  })
}
