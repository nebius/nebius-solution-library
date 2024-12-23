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

resource "terraform_data" "kubectl_cluster_context" {
  depends_on = [
    nebius_mk8s_v1_cluster.this
  ]

  triggers_replace = [
    nebius_mk8s_v1_cluster.this.id,
    timestamp(),
  ]

  provisioner "local-exec" {
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command = join(
      " ",
      [
        "nebius", "mk8s", "cluster", "get-credentials",
        "--context-name", local.context_name,
        "--external",
        "--force",
        "--id", nebius_mk8s_v1_cluster.this.id
      ]
    )
  }
}
