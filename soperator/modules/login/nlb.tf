data "kubernetes_nodes" "this" {
  count = var.nlb_used ? 1 : 0

  metadata {
    labels = module.labels.label_group_name_nlb
  }
}

resource "terraform_data" "nlb_node_ip" {
  count = var.nlb_used ? 1 : 0

  depends_on = [
    data.kubernetes_nodes.this
  ]

  triggers_replace = [
    one(one(one(data.kubernetes_nodes.this).nodes).metadata).name
  ]

  input = one([for address in one(one(one(data.kubernetes_nodes.this).nodes).status).addresses :
    address.address
    if address.type == "ExternalIP"
  ])
}
