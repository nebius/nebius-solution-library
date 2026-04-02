# Replicates the previous nebius/eu-north1 configuration

project_id       = ""
subnet_id        = ""
viewers_group_id = ""
iam_token        = ""
region           = "eu-north1"

cluster_name           = "saturn-cluster"
saturn_domain          = ""
saturn_admin_email     = ""
saturn_customer_name   = ""
saturn_bootstrap_token = ""

node_pools = [
  # CPU sizes
  { platform = "cpu-d3", preset = "4vcpu-16gb", max_nodes = 100 },
  { platform = "cpu-d3", preset = "16vcpu-64gb", max_nodes = 100 },
  { platform = "cpu-d3", preset = "64vcpu-256gb", max_nodes = 100 },
  # H100 GPU - 1-GPU
  { platform = "gpu-h100-sxm", preset = "1gpu-16vcpu-200gb", max_nodes = 100 },
  # H100 GPU - 8-GPU (InfiniBand fabric-6)
  { platform = "gpu-h100-sxm", preset = "8gpu-128vcpu-1600gb", max_nodes = 100, infiniband_fabric = "fabric-6" },
  # H200 GPU - 1-GPU
  { platform = "gpu-h200-sxm", preset = "1gpu-16vcpu-200gb", max_nodes = 100 },
  # H200 GPU - 8-GPU (InfiniBand fabric-7)
  { platform = "gpu-h200-sxm", preset = "8gpu-128vcpu-1600gb", max_nodes = 100, infiniband_fabric = "fabric-7" },
]
