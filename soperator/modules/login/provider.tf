terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 3.0.1, < 4.0.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.5.3, < 3.0.0"
    }
  }
}

module "labels" {
  source = "../labels"
}
