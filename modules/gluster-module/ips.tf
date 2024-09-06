resource "nebius_vpc_v1alpha1_allocation" "glusterfs" {
  count     = var.storage_nodes
  parent_id = var.parent_id
  name      = "glusterfs-${count.index}"
  ipv4_private = {
    subnet_id = var.subnet_id
  }
}