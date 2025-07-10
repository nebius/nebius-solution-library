output "jail" {
  description = "Jail filestore."
  value       = local.jail
}

output "jail_id" {
  value = local.jail.id
}