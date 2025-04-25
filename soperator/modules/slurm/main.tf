resource "helm_release" "mariadb_operator" {
  count = var.accounting_enabled ? 1 : 0

  depends_on = [
    module.monitoring,
    module.certificate_manager,
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
  depends_on = [
    terraform_data.check_worker_nodesets,
  ]

  name       = local.helm.chart.slurm_cluster_storage
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.slurm_cluster_storage}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/helm_values/slurm_cluster_storage.yaml.tftpl", {
    scheduling = local.node_filters

    volume = {
      controller_spool = {
        size   = "${var.filestores.controller_spool.size_gibibytes}Gi"
        device = var.filestores.controller_spool.device
      }
      jail = {
        size   = "${var.filestores.jail.size_gibibytes}Gi"
        device = var.filestores.jail.device
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

  set {
    name  = "controllerManager.manager.env.isApparmorCrdInstalled"
    value = var.use_default_apparmor_profile
  }

  set {
    name  = "controllerManager.kubeRbacProxy.image.repository"
    value = local.kube_rbac_proxy.image
  }

  set {
    name  = "controllerManager.kubeRbacProxy.image.tag"
    value = local.kube_rbac_proxy.tag
  }

  set {
    name  = "certManager.enabled"
    value = var.telemetry_enabled
  }

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "nodeconfigurator" {
  depends_on = [
    helm_release.slurm_operator,
  ]
  count = var.enable_node_configurator ? 1 : 0

  name       = local.helm.chart.nodeconfigurator
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.nodeconfigurator}"
  version    = local.helm.version.slurm

  values = [templatefile("${path.module}/templates/helm_values/node_configurator.yaml.tftpl", {
    rebooter = {
      log_level = var.node_configurator_log_level
      image = {
        repository = "${local.image.repository}/rebooter"
        tag        = local.image.tag
      }
      resources = {
        limits = {
          memory = local.resources.node_configurator.limits.memory
        }
        requests = {
          cpu    = local.resources.node_configurator.requests.cpu
          memory = local.resources.node_configurator.requests.memory
        }
      }
    }
  })]

  create_namespace = true
  namespace        = "${local.helm.chart.operator.slurm}-system"
}

resource "helm_release" "slurm_checks_operator" {
  depends_on = [
    helm_release.slurm_operator,
  ]
  count = var.enable_soperator_checks ? 1 : 0

  name       = local.helm.chart.operator.slurmchecks
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.operator.slurmchecks}"
  version    = local.helm.version.slurm

  values = [templatefile("${path.module}/templates/helm_values/slurm_checks.yaml.tftpl", {
    checks : {
      resources : {
        limits : {
          memory : local.resources.slurm_checks.limits.memory
        }
        requests : {
          cpu : local.resources.slurm_checks.requests.cpu
          memory : local.resources.slurm_checks.requests.memory
        }
      }
    }
  })]

  create_namespace = true
  namespace        = "${local.helm.chart.operator.slurm}-system"
}

resource "helm_release" "custom_supervisord_config" {
  name       = "custom-supervisord-config"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/custom_supervisord_cm.yaml.tftpl", {})]

  wait = true
}

resource "helm_release" "default_prolog_script" {
  name       = "slurm-prolog"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/slurm_prolog_cm.yaml.tftpl", {})]

  wait = true
}

resource "helm_release" "default_epilog_script" {
  name       = "slurm-epilog"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/slurm_epilog_cm.yaml.tftpl", {})]

  wait = true
}

resource "helm_release" "motd_nebius_o11y_script" {
  name       = "motd-nebius-o11y-script"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/motd_nebius_o11y_cm.yaml.tftpl", {
    telemetry_grafana_admin_password = var.telemetry_grafana_admin_password
  })]

  wait = true
}

resource "helm_release" "image_storage_conf" {
  count = var.node_local_image_storage.enabled ? 1 : 0

  name       = "image-storage"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/image_storage_cm.yaml.tftpl", {})]

  wait = true
}

resource "helm_release" "spo" {
  depends_on = [
    module.monitoring,
  ]
  count = var.use_default_apparmor_profile ? 1 : 0

  name       = "security-profiles-operator"
  repository = local.helm.repository.spo
  chart      = local.helm.chart.spo
  version    = local.helm.version.spo

  create_namespace = true
  namespace        = "security-profiles-operator-system"

  values = [templatefile("${path.module}/templates/spo_values.tftpl", {})]
}

