data "units_data_size" "k8s_ephemeral_storage_reserve" {
  gibibytes = 48
}

locals {
  reserve = {
    cpu = {
      coefficient = 1
      count       = 1
    }
    ram = {
      coefficient = 0.95
      count       = 2
    }
    ephemeral_storage = {
      coefficient = 0.85
      count       = data.units_data_size.k8s_ephemeral_storage_reserve
    }
  }
}
