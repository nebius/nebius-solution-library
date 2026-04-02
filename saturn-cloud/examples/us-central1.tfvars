# Replicates the previous nebius/us-central1 configuration

project_id       = "project-u00f9898pr00qmxch9byhe"
subnet_id        = "vpcsubnet-u00z0n6raqyjvjdv1d"
viewers_group_id = "group-e00hzrbenwh3fmggny"
iam_token        = ""
region           = "us-central1"

cluster_name           = "saturn-cluster-nebius-demo"
saturn_domain          = "nebius-us.saturnenterprise.io"
saturn_admin_email     = "hugo+nebius-us@saturncloud.io"
saturn_customer_name   = "nebius-us"
saturn_bootstrap_token = ""

node_pools = [
  # CPU sizes
  { platform = "cpu-d3", preset = "4vcpu-16gb", max_nodes = 100 },
  { platform = "cpu-d3", preset = "16vcpu-64gb", max_nodes = 100 },
  { platform = "cpu-d3", preset = "64vcpu-256gb", max_nodes = 100 },
  # H200 GPU - 1-GPU
  { platform = "gpu-h200-sxm", preset = "1gpu-16vcpu-200gb", max_nodes = 100 },
  # H200 GPU - 8-GPU (InfiniBand us-central1-a)
  { platform = "gpu-h200-sxm", preset = "8gpu-128vcpu-1600gb", max_nodes = 100, infiniband_fabric = "us-central1-a" },
]
