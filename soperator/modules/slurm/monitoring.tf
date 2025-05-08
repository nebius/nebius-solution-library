module "monitoring" {
  count = var.telemetry_enabled ? 1 : 0
  depends_on = [
    helm_release.flux2_sync,
  ]

  source = "../monitoring"

  slurm_cluster_name = var.name

  providers = {
    helm = helm
  }
}

locals {
  namespace = {
    logs       = "logs-system"
    monitoring = "monitoring-system"
  }

  repository = {
    raw = {
      repository = "https://bedag.github.io/helm-charts/"
      chart      = "raw"
      version    = "2.0.0"
    }
  }

  images_open_telemetry_operator = {
    collector_image = {
      repository = "cr.eu-north1.nebius.cloud/observability/nebius-o11y-agent"
      tag        = "0.2.252"
    }
  }

  metrics_collector = {
    host = "vmsingle-metrics-victoria-metrics-k8s-stack.${local.namespace.monitoring}.svc.cluster.local"
    port = 8429
  }

  vm_logs_server = {
    name = "logs"
  }
}

resource "terraform_data" "wait_for_manual_o11y_token_creation" {
  count = var.telemetry_enabled || var.public_o11y_enabled ? 1 : 0
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOF
      set -e

      MAX_RETRIES=30
      SLEEP_SECONDS=5

      SECRET_NAME="o11y-writer-sa-token"
      KEY_NAME="accessToken"

      NAMESPACE="${local.namespace.logs}"
      CONTEXT="${var.k8s_cluster_context}"

      # Loop until the secret with the specified key is found or we reach MAX_RETRIES
      for i in $(seq 1 $MAX_RETRIES); do
        # Try to retrieve the 'accessToken' data from the secret
        if kubectl get secret "$SECRET_NAME" \
          -n "$NAMESPACE" \
          --context "$CONTEXT" \
          -o "jsonpath={.data.$KEY_NAME}" 2>/dev/null | grep -q '[^[:space:]]'; then
          echo "Secret '$SECRET_NAME' with key '$KEY_NAME' is present."
          exit 0
        fi

        echo "($i/$MAX_RETRIES) Waiting for the secret '$SECRET_NAME' to contain '$KEY_NAME'..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Timeout reached. Secret '$SECRET_NAME' does not contain '$KEY_NAME'."
      exit 1
    EOF
  }
}
