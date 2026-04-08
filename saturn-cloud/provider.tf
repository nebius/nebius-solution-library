provider "nebius" {
  domain = "api.${var.region}.nebius.cloud:443"
}

provider "helm" {
  kubernetes = {
    host                   = nebius_mk8s_v1_cluster.saturn_cluster.status.control_plane.endpoints.public_endpoint
    cluster_ca_certificate = nebius_mk8s_v1_cluster.saturn_cluster.status.control_plane.auth.cluster_ca_certificate
    token                  = var.iam_token
  }
}
