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

# Karpenter requires special service account for the system cpu nodegroup
#
resource "nebius_iam_v1_service_account" "karpenter_system_sa" {
  count     = var.enable_karpenter ? 1 : 0
  name      = "${var.cluster_name}-karpenter-manager"
  parent_id = var.parent_id
  description = "Service account for the karpenter system nodegroup"
}

# We create a group because access permits can only be granted to groups
resource "nebius_iam_v1_group" "karpenter_manager" {
  count       = var.enable_karpenter ? 1 : 0
  name        = "${var.cluster_name}-karpenter-manager"
  parent_id   = var.tenant_id
}

# Grant project admin access to the project for the karpenter-manager group
resource "nebius_iam_v1_access_permit" "karpenter_manager_project_admin" {
  count       = var.enable_karpenter ? 1 : 0
  parent_id   = nebius_iam_v1_group.karpenter_manager[count.index].id
  resource_id = var.parent_id
  role        = "admin"
}

# Grant project viewer access to the tenant for the karpenter-manager group
resource "nebius_iam_v1_access_permit" "karpenter_manager_tenant_viewer" {
  count       = var.enable_karpenter ? 1 : 0
  parent_id   = nebius_iam_v1_group.karpenter_manager[count.index].id
  resource_id = var.tenant_id
  role        = "viewer"
}


# Add service account to the group
resource "nebius_iam_v1_group_membership" "karpenter_manager_membership" {
  count     = var.enable_karpenter ? 1 : 0
  parent_id = nebius_iam_v1_group.karpenter_manager[count.index].id
  member_id = nebius_iam_v1_service_account.karpenter_system_sa[count.index].id
}
