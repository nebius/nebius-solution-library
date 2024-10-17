resource "terraform_data" "connection_ip" {
  depends_on = [
    terraform_data.nlb_node_ip,
    terraform_data.lb_service_ip,
  ]

  triggers_replace = [
    terraform_data.nlb_node_ip,
    terraform_data.lb_service_ip,
  ]

  input = (
    var.nlb_used
    ? one(terraform_data.nlb_node_ip).output
    : one(terraform_data.lb_service_ip).output
  )
}

resource "local_file" "this" {
  depends_on = [
    terraform_data.connection_ip,
  ]

  filename        = "${path.root}/login.sh"
  file_permission = "0774"
  content = templatefile("${path.module}/templates/login.sh.tftpl", {
    address = terraform_data.connection_ip.output
  })
}
