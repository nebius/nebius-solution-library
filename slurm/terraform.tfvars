parent_id             = "project-e00..."
subnet_id             = "vpcsubnet-e00..."
cluster_workers_count = 2            # amount of workers
mysql_jobs_backend    = false        # Do you want to use mysql
shared_fs_type        = "filesystem" # "nfs" or "filesystem"
# ssh_public_key = {
#   key  = "put your public ssh key here"
#   path = "put path to ssh key here"
# }

master_platform = "cpu-e2"
master_preset   = "4vcpu-16gb"
worker_platform = "gpu-h100-sxm"
worker_preset   = "8gpu-128vcpu-1600gb"