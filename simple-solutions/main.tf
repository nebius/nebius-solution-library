module "instance-module" {
  providers = {
    nebius = nebius
  }
  source         = "../modules/instance"
  parent_id      = var.parent_id
  subnet_id      = var.subnet_id
}
