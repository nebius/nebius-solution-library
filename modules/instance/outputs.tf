output "internal_ip" {
  description = "The internal IP address"
  value       = trimsuffix(nebius_compute_v1_instance.instance.status.network_interfaces[0].ip_address.address, "/32")
}
output "public_ip" {
  description = "The public IP address"
  value       = trimsuffix(nebius_compute_v1_instance.instance.status.network_interfaces[0].public_ip_address.address, "/32")
}
