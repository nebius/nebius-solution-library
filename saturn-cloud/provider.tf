provider "nebius" {
  service_account = {
    private_key_file_env = "NB_AUTHKEY_PRIVATE_PATH"
    public_key_id_env    = "NB_AUTHKEY_PUBLIC_ID"
    account_id_env       = "NB_SA_ID"
  }
}

provider "helm" {
  kubernetes = {
    host                   = nebius_mk8s_v1_cluster.saturn_cluster.status.control_plane.endpoints.public_endpoint
    cluster_ca_certificate = nebius_mk8s_v1_cluster.saturn_cluster.status.control_plane.auth.cluster_ca_certificate
    token                  = var.iam_token
  }
}
