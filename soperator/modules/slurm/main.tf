resource "terraform_data" "wait_for_slurm_cluster" {
  depends_on = [
    helm_release.flux2_sync,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOF
      set -e

      CONTEXT="${var.k8s_cluster_context}"
      NAMESPACE="flux-system"
      HELMRELEASE_NAME="flux-system-soperator-fluxcd-slurm-cluster"
      TIMEOUT_MINUTES=60
      MAX_RETRIES=$((TIMEOUT_MINUTES * 12))  # Check every 5 seconds
      SLEEP_SECONDS=5

      echo "Waiting for HelmRelease CRD to be available..."
      for i in $(seq 1 $MAX_RETRIES); do
        if kubectl get crd helmreleases.helm.toolkit.fluxcd.io --context "$CONTEXT" 2>/dev/null; then
          echo "HelmRelease CRD is available."
          break
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease CRD."
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease CRD..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Waiting for HelmRelease $HELMRELEASE_NAME to be created..."
      for i in $(seq 1 $MAX_RETRIES); do
        if kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" 2>/dev/null; then
          echo "HelmRelease $HELMRELEASE_NAME exists."
          break
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease $HELMRELEASE_NAME to be created."
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease $HELMRELEASE_NAME to be created..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed..."
      for i in $(seq 1 $MAX_RETRIES); do
        # Check if the HelmRelease is in the "Released" state
        RELEASE_STATUS=$(kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" -o jsonpath='{.status.conditions[?(@.type=="Released")]}' 2>/dev/null)
        
        if [ -n "$RELEASE_STATUS" ]; then
          RELEASE_STATUS_REASON=$(echo "$RELEASE_STATUS" | jq -r '.reason')
          RELEASE_STATUS_STATUS=$(echo "$RELEASE_STATUS" | jq -r '.status')
          
          if [ "$RELEASE_STATUS_REASON" == "InstallSucceeded" ] && [ "$RELEASE_STATUS_STATUS" == "True" ]; then
            echo "HelmRelease $HELMRELEASE_NAME has been successfully installed."
            echo "Details:"
            echo "$RELEASE_STATUS" | jq .
            exit 0
          fi
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed."
          echo "Current status:"
          kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" -o yaml
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed..."
        sleep "$SLEEP_SECONDS"
      done
    EOF
  }
}

resource "helm_release" "soperator_fluxcd_cm" {
  name       = "terraform-fluxcd-values"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

  values = [templatefile("${path.module}/templates/helm_values/terraform_fluxcd_values.yaml.tftpl", {
    backups_enabled    = var.backups_enabled
    telemetry_enabled  = var.telemetry_enabled
    accounting_enabled = var.accounting_enabled

    apparmor_enabled        = var.use_default_apparmor_profile
    enable_soperator_checks = var.enable_soperator_checks

    operator_version                   = var.operator_version
    cert_manager_version               = var.cert_manager_version
    k8up_version                       = var.k8up_version
    mariadb_operator_version           = var.mariadb_operator_version
    opentelemetry_collector_version    = var.opentelemetry_collector_version
    prometheus_crds_version            = var.prometheus_crds_version
    security_profiles_operator_version = var.security_profiles_operator_version
    vmstack_version                    = var.vmstack_version
    vmstack_crds_version               = var.vmstack_crds_version
    vmlogs_version                     = var.vmlogs_version


    cluster_name        = var.cluster_name
    public_o11y_enabled = var.public_o11y_enabled
    metrics_collector   = local.metrics_collector
    create_pvcs         = var.create_pvcs

    slurm_cluster_storage = {
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
    }

    slurm_cluster = {
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

    }

    resources = {
      vm_single         = var.resources_vm_single
      vm_agent          = var.resources_vm_agent
      vm_logs           = var.resources_vm_logs_server
      logs_collector    = var.resources_logs_collector
      events_collector  = var.resources_events_collector
      node_configurator = local.resources.node_configurator
      slurm_checks      = local.resources.slurm_checks
    }

  })]
}

resource "helm_release" "flux2_sync" {
  depends_on = [
    helm_release.flux2_sync,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOF
      set -e

      CONTEXT="${var.k8s_cluster_context}"
      NAMESPACE="flux-system"
      HELMRELEASE_NAME="flux-system-soperator-fluxcd-slurm-cluster"
      TIMEOUT_MINUTES=60
      MAX_RETRIES=$((TIMEOUT_MINUTES * 12))  # Check every 5 seconds
      SLEEP_SECONDS=5

      echo "Waiting for HelmRelease CRD to be available..."
      for i in $(seq 1 $MAX_RETRIES); do
        if kubectl get crd helmreleases.helm.toolkit.fluxcd.io --context "$CONTEXT" 2>/dev/null; then
          echo "HelmRelease CRD is available."
          break
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease CRD."
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease CRD..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Waiting for HelmRelease $HELMRELEASE_NAME to be created..."
      for i in $(seq 1 $MAX_RETRIES); do
        if kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" 2>/dev/null; then
          echo "HelmRelease $HELMRELEASE_NAME exists."
          break
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease $HELMRELEASE_NAME to be created."
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease $HELMRELEASE_NAME to be created..."
        sleep "$SLEEP_SECONDS"
      done

      echo "Waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed..."
      for i in $(seq 1 $MAX_RETRIES); do
        # Check if the HelmRelease is in the "Released" state
        RELEASE_STATUS=$(kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" -o jsonpath='{.status.conditions[?(@.type=="Released")]}' 2>/dev/null)
        
        if [ -n "$RELEASE_STATUS" ]; then
          RELEASE_STATUS_REASON=$(echo "$RELEASE_STATUS" | jq -r '.reason')
          RELEASE_STATUS_STATUS=$(echo "$RELEASE_STATUS" | jq -r '.status')
          
          if [ "$RELEASE_STATUS_REASON" == "InstallSucceeded" ] && [ "$RELEASE_STATUS_STATUS" == "True" ]; then
            echo "HelmRelease $HELMRELEASE_NAME has been successfully installed."
            echo "Details:"
            echo "$RELEASE_STATUS" | jq .
            exit 0
          fi
        fi

        if [ $i -eq $MAX_RETRIES ]; then
          echo "Timeout reached waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed."
          echo "Current status:"
          kubectl get helmreleases.helm.toolkit.fluxcd.io "$HELMRELEASE_NAME" -n "$NAMESPACE" --context "$CONTEXT" -o yaml
          exit 1
        fi

        echo "($i/$MAX_RETRIES) Waiting for HelmRelease $HELMRELEASE_NAME to be successfully installed..."
        sleep "$SLEEP_SECONDS"
      done
    EOF
  }
}

resource "helm_release" "soperator_fluxcd_cm" {
  name       = "terraform-fluxcd-values"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = "flux-system"

  values = [templatefile("${path.module}/templates/helm_values/terraform_fluxcd_values.yaml.tftpl", {
    backups_enabled    = var.backups_enabled
    telemetry_enabled  = var.telemetry_enabled
    accounting_enabled = var.accounting_enabled

    apparmor_enabled        = var.use_default_apparmor_profile
    enable_soperator_checks = var.enable_soperator_checks

    operator_version                   = var.operator_version
    cert_manager_version               = var.cert_manager_version
    k8up_version                       = var.k8up_version
    mariadb_operator_version           = var.mariadb_operator_version
    opentelemetry_collector_version    = var.opentelemetry_collector_version
    prometheus_crds_version            = var.prometheus_crds_version
    security_profiles_operator_version = var.security_profiles_operator_version
    vmstack_version                    = var.vmstack_version
    vmstack_crds_version               = var.vmstack_crds_version
    vmlogs_version                     = var.vmlogs_version


    cluster_name        = var.cluster_name
    public_o11y_enabled = var.public_o11y_enabled
    metrics_collector   = local.metrics_collector
    create_pvcs         = var.create_pvcs

    slurm_cluster_storage = {
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
    }

    slurm_cluster = {
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

    }

    resources = {
      vm_single         = var.resources_vm_single
      vm_agent          = var.resources_vm_agent
      vm_logs           = var.resources_vm_logs_server
      logs_collector    = var.resources_logs_collector
      events_collector  = var.resources_events_collector
      node_configurator = local.resources.node_configurator
      slurm_checks      = local.resources.slurm_checks
    }

  })]
}

resource "helm_release" "flux2_sync" {
  depends_on = [
    helm_release.soperator_fluxcd_cm,
  ]
  repository = "https://fluxcd-community.github.io/helm-charts"
  chart      = "flux2-sync"
  version    = "1.8.2"

  # Note: Do not change the name or namespace of this resource. The below mimics the behaviour of "flux bootstrap".
  name      = "flux-system"
  namespace = "flux-system"

  set {
    name  = "gitRepository.spec.url"
    value = "https://github.com/${var.github_org}/${var.github_repository}"
  }

  set {
    name  = "gitRepository.spec.ref.branch"
    value = var.github_branch
  }

  set {
    name  = "gitRepository.spec.interval"
    value = var.flux_interval
  }

  set {
    name  = "kustomization.spec.interval"
    value = var.flux_interval
  }

  set {
    name  = "kustomization.spec.postBuild.substitute.soperator_version"
    value = var.operator_version
  }
  set {
    name  = "kustomization.spec.path"
    value = var.flux_kustomization_path
  }
  set {
    name  = "kustomization.spec.prune"
    value = "false"
  }
}