resource "helm_release" "slurm_cluster" {
  depends_on = [
    helm_release.slurm_operator,
    helm_release.slurm_cluster_storage,
    helm_release.custom_supervisord_config,
    helm_release.default_prolog_script,
    helm_release.default_epilog_script,
    helm_release.motd_nebius_o11y_script,
    helm_release.spo,
  ]

  name       = local.helm.chart.slurm_cluster
  repository = local.helm.repository.slurm
  chart      = "helm-${local.helm.chart.slurm_cluster}"
  version    = local.helm.version.slurm

  create_namespace = true
  namespace        = var.name

  values = [templatefile("${path.module}/templates/helm_values/slurm_cluster.yaml.tftpl", {
    name                      = var.name
    useDefaultAppArmorProfile = var.use_default_apparmor_profile
    maintenance               = var.maintenance

    partition_configuration = {
      slurm_config_type = var.slurm_partition_config_type
      slurm_raw_config  = var.slurm_partition_raw_config
    }

    slurm_worker_features = var.slurm_worker_features
    slurm_health_check_config = var.slurm_health_check_config

    k8s_node_filters = local.node_filters

    jail_submounts = [for submount in var.filestores.jail_submounts : {
      name       = submount.name
      mount_path = submount.mount_path
    }]
    node_local_jail_submounts = var.node_local_jail_submounts
    node_local_image_storage  = var.node_local_image_storage

    nfs = var.nfs

    default_prolog_enabled = var.default_prolog_enabled
    default_epilog_enabled = var.default_epilog_enabled

    nccl_topology_type = var.nccl_topology_type
    nccl_benchmark = {
      enable         = var.nccl_benchmark_enable
      schedule       = var.nccl_benchmark_schedule
      min_threshold  = var.nccl_benchmark_min_threshold
      use_infiniband = var.nccl_use_infiniband
    }

    nodes = {
      accounting = {
        enabled              = var.accounting_enabled
        use_protected_secret = var.use_protected_secret
        mariadb_operator = var.accounting_enabled ? {
          enabled         = var.accounting_enabled
          storage_size    = var.accounting_enabled ? var.filestores.accounting.size_gibibytes : 0
          metrics_enabled = var.telemetry_enabled
          resources       = local.resources.mariadb
        } : null
        slurmdbd_config = var.slurmdbd_config
        slurm_config    = var.slurm_accounting_config
        resources = var.accounting_enabled ? {
          cpu               = var.resources.accounting.cpu_cores - local.resources.munge.cpu - local.resources.mariadb.cpu
          memory            = var.resources.accounting.memory_gibibytes - local.resources.munge.memory - local.resources.mariadb.memory
          ephemeral_storage = var.resources.accounting.ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage - local.resources.mariadb.ephemeral_storage
        } : null
      }

      controller = {
        size = var.node_count.controller
        resources = {
          cpu               = var.resources.controller.cpu_cores - local.resources.munge.cpu - local.resources.kruise_daemon.cpu
          memory            = var.resources.controller.memory_gibibytes - local.resources.munge.memory - local.resources.kruise_daemon.memory
          ephemeral_storage = var.resources.controller.ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage
        }
      }

      worker = {
        size = one(var.node_count.worker)
        resources = {
          cpu               = floor(one(var.resources.worker).cpu_cores - local.resources.munge.cpu) - local.resources.kruise_daemon.cpu
          memory            = floor(one(var.resources.worker).memory_gibibytes - local.resources.munge.memory) - local.resources.kruise_daemon.memory
          ephemeral_storage = floor(one(var.resources.worker).ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage)
          gpus              = one(var.resources.worker).gpus
        }
        shared_memory            = var.shared_memory_size_gibibytes
        slurm_node_extra         = local.slurm_node_extra
        sshd_config_map_ref_name = var.worker_sshd_config_map_ref_name
      }

      login = {
        size                     = var.node_count.login
        allocation_id            = var.login_allocation_id
        sshd_config_map_ref_name = var.login_sshd_config_map_ref_name
        root_public_keys         = var.login_ssh_root_public_keys
        resources = {
          cpu               = floor(var.resources.login.cpu_cores - local.resources.munge.cpu - local.resources.kruise_daemon.cpu)
          memory            = floor(var.resources.login.memory_gibibytes - local.resources.munge.memory - local.resources.kruise_daemon.memory)
          ephemeral_storage = floor(var.resources.login.ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage)
        }
      }

      exporter = {
        enabled   = var.exporter_enabled
        resources = local.resources.exporter
      }

      munge = {
        resources = local.resources.munge
      }

      rest = {
        enabled   = var.rest_enabled
        resources = local.resources.rest
      }
    }

    sconfigcontroller = {
      node = {
        k8s_node_filter_name = var.sconfigcontroller.node.k8s_node_filter_name
        size                 = var.sconfigcontroller.node.size
      }
      container = {
        image_pull_policy = var.sconfigcontroller.container.image_pull_policy
        resources = {
          cpu               = var.sconfigcontroller.container.resources.cpu
          memory            = var.sconfigcontroller.container.resources.memory
          ephemeral_storage = var.sconfigcontroller.container.resources.ephemeral_storage
        }
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
    command = join(
      " ",
      [
        "kubectl", "wait",
        "--for=jsonpath='{.status.phase}'=Available",
        "--timeout", "1h",
        "--context", var.k8s_cluster_context,
        "-n", var.name,
        "slurmcluster.slurm.nebius.ai/${var.name}"
      ]
    )
  }
}
