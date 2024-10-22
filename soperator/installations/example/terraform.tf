terraform {
  required_version = ">=1.8.0"

  required_providers {
    nebius = {
      source  = "terraform-provider-nebius.storage.ai.nebius.cloud/nebius/nebius"
      version = "0.4.4"
    }

    units = {
      source  = "dstaroff/units"
      version = ">=1.1.1"
    }

    kubernetes = {
      source = "hashicorp/kubernetes"
    }

    helm = {
      source = "hashicorp/helm"
    }
  }
}

provider "nebius" {
  domain = "api.eu.nebius.cloud:443"
}

provider "units" {}

provider "kubernetes" {
  host                   = module.k8s.control_plane.public_endpoint
  cluster_ca_certificate = module.k8s.control_plane.cluster_ca_certificate
  token                  = var.iam_token
}

provider "helm" {
  kubernetes {
    host                   = module.k8s.control_plane.public_endpoint
    cluster_ca_certificate = module.k8s.control_plane.cluster_ca_certificate
    token                  = var.iam_token
  }
}

module "resources" {
  source = "../../modules/available_resources"
}
