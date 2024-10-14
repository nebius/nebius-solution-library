# region NLB

data "kubernetes_nodes" "this" {
  count = var.nlb_used ? 1 : 0

  metadata {
    labels = module.labels.label_group_name_nlb
  }
}

resource "terraform_data" "nlb_node_address" {
  count = var.nlb_used ? 1 : 0

  input = one([for address in one(one(one(data.kubernetes_nodes.this).nodes).status).addresses :
    address.address
    if address.type == "ExternalIP"
  ])
}

# endregion NLB

# region LB

data "kubernetes_service" "slurm_login" {
  count = !var.nlb_used ? 1 : 0

  metadata {
    namespace = var.slurm_cluster_name
    name      = "${var.slurm_cluster_name}-login-svc"
  }
}

resource "terraform_data" "lb_address" {
  count = !var.nlb_used ? 1 : 0

  input = one(one(one(one(data.kubernetes_service.slurm_login).status).load_balancer).ingress).ip

  lifecycle {
    precondition {
      condition = (data.kubernetes_service.slurm_login == null ? false
        : (length(one(data.kubernetes_service.slurm_login).status) == 0 ? false
          : (length(one(one(data.kubernetes_service.slurm_login).status).load_balancer) == 0 ? false
            : (length(one(one(one(data.kubernetes_service.slurm_login).status).load_balancer).ingress) == 0 ? false
              : (one(one(one(one(data.kubernetes_service.slurm_login).status).load_balancer).ingress).ip == "" ? false
                : true
              )
            )
          )
        )
      )

      error_message = "Slurm Login service is not yet assigned to any IP."
    }
  }
}

# endregion LB

locals {
  ip = (
    var.nlb_used
    ? one(terraform_data.nlb_node_address).output
    : one(terraform_data.lb_address).output
  )
}

resource "local_file" "this" {
  filename        = "${path.root}/login.sh"
  file_permission = "0774"
  content = templatefile("${path.module}/templates/login.sh.tftpl", {
    address = local.ip
  })
}
