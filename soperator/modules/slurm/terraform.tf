terraform {
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.16.0"
    }
  }
}

module "labels" {
  source = "../labels"
}
