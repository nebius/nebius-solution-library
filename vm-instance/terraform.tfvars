#parent_id      = "" # The project-id in this context
#subnet_id      = "" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id


#preset = "16vcpu-64gb"
#platform = "cpu-d3"
preset = "8gpu-128vcpu-1600gb"
#preset = "1gpu-16vcpu-200gb"
platform = "gpu-h100-sxm"

users = [
  {
    user_name = "tux",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  },
  {
    user_name = "tux2",
    ssh_public_key = "<SSH KEY STRING>"
  }
]

public_ip = true
create_public_ip_for_all_instances = false
instance_count = 1

shared_filesystem_id = ""
mount_bucket = "fabric-6"

fabric = ""
