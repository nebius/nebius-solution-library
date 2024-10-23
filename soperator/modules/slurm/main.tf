resource "helm_release" "mariadb_operator" {
  count = var.accounting_enabled ? 1 : 0

  depends_on = [
    module.monitoring,
  ]

  name       = local.helm.chart.operator.mariadb
  repository = local.helm.repository.mariadb
  chart      = local.helm.chart.operator.mariadb
  version    = local.helm.version.mariadb

  create_namespace = true
  namespace        = var.mariadb_operator_namespace

  set {
    name  = "metrics.enabled"
    value = var.telemetry_enabled
  }
  set {
    name  = "metrics.serviceMonitor.enabled"
    value = var.telemetry_enabled
  }
  set {
    name  = "metrics.serviceMonitor.interval"
    value = "30s"
  }
  set {
    name  = "metrics.serviceMonitor.scrapeTimeout"
    value = "25s"
  }
  set {
    name  = "serviceAccount.enabled"
    value = true
  }

  set {
    name  = "cert.certManager.enabled"
    value = var.telemetry_enabled
  }

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "slurm_cluster_crd" {
  name       = local.helm.chart.slurm_operator_crds
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.slurm_operator_crds}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = "${local.helm.chart.operator.slurm}-system"

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "slurm_cluster_storage" {
  name       = local.helm.chart.slurm_cluster_storage
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.slurm_cluster_storage}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/helm_values/slurm_cluster_storage.yaml.tftpl", {
    scheduling = {
      key = module.labels.key_slurm_node_group_name
      cpu = module.labels.name_node_group_cpu
      gpu = module.labels.name_node_group_gpu
    }
    volume = {
      jail = {
        size   = "${var.filestores.jail.size_gibibytes}Gi"
        device = var.filestores.jail.device
      }
      controller_spool = {
        size   = "${var.filestores.controller_spool.size_gibibytes}Gi"
        device = var.filestores.controller_spool.device
      }
      jail_submounts = [for submount in var.filestores.jail_submounts : {
        name   = submount.name
        size   = "${submount.size_gibibytes}Gi"
        device = submount.device
      }]
      accounting = var.accounting_enabled ? {
        enabled = true
        size    = "${var.filestores.accounting.size_gibibytes}Gi"
        device  = var.filestores.accounting.device
      } : { enabled = false }
    }
  })]

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "slurm_operator" {
  depends_on = [
    helm_release.slurm_cluster_crd,
    helm_release.mariadb_operator,
    module.monitoring,
  ]

  name       = local.helm.chart.operator.slurm
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.operator.slurm}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = "${local.helm.chart.operator.slurm}-system"

  set {
    name  = "fullnameOverride"
    value = local.helm.chart.operator.slurm
  }

  set {
    name  = "controllerManager.manager.env.isPrometheusCrdInstalled"
    value = var.telemetry_enabled
  }

  set {
    name  = "controllerManager.manager.env.isMariadbCrdInstalled"
    value = var.accounting_enabled
  }

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "slurm_cluster" {
  depends_on = [
    helm_release.slurm_operator,
    helm_release.slurm_cluster_storage,
  ]

  name       = local.helm.chart.slurm_cluster
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.slurm_cluster}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/helm_values/slurm_cluster.yaml.tftpl", {
    name = var.name

    partition_configuration = {
      slurm_config_type = var.slurm_partition_config_type
      slurm_raw_config = var.slurm_partition_raw_config
    }

    k8s_node_filters = {
      non_gpu = {
        name = module.labels.name_node_group_cpu
        affinity = {
          key   = module.labels.key_slurm_node_group_name
          value = module.labels.name_node_group_cpu
        }
      }
      gpu = {
        name = module.labels.name_node_group_gpu
        affinity = {
          key   = module.labels.key_slurm_node_group_name
          value = module.labels.name_node_group_gpu
        }
      }
    },

    jail_submounts = [for submount in var.filestores.jail_submounts : {
      name       = submount.name
      mount_path = submount.mount_path
    }]

    nccl_topology_type = var.nccl_topology_type
    ncclBenchmark = {
      enable        = var.nccl_benchmark_enable
      schedule      = var.nccl_benchmark_schedule
      min_threshold = var.nccl_benchmark_min_threshold
    }

    nodes = {
      accounting = {
        enabled = var.accounting_enabled
        mariadbOperator = {
          metricsEnabled = var.telemetry_enabled
          enabled        = var.accounting_enabled
          storage_size   = var.accounting_enabled ? var.filestores.accounting.size_gibibytes : 0
        }
        slurmdbdConfig = var.slurmdbd_config
        slurmConfig    = var.slurm_accounting_config

      }
      controller = {
        size = var.node_count.controller
      }
      worker = {
        size = var.node_count.worker
        resources = {
          cpu               = var.worker_resources.cpu_cores
          memory            = var.worker_resources.memory_gibibytes
          ephemeral_storage = var.worker_resources.ephemeral_storage_gibibytes
          gpus              = var.worker_resources.gpus
        }
        shared_memory = var.shared_memory_size_gibibytes
      }
      login = {
        size             = var.node_count.controller
        service_type     = var.login_service_type
        allocation_id    = var.login_allocation_id
        node_port        = var.login_node_port
        root_public_keys = var.login_ssh_root_public_keys
      }
      exporter = {
        enabled = var.exporter_enabled
      }

    }

    telemetry = {
      enabled = var.telemetry_enabled
      metrics_collector = var.telemetry_enabled ? {
        endpoint = one(module.monitoring).metrics_collector_endpoint
      } : null
    }
  })]

  wait          = true
  wait_for_jobs = true
}

resource "terraform_data" "wait_for_slurm_cluster" {
  depends_on = [
    helm_release.slurm_cluster
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = "kubectl wait --for=jsonpath='{.status.phase}'=Available --timeout 1h -n ${var.name} slurmcluster.slurm.nebius.ai/${var.name}"
  }
}
