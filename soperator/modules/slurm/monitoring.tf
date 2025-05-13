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

module "monitoring" {
  count = var.telemetry_enabled ? 1 : 0
  depends_on = [
    helm_release.flux2_sync,
    terraform_data.wait_for_monitoring_namespace,
  ]

  source = "../monitoring"

  slurm_cluster_name = var.name

  providers = {
    helm = helm
  }
}

resource "terraform_data" "wait_for_monitoring_namespace" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOF
      set -e

      MAX_RETRIES=50
      SLEEP_SECONDS=5

      NAMESPACE="monitoring-system"
      CONTEXT="${var.k8s_cluster_context}"

      # Loop until the namespace is found or we reach MAX_RETRIES
      for i in $(seq 1 $MAX_RETRIES); do
        # Try to retrieve the namespace
        if kubectl get namespace "$NAMESPACE" --context "$CONTEXT" 2>/dev/null; then
          echo "Namespace '$NAMESPACE' is present and ready."
          exit 0
        fi

        echo "($i/$MAX_RETRIES) Waiting for namespace '$NAMESPACE' to be created..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Timeout reached. Namespace '$NAMESPACE' was not created within the allowed time."
      exit 1
    EOF
  }
}
