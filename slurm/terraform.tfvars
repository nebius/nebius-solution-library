# Cloud environment and network
parent_id      = "project-e00dppgnh7smdq475s" # The project-id in this context
subnet_id      = "vpcsubnet-e00bdce2b4npsj1m25" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
cluster_workers_count = 2     # amount of workers
mysql_jobs_backend    = false # Do you want to use mysql
shared_fs_type        = "filesystem"
ssh_public_key = {
# key  = "put your public ssh key here" OR
path = "~/.ssh/id_ed25519.pub"
}
fs_size = 5 * 1024 * 1024 * 1024 * 1024