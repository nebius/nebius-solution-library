locals {
  node_ssh_access = {
    enabled = length(var.node_ssh_access_users) > 0
    cloud_init_data = templatefile("${path.module}/templates/cloud_init.yaml.tftpl", {
      ssh_users = var.node_ssh_access_users
    })
  }
}
