# parent_id      = "" # The project-id in this context
# subnet_id      = "" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
# region         = "" # Project region
# ssh_user_name  = "" # Username you want to use to connect to the nodes
# ssh_public_key = {
# key  = "put your public ssh key here" OR
# path = "put path to ssh key here"
# }
cluster_workers_count = 2            # amount of workers
mysql_jobs_backend    = false        # Do you want to use mysql
shared_fs_type        = "filesystem" # "nfs" or "filesystem"

# master_platform = 
# master_preset   = 
# worker_platform = 
# worker_preset   = 