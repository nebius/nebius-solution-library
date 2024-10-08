locals {
  helm = {
    repository = "cr.nemax.nebius.cloud/yc-marketplace/nebius"
    chart = {
      operator = {
        network = {
          name    = "network-operator"
          version = "24.4.0"
        }
        gpu = {
          name    = "gpu-operator"
          version = "v24.3.0"
        }
      }
    }
  }
}
