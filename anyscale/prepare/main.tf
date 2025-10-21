data "nebius_vpc_v1_subnet" "subnet" {
  id = var.subnet_id
}

module "nfs-server" {
  source = "../../nfs-server"

  providers = {
    nebius = nebius
  }

  parent_id = var.parent_id
  subnet_id = var.subnet_id
  region    = var.region

  ssh_user_name   = local.config.ssh_user_name
  ssh_public_keys = [local.config.ssh_public_key]

  nfs_ip_range = try(flatten(data.nebius_vpc_v1_subnet.subnet.ipv4_private_pools.pools)[0].cidr, "")

  cpu_nodes_platform = local.config.nfs_server.cpu_nodes_platform
  cpu_nodes_preset   = local.config.nfs_server.cpu_nodes_preset
  nfs_size           = local.config.nfs_server.nfs_size * 1024 * 1024 * 1024
}

resource "nebius_storage_v1_bucket" "anyscale" {
  parent_id         = var.parent_id
  name              = join("-", ["anyscale", local.release-suffix])
  versioning_policy = "DISABLED"
}
