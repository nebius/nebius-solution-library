resource "helm_release" "create_nebius_user_and_ssh_check" {
  name       = "create-nebius-user-and-ssh-check"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.slurm_cluster_namespace

  values = [templatefile("${path.module}/templates/create_nebius_user_and_ssh_check.yaml.tftpl", {
    slurm_cluster_namespace = var.slurm_cluster_namespace
    slurm_cluster_ip        = var.slurm_cluster_ip
    slurm_cluster_name      = var.slurm_cluster_name
    num_of_login_nodes      = var.num_of_login_nodes
  })]

  wait = true
}

resource "terraform_data" "wait_for_create_nebius_user_and_ssh_check" {
  depends_on = [
    helm_release.create_nebius_user_and_ssh_check
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.k8sJobsStatus.lastK8sJobStatus}'=Complete",
        "--timeout", "1m",
        "--context", var.k8s_cluster_context,
        "-n", var.slurm_cluster_namespace,
        "activechecks.slurm.nebius.ai/create-nebius-user-and-ssh-check"
      ]
    )
  }
}
