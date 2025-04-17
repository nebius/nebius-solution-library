resource "helm_release" "slurm_cluster_storage" {
  depends_on = [
    terraform_data.check_worker_nodesets,
  ]

  name       = "slurm-cluster-storage-cm"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

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
    module.monitoring,
  ]

  name       = "soperator-cm"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

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

  name       = "nodeconfigurator-cm"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

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
}

resource "helm_release" "slurm_checks_operator" {
  depends_on = [
    helm_release.slurm_operator,
  ]
  count = var.enable_soperator_checks ? 1 : 0

  name       = "slurm-checks-cm"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

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

}

resource "helm_release" "slurm_cluster" {

  name       = "slurm-cluster-cm"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

  values = [templatefile("${path.module}/templates/helm_values/slurm_cluster.yaml.tftpl", {
    name                      = var.name
    useDefaultAppArmorProfile = var.use_default_apparmor_profile
    maintenance               = var.maintenance

    partition_configuration = {
      slurm_config_type = var.slurm_partition_config_type
      slurm_raw_config  = var.slurm_partition_raw_config
    }

    slurm_worker_features     = var.slurm_worker_features
    slurm_health_check_config = var.slurm_health_check_config

    k8s_node_filters = local.node_filters

    jail_submounts = [for submount in var.filestores.jail_submounts : {
      name       = submount.name
      mount_path = submount.mount_path
    }]

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
