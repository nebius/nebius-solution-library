terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "<3.0.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.5.3"
    }
  }
}

module "labels" {
  source = "../labels"
}
