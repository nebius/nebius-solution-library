terraform {
  required_providers {
    nebius = {
      source = "terraform-provider.storage.eu-north1.nebius.cloud/nebius/nebius"
    }
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
    units = {
      source  = "dstaroff/units"
      version = ">=1.1.1"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = ">=1.19.0"
    }
  }
}

provider "nebius" {
  domain = "api.eu.nebius.cloud:443"
}

provider "kubernetes" {
  alias                  = "nims"
  host                   = module.cluster.kube_cluster.endpoints.public_endpoint
  cluster_ca_certificate = nonsensitive(module.cluster.kube_cluster_ca_certificate)
  token                  = var.iam_token
}
