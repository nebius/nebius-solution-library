module "karpenter" {
  count  = var.enable_karpenter ? 1 : 0
  source = "../modules/karpenter"

  parent_id    = var.parent_id
  tenant_id    = var.tenant_id
  cluster_id   = nebius_mk8s_v1_cluster.k8s-cluster.id
  cluster_name = var.cluster_name
  subnet_id    = var.subnet_id

  k8s_version              = var.k8s_version
  karpenter_version        = var.karpenter_version
  create_default_nodepools = var.karpenter_create_nodepools

  # Image families for NodeClasses (override if default naming doesn't work)
  cpu_nodeclass_image_family = var.karpenter_cpu_image_family
  gpu_nodeclass_image_family = var.karpenter_gpu_image_family

  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
  ]
}
