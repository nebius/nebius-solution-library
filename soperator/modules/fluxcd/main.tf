resource "terraform_data" "flux_namespace" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "create", "namespace", "flux-system",
        "--context", var.k8s_cluster_context,
      ]
    )
  }
  triggers_replace = {
    first_run = "true"
  }
}

resource "terraform_data" "flux2" {
  depends_on = [terraform_data.flux_namespace]
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "kubectl", "--context", var.k8s_cluster_context,
        "apply", "-f", "https://github.com/fluxcd/flux2/releases/download/${var.flux_version}/install.yaml",
      ]
    )
  }
  triggers_replace = {
    first_run = "true"
  }
}
