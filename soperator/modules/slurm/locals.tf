locals {
  helm = {
    repository = {
      slurm   = "oci://cr.eu-north1.nebius.cloud/soperator"
      mariadb = "https://helm.mariadb.com/mariadb-operator"
    }

    chart = {
      slurm_cluster         = "slurm-cluster"
      slurm_cluster_storage = "slurm-cluster-storage"
      slurm_operator_crds   = "soperator-crds"

      operator = {
        slurm   = "soperator"
        mariadb = "mariadb-operator"
      }
    }

    version = {
      slurm   = var.operator_version
      mariadb = "0.31.0"
    }
  }
}
