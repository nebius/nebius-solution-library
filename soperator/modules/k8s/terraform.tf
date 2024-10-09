terraform {
  required_providers {
    nebius = {
      source = "terraform-provider-nebius.storage.ai.nebius.cloud/nebius/nebius"
    }

    units = {
      source = "dstaroff/units"
    }
  }
}

module "labels" {
  source = "../labels"
}
