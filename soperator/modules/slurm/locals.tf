locals {
  helm = {
    repository = {
      slurm   = "oci://cr.eu-north1.nebius.cloud/soperator${!var.operator_stable ? "-unstable" : ""}"
      mariadb = "https://helm.mariadb.com/mariadb-operator"
      raw     = "https://bedag.github.io/helm-charts/"
      spo     = "oci://cr.eu-north1.nebius.cloud/e00xdc03sb7gpqfd0a/security-profiles-operator"
    }

    chart = {
      slurm_cluster         = "slurm-cluster"
      slurm_cluster_storage = "slurm-cluster-storage"
      slurm_operator_crds   = "soperator-crds"
      raw                   = "raw"
      spo                   = "security-profiles-operator"

      operator = {
        slurm   = "soperator"
        mariadb = "mariadb-operator"
      }
    }

    version = {
      slurm   = var.operator_version
      mariadb = "0.31.0"
      raw     = "2.0.0"
      spo     = "0.8.4"
    }
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
  }

  resources = {
    munge = {
      cpu               = 0.1
      memory            = 0.5
      ephemeral_storage = 5
    }
    exporter = {
      cpu               = 0.25
      memory            = 0.25
      ephemeral_storage = 0.5
    }
    rest = {
      cpu               = 1
      memory            = 1
      ephemeral_storage = 0.5
    }
    mariadb = {
      cpu               = 1
      memory            = 1
      ephemeral_storage = 5
    }
  }

  slurm_node_extra = "\\\"{ \\\\\\\"monitoring\\\\\\\": \\\\\\\"https://console.eu.nebius.com/${var.iam_project_id}/compute/instances/$INSTANCE_ID/monitoring\\\\\\\" }\\\""
}
