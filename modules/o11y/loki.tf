# FIXME uncomment when SA and SA_access_bindings are added to public api
#resource "nebius_iam_v1_service_account" "sa-tf" {
#  count       = var.o11y.loki ? 1 : 0
#  parent_id   = var.parent_id
#  description = "just testing terraform"
#  name        = "test-sa-tf"
#}
#resource "nebius_iam_v1_access_binding" "sa-editor-tf" {
#  depends_on  = [nebius_iam_v1_service_account.sa-tf[0]]
#  parent_id   = var.parent_id
#  subject_id  = nebius_iam_v1_service_account.sa-tf[0].id
#  resource_id = "test-sa-editor-tf"
#  role        = "editor"
#}
// Use keys to create bucket

locals {
  # Get the number of nodes in the cluster
  node_count = var.cpu_nodes_count + var.gpu_nodes_count

  # Calculate replication factor as a fraction of node count
  # For example, 5% of node count (0.05)
  replication_fraction = 0.05

  # Calculate the raw replication value
  raw_replication = local.node_count * local.replication_fraction

  # Round to nearest whole number (since replicas must be integers)
  # Ensure at least 1 replica and set a minimum for resiliency (e.g., 2)
  replication_factor = var.o11y.loki.replication_factor != null ? var.o11y.loki.replication_factor : max(2, ceil(local.raw_replication))
}

resource "random_string" "loki_unique_id" {
  count   = var.o11y.loki.enabled ? 1 : 0
  length  = 2
  upper   = false
  lower   = true
  numeric = true
  special = false
}

resource "nebius_storage_v1_bucket" "loki-bucket-chunks" {
  count             = var.o11y.loki.enabled ? 1 : 0
  parent_id         = var.parent_id
  name              = "loki-${var.cluster_id}-${random_string.loki_unique_id[0].result}-chunks"
  versioning_policy = "DISABLED"
}

resource "nebius_storage_v1_bucket" "loki-bucket-ruler" {
  count             = var.o11y.loki.enabled ? 1 : 0
  parent_id         = var.parent_id
  name              = "loki-${var.cluster_id}-${random_string.loki_unique_id[0].result}-ruler"
  versioning_policy = "DISABLED"
}

resource "nebius_storage_v1_bucket" "loki-bucket-admin" {
  count             = var.o11y.loki.enabled ? 1 : 0
  parent_id         = var.parent_id
  name              = "loki-${var.cluster_id}-${random_string.loki_unique_id[0].result}-admin"
  versioning_policy = "DISABLED"
}

resource "nebius_applications_v1alpha1_k8s_release" "loki" {
  count = var.o11y.loki.enabled ? 1 : 0

  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "loki"
  namespace        = var.namespace
  product_slug     = "nebius/loki"

  set = {
    "loki.storage.bucketPrefix" : "loki-${var.cluster_id}-${random_string.loki_unique_id[0].result}",
    "loki.storage.s3.region" : var.o11y.loki.region,
    "loki.commonConfig.replication_factor" : local.replication_factor,
    # FIXME S3 keys are not implemented in the public TF yet
    "loki.storage.s3.accessKeyId" : var.o11y.loki.aws_access_key_id,
    "loki.storage.s3.secretAccessKey" : var.o11y.loki.secret_key
  }

}