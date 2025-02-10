terraform {
  required_providers {
    nebius = {
      source = "terraform-provider-nebius.storage.ai.nebius.cloud/nebius/nebius"
    }
  }
}

provider "nebius" {
  domain = "api.eu.nebius.cloud:443"
}
