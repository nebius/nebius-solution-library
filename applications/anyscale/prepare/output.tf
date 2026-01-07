output "object_storage_bucket_name" {
  value       = join("-", ["anyscale", local.release-suffix])
  description = "The object storage bucket"
}

output "nfs_server_internal_ip" {
  value       = module.nfs-server.nfs_server_internal_ip
  description = "Private IP address of the NFS server"
}
