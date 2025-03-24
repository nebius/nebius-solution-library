locals {
  namespace = {
    logs       = "logs-system"
    monitoring = "monitoring-system"
  }

  repository = {
    victoria_metrics = "https://victoriametrics.github.io/helm-charts/"
    logs_collector = {
      repository = "https://open-telemetry.github.io/opentelemetry-helm-charts"
      chart      = "opentelemetry-collector"
      version    = "0.117.1"
      name       = "logs"
    }
    raw = {
      repository = "https://bedag.github.io/helm-charts/"
      chart      = "raw"
      version    = "2.0.0"
    }
  }

  images_open_telemetry_operator = {
    opentelemetry_operator = {
      repository = "ghcr.io/open-telemetry/opentelemetry-operator/opentelemetry-operator"
      tag        = "0.119.0"
    }
    collector_image = {
      repository = "cr.eu-north1.nebius.cloud/observability/nebius-o11y-agent"
      tag        = "0.2.241"
    }
  }

  metrics_collector = {
    host = "vmsingle-slurm.${local.namespace.monitoring}.svc.cluster.local"
    port = 8429
  }

  vm_logs_server = {
    name = "vm"
  }
}

resource "helm_release" "prometheus_stack" {
  depends_on = [
    module.certificate_manager,
  ]

  name       = "prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "67.9.0"
  timeout    = 600

  create_namespace = true
  namespace        = local.namespace.monitoring

  values = [templatefile("${path.module}/templates/helm_values/prometheus.yaml.tftpl", {
    admin_password    = var.grafana_admin_password
    metrics_collector = local.metrics_collector
  })]

  wait = true
}

resource "helm_release" "vm_operator" {
  depends_on = [
    module.certificate_manager,
    helm_release.prometheus_stack,
  ]

  name       = "victoria-metrics-operator"
  repository = local.repository.victoria_metrics
  chart      = "victoria-metrics-operator"
  version    = "0.33.6"

  create_namespace = true
  namespace        = local.namespace.monitoring

  values = [templatefile("${path.module}/templates/helm_values/vm_operator.yaml.tftpl", {
    resources = var.resources_vm_operator
  })]

  wait = true
}

resource "helm_release" "vm_logs_server" {
  depends_on = [
    helm_release.vm_operator,
  ]

  name       = local.vm_logs_server.name
  repository = local.repository.victoria_metrics
  chart      = "victoria-logs-single"
  version    = "0.9.3"
  timeout    = 600

  create_namespace = true
  namespace        = local.namespace.logs

  values = [templatefile("${path.module}/templates/helm_values/vm_logs_server.yaml.tftpl", {
    vm_logs_service_name = local.vm_logs_server.name
    resources            = var.resources_vm_logs_server
    create_pvcs          = var.create_pvcs
  })]

  wait = true
}

resource "terraform_data" "wait_for_manual_o11y_token_creation" {
  count = var.public_o11y_enabled ? 1 : 0
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
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

resource "helm_release" "fb_logs_collector" {
  depends_on = [
    helm_release.vm_logs_server,
  ]

  name       = local.repository.logs_collector.name
  repository = local.repository.logs_collector.repository
  chart      = local.repository.logs_collector.chart
  version    = local.repository.logs_collector.version

  namespace = local.namespace.logs

  values = [templatefile("${path.module}/templates/helm_values/logs_collector.yaml.tftpl", {
    namespace            = local.namespace.logs,
    image                = local.images_open_telemetry_operator.collector_image
    resources            = var.resources_logs_collector
    vm_logs_service_name = format("%s-victoria-logs-single-server.%s.svc.cluster.local.", local.vm_logs_server.name, local.namespace.logs)
    cluster_name         = var.cluster_name
    public_o11y_enabled  = var.public_o11y_enabled
  })]

  wait = true
}

resource "helm_release" "events_collector" {
  depends_on = [
    helm_release.vm_logs_server,
  ]

  name       = "events"
  repository = local.repository.logs_collector.repository
  chart      = local.repository.logs_collector.chart
  version    = local.repository.logs_collector.version

  namespace = local.namespace.logs

  values = [templatefile("${path.module}/templates/helm_values/events_collector.yaml.tftpl", {
    namespace            = local.namespace.logs,
    image                = local.images_open_telemetry_operator.collector_image
    resources            = var.resources_events_collector
    vm_logs_service_name = format("%s-victoria-logs-single-server.%s.svc.cluster.local.", local.vm_logs_server.name, local.namespace.logs)
    cluster_name         = var.cluster_name
    public_o11y_enabled  = var.public_o11y_enabled
  })]

  wait = true
}

resource "helm_release" "slurm_monitor" {
  depends_on = [
    helm_release.vm_operator,
  ]

  name       = "slurm-monitor"
  repository = local.repository.raw.repository
  chart      = local.repository.raw.chart
  version    = local.repository.raw.version

  namespace = local.namespace.monitoring

  values = [templatefile("${path.module}/templates/helm_values/slurm_monitor.yaml.tftpl", {
    metrics_collector = local.metrics_collector
    create_pvcs       = var.create_pvcs
    resources = {
      vm_single = var.resources_vm_single
      vm_agent  = var.resources_vm_agent
    }
  })]

  wait = true
}

resource "helm_release" "dashboard" {
  for_each = tomap({
    gpu_metrics        = "gpu-metrics"
    slurm_exporter     = "exporter"
    kube_state_metrics = "kube-state-metrics"
    node_exporter      = "node-exporter"
    pod_resources      = "pod-resources"
  })

  depends_on = [
    helm_release.fb_logs_collector,
  ]

  name       = "${var.slurm_cluster_name}-grafana-dashboard-${each.value}"
  repository = local.repository.raw.repository
  chart      = local.repository.raw.chart
  version    = local.repository.raw.version

  namespace = local.namespace.monitoring

  values = [templatefile("${path.module}/templates/dashboards/${each.key}.yaml.tftpl", {
    namespace = local.namespace.monitoring
    name      = "${var.slurm_cluster_name}-${each.value}"
    filename  = "${each.value}.json"
  })]

  wait = true
}
