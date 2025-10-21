output "nfs_server_internal_ip" {
  description = "The internal IP address to access the NFS server"
  value       = module.nfs-module.nfs_server_internal_ip
}
