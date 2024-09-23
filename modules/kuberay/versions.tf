terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
    }
    nebius = {
      source  = "terraform-provider-nebius.storage.ai.nebius.cloud/nebius/nebius"
    }
  }
}