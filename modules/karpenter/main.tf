locals {
  name_prefix      = "karpenter-${var.cluster_name}"
  cpu_image_family = coalesce(var.cpu_nodeclass_image_family, "mk8s-worker-node-v-1-31")
  gpu_image_family = coalesce(var.gpu_nodeclass_image_family, "mk8s-worker-node-v-1-31-cuda12")
}

# Service account for Karpenter to manage Nebius Cloud resources
resource "nebius_iam_v1_service_account" "karpenter-node-sa" {
  name        = local.name_prefix
  parent_id   = var.parent_id
  description = "${local.name_prefix} service account"
}

# We create a group because access permits can only be granted to groups
resource "nebius_iam_v1_group" "karpenter-manager" {
  name      = "${var.parent_id}-${local.name_prefix}-karpenter-manager"
  parent_id = var.tenant_id
}

# Grant project admin access to the project for the karpenter-manager group
resource "nebius_iam_v1_access_permit" "karpenter-manager-project-admin" {
  parent_id   = nebius_iam_v1_group.karpenter-manager.id
  resource_id = var.parent_id
  role        = "admin"
}

# Grant tenant viewer access for the karpenter-manager group
resource "nebius_iam_v1_access_permit" "karpenter-manager-tenant-viewer" {
  parent_id   = nebius_iam_v1_group.karpenter-manager.id
  resource_id = var.tenant_id
  role        = "viewer"
}

# Add service account to the karpenter-manager group
resource "nebius_iam_v1_group_membership" "karpenter-sa-membership" {
  parent_id = nebius_iam_v1_group.karpenter-manager.id
  member_id = nebius_iam_v1_service_account.karpenter-node-sa.id
}
