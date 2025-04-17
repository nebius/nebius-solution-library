output "nfs_server_internal_ip" {
  description = "The internal IP address to access the NFS server"
  value       = trimsuffix(nebius_compute_v1_instance.nfs_server.status.network_interfaces[0].ip_address.address, "/32")
}

output "nfs_export_path" {
  description = "NFS exported filesystem path"
  value       = var.nfs_path
}
