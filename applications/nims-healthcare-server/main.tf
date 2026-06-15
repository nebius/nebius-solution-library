module "cluster" {
  source = "../../k8s-training"

  tenant_id = var.tenant_id
  parent_id = var.parent_id
  region    = var.region
  subnet_id = var.subnet_id

  cluster_name = var.cluster_name
  iam_token    = var.iam_token

  ssh_user_name     = var.ssh_user_name
  ssh_public_key    = var.ssh_public_key
  k8s_version       = var.k8s_version
  etcd_cluster_size = var.etcd_cluster_size

  cpu_nodes_fixed_count = var.cpu_nodes_fixed_count
  cpu_nodes_platform    = var.cpu_nodes_platform
  cpu_nodes_preset      = var.cpu_nodes_preset

  gpu_node_groups                 = var.gpu_node_groups
  gpu_nodes_fixed_count_per_group = var.gpu_nodes_fixed_count_per_group
  gpu_nodes_platform              = var.gpu_nodes_platform
  gpu_nodes_preset                = var.gpu_nodes_preset
  gpu_nodes_driverfull_image      = true
  gpu_disk_size                   = var.gpu_disk_size

  enable_filestore              = true
  existing_filestore            = ""
  filestore_disk_size_gibibytes = var.filestore_disk_size_gibibytes
  filestore_mount_path          = var.filestore_mount_path
  filestore_forbid_deletion     = var.filestore_forbid_deletion
  filesystem_csi                = var.filesystem_csi

  enable_prometheus        = true
  enable_nebius_o11y_agent = true
  enable_grafana           = false
  collectK8sClusterMetrics = true
  loki                     = { enabled = false, replication_factor = 1 }

  enable_k8s_node_group_sa = false
  enable_kuberay_cluster   = false
  enable_kuberay_service   = false
  enable_opa_gatekeeper    = false
  enable_egress_gateway    = false
  infiniband_fabric        = ""
}

module "nims" {
  source = "../../modules/nims"

  providers = {
    kubernetes = kubernetes.nims
  }

  parent_id              = var.parent_id
  namespace              = var.namespace
  ngc_key                = var.ngc_key
  ngc_key_revision       = var.ngc_key_revision
  nim_cache_host_path    = "${trimsuffix(var.filestore_mount_path, "/")}/nim"
  nim_resource_overrides = var.nim_resource_overrides

  openfold3  = true
  boltz2     = true
  msa_search = true
  openfold2  = true

  genmol   = true
  molmim   = true
  diffdock = true

  proteinmpnn = true
  rfdiffusion = true

  evo2_40b                    = var.enable_two_gpu_nims
  qwen3_next_80b_a3b_instruct = var.enable_two_gpu_nims

  depends_on = [
    module.cluster,
  ]
}
