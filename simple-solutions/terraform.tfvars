parent_id      = "<PROJECT-ID>" # The project-id in this context
subnet_id      = "<SUBNET-ID>" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id


#preset = "16vcpu-64gb"
#platform = "cpu-e2"
#preset = "8gpu-128vcpu-1600gb"
preset = "1gpu-16vcpu-200gb"
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

add_extra_storage = false
public_ip = true
instance_count = 1

shared_filesystem_id = ""
