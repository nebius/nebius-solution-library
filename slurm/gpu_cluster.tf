
resource "nebius_compute_v1_gpu_cluster" "gpu-cluster-slurm" {
  parent_id         = var.parent_id
  name              = "gpu-cluster-slurm"
  infiniband_fabric = var.infiniband_fabric
}
