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

resource "random_string" "loki_unique_id" {
  count   = var.o11y.loki.enabled ? 1 : 0
  length  = 8
  upper   = false
  lower   = true
  numeric = true
  special = false
}


resource "nebius_storage_v1_bucket" "loki-bucket" {
  count             = var.o11y.loki.enabled ? 1 : 0
  parent_id         = var.parent_id
  name              = "loki-bucket-${random_string.loki_unique_id[0].result}"
  versioning_policy = "DISABLED"
}
