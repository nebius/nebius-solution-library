# Mk8s cluster name. By default it is "k8s-training"
cluster_name = "k8s-training"

# SSH config
ssh_user_name = "ubuntu" # Username you want to use to connect to the nodes
ssh_public_key = {
  key = "put customers public ssh key here"
  # path = "put path to public ssh key here"
}

# K8s nodes
cpu_nodes_count           = 2 # Number of CPU nodes
gpu_nodes_count_per_group = 2 # Number of GPU nodes per group
gpu_node_groups           = 1 # In case you need more then 100 nodes in cluster you have to put multiple node groups
# CPU platform and presets: https://docs.nebius.com/compute/virtual-machines/types#cpu-configurations
cpu_nodes_platform = "cpu-d3"     # CPU nodes platform
cpu_nodes_preset   = "4vcpu-16gb" # CPU nodes preset
# GPU platform and preset: https://docs.nebius.com/compute/virtual-machines/types#gpu-configurations
gpu_nodes_platform = "gpu-h200-sxm"        # GPU nodes platform: gpu-h100-sxm, gpu-h200-sxm, gpu-b200-sxm
gpu_nodes_preset   = "8gpu-128vcpu-1600gb" # GPU nodes preset: 8gpu-128vcpu-1600gb, 8gpu-128vcpu-1600gb, 8gpu-160vcpu-1792gb
# Infiniband fabrics: https://docs.nebius.com/compute/clusters/gpu#fabrics
infiniband_fabric = "" # Infiniband fabric name

gpu_nodes_driverfull_image = true
enable_k8s_node_group_sa   = true
enable_egress_gateway      = false
cpu_nodes_preemptible      = false
gpu_nodes_preemptible      = false

cpu_nodes_public_ips         = false
gpu_nodes_public_ips         = false
mk8s_cluster_public_endpoint = true # Set it to FALSE only in case if you've deployed the [bastion](https://github.com/nebius/nebius-solutions-library/blob/main/bastion/README.md)
# host first, and you are deploying cluster from the bastion instance

# MIG configuration
# mig_strategy =        # If set, possible values include 'single', 'mixed', 'none'
# mig_parted_config =   # If set, value will be checked against allowed for the selected 'gpu_nodes_platform'

# Observability by Nebius
enable_nebius_o11y_agent = true # Enable or disable Nebius Observability Agent deployment with true or false
enable_grafana           = true # Enable or disable Grafana® solution by Nebius with true or false

# Local Observability installation
enable_prometheus = false # Enable or disable Prometheus and Grafana deployment with true or false
enable_loki       = false # Enable or disable Loki deployment with true or false

# Storage
enable_filestore               = false # Enable or disable Filestore integration with true or false
existing_filestore             = ""    # If enable_filestore = true, with this variable we can add existing filestore. Require string, example existing_filestore = "computefilesystem-e00r7z9vfxmg1bk99s"
filestore_disk_size_gibibytes  = 100   # Set Filestore disk size in Gbytes.
filestore_block_size_kibibytes = 4     # Set Filestore block size in bytes

# KubeRay Cluster
# for GPU isolation to work with kuberay, gpu_nodes_driverfull_image must be set 
# to false.  This is because we enable acess to infiniband via securityContext.privileged
enable_kuberay_cluster = false # Turn KubeRay to false, otherwise gpu capacity will be consumed by KubeRay cluster

#kuberay CPU worker setup
# if you have no CPU only nodes, set these to zero
# kuberay_cpu_worker_image = ""  # set default CPU worker can leave it commented out in most cases
kuberay_min_cpu_replicas = 1
kuberay_max_cpu_replicas = 2
# kuberay_cpu_resources = {
#   cpus = 2
#   memory = 4  # memory allocation in gigabytes
# }

#kuberay GPU worker pod setup
# kuberay_gpu_worker_image = "" # set default gpu worker image see ../modules/kuberay/README.md for more info
kuberay_min_gpu_replicas = 2
kuberay_max_gpu_replicas = 8
# kuberay_gpu_resources = {
#   cpus = 16
#   gpus = 1
#   memory = 150  # memory allocation in gigabytes
# }

# KubeRay Service
# Enable to deploy KubeRay Operator with RayService CR 
enable_kuberay_service = false

