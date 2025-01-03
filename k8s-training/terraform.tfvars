# Cloud environment and network
tenant_id      = "tenant-e00f3wdfzwfjgbcyfv"
parent_id      = "project-e00pxbakhpc6dy244fn77" # The project-id in this context
subnet_id      = "vpcsubnet-e00q830c4c75nztpv4" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
region         = "eu-north1" # Project region
# ssh_user_name  = "" # Username you want to use to connect to the nodes
# ssh_public_key = {
# key  = "put your public ssh key here" OR
# path = "put path to ssh key here"
# }

# K8s nodes
cpu_nodes_count = 3 # Number of CPU nodes
gpu_nodes_count = 1 # Number of GPU nodes
# cpu_nodes_platform =                 # CPU nodes platofm
# cpu_nodes_preset   =                 # CPU nodes preset
# gpu_nodes_platform =                 # GPU nodes platform
# gpu_nodes_preset   =                 # GPU nodes preset
# infiniband_fabric  =                 # Infiniband fabric name.
enable-k8s-node-group-sa = true

# Observability
enable_grafana    = false  # Enable or disable Grafana deployment with true or false
enable_prometheus = false  # Enable or disable Prometheus deployment with true or false
enable_loki       = false # Enable or disable Loki deployment with true or false
enable_dcgm       = false  # Enable or disable NVIDIA DCGM Exporter Dashboard and Alerting deployment with true or false

## Loki
# loki_access_key_id = "" # See the instruction in README.md on how to create this. Leave empty if you are not deploying Loki.
# loki_secret_key    = "" # See the instruction in README.md on how to create this. Leave empty if you are not deploying Loki.

# Storage
## Filestore - recommended
enable_filestore     = true                       # Enable or disable Filestore integration with true or false
filestore_disk_size  = 100 * (1024 * 1024 * 1024) # Set Filestore disk size in bytes. The multiplication makes it easier to set the size in GB. This would set the size as 100GB
filestore_block_size = 4096                       # Set Filestore block size in bytes

## GlusterFS - legacy
enable_glusterfs            = false                      # Enable or disable GlusterFS integration with true or false
glusterfs_storage_nodes     = 3                          # Set amount of storage nodes in GlusterFS cluster
glusterfs_disk_count_per_vm = 2                          # Set amount of disks per storage node in GlusterFS cluster
glusterfs_disk_size         = 100 * (1024 * 1024 * 1024) # Set disk size in bytes. The multiplication makes it easier to set the size in GB. This would set the size as 100GB

# KubeRay
enable_kuberay           = false # Turn KubeRay to false, otherwise gpu capacity will be consumed by KubeRay cluster
kuberay_min_gpu_replicas = 1
kuberay_max_gpu_replicas = 2
