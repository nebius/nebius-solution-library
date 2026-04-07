resource "terraform_data" "flux_namespace" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    # `kubectl create namespace` fails with AlreadyExists on re-runs, making it
    # non-retryable. Piping through `--dry-run=client -o yaml | kubectl apply`
    # produces an idempotent apply that succeeds whether the namespace exists or not.
    # The pipe requires a shell, so the inner command is passed as a bash -c string.
    command = join(" ", [
      "${path.module}/../scripts/retry.sh", "--", "bash", "-c",
      "'kubectl create namespace flux-system --context ${var.k8s_cluster_context} --dry-run=client -o yaml",
      "| kubectl apply --context ${var.k8s_cluster_context} -f -'",
    ])
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
        "${path.module}/../scripts/retry.sh", "--",
        "kubectl", "--context", var.k8s_cluster_context,
        "apply", "-f", "https://github.com/fluxcd/flux2/releases/download/${var.flux_version}/install.yaml",
      ]
    )
  }
  triggers_replace = {
    first_run = "true"
  }
}
