resource "terraform_data" "wait_for_slurm_cluster_hr" {
  depends_on = [
    helm_release.soperator_fluxcd_bootstrap,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = templatefile("${path.module}/scripts/wait_for_flux_hr.sh.tmpl", {
      k8s_cluster_context = var.k8s_cluster_context
      helmrelease_name    = "flux-system-soperator-fluxcd-slurm-cluster"
      timeout_minutes     = 60
    })
  }
}

resource "terraform_data" "wait_for_soperator_activechecks_hr" {
  depends_on = [
    helm_release.soperator_fluxcd_bootstrap,
  ]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = templatefile("${path.module}/scripts/wait_for_flux_hr.sh.tmpl", {
      k8s_cluster_context = var.k8s_cluster_context
      helmrelease_name    = "flux-system-soperator-fluxcd-soperator-activechecks"
      timeout_minutes     = 120
    })
  }
}

resource "terraform_data" "wait_for_slurm_cluster_available" {
  depends_on = [
    terraform_data.wait_for_slurm_cluster_hr
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

resource "helm_release" "soperator_fluxcd_cm" {
  name       = "terraform-fluxcd-values"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = var.flux_namespace

  values = [templatefile("${path.module}/templates/helm_values/terraform_fluxcd_values.yaml.tftpl", {
    soperator_active_checks_override_block = indent(12, local.soperator_activechecks_override_yaml)

    telemetry_enabled  = var.telemetry_enabled
    accounting_enabled = var.accounting_enabled
    iam_tenant_id      = var.iam_tenant_id
    iam_project_id     = var.iam_project_id

    backups_enabled = var.backups_enabled
    backups_config  = var.backups_enabled ? var.backups_config : null

    soperator_helm_repo  = local.helm.repository.slurm
    soperator_image_repo = local.image.repository

    dcgm_job_mapping_enabled = var.dcgm_job_mapping_enabled

    tailscale_enabled       = var.tailscale_enabled
    apparmor_enabled        = var.use_default_apparmor_profile
    enable_soperator_checks = var.enable_soperator_checks

    operator_version = var.operator_version
    operator_feature_gates = join(",", distinct(compact([
      var.slurm_nodesets_enabled ? "NodeSetWorkers=true" : null,
    ])))
    cert_manager_version               = var.cert_manager_version
    k8up_version                       = var.k8up_version
    mariadb_operator_version           = var.mariadb_operator_version
    opentelemetry_collector_version    = var.opentelemetry_collector_version
    prometheus_crds_version            = var.prometheus_crds_version
    security_profiles_operator_version = var.security_profiles_operator_version
    vmstack_version                    = var.vmstack_version
    vmstack_crds_version               = var.vmstack_crds_version
    vmlogs_version                     = var.vmlogs_version
    dcgm_job_map_dir                   = var.dcgm_job_map_dir
    notifier                           = var.soperator_notifier

    name                = var.name
    cluster_name        = var.cluster_name
    region              = var.region
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
      maintenance = var.maintenance

      partition_configuration = {
        slurm_config_type = var.slurm_partition_config_type
        slurm_raw_config  = var.slurm_partition_raw_config
      }

      use_preinstalled_gpu_drivers = var.use_preinstalled_gpu_drivers
      use_cuda13rc                 = var.use_cuda13rc

      slurm_worker_features     = var.slurm_worker_features
      slurm_health_check_config = var.slurm_health_check_config

      k8s_node_filters               = local.node_filters
      maintenance_ignore_node_labels = local.maintenance_ignore_node_labels

      node_local_jail_submounts = var.node_local_jail_submounts
      node_local_image_storage  = var.node_local_image_storage

      jail_submounts = [for submount in var.filestores.jail_submounts : {
        name       = submount.name
        mount_path = submount.mount_path
      }]

      controller_state_on_filestore = var.controller_state_on_filestore

      nfs                    = var.nfs
      nfs_in_k8s             = var.nfs_in_k8s
      nfs_node_group_enabled = var.nfs_node_group_enabled

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
            cpu               = floor(var.resources.controller.cpu_cores - local.resources.munge.cpu - local.resources.kruise_daemon.cpu)
            memory            = floor(var.resources.controller.memory_gibibytes - local.resources.munge.memory - local.resources.kruise_daemon.memory)
            ephemeral_storage = floor(var.resources.controller.ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage)
          }
        }

        worker = {
          size = var.slurm_nodesets_enabled ? 0 : var.node_count.worker[0]
          resources = {
            cpu               = floor(var.resources.worker[0].cpu_cores - local.resources.munge.cpu) - local.resources.kruise_daemon.cpu
            memory            = floor(var.resources.worker[0].memory_gibibytes - local.resources.munge.memory) - local.resources.kruise_daemon.memory
            ephemeral_storage = floor(var.resources.worker[0].ephemeral_storage_gibibytes - local.resources.munge.ephemeral_storage)
            gpus              = var.resources.worker[0].gpus
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
          public_ip                = var.login_public_ip
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
      vm_single           = var.resources_vm_single
      vm_agent            = var.resources_vm_agent
      vm_logs             = var.resources_vm_logs_server
      logs_collector      = var.resources_logs_collector
      jail_logs_collector = var.resources_jail_logs_collector
      events_collector    = var.resources_events_collector
      node_configurator   = local.resources.node_configurator
      slurm_operator      = local.resources.slurm_operator
      slurm_checks        = local.resources.slurm_checks
      dcgm_exporter       = local.resources.dcgm_exporter
      nfs_server          = local.resources.nfs_server
    }

    vm_agent_queue_count = local.vm_agent_queue_count

    slurm_nodesets_enabled    = var.slurm_nodesets_enabled
    slurm_nodesets_partitions = var.slurm_nodesets_partitions
    nodesets                  = var.worker_nodesets

    releases = [
      local_file.flux_release_rendered_nodesets.content,
    ]
  })]
}

resource "helm_release" "soperator_fluxcd_bootstrap" {
  depends_on = [
    helm_release.soperator_fluxcd_cm,
  ]

  name       = "soperator-fluxcd-bootstrap"
  repository = var.operator_stable ? "oci://cr.eu-north1.nebius.cloud/soperator" : "oci://cr.eu-north1.nebius.cloud/soperator-unstable"
  chart      = "helm-soperator-fluxcd-bootstrap"
  version    = var.operator_version
  namespace  = var.flux_namespace

  set {
    name  = "helmRepository.url"
    value = var.operator_stable ? "oci://cr.eu-north1.nebius.cloud/soperator" : "oci://cr.eu-north1.nebius.cloud/soperator-unstable"
  }

  lifecycle {
    ignore_changes = all
  }
}

resource "helm_release" "soperator_fluxcd_ad_hoc_cm" {
  name       = "soperator-fluxcd"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = var.flux_namespace

  values = [templatefile("${path.module}/templates/helm_values/soperator_fluxcd.yaml.tftpl", {})]

  lifecycle {
    ignore_changes = all
  }
}

resource "helm_release" "cm_terraform_soperator_activechecks" {
  name       = "terraform-soperator-activechecks"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw
  namespace  = var.flux_namespace

  values = [templatefile("${path.module}/templates/helm_values/cm_terraform_soperator_activechecks.yaml.tftpl", {})]

  lifecycle {
    ignore_changes = all
  }
}
