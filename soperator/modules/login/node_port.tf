data "kubernetes_nodes" "this" {
  count = var.node_port.used ? 1 : 0

  metadata {
    labels = module.labels.label_nodeset_login
  }
}

locals {
  first_login_node = (var.node_port.used
    ? data.kubernetes_nodes.this[0].nodes[0]
    : null
  )
}

resource "terraform_data" "login_node_ip" {
  count = var.node_port.used ? 1 : 0

  depends_on = [
    data.kubernetes_nodes.this
  ]

  triggers_replace = [
    one(local.first_login_node.metadata).name
  ]

  input = one([for address in one(local.first_login_node.status).addresses :
    address.address
    if address.type == "ExternalIP"
  ])
}
