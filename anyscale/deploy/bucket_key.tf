data "nebius_iam_v1_group" "editors" {
  name      = "editors"
  parent_id = var.tenant_id
}

resource "nebius_iam_v1_service_account" "anyscale_bucket_sa" {
  parent_id = var.parent_id
  name      = join("-", [module.k8s-training.kube_cluster.name, "anyscale-sa"])
  depends_on = [
    module.k8s-training
  ]
}

resource "nebius_iam_v1_group_membership" "anyscale_bucket_sa-editor" {
  parent_id = data.nebius_iam_v1_group.editors.id
  member_id = nebius_iam_v1_service_account.anyscale_bucket_sa.id
}

resource "nebius_iam_v2_access_key" "anyscale_bucket_key" {
  parent_id   = var.parent_id
  name        = "anyscale-s3-bucket-key"
  description = "Access key for Anyscale bucket"
  account = {
    service_account = {
      id = nebius_iam_v1_service_account.anyscale_bucket_sa.id
    }
  }
}
