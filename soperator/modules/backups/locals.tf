locals {
  helm = {
    repository = {
      raw  = "https://bedag.github.io/helm-charts/"
      k8up = "https://k8up-io.github.io/k8up"
    }

    chart = {
      raw       = "raw"
      k8up      = "k8up"
      k8up_crds = "k8up-crds"
    }

    version = {
      raw  = "2.0.0"
      k8up = "4.8.3"
    }
  }

  secret_name   = "jail-backup"
  schedule_name = "jail-backup"
}
