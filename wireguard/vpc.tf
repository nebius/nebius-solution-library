resource "nebius_vpc_v1_allocation" "wireguard-ip-allocation" {
  count     = local.public_ip_allocation ? 1 : 0
  parent_id = var.parent_id
  name      = "wireguard-ip-allocation"
  ipv4_public = {
    subnet_id = var.subnet_id
  }
}
