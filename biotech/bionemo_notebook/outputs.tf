output "bionemo_ids" {
  description = "List of all BioNeMo JupyterHub release IDs"
  value       = [for r in nebius_applications_v1alpha1_k8s_release.bionemo : r.id]
}

