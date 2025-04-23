output "storage_classes" {
  description = "Created storage classes grouped by (disk type) / (fs type)."
  value       = local.storage_class_names_by
}
