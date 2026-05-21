data "nebius_vpc_v1_subnet" "bastion" {
  count = var.enable_bastion_security_group ? 1 : 0

  id = var.subnet_id
}

resource "terraform_data" "validate_bastion_security_group_inputs" {
  count = var.enable_bastion_security_group ? 1 : 0

  input = local.bastion_ssh_source_cidrs

  lifecycle {
    precondition {
      condition     = length(local.bastion_ssh_source_cidrs) > 0
      error_message = "bastion_allowed_ssh_cidrs must contain at least one CIDR when enable_bastion_security_group is true."
    }
  }
}

module "bastion_security_group" {
  count = var.enable_bastion_security_group ? 1 : 0

  source = "../modules/security-group"

  parent_id  = var.parent_id
  network_id = data.nebius_vpc_v1_subnet.bastion[0].network_id
  name       = var.bastion_security_group_name

  labels = {
    "library-solution" = "bastion"
  }

  allow_unrestricted_ingress_rules = var.bastion_allow_unrestricted_ingress_rules
  ingress_rules                    = merge(local.bastion_default_ingress_rules, var.bastion_extra_ingress_rules)
  egress_rules                     = merge(local.bastion_default_egress_rules, var.bastion_extra_egress_rules)

  depends_on = [
    terraform_data.validate_bastion_security_group_inputs
  ]
}
