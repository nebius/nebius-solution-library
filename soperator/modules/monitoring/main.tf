locals {
  namespace = {
    logs       = "logs-system"
    monitoring = "monitoring-system"
  }

  repository = {
    victoria_metrics = "https://victoriametrics.github.io/helm-charts/"
    raw = {
      repository = "https://bedag.github.io/helm-charts/"
      chart      = "raw"
      version    = "2.0.0"
    }
  }

  metrics_collector = {
    host = "vmsingle-slurm.${local.namespace.monitoring}.svc.cluster.local"
    port = 8429
  }

  vm_logs_server = {
    name = "vm-logs-server"
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
  version    = "0.5.4"
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

resource "helm_release" "fb_logs_collector" {
  depends_on = [
    helm_release.vm_logs_server,
  ]

  name       = "fb-logs-collector"
  repository = "https://fluent.github.io/helm-charts"
  chart      = "fluent-bit"
  version    = "0.47.7"

  namespace = local.namespace.logs

  values = [templatefile("${path.module}/templates/helm_values/fb_logs_collector.yaml.tftpl", {
    namespace            = local.namespace.logs,
    resources            = var.resources_fb_logs_collector
    vm_logs_service_name = local.vm_logs_server.name
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
    slurm_exporter         = "exporter"
    kube_state_metrics     = "kube-state-metrics"
    pod_resources          = "pod-resources"
    workers_overview       = "workers-overview"
    workers_detailed_stats = "workers-detailed-stats"
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
