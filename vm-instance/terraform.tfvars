parent_id = "" # The project-id in this context
subnet_id = "" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id

# VM configuration - 24 x h200
preset = "8gpu-128vcpu-1600gb"
platform = "gpu-h200-sxm"
instance_count = 3

# Extra storage configuration
add_extra_storage = true
extra_storage_size_gb = 100
extra_storage_class = "NETWORK_SSD"
extra_path = "/mnt/test_storage"

# Add users of the cluster here
users = [
  {
    user_name    = "tux",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  },
  {
    user_name      = "tux2",
    ssh_public_key = "~/.ssh/id_rsa.pub"
  }
]

public_ip                          = true
create_public_ip_for_all_instances = false

shared_filesystem_id = ""
mount_bucket         = ""

# Choose allocated fabric
fabric = "fabric-6"
