module "instance-module" {
  providers = {
    nebius = nebius
  }
  source         = "../modules/instance"
  parent_id      = var.parent_id
  subnet_id      = var.subnet_id
  count          = var.instance_count
  instance_name = "instance-${count.index}"
}
