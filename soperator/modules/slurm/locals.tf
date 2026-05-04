locals {
  kube_rbac_proxy = {
    image = "gcr.io/kubebuilder/kube-rbac-proxy"
    tag   = "v0.15.0"
  }
  helm = {
    repository = {
      slurm        = "oci://cr.eu-north1.nebius.cloud/soperator${!var.operator_stable ? "-unstable" : ""}"
      slurm_stable = "oci://cr.eu-north1.nebius.cloud/soperator"
      mariadb      = "https://helm.mariadb.com/mariadb-operator"
      raw          = "https://bedag.github.io/helm-charts/"
      spo          = "oci://cr.eu-north1.nebius.cloud/e00xdc03sb7gpqfd0a"
    }

    chart = {
      slurm_cluster         = "slurm-cluster"
      slurm_cluster_storage = "slurm-cluster-storage"
      slurm_operator_crds   = "soperator-crds"
      nodeconfigurator      = "nodeconfigurator"
      raw                   = "raw"
      spo                   = "security-profiles-operator"

      operator = {
        slurm       = "soperator"
        slurmchecks = "soperatorchecks"
        mariadb     = "mariadb-operator"
      }
    }

    version = {
      slurm   = var.operator_version
      mariadb = "25.10.2"
      raw     = "2.0.0"
      spo     = "0.8.4-soperator"
    }
  }

  image = {
    repository        = "cr.eu-north1.nebius.cloud/soperator${!var.operator_stable ? "-unstable" : ""}"
    repository_stable = "cr.eu-north1.nebius.cloud/soperator"
    tag               = var.operator_version
  }

  node_filters = {
    label = {
      gpu = module.labels.key_nvidia_gpu

      nodeset    = module.labels.key_slurm_nodeset_name
      system     = module.labels.name_nodeset_system
      controller = module.labels.name_nodeset_controller
      worker     = module.labels.name_nodeset_worker
      login      = module.labels.name_nodeset_login
      accounting = module.labels.name_nodeset_accounting
      nfs        = module.labels.name_nodeset_nfs
    }

    system = {
      name  = module.labels.name_nodeset_system
      match = module.labels.name_nodeset_system
    }
    controller = {
      name  = module.labels.name_nodeset_controller
      match = module.labels.name_nodeset_controller
    }
    worker = {
      name        = module.labels.name_nodeset_worker
      matches     = [for i in range(length(var.node_count.worker)) : join("-", [module.labels.name_nodeset_worker, i])]
      gpu_present = length([for i in range(length(var.node_count.worker)) : var.resources.worker[i].gpus]) > 0
    }
    login = {
      name  = module.labels.name_nodeset_login
      match = module.labels.name_nodeset_login
    }
    accounting = {
      name  = module.labels.name_nodeset_accounting
      match = module.labels.name_nodeset_accounting
    }
    nfs = {
      name  = module.labels.name_nodeset_nfs
      match = module.labels.name_nodeset_nfs
    }
  }

  maintenance_ignore_node_labels = flatten([
    for group in var.maintenance_ignore_node_groups : [
      for match_value in try(
        [local.node_filters[group].match],
        try(local.node_filters[group].matches, [])
      ) :
      format("%s=%s", local.node_filters.label.nodeset, match_value)
    ]
  ])

  resources = {
    munge = {
      cpu               = 0.1
      memory            = 0.5
      ephemeral_storage = 5
    }
    sssd = {
      cpu               = 0.2
      memory            = 0.5
      ephemeral_storage = 5
    }
    exporter = {
      cpu               = var.resources.exporter != null ? var.resources.exporter.cpu_cores : 0.25
      memory            = var.resources.exporter != null ? var.resources.exporter.memory_gibibytes : 0.25
      ephemeral_storage = var.resources.exporter != null ? var.resources.exporter.ephemeral_storage_gibibytes : 0.5
    }
    rest = {
      cpu               = var.resources.rest != null ? var.resources.rest.cpu_cores : 2
      memory            = var.resources.rest != null ? var.resources.rest.memory_gibibytes : 8
      ephemeral_storage = var.resources.rest != null ? var.resources.rest.ephemeral_storage_gibibytes : 0.5
    }
    mariadb = {
      cpu               = var.resources.mariadb != null ? var.resources.mariadb.cpu_cores : 2
      memory            = var.resources.mariadb != null ? var.resources.mariadb.memory_gibibytes : 12
      ephemeral_storage = var.resources.mariadb != null ? var.resources.mariadb.ephemeral_storage_gibibytes : 16
    }
    node_configurator = {
      limits = {
        memory = var.resources.node_configurator != null ? var.resources.node_configurator.limits.memory_gibibytes : 0.25
      }
      requests = {
        memory = var.resources.node_configurator != null ? var.resources.node_configurator.requests.memory_gibibytes : 0.25
        cpu    = var.resources.node_configurator != null ? var.resources.node_configurator.requests.cpu_cores : 0.5
      }
    }
    slurm_operator = {
      limits = {
        memory = var.resources.slurm_operator != null ? var.resources.slurm_operator.limits.memory_gibibytes : 2
      }
      requests = {
        memory = var.resources.slurm_operator != null ? var.resources.slurm_operator.requests.memory_gibibytes : 2
        cpu    = var.resources.slurm_operator != null ? var.resources.slurm_operator.requests.cpu_cores : 1
      }
    }
    slurm_checks = {
      limits = {
        memory = var.resources.slurm_checks != null ? var.resources.slurm_checks.limits.memory_gibibytes : 2
      }
      requests = {
        memory = var.resources.slurm_checks != null ? var.resources.slurm_checks.requests.memory_gibibytes : 2
        cpu    = var.resources.slurm_checks != null ? var.resources.slurm_checks.requests.cpu_cores : 0.5
      }
    }
    kruise_daemon = {
      cpu    = var.resources.kruise_daemon != null ? var.resources.kruise_daemon.cpu_cores : 0.05
      memory = var.resources.kruise_daemon != null ? var.resources.kruise_daemon.memory_gibibytes : 0.128
    }
    dcgm_exporter = {
      cpu    = var.resources.dcgm_exporter != null ? var.resources.dcgm_exporter.cpu_cores : 0.05
      memory = var.resources.dcgm_exporter != null ? var.resources.dcgm_exporter.memory_gibibytes : 0.5
    }
    nfs_server = {
      limits = {
        memory = var.resources.nfs != null ? var.resources.nfs.memory_gibibytes : 1
      }
      requests = {
        memory = var.resources.nfs != null ? var.resources.nfs.memory_gibibytes : 1
        cpu    = var.resources.nfs != null ? var.resources.nfs.cpu_cores : 1
      }
    }
  }

  slurm_node_extra = "\\\"{ \\\\\\\"ib_pod\\\\\\\": \\\\\\\"$TOPO_SWITCH_TIER2\\\\\\\", \\\\\\\"ib_su\\\\\\\": \\\\\\\"$TOPO_SWITCH_TIER1\\\\\\\" }\\\""

  # Calculate vmagent remote write queue count based on cluster size
  # This sets metrics ingestion capacity for larger clusters properly
  vm_agent_queue_count = 2 + floor(sum(var.node_count.worker) / 60)

  # kube-state-metrics starts exceeding the default 32MiB scrape limit around 1.1k workers.
  kube_state_metrics_large_cluster_worker_threshold = 1000
  kube_state_metrics_large_cluster_max_scrape_size  = 150554432
  kube_state_metrics_max_scrape_size = (
    var.kube_state_metrics_max_scrape_size != null
    ? var.kube_state_metrics_max_scrape_size
    : (
      sum(var.node_count.worker) >= local.kube_state_metrics_large_cluster_worker_threshold
      ? local.kube_state_metrics_large_cluster_max_scrape_size
      : null
    )
  )

  namespace = {
    logs       = "logs-system"
    monitoring = "monitoring-system"
  }

  metrics_collector = {
    host = "vmsingle-metrics-victoria-metrics-k8s-stack.${local.namespace.monitoring}.svc.cluster.local"
    port = 8429
  }
}
