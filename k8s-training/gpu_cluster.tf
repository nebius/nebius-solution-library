resource "nebius_compute_v1_gpu_cluster" "fabric_2" {
  infiniband_fabric = var.infiniband_fabric
  parent_id         = var.parent_id
  name              = join("-", [var.infiniband_fabric, local.release-suffix])
}
