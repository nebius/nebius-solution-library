resource "helm_release" "flux2" {
  depends_on = [terraform_data.flux_namespace]

  repository = "https://fluxcd-community.github.io/helm-charts"
  chart      = "flux2"
  version    = var.flux_version

  name      = "flux2"
  namespace = "flux-system"
}

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
