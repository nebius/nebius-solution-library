resource "helm_release" "karpenter" {
  name      = "karpenter"
  namespace = "karpenter"

  repository = "oci://cr.eu-north1.nebius.cloud/e00w67thrrz5nhprjm/helm"

  chart   = "karpenter"
  version = var.karpenter_version

  create_namespace = true
  atomic           = true

  values = [
    file("${path.module}/values.yaml")
  ]

  set = [
    {
      name  = "controller.image.tag"
      value = var.karpenter_version
    },
    {
      name  = "controller.settings.parentID"
      value = var.parent_id
    },
    {
      name  = "controller.settings.clusterID"
      value = var.cluster_id
    }
  ]

  depends_on = [
    nebius_iam_v1_group_membership.karpenter-sa-membership
  ]
}
