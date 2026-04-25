# Mk8s cluster name. By default it is "k8s-training"
cluster_name = "k8s-training"

# SSH config
ssh_user_name = "ubuntu" # Username you want to use to connect to the nodes
ssh_public_key = {
  key = "put Nebius Cloud user's public SSH key here"
  # path = "put path to public ssh key here"
}

# K8s nodes
cpu_nodes_fixed_count = 2 # Used only when cpu_nodes_autoscaling.enabled = false
cpu_nodes_autoscaling = {
  enabled = false
  # min_size options:
  # - null: min=max, no scale-down (default, recommended - saves ~10 min on initial provisioning)
  #   it can be changed to a number later if needed.
  # - N: can scale down to N nodes
  min_size = null
  max_size = 4
}
gpu_nodes_fixed_count_per_group = 1 # Number of GPU nodes per group, used only when gpu_nodes_autoscaling.enabled = false
gpu_nodes_autoscaling = {
  enabled = false
  # min_size options:
  # - null: min=max, no scale-down (default, recommended - saves ~10 min on initial provisioning)
  #   it can be changed to a number later if needed.
  # - N: can scale down to N nodes
  min_size = null
  max_size = 1
}
gpu_node_groups = 1 # In case you need more then 100 nodes in cluster you have to put multiple node groups
# CPU platform and presets: https://docs.nebius.com/compute/virtual-machines/types#cpu-configurations
cpu_nodes_platform = "cpu-d3"     # CPU nodes platform
cpu_nodes_preset   = "4vcpu-16gb" # CPU nodes preset
# GPU platform and preset: https://docs.nebius.com/compute/virtual-machines/types#gpu-configurations
gpu_nodes_platform = "gpu-h200-sxm"        # GPU nodes platform: gpu-h100-sxm, gpu-h200-sxm, gpu-b200-sxm
gpu_nodes_preset   = "8gpu-128vcpu-1600gb" # GPU nodes preset: 8gpu-128vcpu-1600gb, 8gpu-128vcpu-1600gb, 8gpu-160vcpu-1792gb
# Infiniband fabrics: https://docs.nebius.com/compute/clusters/gpu#fabrics
infiniband_fabric = "" # Leave empty to disable GPU clustering for RTX6000 deployments or single-node deployments.

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
loki = {
  enabled            = true # Enable or disable Loki deployment with true or false
  replication_factor = 2    # Number of Loki replicas for each log chunk (higher = better availability, more storage/network cost)
}
# Storage
enable_filestore               = false # Enable or disable Filestore integration with true or false
existing_filestore             = ""    # If enable_filestore = true, with this variable we can add existing filestore. Require string, example existing_filestore = "computefilesystem-e00r7z9vfxmg1bk99s"
filestore_disk_size_gibibytes  = 100   # Set Filestore disk size in Gbytes.
filestore_block_size_kibibytes = 4     # Set Filestore block size in bytes
filestore_forbid_deletion      = false # Set to true to protect Terraform-created Filestore from deletion.

# Shared filesystem CSI driver. Enable only when using Shared Filesystem.
# filesystem_csi = {
#   chart_version                       = "0.1.5"
#   namespace                           = "kube-system"
#   make_default_storage_class          = true
#   previous_default_storage_class_name = "compute-csi-default-sc"
# }

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

# Optional Kubernetes RBAC bindings for Kubernetes cluster access.
# Keep disabled until the access model is approved.
# k8s_rbac_bindings = {
#   enabled = true
#   cluster_role_bindings = {
#     nebius_viewer_cluster_admin = {
#       name      = "nebius-cluster-admin"
#       role_name = "cluster-admin"
#       subjects = [
#         {
#           kind      = "Group"
#           name      = "nebius:viewer"
#           api_group = "rbac.authorization.k8s.io"
#         }
#       ]
#     }
#   }
# }

# enable OPA gatekeeper (default: false)
# opa_gatekeeper_enable = true 

# enable binpacking scheduler (default: false)
# binpacking_enable = true

# If binpacking is enabled force it for the default namespace, instead
# of requiring each pod to opt-in using spec.schedulerName
# requires opa_gatekeeper_enable = true
# default: ["default"]
# binpacking_forced_namespaces = [ "default" ]

# must be less than or equalt to API version defaults to cluster version 
# if not defined and it is explicitly defined otherwise it defaults to 1.32.9 (in locals.tf)
# binpacking_kube_sched_ver = "1.32.9"
