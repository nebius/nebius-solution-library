resource "helm_release" "create_nebius_user" {
  count = var.checks.create_nebius_user ? 1 : 0

  name       = "create-nebius-user-check"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.slurm_cluster_namespace

  values = [templatefile("${path.module}/templates/create_user_check.yaml.tftpl", {
    slurm_cluster_namespace = var.slurm_cluster_namespace
    slurm_cluster_name      = var.slurm_cluster_name
    user_name               = var.checks.nebius_username
    save_ssh_key            = false
  })]

  wait = true
}

resource "terraform_data" "wait_for_create_user_nebius_check" {
  depends_on = [
    helm_release.create_nebius_user
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.k8sJobsStatus.lastK8sJobStatus}'=Complete",
        "--timeout", "2m",
        "--context", var.k8s_cluster_context,
        "-n", var.slurm_cluster_namespace,
        "activechecks.slurm.nebius.ai/create-user-${var.checks.nebius_username}"
      ]
    )
  }
}

resource "helm_release" "create_soperatorchecks_user" {
  count = var.checks.create_soperatorchecks_user ? 1 : 0

  depends_on = [ 
    terraform_data.wait_for_create_user_nebius_check
  ]

  name       = "create-soperatorchecks-user-check"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.slurm_cluster_namespace

  values = [templatefile("${path.module}/templates/create_user_check.yaml.tftpl", {
    slurm_cluster_namespace = var.slurm_cluster_namespace
    slurm_cluster_name      = var.slurm_cluster_name
    user_name               = var.checks.soperatorchecks_username
    save_ssh_key            = true
  })]

  wait = true
}

resource "terraform_data" "wait_for_create_user_soperatorchecks_check" {
  depends_on = [
    helm_release.create_soperatorchecks_user
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.k8sJobsStatus.lastK8sJobStatus}'=Complete",
        "--timeout", "2m",
        "--context", var.k8s_cluster_context,
        "-n", var.slurm_cluster_namespace,
        "activechecks.slurm.nebius.ai/create-user-${var.checks.soperatorchecks_username}"
      ]
    )
  }
}

resource "helm_release" "install_package_check" {
  count = var.checks.install_package_check_enabled ? 1 : 0

  depends_on = [ 
    terraform_data.wait_for_create_user_soperatorchecks_check 
  ]

  name       = "install-package-check"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.slurm_cluster_namespace

  values = [templatefile("${path.module}/templates/install_package.yaml.tftpl", {
    slurm_cluster_namespace = var.slurm_cluster_namespace
    slurm_cluster_name      = var.slurm_cluster_name
    user_name               = var.checks.soperatorchecks_username
  })]

  wait = true
}

resource "helm_release" "ssh_check" {
  count = var.checks.ssh_check_enabled ? 1 : 0

  depends_on = [ 
    terraform_data.wait_for_create_user_soperatorchecks_check 
  ]

  name       = "ssh-check"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.slurm_cluster_namespace

  values = [templatefile("${path.module}/templates/ssh_check.yaml.tftpl", {
    slurm_cluster_namespace = var.slurm_cluster_namespace
    slurm_cluster_name      = var.slurm_cluster_name
    num_of_login_nodes      = var.num_of_login_nodes
    user_name               = var.checks.soperatorchecks_username
  })]

  wait = true
}

resource "terraform_data" "wait_for_ssh_check" {
  depends_on = [
    helm_release.install_package_check,
    helm_release.ssh_check
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.k8sJobsStatus.lastK8sJobStatus}'=Complete",
        "--timeout", "2m",
        "--context", var.k8s_cluster_context,
        "-n", var.slurm_cluster_namespace,
        "activechecks.slurm.nebius.ai --all"
      ]
    )
  }
}
