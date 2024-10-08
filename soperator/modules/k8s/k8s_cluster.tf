resource "nebius_mk8s_v1_cluster" "this" {
  parent_id = var.iam_project_id

  name = var.name

  control_plane = {
    subnet_id = var.vpc_subnet_id

    version = var.k8s_version
    endpoints = {
      public_endpoint = {}
    }

    etcd_cluster_size = var.etcd_cluster_size
  }

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}
