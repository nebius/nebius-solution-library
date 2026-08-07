terraform {
  required_providers {
    nebius = {
      source  = "terraform-provider.storage.eu-north1.nebius.cloud/nebius/nebius"
      version = ">= 0.5.196, < 0.6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 3.0.1, < 4.0.0"
    }
  }
}

provider "time" {}

resource "time_static" "start" {}

provider "kubernetes" {
  host                   = module.k8s-training.kube_cluster.endpoints.public_endpoint
  cluster_ca_certificate = module.k8s-training.kube_cluster_ca_certificate
  token                  = var.iam_token
}
