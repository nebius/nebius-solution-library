terraform {
  required_providers {
    helm = {
      source = "hashicorp/helm"
    }
  }
}

module "labels" {
  source = "../labels"
}
