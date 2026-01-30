data "kubectl_file_documents" "binpacking_scheduler_manifests" {
  content = file("${path.module}/files/bp-scheduler.yaml")
}

# Use kubectl_file_documents to split multi-document into the kubectl_manifest resource
resource "kubectl_manifest" "binpacking_scheduler" {
  for_each  = data.kubectl_file_documents.binpacking_scheduler_manifests.manifests
  yaml_body = each.value
}

module "opa_gatekeeper" {
  source = "../opa_gatekeeper"
  count  = var.enable_mutator ? 1 : 0
  configs = templatefile("${path.module}/files/opa_gatekeeper_mutator.yaml.tftpl", {
    namespaces = var.mutated_namespaces
  })
}
