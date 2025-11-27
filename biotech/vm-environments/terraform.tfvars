parent_id      = "project-e00be73cx4rz3n5738" # The project-id in this context
subnet_id      = "vpcsubnet-e00x9czc0s04d7991a" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id


#preset = "16vcpu-64gb"
#platform = "cpu-d3"
#preset = "8gpu-128vcpu-1600gb"
preset = "1gpu-16vcpu-200gb"
platform = "gpu-h100-sxm"

users = [
  {
    user_name    = "tux",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  },
  {
    user_name      = "nebius",
    ssh_key_path = "~/.ssh/boston.pub"
  }
]

boot_disk_size_gb                 = 1024
public_ip                          = true
instance_count                     = 30
shared_filesystem_id               = ""
mount_bucket                      = "boston2025"
fabric                            = ""
install_helical                   = false
install_bionemo                   = true
custom_buckets                    = true
