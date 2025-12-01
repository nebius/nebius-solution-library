ssh_user_name: ubuntu
# Public key of the user
ssh_public_key: 
vpc_id: 
k8s_cluster:
  cpu_nodes_count: 1
  gpu_nodes_count_per_group: 1
  gpu_node_groups: 1
  cpu_nodes_platform: "cpu-d3"
  cpu_nodes_preset: "4vcpu-16gb"
  gpu_nodes_platform: "gpu-h100-sxm"
  gpu_nodes_preset: "1gpu-16vcpu-200gb"
  enable_gpu_cluster: true
  infiniband_fabric: "fabric-2"
  gpu_nodes_driverfull_image: true
  enable_k8s_node_group_sa: true
  enable_prometheus: true
  enable_loki: false
  loki_access_key_id: ""
  loki_secret_key: ""
dstack:
  replicaCount: 2
