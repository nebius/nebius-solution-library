# Saturn Cloud configuration for Nebius
#
# Before running terraform, source environment.sh to set Nebius infrastructure variables:
#   source environment.sh

############################
# Saturn Cloud configuration
############################

cluster_name           = "saturn-cluster"
saturn_domain          = "example.saturnenterprise.io"
saturn_admin_email     = "admin@example.com"
saturn_customer_name   = "my-org"
saturn_bootstrap_token = ""

# Uncomment to pin a specific chart version (default: latest)
helm_chart_version = "2026.02.01-85"

############################
# Node pools
############################
# The default includes CPU sizes + H200 1-GPU. Customize as needed.
# 8-GPU presets require infiniband_fabric (obtain from Nebius support).

# node_pools = [
#   # CPU sizes
#   { platform = "cpu-d3", preset = "4vcpu-16gb" },
#   { platform = "cpu-d3", preset = "16vcpu-64gb" },
#   { platform = "cpu-d3", preset = "64vcpu-256gb" },
#   # GPU - H200 1-GPU
#   { platform = "gpu-h200-sxm", preset = "1gpu-16vcpu-200gb" },
#   # GPU - H200 8-GPU (requires InfiniBand fabric from Nebius support)
#   { platform = "gpu-h200-sxm", preset = "8gpu-128vcpu-1600gb", infiniband_fabric = "fabric-7" },
# ]

############################
# Shared Filesystem (filestore)
############################
# A Nebius shared filesystem (ReadWriteMany) is created by default.
# Set enable_filestore = false to opt out.

# enable_filestore              = true   # Set to false to skip creating a shared filesystem
# existing_filestore            = ""     # Use an existing filestore ID, or leave empty to create a new one
# filestore_disk_size_gibibytes = 100    # Size of the shared filesystem in GiB (fixed, does not auto-expand)
