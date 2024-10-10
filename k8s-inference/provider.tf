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

provider "helm" {
  kubernetes {
    host                   = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.endpoints.public_endpoint
    cluster_ca_certificate = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.auth.cluster_ca_certificate
    token                  = var.iam_token
  }
}

provider "kubernetes" {
  host                   = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.endpoints.public_endpoint
  cluster_ca_certificate = nebius_mk8s_v1_cluster.k8s-cluster.status.control_plane.auth.cluster_ca_certificate
  token                  = var.iam_token
}
