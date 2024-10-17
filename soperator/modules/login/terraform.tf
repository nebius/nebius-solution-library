terraform {
  required_providers {
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
    local = {
      source = "hashicorp/local"
    }
  }
}

module "labels" {
  source = "../labels"
}
