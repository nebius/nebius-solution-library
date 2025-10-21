module "k8s-training" {
  source = "../../k8s-training"

  tenant_id = var.tenant_id
  parent_id = var.parent_id
  subnet_id = var.subnet_id
  region    = var.region
  iam_token = var.iam_token

  ssh_user_name = local.config.ssh_user_name
  ssh_public_key = {
    key = local.config.ssh_public_key
  }
  cpu_nodes_count            = local.config.k8s_cluster.cpu_nodes_count
  gpu_nodes_count_per_group  = local.config.k8s_cluster.gpu_nodes_count_per_group
  gpu_node_groups            = local.config.k8s_cluster.gpu_node_groups
  cpu_nodes_platform         = local.config.k8s_cluster.cpu_nodes_platform
  cpu_nodes_preset           = local.config.k8s_cluster.cpu_nodes_preset
  gpu_nodes_platform         = local.config.k8s_cluster.gpu_nodes_platform
  gpu_nodes_preset           = local.config.k8s_cluster.gpu_nodes_preset
  enable_gpu_cluster         = local.config.k8s_cluster.enable_gpu_cluster
  infiniband_fabric          = local.config.k8s_cluster.infiniband_fabric
  gpu_nodes_driverfull_image = local.config.k8s_cluster.gpu_nodes_driverfull_image
  enable_k8s_node_group_sa   = local.config.k8s_cluster.enable_k8s_node_group_sa
  enable_prometheus          = local.config.k8s_cluster.enable_prometheus
  enable_loki                = local.config.k8s_cluster.enable_loki
  loki_access_key_id         = local.config.k8s_cluster.loki_access_key_id
  loki_secret_key            = local.config.k8s_cluster.loki_secret_key
}

resource "nebius_applications_v1alpha1_k8s_release" "this" {
  cluster_id = module.k8s-training.kube_cluster.id
  parent_id  = var.parent_id

  application_name = "anyscale-operator"
  namespace        = "anyscale-operator"
  product_slug     = "nebius/anyscale-operator"

  set = {
    "cloudDeploymentId" : local.config.anyscale.cloud_deployment_id,
    "anyscaleCliToken" : local.config.anyscale.anyscale_cli_token,
    "aws.objectStorage.endpoint_url" : "https://storage.${var.region}.nebius.cloud:443",
    "aws.credentialSecret.accessKeyId" : nebius_iam_v2_access_key.anyscale_bucket_key.status.aws_access_key_id,
    "aws.credentialSecret.secretAccessKey" : nebius_iam_v2_access_key.anyscale_bucket_key.status.secret
  }

  depends_on = [
    module.k8s-training
  ]
}
